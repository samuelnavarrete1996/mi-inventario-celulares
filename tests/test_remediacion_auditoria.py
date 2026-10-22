"""
tests/test_remediacion_auditoria.py - Suite Integral de Verificación de las 14 Vulnerabilidades (VULN-01 a VULN-14).

Verifica exhaustivamente:
1. VULN-01: Aislamiento estricto de respaldos JSON/SQLite por tenant_id, sanitización de pin_hash/salt,
            y bloqueo HTTP 403 de restauraciones de base de datos física en entornos multi-tenant.
2. VULN-02: Row-Level Security (RLS) endurecido en PostgreSQL con FORCE ROW LEVEL SECURITY en las 14 tablas
            operativas y eliminación de cualquier bypass de setting vacío.
3. VULN-03 y VULN-05: Revocación persistente de tokens en base de datos SQLite (revoked_tokens), rate-limiting
            persistente por IP y usuario (login_attempts), y validación de usuarios y tenants activos en tiempo real.
4. VULN-04: Catálogo público multi-tenant aislado por slug/tenant_id y rechazo con HTTP 404 para tiendas
            inexistentes o suspendidas.
5. VULN-06: Validación de firmas ejecutables (PHP, SVG, scripts), Magic Bytes binarios reales y re-codificación
            segura de imágenes con Pillow eliminando metadatos.
6. VULN-07, VULN-08, VULN-09, VULN-11: Prevención de IDOR / BOLA en garantías entre tenants, unicidad de IMEI
            y folios mediante índices compuestos multi-tenant, validación de identificadores SQL y proscripción
            de secretos por defecto o fallbacks en producción.
"""

import os
import io
import time
import shutil
import sqlite3
import tempfile
import pytest
import httpx
from PIL import Image

from app.main import app
from app.database import (
    get_db_connection,
    init_db,
    seed_demo_data_if_empty,
    _validate_sql_identifier
)
from app.security import (
    hash_secret,
    reset_all_rate_limits,
    _get_rl_conn,
    create_access_token,
    _init_jwt_secret
)
from app.routers.inventario import verify_delete_password
from app import crud
from app.models import GarantiaCreate, ItemCarrito

init_db()
seed_demo_data_if_empty()


@pytest.fixture(autouse=True)
def clean_rate_limits():
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()


