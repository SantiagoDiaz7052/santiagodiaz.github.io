"""
core/vision_pantalla.py — Zelic ve la pantalla bajo demanda
Solo toma captura cuando el usuario lo pide explícitamente.
"""

import base64
import io
import mss
from PIL import Image
from google import genai
from google.genai import types


SYSTEM_PROMPT_VISION = """Eres Zelic, una IA asistente personal sarcástica, ingeniosa y útil.
Acabas de tomar una captura de la pantalla del usuario.
Analiza lo que ves y responde a su pregunta o petición de forma concisa.
Máximo 3 líneas. Responde en el mismo idioma del usuario."""


def analizar(client: genai.Client, pregunta: str,
             model: str = "gemini-2.5-flash") -> str:
    """
    Toma UNA captura de pantalla y responde la pregunta del usuario.
    Sin loops, sin tokens innecesarios.
    """
    captura = _tomar_captura()
    if not captura:
        return "No pude tomar la captura. ¿Tienes varios monitores? Intenta de nuevo."

    prompt = (
        f"El usuario pregunta: \"{pregunta}\"\n"
        f"Responde basándote en lo que ves en la pantalla con tu personalidad."
        if pregunta else
        "Describe brevemente qué está haciendo el usuario y ofrece ayuda si es relevante."
    )

    return _analizar_imagen(client, captura, prompt, model)


def _tomar_captura() -> bytes | None:
    """Toma captura del monitor principal y la comprime."""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            captura = sct.grab(monitor)
            img = Image.frombytes("RGB", captura.size, captura.bgra, "raw", "BGRX")
            img = img.resize((1280, 720), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=65)
            return buffer.getvalue()
    except Exception as e:
        print(f"[Visión] Error captura: {e}")
        return None


def _analizar_imagen(client: genai.Client, imagen_bytes: bytes,
                     prompt: str, model: str) -> str:
    """Envía imagen + pregunta a Gemini Vision."""
    imagen_b64 = base64.b64encode(imagen_bytes).decode("utf-8")
    try:
        respuesta = client.models.generate_content(
            model=model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(text=SYSTEM_PROMPT_VISION),
                        types.Part(inline_data=types.Blob(
                            mime_type="image/jpeg",
                            data=imagen_b64
                        )),
                        types.Part(text=prompt),
                    ]
                )
            ]
        )
        return (respuesta.text or "No pude analizar la pantalla.").strip()
    except Exception as e:
        print(f"[Visión] Error Gemini: {e}")
        return f"Error al analizar la pantalla: {e}"