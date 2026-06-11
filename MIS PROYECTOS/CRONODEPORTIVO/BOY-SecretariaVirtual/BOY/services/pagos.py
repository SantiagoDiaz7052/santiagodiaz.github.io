from services.supabase_client import supabase
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
import httpx
import base64

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def analizar_comprobante(imagen_url: str, monto_esperado: float) -> dict:
    """Descarga la imagen y la analiza con Gemini Vision"""
    try:
        # Descargar imagen desde Twilio
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        
        response = httpx.get(
            imagen_url, 
            auth=(twilio_sid, twilio_token),
            timeout=15
        )
        imagen_base64 = base64.b64encode(response.content).decode("utf-8")
        content_type = response.headers.get("content-type", "image/jpeg")

        prompt = f"""Analiza este comprobante de pago colombiano.
Extrae la siguiente información en formato exacto:

MONTO: (solo el número, sin puntos ni comas, ejemplo: 90000)
FECHA: (formato YYYY-MM-DD, si no se ve claramente escribe DESCONOCIDA)
REFERENCIA: (número de referencia o transacción, si no hay escribe NINGUNA)
ES_COMPROBANTE: (SI o NO, si parece una imagen legítima de pago)
PLATAFORMA: (Nequi, Daviplata, transferencia bancaria, o DESCONOCIDA)

Monto esperado: ${monto_esperado:,.0f} COP
¿El monto coincide aproximadamente? Responde solo con el formato pedido."""

        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=[
                types.Content(parts=[
                    types.Part(
                        inline_data=types.Blob(
                            mime_type=content_type,
                            data=imagen_base64
                        )
                    ),
                    types.Part(text=prompt)
                ])
            ]
        )

        texto = response.text
        resultado = {
            "es_comprobante": False,
            "monto_detectado": None,
            "referencia": None,
            "fecha": None,
            "plataforma": None,
            "texto_completo": texto
        }

        for linea in texto.strip().split("\n"):
            if "MONTO:" in linea:
                try:
                    monto_str = linea.split("MONTO:")[1].strip().replace(".", "").replace(",", "")
                    resultado["monto_detectado"] = float(monto_str)
                except:
                    pass
            elif "FECHA:" in linea:
                resultado["fecha"] = linea.split("FECHA:")[1].strip()
            elif "REFERENCIA:" in linea:
                resultado["referencia"] = linea.split("REFERENCIA:")[1].strip()
            elif "ES_COMPROBANTE:" in linea:
                resultado["es_comprobante"] = "SI" in linea.upper()
            elif "PLATAFORMA:" in linea:
                resultado["plataforma"] = linea.split("PLATAFORMA:")[1].strip()

        return resultado

    except Exception as e:
        return {
            "es_comprobante": False,
            "monto_detectado": None,
            "referencia": None,
            "fecha": None,
            "plataforma": None,
            "error": str(e)
        }


def registrar_pago_pendiente(club_id: str, deportista_id: str, 
                              monto_esperado: float, mes_anio: str,
                              imagen_url: str, analisis: dict) -> dict:
    """Registra el pago en Supabase como pendiente de verificación"""
    
    pago = supabase.table("pagos").insert({
        "club_id": club_id,
        "deportista_id": deportista_id,
        "monto": monto_esperado,
        "monto_detectado": analisis.get("monto_detectado"),
        "referencia_detectada": analisis.get("referencia"),
        "fecha_detectada": analisis.get("fecha"),
        "tipo_pago": analisis.get("plataforma", "desconocido"),
        "tipo": "mensualidad",
        "mes_anio": mes_anio,
        "imagen_url": imagen_url,
        "estado": "pendiente_verificacion",
        "wompi_data": {"analisis_gemini": analisis.get("texto_completo")}
    }).execute()

    return pago.data[0] if pago.data else {}


def obtener_pagos_pendientes(club_id: str) -> list:
    """Para el panel de admin - lista pagos por verificar"""
    resultado = supabase.table("pagos")\
        .select("*, deportistas(nombre, documento)")\
        .eq("club_id", club_id)\
        .eq("estado", "pendiente_verificacion")\
        .order("created_at", desc=True)\
        .execute()
    return resultado.data or []


def aprobar_pago(pago_id: str, verificado_por: str = "admin") -> bool:
    """Admin aprueba el pago"""
    supabase.table("pagos").update({
        "estado": "aprobado",
        "verificado_por": verificado_por
    }).eq("id", pago_id).execute()

    # Actualizar mensualidad si existe
    pago = supabase.table("pagos").select("*").eq("id", pago_id).single().execute()
    if pago.data and pago.data.get("deportista_id") and pago.data.get("mes_anio"):
        supabase.table("mensualidades").update({
            "estado": "pagado",
            "pagado_at": "now()"
        }).eq("deportista_id", pago.data["deportista_id"])\
          .eq("mes_anio", pago.data["mes_anio"])\
          .execute()
    return True


def rechazar_pago(pago_id: str, motivo: str = "") -> bool:
    """Admin rechaza el pago"""
    supabase.table("pagos").update({
        "estado": "rechazado",
        "notas_verificacion": motivo
    }).eq("id", pago_id).execute()
    return True