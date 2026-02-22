from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os
import requests 
import io
import PyPDF2
from supabase import create_client, Client
from ml_engine import analyze_risk

from dotenv import load_dotenv

# Load .env file from the parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)
CORS(app)

# ==========================================
# 1. API KEYS CONFIGURATION
# ==========================================
# GEMINI KEY
MY_SECRET_KEY = os.getenv("GEMINI_API_KEY")

# SUPABASE KEYS (You need to get these from your Supabase Dashboard)
# Go to Project Settings -> API
SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")        # e.g. https://xyz.supabase.co
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")   # ⚠️ Use SERVICE_ROLE key to allow writing

# 2. INITIALIZE CLIENTS
genai.configure(api_key=MY_SECRET_KEY)
# Initialize Gemini Model
model = genai.GenerativeModel('gemini-2.5-flash')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# ROUTE 1: CHATBOT (RAG ENABLED)
# ==========================================
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')
    language = data.get('language', 'en')
    user_id = data.get('user_id')
    use_records = data.get('use_records', False)  # Get the toggle state

    print(f"📩 Chat Query: {user_message}")
    print(f"🔐 Use Records: {use_records}")

    context_text = ""
    
    # --- 1. SEARCH SUPABASE (ONLY IF TOGGLE IS ON) ---
    if user_id and use_records:  # Added use_records check
        try:
            # Generate Vector for Question
            query_embedding = genai.embed_content(
                model="models/text-embedding-004",
                content=user_message,
                task_type="retrieval_query"
            )['embedding']

            # Search Database
            response = supabase.rpc('match_document_chunks', {
                'query_embedding': query_embedding,
                'match_threshold': 0.5,
                'match_count': 5,
                'filter_user_id': user_id
            }).execute()

            # Build Context
            if response.data:
                context_text = "\n\nRelevant Medical Records:\n"
                for item in response.data:
                    context_text += f"- {item['content']}\n"
                print(f"✅ Found {len(response.data)} relevant records.")
            else:
                print("⚠️ No relevant records found.")

        except Exception as e:
            print(f"❌ Search Error: {e}")
    elif user_id and not use_records:
        print("📵 Records access OFF - answering without medical records")

    # --- 2. GENERATE ANSWER ---
    system_prompt = f"""
    You are a Holistic Health AI.
    
    CONTEXT FROM PATIENT RECORDS:
    {context_text}
    
    INSTRUCTIONS:
    1. If context is provided, USE IT to answer. Cite the records.
    2. If no context, answer general health questions normally.
    3. Strict 6-point Markdown format ONLY for symptoms/treatment.

    Respond in language code: {language}. Use emojis.
    """

    try:
        print("🤖 Chat Assistant (Using gemini-2.5-flash)")
        response = model.generate_content(system_prompt + "\n\nUser Query: " + user_message)
        return jsonify({ "success": True, "response": response.text })
    except Exception as e:
        print(f"❌ Gemini Error: {e}")
        return jsonify({ "success": False, "error": str(e) }), 500

# ==========================================
# ROUTE 2: DOCUMENT PROCESSING (NEW!)
# ==========================================
@app.route('/process_document', methods=['POST'])
def process_document():
    data = request.json
    file_url = data.get('file_url')
    record_id = data.get('record_id')
    patient_id = data.get('patient_id')

    if not file_url:
        return jsonify({"error": "Missing file_url"}), 400

    print(f"📥 Processing URL: {file_url}")

    try:
        # 1. Download PDF
        response = requests.get(file_url)
        response.raise_for_status()
        
        # 2. Extract Text
        pdf_file = io.BytesIO(response.content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        full_text = ""
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

        # ... (after extracting full_text) ...

        if not full_text.strip():
            return jsonify({"success": False, "error": "PDF is empty or image-based."}), 400

        # ---------------------------------------------------------
        # NEW STEP: Save the full text to the main 'records' table
        # ---------------------------------------------------------
        try:
            supabase.table("records").update({
                "extracted_text": full_text
            }).eq("id", record_id).execute()
            print("✅ Saved full text to records table.")
        except Exception as e:
            print(f"⚠️ Warning: Could not save full text to records: {e}")
            # We continue even if this fails, because we still want the AI chunks

        # ---------------------------------------------------------
        # EXISTING STEPS: Chunking & Embedding
        # ---------------------------------------------------------

        # 3. Chunk Text
        chunk_size = 500
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        print(f"📄 Generated {len(chunks)} chunks. Creating vectors...")

        # 4. Embed & Save
        rows_to_insert = []
        for chunk in chunks:
            embedding_result = genai.embed_content(
                model="models/text-embedding-004",
                content=chunk,
                task_type="retrieval_document"
            )
            
            rows_to_insert.append({
                "record_id": record_id,
                "patient_id": patient_id,
                "content": chunk,
                "embedding": embedding_result['embedding']
            })

        # Batch Insert
        if rows_to_insert:
            supabase.table("document_chunks").insert(rows_to_insert).execute()

        print("✅ Analysis Complete.")
        return jsonify({"success": True, "chunks": len(rows_to_insert)})

    except Exception as e:
        print(f"❌ Process Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/analyze_health', methods=['POST'])
def analyze_health():
    try:
        data = request.json
        user_id = data.get('user_id')
        
        # 🔧 FIX: Query the 'document_chunks' TABLE directly
        # The schema shows this table has 'patient_id' and 'content' columns.
        response = supabase.table('document_chunks')\
            .select('content')\
            .eq('patient_id', user_id)\
            .execute()
        
        # Check if we got data
        if not response.data:
            # FALLBACK: Try fetching from 'records' table 'extracted_text' column
            # (I saw 'extracted_text' in your schema dump too!)
            print("No chunks found, trying records.extracted_text...")
            fallback_response = supabase.table('records')\
                .select('extracted_text')\
                .eq('patient_id', user_id)\
                .execute()
                
            if not fallback_response.data:
                return jsonify({"success": False, "error": "No medical records found for analysis"})
            
            # Use fallback data
            text_records = [r['extracted_text'] for r in fallback_response.data if r.get('extracted_text')]
        else:
            # Use document_chunks data
            text_records = [item['content'] for item in response.data if item.get('content')]

        if not text_records:
            return jsonify({"success": False, "error": "Records exist but contain no text."})

        # Run the AI
        analysis_result = analyze_risk(text_records)
        
        return jsonify({
            "success": True,
            "prediction": analysis_result
        })

    except Exception as e:
        print(f"Server Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
if __name__ == '__main__':
    print("🚀 Starting Flask Server on Port 5000...")
    app.run(debug=True, port=5000)