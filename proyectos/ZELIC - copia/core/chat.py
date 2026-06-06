from google import genai   
from google.genai import types

from CONFIG.config import PERSONALIDAD_FULL_ZELIC

SYSTEM_PROMPT = PERSONALIDAD_FULL_ZELIC


###definimos la funcion responder (), se asigna el modelo a al modelo y el historial
def responder(client: genai.Client, memoria, model: str = "gemini-2.5-flash") -> str:
    historial = memoria.construir_historial()
    contenido = [
        types.Content(role="user",  parts=[types.Part(text=SYSTEM_PROMPT)]),
        types.Content(role="model", parts=[types.Part(text="Entendido. Estoy lista — aunque 'lista' es quedarse corto.")]),
        *historial,
    ]
    respuesta = client.models.generate_content(model=model, contents=contenido)
    return respuesta.text.strip()