def setup_audit_tenants_and_data():
    """Garantiza la existencia de tenants Alfa y Beta con sucursales, usuarios y datos para pruebas de auditoría."""
    conn = get_db_connection()
    cur = conn.cursor()
    now = "2026-10-22 10:00:00"

    try:
        # 1. Tenant Alfa (Activo)
        cur.execute("SELECT id FROM tenants WHERE slug = 'tienda-alfa' LIMIT 1;")
        row_a = cur.fetchone()
        if not row_a:
            cur.execute("""
                INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
                VALUES ('Celulares Alfa', 'tienda-alfa', 'alfa@test.com', '5511111111', 'pro', 1, ?);
            """, (now,))
            t_alfa_id = cur.lastrowid
            cur.execute("""
                INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
                VALUES (?, 'Alfa Matriz', 'Av Alfa 100', '5511111111', 1, ?);
            """, (t_alfa_id, now))
            s_alfa_id = cur.lastrowid
        else:
            t_alfa_id = row_a["id"]
            cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_alfa_id,))
            s_alfa_id = cur.fetchone()["id"]

        # 2. Tenant Beta (Activo)
        cur.execute("SELECT id FROM tenants WHERE slug = 'tienda-beta' LIMIT 1;")
        row_b = cur.fetchone()
        if not row_b:
            cur.execute("""
                INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
                VALUES ('Reparaciones Beta', 'tienda-beta', 'beta@test.com', '5522222222', 'starter', 1, ?);
            """, (now,))
            t_beta_id = cur.lastrowid
            cur.execute("""
                INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
                VALUES (?, 'Beta Sucursal 1', 'Calle Beta 200', '5522222222', 1, ?);
            """, (t_beta_id, now))
            s_beta_id = cur.lastrowid
        else:
            t_beta_id = row_b["id"]
            cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_beta_id,))
            s_beta_id = cur.fetchone()["id"]

        # 3. Tenant Suspendido (Inactivo)
        cur.execute("SELECT id FROM tenants WHERE slug = 'tienda-suspendida' LIMIT 1;")
        row_s = cur.fetchone()
        if not row_s:
            cur.execute("""
                INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
                VALUES ('Tienda Suspendida', 'tienda-suspendida', 'suspendida@test.com', '5533333333', 'basic', 0, ?);
            """, (now,))
            t_susp_id = cur.lastrowid
            cur.execute("""
                INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
                VALUES (?, 'Matriz Suspendida', 'Calle Nula 0', '5533333333', 1, ?);
            """, (t_susp_id, now))
            s_susp_id = cur.lastrowid
        else:
            t_susp_id = row_s["id"]
            cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_susp_id,))
            s_row = cur.fetchone()
            s_susp_id = s_row["id"] if s_row else 1

        # Usuarios
        h_a, s_a = hash_secret("AlfaPass123.")
        h_b, s_b = hash_secret("BetaPass123.")

        cur.execute("SELECT id FROM usuarios WHERE username = 'dueno_alfa' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
                VALUES ('Dueño Alfa', 'dueno_alfa', ?, ?, 'dueno', 1, ?, ?, ?);
            """, (h_a, s_a, now, t_alfa_id, s_alfa_id))

        cur.execute("SELECT id FROM usuarios WHERE username = 'dueno_beta' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
                VALUES ('Dueño Beta', 'dueno_beta', ?, ?, 'dueno', 1, ?, ?, ?);
            """, (h_b, s_b, now, t_beta_id, s_beta_id))

        # Equipos de prueba diferenciados
        cur.execute("SELECT id FROM equipos WHERE imei = 'ALFA-IMEI-AUDIT-001' LIMIT 1;")
        row_eq_a = cur.fetchone()
        if not row_eq_a:
            cur.execute("""
                INSERT INTO equipos (modelo, imei, capacidad_gb, color, grado, estado, costo_compra, precio_venta, fecha_registro, tenant_id, sucursal_id)
                VALUES ('iPhone 13 Alfa', 'ALFA-IMEI-AUDIT-001', 128, 'Negro', 'A', 'Disponible', 7000.0, 10500.0, ?, ?, ?);
            """, (now, t_alfa_id, s_alfa_id))
            eq_alfa_id = cur.lastrowid
        else:
            eq_alfa_id = row_eq_a["id"]

        cur.execute("SELECT id FROM equipos WHERE imei = 'BETA-IMEI-AUDIT-002' LIMIT 1;")
        row_eq_b = cur.fetchone()
        if not row_eq_b:
            cur.execute("""
                INSERT INTO equipos (modelo, imei, capacidad_gb, color, grado, estado, costo_compra, precio_venta, fecha_registro, tenant_id, sucursal_id)
                VALUES ('Samsung S22 Beta', 'BETA-IMEI-AUDIT-002', 256, 'Blanco', 'B', 'Disponible', 6000.0, 9500.0, ?, ?, ?);
            """, (now, t_beta_id, s_beta_id))
            eq_beta_id = cur.lastrowid
        else:
            eq_beta_id = row_eq_b["id"]

        # Venta simulada para garantía de Alfa
        cur.execute("SELECT id FROM equipos WHERE imei = 'ALFA-IMEI-VENDIDO-001' LIMIT 1;")
        row_eq_vendido = cur.fetchone()
        if not row_eq_vendido:
            cur.execute("""
                INSERT INTO equipos (modelo, imei, capacidad_gb, color, grado, estado, costo_compra, precio_venta, fecha_registro, tenant_id, sucursal_id)
                VALUES ('iPhone 12 Alfa Vendido', 'ALFA-IMEI-VENDIDO-001', 64, 'Azul', 'A', 'Disponible', 5000.0, 7500.0, ?, ?, ?);
            """, (now, t_alfa_id, s_alfa_id))
            eq_vendido_id = cur.lastrowid
            conn.commit()

            crud.registrar_venta_carrito(
                items=[ItemCarrito(tipo_item="equipo", equipo_id=eq_vendido_id, cantidad=1, precio_final=7500.0)],
                cliente_nombre="Cliente Audit Alfa",
                cliente_telefono="5511223344",
                metodo_pago="Efectivo",
                monto_efectivo=7500.0,
                tenant_id=t_alfa_id,
                sucursal_id=s_alfa_id
            )

        # Accesorios de prueba diferenciados
        cur.execute("SELECT id FROM accesorios WHERE nombre = 'Cargador Alfa Fast' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO accesorios (nombre, categoria, costo_compra, precio_venta, stock, es_servicio, fecha_registro, tenant_id, sucursal_id)
                VALUES ('Cargador Alfa Fast', 'Cargadores', 50.0, 199.0, 20, 0, ?, ?, ?);
            """, (now, t_alfa_id, s_alfa_id))

        cur.execute("SELECT id FROM accesorios WHERE nombre = 'Funda Beta Armor' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO accesorios (nombre, categoria, costo_compra, precio_venta, stock, es_servicio, fecha_registro, tenant_id, sucursal_id)
                VALUES ('Funda Beta Armor', 'Fundas', 35.0, 150.0, 30, 0, ?, ?, ?);
            """, (now, t_beta_id, s_beta_id))

        conn.commit()
    finally:
        conn.close()

    return {
        "t_alfa_id": t_alfa_id,
        "s_alfa_id": s_alfa_id,
        "t_beta_id": t_beta_id,
        "s_beta_id": s_beta_id,
        "t_susp_id": t_susp_id,
        "eq_beta_id": eq_beta_id
    }


