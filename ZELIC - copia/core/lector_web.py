"""
lector_web.py — Módulo de lectura de URLs para ZELIC
Extrae texto visible de páginas web a partir de URLs detectadas en el mensaje.
"""

import re
import requests
from bs4 import BeautifulSoup

# ─── Configuración ────────────────────────────────────────────────────────────

TIMEOUT = 10  # segundos máximo por request

MAX_CHARS = 9000  # límite de caracteres de texto extraído por URL

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Etiquetas cuyo contenido se elimina antes de extraer texto
ETIQUETAS_BASURA = ["script", "style", "noscript", "head", "meta", "link"]


# ─── Funciones públicas ───────────────────────────────────────────────────────

def extraer_urls(texto: str) -> list[str]:
    """
    Detecta y devuelve todas las URLs presentes en el texto del usuario.

    Args:
        texto: Mensaje completo del usuario.

    Returns:
        Lista de URLs encontradas (puede estar vacía).
    """
    patron = r'https?://[^\s\'"<>]+'
    return re.findall(patron, texto)


def obtener_html(url: str) -> str | None:
    """
    Descarga el HTML de una URL con timeout y User-Agent real.

    Args:
        url: URL a descargar.

    Returns:
        Contenido HTML como string, o None si hubo error.
    """
    try:
        respuesta = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        respuesta.raise_for_status()
        return respuesta.text
    except requests.exceptions.Timeout:
        print(f"[lector_web] Timeout al acceder a: {url}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"[lector_web] Error de conexión: {url}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"[lector_web] Error HTTP {e.response.status_code}: {url}")
        return None
    except Exception as e:
        print(f"[lector_web] Error inesperado al descargar {url}: {e}")
        return None


def limpiar_html(html: str) -> str:
    """
    Elimina etiquetas de ruido (script, style, noscript…) y extrae
    solo el texto visible, limitado a MAX_CHARS caracteres.

    Args:
        html: Contenido HTML crudo.

    Returns:
        Texto limpio y recortado.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Eliminar etiquetas de ruido y su contenido
        for tag in soup.find_all(ETIQUETAS_BASURA):
            tag.decompose()

        # Extraer texto visible, separando bloques con salto de línea
        texto = soup.get_text(separator="\n", strip=True)

        # Colapsar líneas vacías múltiples
        lineas = [l for l in texto.splitlines() if l.strip()]
        texto_limpio = "\n".join(lineas)

        # Limitar longitud
        if len(texto_limpio) > MAX_CHARS:
            texto_limpio = texto_limpio[:MAX_CHARS] + "\n[... contenido recortado por longitud ...]"

        return texto_limpio

    except Exception as e:
        print(f"[lector_web] Error al limpiar HTML: {e}")
        return ""


def leer_url(url: str) -> str:
    """
    Pipeline completo para una sola URL:
    descarga → limpia → devuelve texto o mensaje de error.

    Args:
        url: URL a procesar.

    Returns:
        Texto extraído, o mensaje de error legible.
    """
    html = obtener_html(url)

    if html is None:
        return f"[No pude leer la página: {url}]"

    texto = limpiar_html(html)

    if not texto.strip():
        return f"[La página no tiene texto legible: {url}]"

    return texto


def leer_urls(texto: str) -> dict:
    """
    Detecta todas las URLs en el mensaje y las procesa.

    Args:
        texto: Mensaje completo del usuario.

    Returns:
        Diccionario con:
          - "urls": lista de URLs encontradas
          - "contenidos": dict {url: texto_extraido}
          - "contexto_web": string formateado listo para sistema.py
          - "hay_urls": bool, True si se encontró al menos una URL
    """
    urls = extraer_urls(texto)

    if not urls:
        return {
            "urls": [],
            "contenidos": {},
            "contexto_web": "",
            "hay_urls": False,
        }

    contenidos = {}
    bloques = []

    for url in urls:
        print(f"[lector_web] Procesando URL: {url}")
        contenido = leer_url(url)
        contenidos[url] = contenido
        bloques.append(f"--- Contenido de {url} ---\n{contenido}\n")

    contexto_web = "\n".join(bloques)

    return {
        "urls": urls,
        "contenidos": contenidos,
        "contexto_web": contexto_web,
        "hay_urls": True,
    }