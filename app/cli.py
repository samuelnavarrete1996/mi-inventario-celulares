"""
app/cli.py - Herramienta de Línea de Comandos para Administración SaaS Multi-Tenant.
Permite registrar nuevos clientes (tenants), crear su sucursal matriz, inicializar
su configuración de marca blanca y aprovisionar al usuario administrador (dueño)
con hashing seguro Argon2id.

Uso:
    python -m app.cli crear-tienda --nombre "Celulares San Juan" --slug "celulares-san-juan" --admin "juan_dueno" --password "ClaveSegura123" --email "contacto@tienda.com"
"""

import sys
import re
import argparse
from datetime import datetime
from typing import Optional, Dict, Any, List

# Forzar codificación segura en entornos con codepages heredados (Windows CMD/PowerShell)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.database import get_db_connection, init_db
from app.security import hash_secret


def crear_tienda(
    nombre: str,
    slug: str,
    admin: str,
    password: str,
    email: str = "",
    telefono: str = "",
    direccion: str = "Matriz Centro",
    plan: str = "pro"
) -> Dict[str, Any]:
    """
    Crea un nuevo tenant en la base de datos (PostgreSQL o SQLite):
    1. Registra el tenant con plan 'pro' y activo=True.
    2. Crea la sucursal matriz.
    3. Inicializa la configuración de marca blanca de tienda.
    4. Crea el usuario administrador con rol 'dueno' y credenciales Argon2id.
    Retorna un diccionario con los datos del tenant creado.
    """
    # 1. Asegurar tablas inicializadas
    init_db()

    # 2. Validaciones básicas
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre comercial no puede estar vacío.")

    slug = slug.strip().lower()
    if not slug:
        raise ValueError("El slug no puede estar vacío.")
    if not re.match(r"^[a-z0-9_-]+$", slug):
        raise ValueError(
            f"El slug '{slug}' contiene caracteres no permitidos. Solo se admiten letras minúsculas, números, guiones y guiones bajos."
        )

    admin = admin.strip()
    if not admin:
        raise ValueError("El nombre de usuario administrador no puede estar vacío.")

    if not password or len(password) < 6:
        raise ValueError("La contraseña debe contener al menos 6 caracteres.")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # 3. Validar unicidad de slug
        cur.execute("SELECT id FROM tenants WHERE slug = ? LIMIT 1;", (slug,))
        if cur.fetchone():
            raise ValueError(f"El slug '{slug}' ya está registrado por otra tienda.")

        # 4. Validar unicidad de username
        cur.execute("SELECT id FROM usuarios WHERE username = ? LIMIT 1;", (admin,))
        if cur.fetchone():
            raise ValueError(f"El nombre de usuario '{admin}' ya se encuentra en uso.")

        # 5. Insertar Tenant
        cur.execute("""
            INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (nombre, slug, email or "", telefono or "", plan or "pro", True, now))
        tenant_id = cur.lastrowid
        if not tenant_id:
            cur.execute("SELECT id FROM tenants WHERE slug = ? LIMIT 1;", (slug,))
            row = cur.fetchone()
            tenant_id = row["id"] if row else None

        if not tenant_id:
            raise RuntimeError("No se pudo obtener el identificador del nuevo tenant.")

        # 6. Insertar Sucursal Matriz
        cur.execute("""
            INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (tenant_id, direccion or "Matriz Centro", direccion or "Matriz Principal", telefono or "", True, now))
        sucursal_id = cur.lastrowid
        if not sucursal_id:
            cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? AND es_matriz = ? LIMIT 1;", (tenant_id, True))
            row = cur.fetchone()
            sucursal_id = row["id"] if row else None

        # 7. Insertar Configuración de Tienda
        encabezado = f"{nombre} | Compra, Venta y Servicio Especializado"
        pie_garantia = "Garantía de 30 días válida únicamente con este comprobante original. No cubre daños por humedad o golpes."
        cur.execute("""
            INSERT INTO configuracion_tienda (tenant_id, logo_url, encabezado_ticket, pie_ticket_garantia, whatsapp_notificaciones, fecha_actualizacion)
            VALUES (?, NULL, ?, ?, ?, ?);
        """, (tenant_id, encabezado, pie_garantia, telefono or "", now))

        # 8. Insertar Usuario Administrador (Dueño) con Argon2id
        pin_hash, salt = hash_secret(password)
        cur.execute("""
            INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES (?, ?, ?, ?, 'dueno', ?, ?, ?, ?);
        """, (f"Dueño - {nombre}", admin, pin_hash, salt, True, now, tenant_id, sucursal_id))
        user_id = cur.lastrowid
        if not user_id:
            cur.execute("SELECT id FROM usuarios WHERE username = ? LIMIT 1;", (admin,))
            row = cur.fetchone()
            user_id = row["id"] if row else None

        conn.commit()

        resultado = {
            "tenant_id": tenant_id,
            "nombre_comercial": nombre,
            "slug": slug,
            "plan": plan or "pro",
            "activo": True,
            "sucursal_id": sucursal_id,
            "sucursal_nombre": direccion or "Matriz Centro",
            "user_id": user_id,
            "admin_username": admin,
            "email_contacto": email or "",
            "telefono": telefono or "",
            "fecha_creacion": now
        }
        return resultado
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def listar_tiendas() -> List[Dict[str, Any]]:
    """Consulta y retorna todas las tiendas / tenants registrados en el sistema."""
    init_db()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.id, t.nombre_comercial, t.slug, t.email_contacto, t.telefono, t.plan, t.activo, t.fecha_creacion,
                   COUNT(s.id) as total_sucursales
            FROM tenants t
            LEFT JOIN sucursales s ON s.tenant_id = t.id
            GROUP BY t.id, t.nombre_comercial, t.slug, t.email_contacto, t.telefono, t.plan, t.activo, t.fecha_creacion
            ORDER BY t.id ASC;
        """)
        rows = cur.fetchall()
        tiendas = []
        for r in rows:
            tiendas.append({
                "id": r["id"],
                "nombre_comercial": r["nombre_comercial"],
                "slug": r["slug"],
                "email_contacto": r["email_contacto"],
                "telefono": r["telefono"],
                "plan": r["plan"],
                "activo": bool(r["activo"]),
                "fecha_creacion": r["fecha_creacion"],
                "total_sucursales": r["total_sucursales"]
            })
        return tiendas
    finally:
        conn.close()


def imprimir_resumen_alta(data: Dict[str, Any], password: str) -> None:
    """Imprime en consola el resumen con las credenciales y enlaces directos."""
    slug = data["slug"]
    admin = data["admin_username"]
    nombre = data["nombre_comercial"]
    tenant_id = data["tenant_id"]
    plan = data["plan"]
    sucursal = data["sucursal_nombre"]
    email = data["email_contacto"] or "No especificado"

    banner = f"""
