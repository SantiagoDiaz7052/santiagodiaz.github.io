from services.supabase_client import supabase
from services.gemini import get_respuesta

def procesar_mensaje(numero_usuario: str, numero_club: str, nombre: str, mensaje: str) -> str:

    club_res = supabase.table("clubs")\
        .select("*")\
        .eq("whatsapp_number", numero_club)\
        .eq("activo", True)\
        .single()\
        .execute()

    if not club_res.data:
        return "Lo siento, este servicio no está disponible."

    club = club_res.data
    club_id = club["id"]
    system_prompt = club["system_prompt"]

    conv_res = supabase.table("conversaciones")\
        .select("*")\
        .eq("club_id", club_id)\
        .eq("numero_usuario", numero_usuario)\
        .execute()

    if conv_res.data:
        conversacion = conv_res.data[0]
        historial = conversacion["historial"]
    else:
        historial = []
        supabase.table("conversaciones").insert({
            "club_id": club_id,
            "numero_usuario": numero_usuario,
            "nombre_usuario": nombre,
            "historial": []
        }).execute()

    # Pasamos club_id a Gemini para que pueda ejecutar funciones
    respuesta = get_respuesta(system_prompt, historial, mensaje, club_id=club_id)

    historial.append({"role": "user", "content": mensaje})
    historial.append({"role": "assistant", "content": respuesta})
    historial = historial[-20:]

    supabase.table("conversaciones")\
        .update({"historial": historial, "nombre_usuario": nombre})\
        .eq("club_id", club_id)\
        .eq("numero_usuario", numero_usuario)\
        .execute()

    return respuesta