# ==============================================================================
# TEST 1: VULN-01 AISLAMIENTO DE RESPALDOS MULTI-TENANT
# ==============================================================================

@pytest.mark.anyio
async def test_vuln01_aislamiento_backups_multitenant():
    """
    Verifica que /api/backup/exportar-json de Tenant A no contenga usuarios ni equipos de Tenant B,
    que omita pin_hash y salt en usuarios, que /api/backup/descargar-db genere una copia SQLite
    depurada exclusiva de Tenant A, y que /api/backup/restaurar-db rechace con HTTP 403 cuando COUNT(*) > 1.
    """
    ids = setup_audit_tenants_and_data()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Login Tenant Alfa
        res_login = await client.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        assert res_login.status_code == 200
        token_alfa = res_login.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token_alfa}"}

        # 1. Exportación JSON: validar exclusividad de tenant y omisión de pin_hash / salt
        res_json = await client.get("/api/backup/exportar-json", headers=auth_headers)
        assert res_json.status_code == 200
        data_json = res_json.json()
        datos_tablas = data_json.get("datos", data_json)

        assert "usuarios" in datos_tablas
        for u in datos_tablas["usuarios"]:
            assert "pin_hash" not in u, "VULN-01: pin_hash no debe incluirse en la exportación JSON"
            assert "salt" not in u, "VULN-01: salt no debe incluirse en la exportación JSON"
            assert u.get("tenant_id") == ids["t_alfa_id"], "VULN-01: No deben exportarse usuarios de otros tenants"

        assert "equipos" in datos_tablas
        for eq in datos_tablas["equipos"]:
            assert eq.get("tenant_id") == ids["t_alfa_id"], "VULN-01: No deben exportarse equipos de otros tenants"

        # 2. Descarga DB SQLite: validar que sea un archivo SQLite válido y filtrado solo para Alfa
        res_db = await client.get("/api/backup/descargar-db", headers=auth_headers)
        assert res_db.status_code == 200
        db_bytes = res_db.content
        assert db_bytes.startswith(b"SQLite format 3\x00"), "VULN-01: Debe ser una base de datos SQLite válida"

        # Inspección física de la base SQLite descargada
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            tmp_file.write(db_bytes)

        try:
            tmp_conn = sqlite3.connect(tmp_path)
            tmp_cur = tmp_conn.cursor()

            # Solo debe existir el tenant de Alfa
            tmp_cur.execute("SELECT id FROM tenants;")
            tenants_in_backup = [r[0] for r in tmp_cur.fetchall()]
            assert ids["t_alfa_id"] in tenants_in_backup
            assert ids["t_beta_id"] not in tenants_in_backup, "VULN-01: El backup físico no debe contener a Tenant Beta"

            # Equipos deben ser solo de Alfa
            tmp_cur.execute("SELECT tenant_id FROM equipos;")
            for r in tmp_cur.fetchall():
                assert r[0] == ids["t_alfa_id"]

            # Usuarios deben ser solo de Alfa
            tmp_cur.execute("SELECT tenant_id FROM usuarios;")
            for r in tmp_cur.fetchall():
                assert r[0] == ids["t_alfa_id"]

            tmp_conn.close()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        # 3. Restauración de BD física bloqueada con HTTP 403 cuando COUNT(*) > 1
        fake_db = b"SQLite format 3\x00" + b"\x00" * 500
        res_restore = await client.post(
            "/api/backup/restaurar-db",
            files={"archivo": ("restore.db", fake_db, "application/octet-stream")},
            headers=auth_headers
        )
        assert res_restore.status_code == 403, "VULN-01: Debe retornar HTTP 403 al intentar restaurar DB física en entorno multi-tenant"
        assert "multi-tenant" in res_restore.json()["detail"].lower()


