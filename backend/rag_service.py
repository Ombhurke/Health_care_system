import google.generativeai as genai
from supabase import create_client, Client
import requests
import io
import PyPDF2
from typing import List

class RAGService:
    """
    Service for handling Retrieval Augmented Generation (RAG)
    using Supabase vector database
    """
    
    def __init__(self, supabase_url: str, supabase_key: str):
        self.supabase: Client = create_client(supabase_url, supabase_key)
    
    async def search_records(
        self, 
        user_id: str, 
        query: str,
        match_threshold: float = 0.5,
        match_count: int = 5
    ) -> str:
        """
        Search medical records using vector similarity
        
        Args:
            user_id: Patient ID
            query: Search query
            match_threshold: Minimum similarity score (0-1)
            match_count: Number of results to return
            
        Returns:
            Formatted context text from matched records
        """
        try:
            # Generate embedding for query
            query_embedding = genai.embed_content(
                model="models/text-embedding-004",
                content=query,
                task_type="retrieval_query"
            )['embedding']
            
            # Search vector database
            response = self.supabase.rpc('match_document_chunks', {
                'query_embedding': query_embedding,
                'match_threshold': match_threshold,
                'match_count': match_count,
                'filter_user_id': user_id
            }).execute()
            
            # Format results
            if response.data:
                context_text = "\n\nRelevant Medical Records:\n"
                for item in response.data:
                    context_text += f"- {item['content']}\n"
                return context_text
            
            return ""
            
        except Exception as e:
            print(f"❌ RAG Search Error: {e}")
            return ""
    
    async def process_document(
        self,
        file_url: str,
        record_id: str,
        patient_id: str,
        chunk_size: int = 500
    ) -> dict:
        """
        Process a PDF document: extract text, create chunks, generate embeddings
        
        Args:
            file_url: URL of the PDF file
            record_id: Database record ID
            patient_id: Patient ID
            chunk_size: Size of text chunks
            
        Returns:
            Dictionary with processing results
        """
        try:
            print(f"📥 Downloading file from: {file_url}")
            
            # Download file
            response = requests.get(file_url)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '').lower()
            
            full_text = ""
            
            if 'application/pdf' in content_type:
                print("📄 Processing as PDF...")
                pdf_file = io.BytesIO(response.content)
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"
            elif 'image/' in content_type or file_url.lower().endswith(('.png', '.jpg', '.jpeg')):
                print("🖼️ Processing as Image...")
                # Use Gemini-1.5-flash for OCR
                vision_model = genai.GenerativeModel('gemini-2.5-flash')
                print(f"🧬 Using vision model to extract text from {content_type}")
                
                try:
                    print("🤖 Image OCR (Using gemini-2.5-flash)")
                    vision_response = vision_model.generate_content([
                        "Extract all text from this medical record image. Give me the raw text as is.",
                        {'mime_type': 'image/jpeg' if 'jpeg' in content_type or 'jpg' in content_type else 'image/png', 'data': response.content}
                    ])
                    full_text = vision_response.text
                    print(f"✅ Extracted {len(full_text)} characters from image")
                except Exception as ve:
                    print(f"❌ AI OCR failed: {ve}")
                    raise ValueError(f"AI OCR failed: {ve}")
            else:
                # Fallback: try PDF if unknown
                try:
                    pdf_file = io.BytesIO(response.content)
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    for page in pdf_reader.pages:
                        text = page.extract_text()
                        if text:
                            full_text += text + "\n"
                except:
                    raise ValueError(f"Unsupported file type: {content_type}")
            
            if not full_text.strip():
                raise ValueError("Could not extract any text from the file")
            
            # Save full text to records table (DEPRECATED - Now storing in document_chunks)
            # Record text is strictly stored as vector chunks moving forward.
            
            # Create chunks
            chunks = [
                full_text[i:i+chunk_size] 
                for i in range(0, len(full_text), chunk_size)
            ]
            
            print(f"📄 Created {len(chunks)} chunks, generating embeddings...")
            
            # Generate embeddings and prepare for batch insert
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
            
            # Batch insert to database
            if rows_to_insert:
                self.supabase.table("document_chunks").insert(rows_to_insert).execute()
                print(f"✅ Inserted {len(rows_to_insert)} chunks into database")
            
            return {
                "chunks": len(rows_to_insert),
                "text_length": len(full_text)
            }
            
        except Exception as e:
            print(f"❌ Document Processing Error: {e}")
            raise
    
    async def get_patient_records(self, user_id: str) -> List[str]:
        """
        Get all text records for a patient (for health analysis)
        
        Args:
            user_id: Patient ID
            
        Returns:
            List of text records
        """
        try:
            # Try document_chunks first
            print(f"🔍 Fetching chunks for user: {user_id}")
            response = self.supabase.table('document_chunks')\
                .select('content')\
                .eq('patient_id', user_id)\
                .execute()
            
            if response.data:
                print(f"✅ Found {len(response.data)} chunks")
                if len(response.data) > 0:
                     print(f"📄 First chunk preview: {response.data[0].get('content', '')[:100]}...")
                return [item['content'] for item in response.data if item.get('content')]
            
            
            print("❌ No chunks found for patient")
            return []
            
        except Exception as e:
            print(f"❌ Error fetching patient records: {e}")
            return []

    async def get_patient_records_with_dates(self, user_id: str) -> List[dict]:
        """
        Get all text records with timestamps for trend analysis
        """
        try:
            # Fetch chunks from document_chunks table and join with records to get creation dates
            response = self.supabase.table('document_chunks')\
                .select('content, created_at, records!inner(created_at)')\
                .eq('patient_id', user_id)\
                .order('created_at', desc=False)\
                .execute()
            
            if response.data:
                # Group by original record date if available, else chunk date
                return [
                    {
                        "date": item.get('records', {}).get('created_at') or item['created_at'], 
                        "text": item['content']
                    } 
                    for item in response.data 
                    if item.get('content')
                ]
            
            return []
            
        except Exception as e:
            print(f"❌ Error fetching patient records with dates: {e}")
            return []