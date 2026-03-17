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
            if not url or not key:
                raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
            cls._instance = create_client(url, key)
        return cls._instance

supabase = SupabaseClient.get_instance()
