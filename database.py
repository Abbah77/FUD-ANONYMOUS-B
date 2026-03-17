import os
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import Optional

load_dotenv()

class SupabaseClient:
    _instance: Optional[Client] = None

    @classmethod
    def get_instance(cls) -> Client:
        if cls._instance is None:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            
            # Log for debugging (remove in production)
            print(f"SUPABASE_URL: {'Set' if url else 'NOT SET'}")
            print(f"SUPABASE_KEY: {'Set' if key else 'NOT SET'}")
            
            if not url:
                raise ValueError("SUPABASE_URL environment variable is not set")
            if not key:
                raise ValueError("SUPABASE_KEY environment variable is not set")
                
            # Validate URL format
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
                
            try:
                cls._instance = create_client(url, key)
                print("✅ Supabase client created successfully")
            except Exception as e:
                print(f"❌ Failed to create Supabase client: {e}")
                raise
                
        return cls._instance

# Create instance
try:
    supabase = SupabaseClient.get_instance()
except Exception as e:
    print(f"⚠️ Warning: Could not initialize Supabase: {e}")
    supabase = None  # Will cause endpoints to fail gracefully