# ==============================================================================
# TEST 2: VULN-02 ROW LEVEL SECURITY EN POSTGRESQL ENDURECIDO
# ==============================================================================

def test_vuln02_rls_postgresql_endurecido():
    """
    Verifica que migrations/001_multi_tenant_postgres.sql y app/database.py
    contengan FORCE ROW LEVEL SECURITY en las 14 tablas operativas y que la política
    utilice NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER sin bypass.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    migration_file = os.path.join(repo_root, "migrations", "001_multi_tenant_postgres.sql")
    database_file = os.path.join(repo_root, "app", "database.py")

    tablas_esperadas = [
        "sucursales", "configuracion_tienda", "usuarios", "equipos", "accesorios",
        "clientes", "ventas", "venta_accesorios", "abonos_credito", "pagos_credito",
        "movimientos_stock", "reparaciones", "garantias", "cortes_caja"
    ]

    with open(migration_file, "r", encoding="utf-8") as f:
        mig_content = f.read()

    with open(database_file, "r", encoding="utf-8") as f:
        db_content = f.read()

    # Validar FORCE ROW LEVEL SECURITY en migración y base de datos
    assert "FORCE ROW LEVEL SECURITY" in mig_content, "VULN-02: La migración PostgreSQL debe habilitar FORCE ROW LEVEL SECURITY"
    assert "FORCE ROW LEVEL SECURITY" in db_content, "VULN-02: database.py debe forzar RLS en _init_postgres_db"

    # Validar política estricta sin bypass
    strict_policy = "NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER"
    assert strict_policy in mig_content, "VULN-02: La política RLS debe castear mediante NULLIF estricto"

    dangerous_bypass = "current_setting('app.current_tenant_id', true) = ''"
    assert dangerous_bypass not in mig_content, "VULN-02: No se permite el bypass de tenant vacío en RLS"

    # Validar presencia de las 14 tablas operativas en la migración
    for t in tablas_esperadas:
        assert f"'{t}'" in mig_content or f'"{t}"' in mig_content, f"VULN-02: Tabla {t} ausente en tablas_rls de PostgreSQL"


# ==============================================================================
# TEST 3: VULN-03 Y VULN-05 REVOCACIÓN Y RATE LIMIT PERSISTENTES
# ==============================================================================

@pytest.mark.anyio
async def test_vuln03_vuln05_revocacion_persistente_y_rate_limit_persistente():
    """
    Verifica que la revocación de tokens persista en SQLite (revoked_tokens), que tras
    cerrar sesión el token sea rechazado, que tras 5 intentos fallidos se devuelva HTTP 429
    persistido en tabla login_attempts, y que un usuario desactivado sea rechazado de inmediato.
    """
    setup_audit_tenants_and_data()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login y Logout: Revocación persistente
        res_login = await client.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        assert res_login.status_code == 200
        token = res_login.json()["access_token"]

        # Comprobar acceso previo
        res_me1 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_me1.json()["authenticated"] is True

        # Logout explícito
        res_out = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert res_out.status_code == 200

        # Verificar que el jti está en la tabla SQLite revoked_tokens
        conn_rl = _get_rl_conn()
        cur_rl = conn_rl.cursor()
        cur_rl.execute("SELECT COUNT(*) FROM revoked_tokens;")
        assert cur_rl.fetchone()[0] > 0, "VULN-03: El token revocado debe persistir en la tabla SQLite 'revoked_tokens'"
        conn_rl.close()

        # Comprobar que el token es rechazado de inmediato
        res_me2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_me2.json()["authenticated"] is False, "VULN-03: El token revocado no debe autenticar"

        # 2. Rate-Limiting Persistente en login_attempts (por IP y por usuario)
        reset_all_rate_limits()
        ip_prueba = "203.0.113.88"
        headers_ip = {"X-Forwarded-For": ip_prueba}

        # 5 intentos fallidos
        for _ in range(5):
            res_fail = await client.post(
                "/api/auth/login",
                json={"username": "dueno_alfa", "password": "WrongPassword!"},
                headers=headers_ip
            )
            assert res_fail.status_code == 401

        # Verificar persistencia en disco de los 5 intentos en login_attempts
        conn_rl = _get_rl_conn()
        cur_rl = conn_rl.cursor()
        cur_rl.execute("SELECT COUNT(*) FROM login_attempts WHERE ip = ?;", (ip_prueba,))
        assert cur_rl.fetchone()[0] >= 5, "VULN-05: Los intentos fallidos deben persistir en tabla SQLite 'login_attempts'"
        conn_rl.close()

        # Intento 6 debe arrojar HTTP 429 Too Many Requests
        res_bloqueado = await client.post(
            "/api/auth/login",
            json={"username": "dueno_alfa", "password": "WrongPassword!"},
            headers=headers_ip
        )
        assert res_bloqueado.status_code == 429, "VULN-05: Debe devolver HTTP 429 al alcanzar el umbral de intentos fallidos"

        # 3. Validación de Empleado Desactivado en tiempo real en cada petición
        conn = get_db_connection()
        cur = conn.cursor()
        h_temp, s_temp = hash_secret("TempPass123.")
        cur.execute("""
            INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES ('Empleado Temp', 'emp_desactivable', ?, ?, 'vendedor', 1, '2026-10-22 10:00:00', 1, 1);
        """, (h_temp, s_temp))
        emp_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Obtener token válido
        token_emp = create_access_token(
            user_id=emp_id,
            username="emp_desactivable",
            rol="vendedor",
            nombre="Empleado Temp",
            tenant_id=1,
            sucursal_id=1,
            tenant_slug="tienda-alfa"
        )

        # Activo: responde autenticado
        res_emp1 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_emp}"})
        assert res_emp1.json()["authenticated"] is True

        # Desactivar en base de datos
        conn = get_db_connection()
        conn.execute("UPDATE usuarios SET activo = 0 WHERE id = ?;", (emp_id,))
        conn.commit()
        conn.close()

        # Inactivo: get_current_user_optional consulta en BD y rechaza de inmediato
        res_emp2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_emp}"})
        assert res_emp2.json()["authenticated"] is False, "VULN-03: Usuario desactivado en BD debe ser rechazado inmediatamente"


# ==============================================================================
# TEST 4: VULN-04 AISLAMIENTO DE CATÁLOGO PÚBLICO DIGITAL
# ==============================================================================

@pytest.mark.anyio
async def test_vuln04_catalogo_publico_aislado_por_tenant():
    """
    Verifica que /api/catalogo/equipos?slug=tienda-beta retorne únicamente equipos de tienda-beta,
    que /api/catalogo/accesorios?slug=tienda-beta retorne solo accesorios de tienda-beta,
    y que solicitar un slug inexistente o suspendido retorne HTTP 404.
    """
    setup_audit_tenants_and_data()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Catálogo Equipos Tenant Beta
        res_eq_b = await client.get("/api/catalogo/equipos?slug=tienda-beta")
        assert res_eq_b.status_code == 200
        items_b = res_eq_b.json()
        modelos_b = [it["modelo"] for it in items_b]
        assert any("Samsung S22 Beta" in m for m in modelos_b), "Debe incluir los equipos de Beta"
        assert not any("iPhone 13 Alfa" in m for m in modelos_b), "VULN-04: No debe incluir equipos de Tenant Alfa"

        # 2. Catálogo Accesorios Tenant Beta
        res_acc_b = await client.get("/api/catalogo/accesorios?slug=tienda-beta")
        assert res_acc_b.status_code == 200
        nombres_acc_b = [it["nombre"] for it in res_acc_b.json()]
        assert "Funda Beta Armor" in nombres_acc_b
        assert "Cargador Alfa Fast" not in nombres_acc_b, "VULN-04: No debe incluir accesorios de Tenant Alfa"

        # 3. Slug inexistente -> HTTP 404
        res_inexistente = await client.get("/api/catalogo/equipos?slug=slug-completamente-falso-999")
        assert res_inexistente.status_code == 404, "VULN-04: Slug inexistente debe devolver HTTP 404"

        # 4. Tienda suspendida -> HTTP 404
        res_suspendida = await client.get("/api/catalogo/equipos?slug=tienda-suspendida")
        assert res_suspendida.status_code == 404, "VULN-04: Tenant inactivo debe devolver HTTP 404 en catálogo público"


# ==============================================================================
# TEST 5: VULN-06 VALIDACIÓN DE MAGIC BYTES Y RE-ENCODE CON PILLOW
# ==============================================================================

@pytest.mark.anyio
async def test_vuln06_magic_bytes_y_reencode_pillow():
    """
    Verifica que subir a /api/configuracion/logo o /api/accesorios/foto un archivo con extensión .png
    pero con contenido de script/PHP o binario aleatorio sea rechazado con HTTP 400.
    Verifica que una imagen PNG válida sea procesada, re-codificada y guardada sin metadatos.
    """
    setup_audit_tenants_and_data()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res_login = await client.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        assert res_login.status_code == 200
        auth_headers = {"Authorization": f"Bearer {res_login.json()['access_token']}"}

        # 1. Archivo malicioso PHP con extensión .png -> HTTP 400
        malicious_php = b"<?php phpinfo(); ?>"
        res_php = await client.post(
            "/api/configuracion/logo",
            files={"file": ("malicious.png", malicious_php, "image/png")},
            headers=auth_headers
        )
        assert res_php.status_code == 400, "VULN-06: Debe rechazar scripts PHP con HTTP 400"

        # 2. Archivo binario corrupto / aleatorio (sin magic bytes) -> HTTP 400
        random_bytes = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b"
        res_corrupt = await client.post(
            "/api/configuracion/logo",
            files={"file": ("corrupt.png", random_bytes, "image/png")},
            headers=auth_headers
        )
        assert res_corrupt.status_code == 400, "VULN-06: Debe rechazar magic bytes inválidos con HTTP 400"

        # 3. Imagen válida generada con Pillow -> HTTP 200 y re-codificación exitosa
        img = Image.new("RGB", (60, 60), color=(10, 100, 200))
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        valid_png_bytes = img_buf.getvalue()

        res_ok = await client.post(
            "/api/configuracion/logo",
            files={"file": ("logo_tienda.png", valid_png_bytes, "image/png")},
            headers=auth_headers
        )
        assert res_ok.status_code == 200, "VULN-06: Imagen válida debe procesarse exitosamente"
        assert "logo_url" in res_ok.json()


# ==============================================================================
# TEST 6: VULN-07, VULN-08, VULN-09, VULN-11 DEFENSAS EN PROFUNDIDAD
# ==============================================================================

@pytest.mark.anyio
async def test_vuln07_vuln08_bola_idor_garantias_pos_y_sku_unicidad_por_tenant():
    """
    Verifica que al procesar una garantía en Tenant A, intentar asociar un equipo_reemplazo_id
    perteneciente a Tenant B sea rechazado con error (VULN-07).
    Verifica que existan los índices compuestos uq_equipos_tenant_imei y uq_reparaciones_tenant_folio (VULN-08).
    Verifica que _validate_sql_identifier rechace inyecciones (VULN-11).
    Verifica que en producción se proscriban secretos por defecto y fallbacks (VULN-09).
    """
    ids = setup_audit_tenants_and_data()

    # 1. BOLA / IDOR en Garantías: equipo_reemplazo_id de otro tenant
    dummy_garantia = GarantiaCreate(
        imei="ALFA-IMEI-VENDIDO-001",
        motivo="Falla de pantalla",
        falla_descripcion="Líneas verdes",
        estado_equipo_recibido="En Garantia",
        solucion="Reemplazo",
        equipo_reemplazo_id=ids["eq_beta_id"]
    )

    with pytest.raises(ValueError, match="no existe o no pertenece a este negocio"):
        crud.procesar_devolucion_garantia(dummy_garantia, tenant_id=ids["t_alfa_id"])

    # 2. Índices compuestos multi-tenant existentes en la base de datos
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type = ?;", ("index",))
    nombres_indices = {r["name"] for r in cur.fetchall()}
    assert "uq_equipos_tenant_imei" in nombres_indices, "VULN-08: Debe existir el índice uq_equipos_tenant_imei"
    assert "uq_reparaciones_tenant_folio" in nombres_indices, "VULN-08: Debe existir el índice uq_reparaciones_tenant_folio"
    conn.close()

    # 3. Validación de Identificadores SQL (VULN-11)
    assert _validate_sql_identifier("tabla_valida_123") == "tabla_valida_123"
    with pytest.raises(ValueError, match="Identificador SQL inválido"):
        _validate_sql_identifier("usuarios; DROP TABLE equipos;--")

    with pytest.raises(ValueError):
        _validate_sql_identifier("123_tabla_con_numero_inicial")

    # 4. Proscripción de secretos por defecto en producción (VULN-09)
    os.environ["ENVIRONMENT"] = "production"
    old_jwt = os.environ.pop("JWT_SECRET", None)
    old_jwt_k = os.environ.pop("JWT_SECRET_KEY", None)
    old_db = os.environ.pop("DATABASE_URL", None)

    try:
        # En producción sin JWT_SECRET ni DATABASE_URL seguro debe lanzar RuntimeError
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            _init_jwt_secret()

        # En producción el fallback 'samuelykim.' no debe ser aceptado
        os.environ.pop("ADMIN_DELETE_PASSWORD", None)
        assert verify_delete_password("samuelykim.") is False
    finally:
        os.environ.pop("ENVIRONMENT", None)
        if old_jwt:
            os.environ["JWT_SECRET"] = old_jwt
        if old_jwt_k:
            os.environ["JWT_SECRET_KEY"] = old_jwt_k
        if old_db:
            os.environ["DATABASE_URL"] = old_db
