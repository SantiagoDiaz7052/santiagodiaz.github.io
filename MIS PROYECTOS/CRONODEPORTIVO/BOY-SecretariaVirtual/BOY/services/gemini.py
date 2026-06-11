from google import genai
from google.genai import types
from services.inscripciones import inscribir_deportista, consultar_deportista
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PROMPT_BASE = """
Eres una secretaria virtual eficiente de un club de patinaje.

REGLAS ESTRICTAS:
- Responde SIEMPRE en español
- Máximo 3 oraciones por respuesta
- Sin saludos largos ni despedidas
- Sin frases como "claro que sí", "por supuesto", "con gusto"
- Ve directo al punto
- Si necesitas datos del usuario, pide UN solo dato a la vez

PROCESO DE INSCRIPCIÓN:
Cuando el usuario quiera inscribirse, recolecta estos datos UNO POR UNO en este orden:
1. Nombre completo
2. Número de documento
3. Teléfono de contacto
4. Fecha de nacimiento (formato YYYY-MM-DD)
5. Categoría (Infantil, Juvenil o Élite)
Cuando tengas TODOS los datos, llama a la función inscribir_deportista.

CONSULTA DE DEPORTISTA:
Cuando el usuario quiera saber su estado o info, pide el documento y llama a consultar_deportista.
"""

# Definición de herramientas para Gemini
herramientas = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="inscribir_deportista",
            description="Inscribe un nuevo deportista en el club cuando se tienen todos sus datos.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "nombre": types.Schema(type=types.Type.STRING, description="Nombre completo"),
                    "documento": types.Schema(type=types.Type.STRING, description="Número de documento"),
                    "telefono": types.Schema(type=types.Type.STRING, description="Teléfono de contacto"),
                    "fecha_nacimiento": types.Schema(type=types.Type.STRING, description="Fecha YYYY-MM-DD"),
                    "categoria": types.Schema(type=types.Type.STRING, description="Infantil, Juvenil o Élite"),
                },
                required=["nombre", "documento", "telefono", "fecha_nacimiento", "categoria"]
            )
        ),
        types.FunctionDeclaration(
            name="consultar_deportista",
            description="Consulta la información de un deportista por su documento.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "documento": types.Schema(type=types.Type.STRING, description="Número de documento"),
                },
                required=["documento"]
            )
        )
    ])
]

def get_respuesta(system_prompt: str, historial: list, mensaje_nuevo: str, club_id: str = None) -> str:
    contents = []
    for m in historial:
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(
            role=role,
            parts=[types.Part(text=m["content"])]
        ))

    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=mensaje_nuevo)]
    ))

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        config=types.GenerateContentConfig(
            system_instruction=PROMPT_BASE + "\n\n" + system_prompt,
            max_output_tokens=300,
            temperature=0.5,
            tools=herramientas,
        ),
        contents=contents
    )

    # Verificar si Gemini quiere llamar una función
    for part in response.candidates[0].content.parts:
        if part.function_call:
            fn = part.function_call
            args = dict(fn.args)

            if fn.name == "inscribir_deportista" and club_id:
                resultado = inscribir_deportista(club_id=club_id, **args)
                return resultado["mensaje"]

            elif fn.name == "consultar_deportista" and club_id:
                resultado = consultar_deportista(club_id=club_id, **args)
                if resultado["encontrado"]:
                    return (f"Deportista: {resultado['nombre']}\n"
                           f"Categoría: {resultado['categoria']}\n"
                           f"Estado: {resultado['estado']}")
                else:
                    return resultado["mensaje"]

    return response.text