from google import genai
from google.genai import types
from PIL import Image
import os

CARPETA_SALIDA = "data/imagenes"
CARPETA_SALIDA_FALLBACK = "data/imagenes_generadas"


def _carpeta_destino() -> str:
    destino = CARPETA_SALIDA
    if os.path.isfile(destino):
        destino = CARPETA_SALIDA_FALLBACK
    os.makedirs(destino, exist_ok=True)
    return destino


def ruta_imagen_generada() -> str:
    return os.path.join(_carpeta_destino(), "imagen_generada.png")

def generar(client: genai.Client, prompt: str, model: str = "gemini-3.1-flash-image-preview") -> str:
    """Genera una imagen a partir del prompt del usuario y la guarda en data/imagenes/."""
    carpeta_salida = _carpeta_destino()

    respuesta = client.models.generate_content(
        model=model,
        contents=[prompt],
    )

    texto = ""
    for part in respuesta.parts:
        if part.text is not None:
            texto = part.text
        elif part.inline_data is not None:
            imagen = part.as_image()
            ruta = os.path.join(carpeta_salida, "imagen_generada.png")
            imagen.save(ruta)
            print(f"[Imagen] Guardada en: {ruta}")

    return texto if texto else f"Imagen generada y guardada en {ruta_imagen_generada()}"
