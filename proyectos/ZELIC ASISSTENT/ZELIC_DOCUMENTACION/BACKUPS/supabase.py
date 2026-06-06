import os
from dotenv import load_dotenv
from supabase import create_client
from CONFIG.config import SUPABASE_KEY, SUPABASE_URL

load_dotenv()

url = os.getenv(SUPABASE_URL)
key = os.getenv(SUPABASE_KEY)

supabase = create_client(url, key)
print("✅ Conectado a Supabase")