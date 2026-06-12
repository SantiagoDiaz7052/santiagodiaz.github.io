from services.supabase_client import supabase

def inscribir_deportista(club_id: str, nombre: str, documento: str, 
                          telefono: str, categoria: str, fecha_nacimiento: str) -> dict:
    # Verificar si ya existe
    existente = supabase.table("deportistas")\
        .select("id")\
        .eq("club_id", club_id)\
        .eq("documento", documento)\
        .execute()

    if existente.data:
        return {
            "exito": False,
            "mensaje": f"Ya existe un deportista con el documento {documento}."
        }

    # Insertar nuevo deportista
    resultado = supabase.table("deportistas").insert({
        "club_id": club_id,
        "nombre": nombre,
        "documento": documento,
        "telefono": telefono,
        "categoria": categoria,
        "fecha_nacimiento": fecha_nacimiento,
        "estado": "activo"
    }).execute()

    if resultado.data:
        return {
            "exito": True,
            "mensaje": f"¡{nombre} inscrito correctamente en categoría {categoria}!"
        }
    else:
        return {
            "exito": False,
            "mensaje": "Error al inscribir. Intenta de nuevo."
        }

def consultar_deportista(club_id: str, documento: str) -> dict:
    resultado = supabase.table("deportistas")\
        .select("*")\
        .eq("club_id", club_id)\
        .eq("documento", documento)\
        .execute()

    if resultado.data:
        d = resultado.data[0]
        return {
            "encontrado": True,
            "nombre": d["nombre"],
            "categoria": d["categoria"],
            "estado": d["estado"],
            "fecha_inscripcion": d["created_at"]
        }
    else:
        return {
            "encontrado": False,
            "mensaje": "No se encontró ningún deportista con ese documento."
        }