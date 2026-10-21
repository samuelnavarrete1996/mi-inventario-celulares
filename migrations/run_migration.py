#!/usr/bin/env python3
"""
CLI de Migración Multi-Tenant SaaS para Mi Inventario Celulares.
Ejecuta la migración estructural en PostgreSQL (Supabase / Render / RDS) o SQLite local.

Uso:
    python migrations/run_migration.py
    python migrations/run_migration.py --database-url postgresql://user:pass@host:5432/dbname
"""

import sys
import os
import argparse

# Configurar encoding UTF-8 seguro para Windows / Linux
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Asegurar que el directorio raíz esté en sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import database

def run():
    parser = argparse.ArgumentParser(description="Ejecutor de Migración SaaS Multi-Tenant")
    parser.add_argument("--database-url", type=str, default=None, help="Cadena de conexión DATABASE_URL explícita")
    args = parser.parse_args()

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url.strip()
        database.DATABASE_URL = args.database_url.strip()
        try:
            from app.postgres_client import reset_postgres_engine
            reset_postgres_engine()
        except Exception:
            pass

    is_pg = database.is_postgres_enabled()
    is_turso = database.is_turso_enabled()

    motor = "PostgreSQL (Supabase / Cloud)" if is_pg else ("Turso Cloud (libSQL)" if is_turso else "SQLite Local")
    print("=" * 70)
    print(">>> EJECUTANDO MIGRACION MULTI-TENANT SAAS")
    print(f"[*] Motor de Base de Datos Detectado: {motor}")
    if is_pg:
        # Ofuscar contraseña en URL para logs
        url = os.environ.get("DATABASE_URL", "")
        masked_url = url
        if "@" in url:
            creds, host = url.split("@", 1)
            scheme, auth = creds.split("://", 1)
            user = auth.split(":")[0] if ":" in auth else auth
            masked_url = f"{scheme}://{user}:*****@{host}"
        print(f"[*] Conexion: {masked_url}")
    print("=" * 70)

    try:
        # 1. Ejecutar init_db (crea tablas maestras, añade columnas e índices)
        print("\n[1/3] Aplicando esquema de tablas maestras y columnas tenant_id / sucursal_id...")
        database.init_db()
        print("  [OK] Tablas maestras 'tenants', 'sucursales' y 'configuracion_tienda' listas.")
        print("  [OK] Columnas tenant_id y sucursal_id verificadas con índices.")

        # 2. Inicializar tenant demo y backfill de registros
        print("\n[2/3] Verificando tenant de prueba 'Demostracion Celulares' y asignando registros...")
        database.init_demo_tenant_if_empty()
        print("  [OK] Tenant demo verificado.")
        print("  [OK] Sucursal Matriz y configuracion de tienda listas.")
        print("  [OK] Registros existentes asignados al tenant por defecto.")

        # 3. Reporte de verificación y estadísticas
        print("\n[3/3] Consultando estadisticas de la base de datos...")
        conn = database.get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) as count FROM tenants;")
        tot_tenants = cur.fetchone()["count"]

        cur.execute("SELECT COUNT(*) as count FROM sucursales;")
        tot_sucursales = cur.fetchone()["count"]

        cur.execute("SELECT COUNT(*) as count FROM configuracion_tienda;")
        tot_configs = cur.fetchone()["count"]

        print(f"  * Tenants registrados: {tot_tenants}")
        print(f"  * Sucursales activas:  {tot_sucursales}")
        print(f"  * Configuraciones:     {tot_configs}")

        # Listar conteo de registros asociados a tenant
        for t in ['equipos', 'ventas', 'reparaciones', 'accesorios', 'cortes_caja']:
            try:
                cur.execute(f"SELECT COUNT(*) as tot, SUM(CASE WHEN tenant_id IS NOT NULL THEN 1 ELSE 0 END) as con_tenant FROM {t};")
                row = cur.fetchone()
                tot = row["tot"] or 0
                con_t = row["con_tenant"] or 0
                print(f"  * Tabla {t.ljust(14)}: {tot} registros ({con_t} con tenant asignado)")
            except Exception:
                pass

        conn.close()

        print("\n" + "=" * 70)
        print("[OK] MIGRACION COMPLETADA EXITOSAMENTE SIN ERRORES")
        print("=" * 70)
        return 0

    except Exception as e:
        print("\n" + "=" * 70)
        print(f"[ERROR] ERROR DURANTE LA MIGRACION: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(run())
