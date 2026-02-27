from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import google.generativeai as genai
import os
from dotenv import load_dotenv
from typing import Optional
import io
import json
import requests
import asyncio
import PyPDF2

from voice_service import VoiceService
from rag_service import RAGService
from voice_service import VoiceService
from rag_service import RAGService
# ml_engine import removed

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Initialize FastAPI
app = FastAPI(title="Healthcare AI Assistant", version="2.0.0")

# CORS Configuration
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Gemini Model
gemini_model = genai.GenerativeModel('gemini-2.5-flash')
chat_sessions = {}

voice_service = VoiceService(api_key=os.getenv("ELEVENLABS_API_KEY"))
rag_service = RAGService(
    supabase_url=os.getenv("VITE_SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

class ExtractRecordRequest(BaseModel):
    file_url: str
    record_id: str
    patient_id: str

class ExtractRecordRequest(BaseModel):
    file_url: str
    record_id: str
    patient_id: str

class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    use_records: bool = False
    use_voice: bool = False  # New: indicates if user used voice input

class ChatResponse(BaseModel):
    success: bool
    response: str
    audio_url: Optional[str] = None
    audio_data: Optional[str] = None  # Base64 encoded audio
    error: Optional[str] = None

class DocumentProcessRequest(BaseModel):
    file_url: str
    record_id: str
    patient_id: str

class HealthAnalysisRequest(BaseModel):
    user_id: str

class PharmacyChatRequest(BaseModel):
    message: str
    patient_id: str
    language: str = "en"
    use_voice: bool = False

# ==========================================
# ROUTES
# ==========================================
from pharmacy_orchestrator import PharmacyOrchestrator
pharmacy_orchestrator = PharmacyOrchestrator()
pharmacy_service = pharmacy_orchestrator.service # For context fetching

@app.post("/pharmacy/chat")
async def pharmacy_chat(request: PharmacyChatRequest):
    """
    Expert Pharmacy Agent endpoint. 
    Uses clinical pharmacist persona and pharmacy-specific tools.
    """
    try:
        print(f"💊 Pharmacy Query: {request.message}")
        
        # 1. Fetch Context
        profile = await pharmacy_service.get_patient_profile(request.patient_id)
        health_summary = await pharmacy_service.get_patient_health_summary(request.patient_id)
        order_history = await pharmacy_service.get_patient_orders(request.patient_id)
        refill_candidates = await pharmacy_service.get_refill_candidates(request.patient_id)
        
        # 2. Build Expert Pharmacist Prompt
        system_prompt = f"""
You are the **Expert Pharmacy Agent** for MyHealthChain. 
You are a **senior clinical pharmacist AI**.

PATIENT PROFILE: {json.dumps(profile)}
HEALTH SUMMARY: {json.dumps(health_summary)}
ORDER HISTORY: {json.dumps(order_history)}
PROACTIVE REFILL ALERTS: {json.dumps(refill_candidates)}

YOUR CORE RESPONSIBILITIES:
1. **Clinical Safety**: Collect age, allergies, chronic conditions, and current meds if not in profile.
2. **Grounding**: ONLY recommend medicines found in the database. Use tools (search_medicines) to check stock and prescription status.
3. **Safety Policies**: 
   - If `prescription_required` is true, explain you need a valid prescription.
   - Escalate emergencies (chest pain, stroke, etc.) to ER immediately.
4. **Commerce**: Offer order drafting ONLY after clinical suitability is confirmed.
5. **Proactive**: If there are refill alerts, mention them if relevant or at the end of the conversation.

TONE: Professional, caring, and authoritative in pharmacy matters.

LANGUAGE REQUIREMENT: 
- **Conversational Matching**: Prioritize matching the user's conversational language. If the user speaks/types in Hindi or Marathi (even in Roman script/Hinglish/Marathlish, e.g., "Mera naam..."), you MUST respond in that language.
- **Script Policy**: 
  - If language is Hindi ('hi') or detected as Hindi -> Use Devanagari script ONLY.
  - If language is Marathi ('mr') or detected as Marathi -> Use Devanagari script ONLY.
  - If language is English ('en') and no other language is detected -> Use English.
- **UI Fallback**: The UI language code is '{request.language}'. Use this as a guide if the user's language is ambiguous.
- **No Script Mixing**: Do NOT answer in English if the user is using Hindi/Marathi. Translate technical terms only if common, but keep the core response in the matching script.

You have access to tools. If you need to search for a medicine, create an order, or check refills, call the appropriate function.
"""

        # 3. Initialize Agent with local tools
        tools = [
            {
                "function_declarations": [
                    {
                        "name": "get_medicines",
                        "description": "Search medicines table by name.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Medicine name to search for."},
                                "limit": {"type": "integer"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "get_patient_orders",
                        "description": "Fetch a patient’s order history.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "patient_id": {"type": "string", "description": "Patient UUID."},
                                "limit": {"type": "integer"}
                            },
                            "required": ["patient_id"]
                        }
                    },
                    {
                        "name": "create_order_draft",
                        "description": "Create a draft order and items for a patient.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "patient_id": {"type": "string"},
                                "channel": {"type": "string"},
                                "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "medicine_id": {"type": "string"},
                                            "qty": {"type": "integer"},
                                            "dosage_text": {"type": "string"},
                                            "frequency_per_day": {"type": "integer"},
                                            "days_supply": {"type": "integer"}
                                        }
                                    }
                                }
                            },
                            "required": ["patient_id", "items"]
                        }
                    },
                    {
                        "name": "finalize_order",
                        "description": "Perform final safety + stock check and commit the order.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "order_id": {"type": "string"}
                            },
                            "required": ["order_id"]
                        }
                    },
                    {
                        "name": "create_refill_alert",
                        "description": "Store a predicted run-out for proactive outreach.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "patient_id": {"type": "string"},
                                "medicine_id": {"type": "string"},
                                "predicted_runout_date": {"type": "string", "description": "YYYY-MM-DD"}
                            },
                            "required": ["patient_id", "medicine_id", "predicted_runout_date"]
                        }
                    },
                    {
                        "name": "get_refill_alerts",
                        "description": "Fetch pending refill alerts for a patient.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "patient_id": {"type": "string"}
                            },
                            "required": ["patient_id"]
                        }
                    },
                    {
                        "name": "log_notification",
                        "description": "Insert a notification record.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "patient_id": {"type": "string"},
                                "channel": {"type": "string"},
                                "type": {"type": "string"},
                                "payload": {"type": "object"},
                                "status": {"type": "string"}
                            },
                            "required": ["patient_id", "channel", "type", "payload"]
                        }
                    }
                ]
            }
        ]

        # Using gemini-1.5-flash as standardized
        agent_model = genai.GenerativeModel('gemini-2.5-flash', tools=tools)
        chat = agent_model.start_chat()
        
        # Initial message
        try:
            print("🤖 Pharmacy Agent (Using gemini-2.5-flash)")
            response = chat.send_message(f"{system_prompt}\n\nUSER MESSAGE: {request.message}")
        except Exception as e:
            print(f"❌ Gemini Error: {e}")
            raise e
        
        if not response:
             raise Exception("Failed to get initial response from Gemini")

        # Robust Tool Loop
        max_iterations = 5
        iteration = 0
        
        while iteration < max_iterations:
            # Check if there's a function call
            if not response.candidates[0].content.parts[0].function_call:
                break
                
            fc = response.candidates[0].content.parts[0].function_call
            tool_name = fc.name
            args = fc.args
            
            print(f"🛠️ Calling Tool: {tool_name} with {args}")
            
            tool_result = None
            try:
                # Direct dispatch to orchestrator which handles parameter parsing
                if tool_name == "get_medicines":
                    tool_result = await pharmacy_orchestrator.get_medicines(args)
                elif tool_name == "get_patient_orders":
                    tool_result = await pharmacy_orchestrator.get_patient_orders(args)
                elif tool_name == "create_order_draft":
                    tool_result = await pharmacy_orchestrator.create_order_draft(args)
                elif tool_name == "finalize_order":
                    tool_result = await pharmacy_orchestrator.finalize_order(args)
                elif tool_name == "create_refill_alert":
                    tool_result = await pharmacy_orchestrator.create_refill_alert(args)
                elif tool_name == "get_refill_alerts":
                    tool_result = await pharmacy_orchestrator.get_refill_alerts(args)
                elif tool_name == "log_notification":
                    tool_result = await pharmacy_orchestrator.log_notification(args)
                else:
                    tool_result = {"error": f"Tool {tool_name} not found."}
            except Exception as tool_err:
                print(f"❌ Tool Error ({tool_name}): {tool_err}")
                tool_result = {"error": str(tool_err)}

            # Send tool response
            try:
                response = chat.send_message(
                    genai.protos.Content(
                        parts=[genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=tool_name,
                                response={'result': tool_result}
                            )
                        )]
                    )
                )
            except Exception as e:
                print(f"❌ Tool Loop Error: {e}")
                raise e
            
            iteration += 1

        ai_text = response.text

        # Generate voice if requested
        audio_data_b64 = None
        if request.use_voice:
            try:
                audio_bytes = await voice_service.synthesize_empathic(ai_text, request.language)
                if audio_bytes:
                    import base64
                    audio_data_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            except Exception as e:
                print(f"⚠️ Pharmacy Voice synthesis failed: {e}")

        return ChatResponse(success=True, response=ai_text, audio_data=audio_data_b64)
    except Exception as e:
        print(f"❌ Pharmacy Chat Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Check if it's a rate limit error to give a better message
        error_msg = str(e)
        
        # Language-aware error fallbacks
        fallbacks = {
            "hi": "मुझे अभी आपके फार्मेसी रिकॉर्ड्स में परेशानी हो रही है। कृपया थोड़ी देर बाद फिर से प्रयास करें।",
            "mr": "मला आता तुमच्या फार्मसी रेकॉर्डमध्ये अडचण येत आहे. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
            "en": "I'm having trouble with my pharmacy records. Please try again."
        }
        quota_fallbacks = {
            "hi": "मुझे अभी बहुत सारे अनुरोध मिल रहे हैं। कृपया एक पल प्रतीक्षा करें और पुन: प्रयास करें।",
            "mr": "मला सध्या खूप विनंत्या येत आहेत. कृपया क्षणभर थांबा आणि पुन्हा प्रयत्न करा.",
            "en": "I'm currently receiving too many requests. Please wait a moment and try again."
        }
        
        selected_fb = fallbacks.get(request.language, fallbacks["en"])
        selected_quota = quota_fallbacks.get(request.language, quota_fallbacks["en"])

        if "429" in error_msg or "quota" in error_msg.lower() or "RESOURCE_EXHAUSTED" in error_msg:
             return ChatResponse(success=False, response=selected_quota, error=str(e))
             
        return ChatResponse(success=False, response=selected_fb, error=str(e))

# ==========================================
# ROUTES
# ==========================================

# get_health_trends removed

@app.get("/")
async def root():
    return {
        "service": "Healthcare AI Assistant",
        "version": "2.0.0",
        "features": ["Chat", "Voice", "RAG", "Health Analysis"]
    }


# In-memory storage for chat history
# Format: { user_id: [ {"role": "user", "parts": ["msg"]}, {"role": "model", "parts": ["response"]} ] }

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint with RAG support, context window, and optional voice output
    """
    try:
        print(f"📩 Chat Query: {request.message}")
        print(f"🎤 Use Voice: {request.use_voice}")
        print(f"🔐 Use Records: {request.use_records}")
        
        user_id = request.user_id or "anonymous"
        
        # Initialize history for user if not exists
        if user_id not in chat_sessions:
            chat_sessions[user_id] = []
        
        # Get recent history (limit to last 10 messages for context window management)
        recent_history = chat_sessions[user_id][-10:]
        
        # Format history for prompt
        history_text = ""
        for msg in recent_history:
            role = "User" if msg["role"] == "user" else "Assistant"
            content = msg["parts"][0]
            history_text += f"{role}: {content}\n"

        context_text = ""
        
        # Search medical records if enabled
        if request.user_id and request.use_records:
            context_text = await rag_service.search_records(
                user_id=request.user_id,
                query=request.message
            )
            if context_text:
                print(f"✅ Found relevant medical records")
        
        # Detect if message is a greeting or casual conversation
        greeting_keywords = [
            'hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening',
            'how are you', 'whats up', "what's up", 'greetings', 'namaste', 
            'thanks', 'thank you', 'bye', 'goodbye', 'see you', 'ok', 'okay',
            'cool', 'nice', 'great', 'awesome', 'perfect'
        ]
        is_greeting = any(request.message.lower().strip() in keyword or keyword in request.message.lower() 
                         for keyword in greeting_keywords)
        
        # Detect if user wants detailed explanation
        detail_keywords = ['explain', 'detail', 'elaborate', 'tell me more', 'in depth', 'long', 'why', 'how does']
        wants_detail = any(keyword in request.message.lower() for keyword in detail_keywords)
        print(f"👋 Is greeting: {is_greeting}")
        print(f"📝 Detail mode: {wants_detail}")
        
# Build simple, adaptive system prompt
        if is_greeting and not history_text: # Only use greeting prompt if it's the start
            # Simple conversational prompt for greetings
            system_prompt = f"""
You are a friendly Healthcare AI assistant. The user sent a greeting or casual message.

Respond warmly and naturally in a conversational way. Keep it SHORT (1-2 sentences max).
Be friendly and welcoming. Let them know you're here to help with health questions.

Examples:
- User: "Hi" -> "Hello! 👋 I'm your healthcare assistant. How can I help you today?" (But translate this to the chosen language)

LANGUAGE REQUIREMENT: 
- **Detect and Match**: Match the user's conversational language. If the user greets you in Hindi/Marathi (e.g., "Namaste", "Mera naam..."), respond in that language.
- **Script Policy**: 
  - If Hindi/Marathi -> Use Devanagari script.
  - If English -> Use English.
- **UI Guide**: The user's current UI language is '{request.language}'.
- **Strict Consistency**: Never mix scripts. 100% Devanagari for Hindi/Marathi.
"""
        else:
            # Structured medical response prompt
            system_prompt = f"""
You are a friendly, empathetic Healthcare AI. 

PREVIOUS CONVERSATION HISTORY:
{history_text}

CONTEXT FROM RECORDS: {context_text}

CORE INSTRUCTIONS:
1. **LANGUAGE**: Prioritize matching the user's conversational language.
   - If the user uses Hindi or Marathi (even in Roman script), you MUST respond in that language using Devanagari script.
   - UI language hint: '{request.language}'.
   - Even if the user uses a few English words, DO NOT answer in English if the core conversation is Hindi/Marathi. Translate technical medical terms into the target script.
   - CRITICAL: Never mix scripts. 100% Devanagari for Hindi/Marathi.
   
2. **TONE**: Balanced and Professional yet Caring. 
   - **Show Empathy appropriately**: If the user mentions pain, sickness, or worry, START with a brief validating phrase (e.g., "I'm sorry to hear you're not feeling well" or "That sounds painful"). 
   - **Do NOT overdo it**: Avoid being overly dramatic or flowery. Keep it grounded.
   - For general information questions (e.g., "benefits of turmeric"), skip the empathy and go straight to the answer.

3. **FORMAT**: 
   - Start with a direct, helpful answer (1-2 sentences).
   - Use **bullet points** for lists (symptoms, causes, tips) to make it readable.
   - End with a short, encouraging closing or a simple tip.
   - Do NOT force any specific section headers. Flow naturally.

4. **medical_scope**: Only answer health/wellness questions. For others, politely decline.

Language Guidelines:
- Keep sentences short and clear.
- Use simple words (e.g., "tummy" for "abdomen" is okay if context fits, but standard simple English/Hinglish is best).
"""

        
        # Using gemini-1.5-flash as standardized
        try:
            print("🤖 Health Assistant (Using gemini-2.5-flash)")
            response = gemini_model.generate_content(
                system_prompt + "\n\nPatient Message: " + request.message,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=2048,
                )
            )
        except Exception as e:
            print(f"❌ Gemini Error: {e}")
            raise e
        
        # Process response
        if hasattr(response, 'text') and response.text:
            ai_text = response.text
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            ai_text = response.candidates[0].content.parts[0].text
        
        if ai_text:
            print(f"✅ Got response: {len(ai_text)} characters")
        
        # If no response after retries, use fallback
        if not ai_text:
            print("📝 Using fallback response")
            # Include the error for debugging
            debug_info = ""
            
            error_fallbacks = {
                "hi": f"क्षमा करें, मैं अभी उस अनुरोध को संसाधित नहीं कर सका।{debug_info} कृपया कुछ ही पलों में पुन: प्रयास करें। 💙",
                "mr": f"क्षमस्व, मी आत्ता त्या विनंतीवर प्रक्रिया करू शकलो नाही.{debug_info} कृपया थोड्या वेळात पुन्हा प्रयत्न करा. 💙",
                "en": f"I'm sorry, I couldn't process that request right now.{debug_info} Please try again in a moment. 💙"
            }
            ai_text = error_fallbacks.get(request.language, error_fallbacks["en"])
        else:
            # Store conversation in history if response was successful
            if user_id in chat_sessions:
                chat_sessions[user_id].append({"role": "user", "parts": [request.message]})
                chat_sessions[user_id].append({"role": "model", "parts": [ai_text]})
        
        # Generate voice if requested
        audio_data_b64 = None
        if request.use_voice:
            try:
                audio_bytes = await voice_service.synthesize_empathic(
                    text=ai_text,
                    language=request.language
                )
                if audio_bytes:
                    import base64
                    audio_data_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            except Exception as e:
                print(f"⚠️ Voice synthesis failed: {e}")
                # Continue without voice
        
        return ChatResponse(
            success=True,
            response=ai_text,
            audio_data=audio_data_b64
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Chat Error: {e}")
        import traceback
        traceback.print_exc()
        return ChatResponse(
            success=False,
            response="I'm experiencing technical difficulties. Please try again.",
            error=str(e)
        )

@app.post("/synthesize_voice")
async def synthesize_voice(request: dict):
    """
    Dedicated endpoint for voice synthesis
    """
    try:
        text = request.get("text", "")
        language = request.get("language", "en")
        
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        audio_data = await voice_service.synthesize_empathic(text, language)
        
        if not audio_data:
            raise HTTPException(status_code=500, detail="Voice synthesis failed")
        
        # Return audio as streaming response
        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "attachment; filename=response.mp3"
            }
        )
        
    except Exception as e:
        print(f"❌ Voice Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# process_document and analyze_health removed
async def process_extraction_task(file_url: str, record_id: str, patient_id: str):
    """Background task to extract text and update the database."""
    try:
        # (Processing state is now omitted from the DB schema entirely)
        # We rely on the frontend's local extractingId state for UI loaders.

        print(f"📥 Downloading file from: {file_url}")
        
        # Download file
        response = requests.get(file_url)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '').lower()
        file_url_lower = file_url.lower()
        
        full_text = ""
        
        # Determine extraction strategy based on content type or extension
        if 'application/pdf' in content_type or file_url_lower.endswith('.pdf'):
            print("📄 Processing as PDF...")
            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
                    
        elif 'image/' in content_type or file_url_lower.endswith(('.png', '.jpg', '.jpeg')):
            print("🖼️ Processing as Image...")
            print(f"🧬 Using vision model to extract text from {content_type}")
            try:
                # Use Gemini-2.5-flash for OCR
                vision_response = gemini_model.generate_content([
                    "Extract all text from this image exactly as it appears. Do not summarize or format, just give me the raw text.",
                    {'mime_type': 'image/jpeg' if 'jpeg' in content_type or 'jpg' in content_type else 'image/png', 'data': response.content}
                ])
                full_text = vision_response.text
                print(f"✅ Extracted {len(full_text)} characters from image")
            except Exception as ve:
                print(f"❌ AI OCR failed: {ve}")
                raise ValueError(f"AI OCR failed: {ve}")
                
        else:
            # For other text-based files (csv, txt, doc fallback)
            print(f"📝 Processing as other format ({content_type})...")
            try:
                # First try to decode as plain text (works for csv, txt)
                full_text = response.content.decode('utf-8')
            except UnicodeDecodeError:
                # If binary/doc, try asking Gemini to process the raw file if possible (fallback)
                print("🔄 Could not decode as UTF-8, attempting AI extraction fallback...")
                try:
                    # Provide it as a generic document to gemini
                    doc_response = gemini_model.generate_content([
                        "Extract all text from this document file.",
                        {'mime_type': content_type if content_type else 'application/octet-stream', 'data': response.content}
                    ])
                    full_text = doc_response.text
                except Exception as doc_e:
                    print(f"❌ Document extraction fallback failed: {doc_e}")
                    raise ValueError(f"Unsupported or unparseable file type: {content_type}")

        if not full_text or not full_text.strip():
            raise ValueError("Could not extract any text from the file. It may be empty or an unsupported format.")
            
        # Chunk and save text via rag_service (which writes to document_chunks)
        await rag_service.process_document(
            file_url=file_url,
            record_id=record_id,
            patient_id=patient_id
        )
        print("✅ Document chunked and saved to document_chunks table")
        
    except Exception as e:
        print(f"❌ Background Extraction Error: {e}")
        import traceback
        traceback.print_exc()
        # [ERROR] state logging omitted, frontend will timeout or show error if chunks never appear.


@app.post("/extract_record")
async def extract_record(request: ExtractRecordRequest, background_tasks: BackgroundTasks):
    """
    Queues text extraction from a given file URL (doc, csv, pdf, img, png) 
    to be processed in the background.
    """
    # Simply queue the task and return success
    background_tasks.add_task(
        process_extraction_task, 
        request.file_url, 
        request.record_id, 
        request.patient_id
    )
    
    return {
        "success": True,
        "message": "Extraction started in background",
        "status": "processing"
    }
@app.get("/pharmacy/refill-alerts/{patient_id}")
async def get_refill_alerts(patient_id: str):
    """Fetch proactive refill alerts for a patient."""
    alerts = await pharmacy_service.get_refill_candidates(patient_id)
    return {"success": True, "alerts": alerts}

# ==========================================
# Health Insights Reporting
# ==========================================

@app.get("/analyze_health/{patient_id}")
async def analyze_health(patient_id: str):
    """
    Analyzes all extracted records for a patient and returns a JSON payload 
    containing trend metrics, a summary, and actionable tips.
    """
    try:
        # Fetch all processed chunks for this patient, grouping by original document date
        valid_records = await rag_service.get_patient_records_with_dates(patient_id)
            
        if not valid_records:
            return {
                "success": True,
                "data": {
                    "summary": "No medical records have been extracted yet. Please upload and extract records to generate insights.",
                    "metrics": [],
                    "tips": ["Upload your latest lab reports, prescriptions, or discharge summaries to get started."]
                }
            }

        # Combine text for the LLM context
        combined_text = ""
        for r in valid_records:
            date_str = r.get("date") or "Unknown Date"
            text = r.get("text", "")
            # Truncate slightly smaller chunks if there are thousands, but Flash handles 1M+ tokens
            combined_text += f"\n--- Record Chunk ({date_str}) ---\n{text[:2000]}\n"

        # Ask Gemini to return a structured JSON response
        prompt = f"""
        You are an expert AI health analyst. Analyze the following medical records for a patient and output a strict JSON representation of their health trends.
        
        Extract ONLY the following chronological data points: Blood Pressure (Systolic BP and Diastolic BP), Blood Sugar, and Weight.
        Do not extract any other metrics.
        If a specific metric isn't found in a given record, omit it or set it to null for that date.
        Invent reasonable mock trend data ONLY IF no real data exists, but heavily bias toward the real data.
        
        The JSON must match this structure exactly, do not wrap in markdown tags like ```json:
        {{
            "summary": "A 2-3 sentence paragraph summarizing their overall health trajectory based on these records.",
            "profile": {{
                "weight": "e.g., 75 kg or null if not found",
                "height": "e.g., 175 cm or null if not found",
                "age": "e.g., 32 yrs or null if not found",
                "blood_group": "e.g., O+ or null if not found",
                "allergies": ["list of allergies", "or empty array if none found"]
            }},
            "available_metrics": ["List of the exact metric names you found from the allowed list, e.g.", "Systolic BP", "Diastolic BP", "Blood Sugar", "Weight"],
            "metrics": [
                {{"date": "YYYY-MM-DD", "Systolic BP": 120, "Diastolic BP": 80, "Blood Sugar": 95, "Weight": 75}}
            ],
            "tips": [
                "1 actionable, specific tip based on the records",
                "Another actionable tip",
                "A third actionable tip"
            ]
        }}
        
        Records: 
        {combined_text}
        """

        # Generate response asynchronously to not block the event loop
        result = await asyncio.to_thread(gemini_model.generate_content, [prompt])
        response_text = result.text.strip()
        
        # Clean up possible markdown fences
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
            
        parsed_data = json.loads(response_text)
        
        return {
            "success": True,
            "data": parsed_data
        }

    except json.JSONDecodeError as je:
        print(f"❌ Failed to parse AI JSON response: {je}")
        print(f"Raw response was: {result.text}")
        raise HTTPException(status_code=500, detail="AI returned malformed data.")
    except Exception as e:
        print(f"❌ Error generating health insights: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# Startup/Shutdown Events
# ==========================================
@app.on_event("startup")
async def startup_event():
    print("🚀 FastAPI Healthcare AI Server Started")
    print("📍 Server running on: http://localhost:8000")
    print("📖 API Docs available at: http://localhost:8000/docs")
    
    if not os.getenv("ELEVENLABS_API_KEY"):
        print("⚠️ WARNING: ELEVENLABS_API_KEY is missing from .env. Voice synthesis will fail.")
    else:
        print("✅ ElevenLabs API Key detected.")

@app.on_event("shutdown")
async def shutdown_event():
    print("👋 Server shutting down...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )