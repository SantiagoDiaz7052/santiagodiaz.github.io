"""
core/sistema.py — Módulo para abrir apps, archivos, carpetas y explorar el PC
Zelic interpreta el mensaje y ejecuta la acción correspondiente.
"""

import subprocess
import os
import json
from urllib.parse import urlparse
from google import genai
from google.genai import types

from CONFIG.config import PERSONALIDAD_COMPACTA_ZELIC

# ── Apps conocidas (nombre → ruta ejecutable) ──────────────────────────────────
_USER = os.getenv('USERNAME', '')
APPS_CONOCIDAS = {
    "chrome":       r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google":       r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "navegador":    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox":      r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "spotify":      rf"C:\Users\{_USER}\AppData\Roaming\Spotify\Spotify.exe",
    "musica":       rf"C:\Users\{_USER}\AppData\Roaming\Spotify\Spotify.exe",
    "vscode":       rf"C:\Users\{_USER}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "codigo":       rf"C:\Users\{_USER}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "notepad":      r"C:\Windows\System32\notepad.exe",
    "bloc":        r"C:\Windows\System32\notepad.exe",
    "calculadora":  r"C:\Windows\System32\calc.exe",
    "calc":         r"C:\Windows\System32\calc.exe",
    "explorador":   r"C:\Windows\explorer.exe",
    "archivos":     r"C:\Windows\explorer.exe",
    "word":         r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "excel":        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    "powerpoint":   r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    "paint":        r"C:\Windows\System32\mspaint.exe",
    "cmd":          r"C:\Windows\System32\cmd.exe",
    "terminal":     r"C:\Windows\System32\cmd.exe",
    "discord":      rf"C:\Users\{_USER}\AppData\Local\Discord\Update.exe",
    "whatsapp":     rf"C:\Users\{_USER}\AppData\Local\WhatsApp\WhatsApp.exe",
    "steam":        r"C:\Program Files (x86)\Steam\steam.exe",
    "vlc":          r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "zoom":         rf"C:\Users\{_USER}\AppData\Roaming\Zoom\bin\Zoom.exe",
    "visual studio":r"C:\Users\Santiago Diaz\AppData\Local\Programs\Microsoft VS Code",
}

# ── Carpetas conocidas ─────────────────────────────────────────────────────────
CARPETAS_CONOCIDAS = {
    "escritorio":   os.path.join(os.path.expanduser("~"), "Desktop"),
    "desktop":      os.path.join(os.path.expanduser("~"), "Desktop"),
    "documentos":   os.path.join(os.path.expanduser("~"), "Documents"),
    "documents":    os.path.join(os.path.expanduser("~"), "Documents"),
    "descargas":    os.path.join(os.path.expanduser("~"), "Downloads"),
    "downloads":    os.path.join(os.path.expanduser("~"), "Downloads"),
    "imagenes":     os.path.join(os.path.expanduser("~"), "Pictures"),
    "pictures":     os.path.join(os.path.expanduser("~"), "Pictures"),
    "musica":       os.path.join(os.path.expanduser("~"), "Music"),
    "videos":       os.path.join(os.path.expanduser("~"), "Videos"),
    "inicio":       os.path.expanduser("~"),
    "home":         os.path.expanduser("~"),
}


def _resolver_ruta(ruta: str) -> str:
    return os.path.abspath(os.path.expandvars(os.path.expanduser(ruta or "")))


def _ruta_permitida(ruta: str) -> bool:
    ruta_abs = _resolver_ruta(ruta)
    home = _resolver_ruta("~")
    try:
        return os.path.commonpath([home, ruta_abs]) == home
    except ValueError:
        return False


def _url_permitida(url: str) -> str | None:
    limpia = (url or "").strip()
    if not limpia:
        return None
    if any(ch in limpia for ch in "\r\n\t"):
        return None
    if not limpia.startswith(("http://", "https://")):
        limpia = "https://" + limpia

    partes = urlparse(limpia)
    if partes.scheme not in {"http", "https"} or not partes.netloc:
        return None
    return limpia

PROMPT_SISTEMA = """

Responde como Zelic:
{personalidad}

El usuario dijo: "{mensaje}"

Analiza y responde en JSON exacto (sin markdown):
{{
  "accion": "abrir_app" | "abrir_carpeta" | "abrir_url" | "explorar_carpeta" | "ninguna",
  "objetivo": "nombre de app, ruta, URL, o nombre de carpeta (escritorio, documentos, descargas, etc.)",
  "respuesta": "respuesta de Zelic con personalidad (máximo 1 línea)"
}}

Reglas:
- Abrir app → abrir_app, objetivo = nombre en minúsculas
- Abrir carpeta/directorio en explorador → abrir_carpeta, objetivo = ruta o nombre
- Abrir sitio web → abrir_url, objetivo = URL con https://
- VER o LISTAR archivos de una carpeta → explorar_carpeta, objetivo = nombre de carpeta (ej: "escritorio", "descargas")
- No es acción del sistema → ninguna
- responde como zelic : {personalidad}
"""


def construir_prompt_con_web(mensaje: str, contexto_web: str = "") -> str:
    """
    Construye el texto que se guardará en memoria cuando hay contenido web.
    Si no hay URLs, devuelve el mensaje sin cambios.

    Args:
        mensaje:      Texto original del usuario.
        contexto_web: Texto extraído de URLs (puede ser "").

    Returns:
        Mensaje enriquecido con el contenido de las páginas, o el mensaje original.
    """
    if not contexto_web:
        return mensaje

    return (
        f"{mensaje}\n\n"
        f"[Contexto de páginas web mencionadas en el mensaje:]\n"
        f"{contexto_web}"
    )


def ejecutar(client: genai.Client, mensaje: str, model: str = "gemini-2.5-flash",
             contexto_web: str = "") -> str:
    """
    Analiza el mensaje del usuario, ejecuta la acción del sistema correspondiente
    y devuelve la respuesta de Zelic.

    Args:
        client:       Cliente de Google GenAI.
        mensaje:      Texto original del usuario.
        model:        Modelo Gemini a usar.
        contexto_web: Texto extraído de URLs detectadas (puede ser "").
    """
    # Si hay contenido web, enriquecer el mensaje para el análisis de intención
    mensaje_efectivo = construir_prompt_con_web(mensaje, contexto_web)

    prompt = PROMPT_SISTEMA.format(
        mensaje=mensaje_efectivo,
        personalidad=PERSONALIDAD_COMPACTA_ZELIC
    )

    try:
        resp = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])]
        )
        texto = resp.text.strip().replace("```json", "").replace("```", "").strip()
        data  = json.loads(texto)
    except Exception as e:
        return f"No pude procesar esa acción: {e}"

    accion   = data.get("accion", "ninguna")
    objetivo = data.get("objetivo", "").strip()
    respuesta = data.get("respuesta", "Listo.")

    if accion == "abrir_app":
        resultado = _abrir_app(objetivo.lower())
        if resultado != "ok":
            respuesta = resultado

    elif accion == "abrir_carpeta":
        resultado = _abrir_carpeta(objetivo)
        if resultado != "ok":
            respuesta = resultado

    elif accion == "abrir_url":
        resultado = _abrir_url(objetivo)
        if resultado != "ok":
            respuesta = resultado

    elif accion == "explorar_carpeta":
        respuesta = _explorar_carpeta(client, objetivo, mensaje, model)

    return respuesta


def _explorar_carpeta(client: genai.Client, objetivo: str,
                      mensaje_original: str, model: str) -> str:
    """Lista los archivos de una carpeta y los describe con Zelic."""
    objetivo_lower = objetivo.lower()
    ruta = None
    for clave, path in CARPETAS_CONOCIDAS.items():
        if clave in objetivo_lower:
            ruta = path
            break

    if not ruta:
        candidata = _resolver_ruta(objetivo)
        if os.path.exists(candidata):
            ruta = candidata
        else:
            ruta = os.path.expanduser("~")

    if not os.path.exists(ruta):
        return f"No encontré la carpeta '{objetivo}'."

    if not _ruta_permitida(ruta):
        return "Por seguridad solo puedo explorar carpetas dentro de tu usuario."

    try:
        items = os.listdir(ruta)
    except PermissionError:
        return "No tengo permiso para ver esa carpeta."

    if not items:
        return f"La carpeta '{os.path.basename(ruta)}' está vacía."

    # Separar y ordenar
    carpetas = sorted([i for i in items if os.path.isdir(os.path.join(ruta, i))])
    archivos = sorted([i for i in items if os.path.isfile(os.path.join(ruta, i))])

    # Construir lista técnica directamente sin pasar por Gemini JSON
    lineas = [f"📁 {os.path.basename(ruta)}  —  {len(items)} elementos\n"]

    if carpetas:
        lineas.append(f"📂 Carpetas ({len(carpetas)}):")
        for c in carpetas:
            lineas.append(f"   • {c}")

    if archivos:
        lineas.append(f"\n📄 Archivos ({len(archivos)}):")
        for a in archivos:
            # Tamaño del archivo
            try:
                size = os.path.getsize(os.path.join(ruta, a))
                if size < 1024:
                    size_txt = f"{size} B"
                elif size < 1024**2:
                    size_txt = f"{size/1024:.1f} KB"
                else:
                    size_txt = f"{size/1024**2:.1f} MB"
            except:
                size_txt = "?"
            lineas.append(f"   • {a}  ({size_txt})")

    return "\n".join(lineas)


def _abrir_app(nombre: str) -> str:
    nombre = " ".join((nombre or "").lower().split())
    if not nombre:
        return "Dime qué aplicación quieres abrir."

    # Buscar en apps conocidas
    for clave, ruta in APPS_CONOCIDAS.items():
        if clave in nombre or nombre in clave:
            if os.path.isfile(ruta):
                subprocess.Popen([ruta])
                return "ok"

    return f"No encontré '{nombre}' en la lista segura de apps."


def _abrir_carpeta(ruta: str) -> str:
    if not ruta:
        ruta = os.path.expanduser("~")
    elif ruta.lower() in CARPETAS_CONOCIDAS:
        ruta = CARPETAS_CONOCIDAS[ruta.lower()]
    else:
        ruta = _resolver_ruta(ruta)

    if not os.path.isdir(ruta):
        return "No encontré esa carpeta."

    if not _ruta_permitida(ruta):
        return "Por seguridad solo puedo abrir carpetas dentro de tu usuario."

    try:
        os.startfile(ruta)
        return "ok"
    except:
        try:
            subprocess.Popen(["explorer", ruta])
            return "ok"
        except Exception as e:
            return f"No pude abrir esa carpeta: {e}"


def _abrir_url(url: str) -> str:
    url = _url_permitida(url)
    if not url:
        return "Esa URL no parece segura o válida."
    try:
        import webbrowser
        webbrowser.open(url)
        return "ok"
    except Exception as e:
        return f"No pude abrir el navegador: {e}"
    
def procesar(mensaje: str, contexto_web: str = "") -> str:
    """
    Alias de conveniencia para flujos que no tienen acceso al client de genai.
    Devuelve solo el texto enriquecido con el contexto web; el LLM lo procesa
    a través del flujo normal de chat en app.py.

    En la mayoría de los casos preferir ejecutar() directamente.

    Args:
        mensaje:      Texto original del usuario.
        contexto_web: Texto extraído de URLs detectadas (puede ser "").

    Returns:
        Mensaje enriquecido listo para agregar a la memoria de chat.
    """
    return construir_prompt_con_web(mensaje, contexto_web)
