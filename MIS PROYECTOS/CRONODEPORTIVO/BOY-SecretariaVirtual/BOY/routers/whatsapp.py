from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from services.mensajes import procesar_mensaje
from services.pagos import analizar_comprobante, registrar_pago_pendiente
from services.supabase_client import supabase

router = APIRouter()

@router.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    form = await request.form()

    numero_usuario = form.get("From", "")
    numero_club    = form.get("To", "")
    mensaje        = form.get("Body", "").strip()
    nombre         = form.get("ProfileName", "")
    num_media      = int(form.get("NumMedia", "0"))
    media_url      = form.get("MediaUrl0", "")
    media_type     = form.get("MediaContentType0", "")

    # Si envió una imagen, verificar si es comprobante de pago
    if num_media > 0 and media_url and "image" in media_type:
        respuesta = await procesar_imagen_pago(
            numero_usuario, numero_club, nombre, media_url
        )
    else:
        respuesta = procesar_mensaje(numero_usuario, numero_club, nombre, mensaje)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{respuesta}</Message>
</Response>"""

    return PlainTextResponse(content=twiml, media_type="application/xml")


async def procesar_imagen_pago(numero_usuario: str, numero_club: str, 
                                nombre: str, imagen_url: str) -> str:
    # Buscar el club
    club_res = supabase.table("clubs")\
        .select("*")\
        .eq("whatsapp_number", numero_club)\
        .single().execute()

    if not club_res.data:
        return "Lo siento, servicio no disponible."

    club_id = club_res.data["id"]

    # Buscar el deportista por número de teléfono
    deportista_res = supabase.table("deportistas")\
        .select("*")\
        .eq("club_id", club_id)\
        .eq("telefono", numero_usuario.replace("whatsapp:+57", "").replace("whatsapp:+", ""))\
        .execute()

    if not deportista_res.data:
        return "⚠️ No encontré tu registro en el club. ¿Ya estás inscrito? Si no, escribe *1* para inscribirte."

    deportista = deportista_res.data[0]

    # Determinar monto esperado según categoría y sede
    montos = {
        "Iniciación": 90000,
        "Intermedio": 100000,
        "Avanzado": 110000,
        "Escuela": 90000
    }
    monto_esperado = montos.get(deportista["categoria"], 90000)

    # Analizar el comprobante con Gemini Vision
    analisis = analizar_comprobante(imagen_url, monto_esperado)

    if not analisis.get("es_comprobante"):
        return ("⚠️ La imagen no parece ser un comprobante de pago válido.\n"
                "Por favor envía una captura clara de tu pago por Nequi, "
                "Daviplata o transferencia bancaria.")

    # Verificar monto
    monto_detectado = analisis.get("monto_detectado")
    if monto_detectado and abs(monto_detectado - monto_esperado) > 5000:
        return (f"⚠️ El monto detectado (${monto_detectado:,.0f}) no coincide "
                f"con tu mensualidad (${monto_esperado:,.0f}).\n"
                f"¿Tienes alguna duda? Escribe *10* para hablar con Ivonn.")

    # Registrar pago pendiente
    from datetime import datetime
    mes_anio = datetime.now().strftime("%Y-%m")
    registrar_pago_pendiente(
        club_id=club_id,
        deportista_id=deportista["id"],
        monto_esperado=monto_esperado,
        mes_anio=mes_anio,
        imagen_url=imagen_url,
        analisis=analisis
    )

    return (f"✅ Comprobante recibido, {deportista['nombre']}.\n"
            f"💳 Monto: ${monto_esperado:,.0f} | Mes: {mes_anio}\n"
            f"⏳ Tu pago está en verificación. Te confirmamos en breve 💙")