================================================================================
[OK] TIENDA REGISTRADA CON EXITO EN ARQUITECTURA SAAS MULTI-TENANT
================================================================================
* Nombre Comercial:    {nombre}
* Identificador Slug:  {slug}
* Tenant ID:           #{tenant_id}
* Plan de Servicio:    {plan.upper()}
* Sucursal Matriz:     {sucursal} (ID: #{data['sucursal_id']})

ADMINISTRADOR GENERAL (ROL 'DUENO'):
|-- Usuario:           {admin}
|-- Contrasena:        {password}
|-- Hashing Seguro:    Argon2id (OWASP 2026)
+-- Email de Contacto: {email}

ENLACES DIRECTOS:
|-- Punto de Venta / Panel:  /?tenant={slug}
+-- Catalogo Web Publico:    /catalogo?tenant={slug}
================================================================================
"""
    try:
        print(banner)
    except Exception:
        # Fallback en caso extremo de stream sin soporte
        sys.stdout.buffer.write(banner.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Herramienta CLI para Administración de Tenants y Despliegue Cloud (Render & Supabase)"
    )
    parser.add_argument("--database-url", default=None, help="URL de conexión a base de datos (PostgreSQL o SQLite).")
    subparsers = parser.add_subparsers(dest="subcommand", help="Comandos disponibles")

    # Subcomando: crear-tienda
    cmd_crear = subparsers.add_parser(
        "crear-tienda",
        help="Da de alta un nuevo cliente (tenant), sucursal matriz, configuración y administrador."
    )
    cmd_crear.add_argument("--nombre", required=True, help="Nombre comercial de la tienda o negocio.")
    cmd_crear.add_argument("--slug", required=True, help="Identificador único para URL/subdominio (ej: celulares-san-juan).")
    cmd_crear.add_argument("--admin", required=True, help="Nombre de usuario del administrador principal (dueño).")
    cmd_crear.add_argument("--password", required=True, help="Contraseña segura para el administrador.")
    cmd_crear.add_argument("--email", default="", help="Correo electrónico de contacto.")
    cmd_crear.add_argument("--telefono", default="", help="Teléfono de contacto o WhatsApp de la tienda.")
    cmd_crear.add_argument("--direccion", default="Matriz Centro", help="Dirección física de la sucursal matriz.")
    cmd_crear.add_argument("--plan", default="pro", choices=["starter", "pro", "enterprise"], help="Plan SaaS asignado.")

    # Subcomando: listar-tiendas
    subparsers.add_parser("listar-tiendas", help="Lista todas las tiendas y tenants dados de alta.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "database_url", None):
        import os
        os.environ["DATABASE_URL"] = args.database_url.strip()
        import app.database as database
        database.DATABASE_URL = args.database_url.strip()
        try:
            from app.postgres_client import reset_postgres_engine
            reset_postgres_engine()
        except Exception:
            pass

    if not args.subcommand:
        parser.print_help()
        return 0

    if args.subcommand == "crear-tienda":
        try:
            res = crear_tienda(
                nombre=args.nombre,
                slug=args.slug,
                admin=args.admin,
                password=args.password,
                email=args.email,
                telefono=args.telefono,
                direccion=args.direccion,
                plan=args.plan
            )
            imprimir_resumen_alta(res, args.password)
            return 0
        except Exception as e:
            print(f"\n❌ ERROR AL CREAR TIENDA: {e}\n", file=sys.stderr)
            return 1

    if args.subcommand == "listar-tiendas":
        tiendas = listar_tiendas()
        print(f"\nTotal de tiendas registradas: {len(tiendas)}\n")
        print(f"{'ID':<5} {'SLUG':<25} {'NOMBRE COMERCIAL':<30} {'PLAN':<10} {'ACTIVO':<8}")
        print("-" * 80)
        for t in tiendas:
            activo_txt = "Sí" if t["activo"] else "No"
            print(f"{t['id']:<5} {t['slug']:<25} {t['nombre_comercial']:<30} {t['plan']:<10} {activo_txt:<8}")
        print("-" * 80)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
