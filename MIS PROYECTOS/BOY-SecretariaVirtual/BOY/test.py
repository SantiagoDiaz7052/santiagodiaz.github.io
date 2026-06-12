from services.supabase_client import supabase
from services.gemini import get_respuesta

# Probar conexión a Supabase
clubs = supabase.table("clubs").select("*").execute()
print("Clubs en DB:", clubs.data)

# Probar Gemini
respuesta = get_respuesta(
    system_prompt="Eres la secretaria virtual de un club de patinaje. Responde siempre en español.",
    historial=[],
    mensaje_nuevo="Hola, ¿qué servicios ofrecen?"
)
print("\nRespuesta de Gemini:")
print(respuesta)