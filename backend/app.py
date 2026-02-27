from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os
import requests 
import io
import PyPDF2
from supabase import create_client, Client
from supabase import create_client, Client
# ml_engine import removed

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
# process_document and analyze_health removed
if __name__ == '__main__':
    print("🚀 Starting Flask Server on Port 5000...")
    app.run(debug=True, port=5000)