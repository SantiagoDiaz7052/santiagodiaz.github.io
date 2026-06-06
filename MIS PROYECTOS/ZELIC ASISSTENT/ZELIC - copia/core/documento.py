from google import genai
from google.genai import types
import pathlib
from CONFIG.config import PERSONALIDAD_COMPACTA_ZELIC
EXTENSIONES_SOPORTADAS = {".pdf", ".txt", ".md"}

def analizar(client: genai.Client, ruta_archivo: str, instruccion: str = f"Como Zelic, analiza el documento o archivo con tu personalidad: {PERSONALIDAD_COMPACTA_ZELIC}" , model: str = "gemini-2.5-flash") -> str:
    """
    Lee un archivo (PDF o texto) y lo analiza con Gemini.
    - ruta_archivo: ruta al archivo en disco
    - instruccion: lo que el usuario quiere hacer con el documento
    """
    ruta = pathlib.Path(ruta_archivo)
    
    if not ruta.exists():
        return f"No encontré el archivo: {ruta_archivo}"

    if ruta.suffix not in EXTENSIONES_SOPORTADAS:
        return f"Formato no soportado. Usa: {', '.join(EXTENSIONES_SOPORTADAS)}"

    # PDF → mandarlo como bytes con mime_type
    if ruta.suffix == ".pdf":
        contenido = [
            types.Part.from_bytes(
                data=ruta.read_bytes(),
                mime_type="application/pdf",
            ),
            instruccion,
        ]
    else:
        # TXT / MD → leer como texto plano
        texto = ruta.read_text(encoding="utf-8")
        contenido = [f"{instruccion}\n\n{texto}"]

    respuesta = client.models.generate_content(model=model, contents=contenido)
    return respuesta.text.strip()
