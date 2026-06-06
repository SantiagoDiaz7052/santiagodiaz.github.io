"""
migracion_db.py
---------------
Ejecuta esto UNA SOLA VEZ para actualizar tu zelic.db existente
al nuevo esquema sin perder ningún dato.

Uso:
    python migracion_db.py
"""

import sqlite3
import os

DB_PATH = "data/zelic.db"


def migrar():
    if not os.path.exists(DB_PATH):
        print("No existe zelic.db — nada que migrar. Arranca Zelic normalmente.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cambios = 0

    # 1. Agregar columna resumen_memoria a sesiones (si no existe)
    cur.execute("PRAGMA table_info(sesiones)")
    columnas_sesiones = [row[1] for row in cur.fetchall()]

    if "resumen_memoria" not in columnas_sesiones:
        cur.execute("ALTER TABLE sesiones ADD COLUMN resumen_memoria TEXT DEFAULT ''")
        print("✓ Columna resumen_memoria agregada a sesiones")
        cambios += 1
    else:
        print("· resumen_memoria ya existe en sesiones")

    # 2. Crear tabla memoria_usuario (si no existe)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memoria_usuario (
            clave  TEXT PRIMARY KEY,
            valor  TEXT NOT NULL,
            fecha  TEXT NOT NULL
        )
    """)
    print("✓ Tabla memoria_usuario lista")
    cambios += 1

    # 3. Activar WAL para escrituras más rápidas
    conn.execute("PRAGMA journal_mode=WAL")
    print("✓ WAL activado")

    conn.commit()
    conn.close()

    print(f"\n{'═'*40}")
    print(f"Migración completada ({cambios} cambios aplicados).")
    print("Puedes arrancar Zelic normalmente.")
    print(f"{'═'*40}")


if __name__ == "__main__":
    migrar()