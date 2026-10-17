"""
Script de sincronización / migración de datos locales a Turso Cloud Database.
Copia todas las tablas, equipos, clientes, ventas, accesorios y reparaciones
desde inventario.db local hacia la base de datos permanente en la nube de Turso.
"""

import sqlite3
import os
import sys

# Cargar .env
from app.database import init_db, is_turso_enabled, get_db_connection, DATABASE_FILE
from app.turso_client import TursoConnection

def migrar_datos():
    print("=" * 60)
    print("  MIGRACIÓN DE INVENTARIO A TURSO CLOUD DATABASE")
    print("=" * 60)

    if not is_turso_enabled():
        print("[!] ERROR: Las credenciales de Turso no están configuradas en .env")
        return False

    if not os.path.exists(DATABASE_FILE):
        print(f"[!] No se encontró base local en {DATABASE_FILE}. Se inicializará vacía.")
        init_db()
        return True

    print(f"[*] Base de datos local: {DATABASE_FILE}")
    print("[*] Paso 1: Inicializando tablas y esquemas en Turso...")
    init_db()
    print("[+] Esquema verificado en Turso.")

    # Conexiones
    local_conn = sqlite3.connect(DATABASE_FILE)
    local_conn.row_factory = sqlite3.Row
    turso_conn = get_db_connection()

    tablas = [
        "clientes",
        "equipos",
        "ventas",
        "venta_items",
        "garantias",
        "accesorios",
        "cortes_caja",
        "reparaciones"
    ]

    for tabla in tablas:
        cur_local = local_conn.cursor()
        try:
            cur_local.execute(f"SELECT * FROM {tabla}")
            rows = cur_local.fetchall()
        except sqlite3.OperationalError:
            print(f"  - Tabla {tabla}: no existe en local, omitiendo.")
            continue

        if not rows:
            print(f"  - Tabla {tabla}: 0 registros en local.")
            continue

        # Obtener columnas
        cols = [c[0] for c in cur_local.description]
        col_list = ", ".join(cols)
        placeholders = ", ".join(["?"] * len(cols))
        insert_sql = f"INSERT OR REPLACE INTO {tabla} ({col_list}) VALUES ({placeholders})"

        # Convertir rows a listas de valores
        data_rows = []
        for r in rows:
            data_rows.append([r[c] for c in cols])

        print(f"  - Migrando {len(data_rows)} registros de tabla '{tabla}'...")
        cur_turso = turso_conn.cursor()
        
        # Enviar en bloques de 50 para estabilidad
        chunk_size = 50
        for i in range(0, len(data_rows), chunk_size):
            chunk = data_rows[i:i + chunk_size]
            cur_turso.executemany(insert_sql, chunk)

        print(f"  [OK] Tabla '{tabla}' migrada exitosamente ({len(data_rows)} registros).")

    local_conn.close()
    turso_conn.close()

    print("=" * 60)
    print("  MIGRACION COMPLETADA EXITOSAMENTE!")
    print("  Todos tus datos estan ahora seguros en Turso Cloud.")
    print("=" * 60)
    return True

if __name__ == "__main__":
    migrar_datos()
