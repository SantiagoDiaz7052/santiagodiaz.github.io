"""
core/clima.py — Módulo de clima para Zelic
Detecta ubicación por IP y consulta clima con wttr.in (gratis, sin API key)
"""

import requests
from google import genai
from google.genai import types

from CONFIG.config import PERSONALIDAD_ULTRA_COMPACTA_ZELIC


def obtener_ubicacion() -> dict:
    """Detecta ciudad y país por IP usando ip-api.com (gratis)."""
    try:
        r = requests.get("http://ip-api.com/json/", timeout=5)
        data = r.json()
        return {
            "ciudad": data.get("city", ""),
            "pais":   data.get("country", ""),
            "ok":     data.get("status") == "success"
        }
    except Exception as e:
        print(f"[Clima] Error ubicación: {e}")
        return {"ciudad": "", "pais": "", "ok": False}


def obtener_clima(ciudad: str) -> dict:
    """
    Consulta el clima actual usando wttr.in — gratis, sin API key.
    Devuelve temperatura, descripción, humedad y viento.
    """
    try:
        url = f"https://wttr.in/{ciudad}?format=j1&lang=es"
        r   = requests.get(url, timeout=8)
        data = r.json()

        actual = data["current_condition"][0]
        desc   = actual["weatherDesc"][0]["value"]
        temp_c = actual["temp_C"]
        humedad = actual["humidity"]
        viento  = actual["windspeedKmph"]
        sensacion = actual["FeelsLikeC"]

        return {
            "ok":        True,
            "ciudad":    ciudad,
            "desc":      desc,
            "temp_c":    temp_c,
            "sensacion": sensacion,
            "humedad":   humedad,
            "viento":    viento,
        }
    except Exception as e:
        print(f"[Clima] Error clima: {e}")
        return {"ok": False}


def responder(client: genai.Client, mensaje: str,
              ciudad_override: str = "", model: str = "gemini-2.5-flash") -> str:
    """
    Punto de entrada: detecta ubicación, consulta clima
    y genera una respuesta con la personalidad de Zelic.
    """
    # Ubicación
    if ciudad_override:
        ciudad = ciudad_override
    else:
        loc = obtener_ubicacion()
        if not loc["ok"]:
            return "No pude detectar tu ubicación. Dime la ciudad y te digo el clima."
        ciudad = loc["ciudad"]

    # Clima
    clima = obtener_clima(ciudad)
    if not clima["ok"]:
        return f"No pude obtener el clima de {ciudad}. Intenta de nuevo en un momento."

    # Respuesta con personalidad de Zelic
    contexto = (
    f"Current weather in {clima['ciudad']}:\n"
    f"Temperature: {clima['temp_c']}°C (feels like {clima['sensacion']}°C)\n"
    f"Condition: {clima['desc']}\n"
    f"Humidity: {clima['humedad']}%\n"
    f"Wind: {clima['viento']} km/h\n\n"
    f'The user asked: "{mensaje}"\n\n'
    f"{PERSONALIDAD_ULTRA_COMPACTA_ZELIC}"
    f"Give a brief weather response. Maximum 2 lines."
    )

    try:
        resp = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=contexto)])]
        )
        return resp.text.strip()
    except Exception as e:
        return (f"Clima en {ciudad}: {clima['temp_c']}°C, {clima['desc']}. "
                f"Humedad {clima['humedad']}%, viento {clima['viento']} km/h.")