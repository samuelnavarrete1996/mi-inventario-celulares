"""
test_configuracion_y_tickets.py - Pruebas automatizadas para Marca Blanca (White-Label) y Configuración Multi-Tenant.
Verifica:
1. Dueño de Tenant A actualiza su configuración general (nombre comercial, teléfono, dirección, encabezado y políticas de ticket).
2. Dueño de Tenant A sube su logotipo exitosamente (validación MIME y tamaño).
3. Usuario con rol 'vendedor' no puede modificar la configuración ni subir logotipo (HTTP 403 Forbidden).
4. Aislamiento multi-tenant: Dueño de Tenant A no puede modificar ni consultar datos de Tenant B (aislado por token/sesión).
5. Validación de errores: Archivos no permitidos (MIME/extensión) y tamaño superior a 2 MB son rechazados con 400 / 413.
6. Endpoint público de configuración para Marca Blanca en el catálogo web.
"""

import os
import io
import time
import pytest
import httpx
from app.main import app
from app.database import get_db_connection, init_db, seed_demo_data_if_empty
from app.security import hash_secret, reset_all_rate_limits

init_db()
seed_demo_data_if_empty()

@pytest.fixture(autouse=True)
def clean_rate_limits():
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()

def setup_tenants_and_users_config():
    conn = get_db_connection()
    cur = conn.cursor()
    now = "2026-10-21 12:00:00"

    try:
        # 1. Tenant Alfa
        cur.execute("SELECT id FROM tenants WHERE slug = 'alfa-config' LIMIT 1;")
        row_a = cur.fetchone()
        if not row_a:
            cur.execute("""
                INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
                VALUES ('Tienda Alfa Original', 'alfa-config', 'alfa@cfg.com', '5511223344', 'pro', 1, ?);
            """, (now,))
            t_alfa_id = cur.lastrowid
            cur.execute("""
                INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
                VALUES (?, 'Alfa Matriz', 'Calle Alfa 1', '5511223344', 1, ?);
            """, (t_alfa_id, now))
            s_alfa_id = cur.lastrowid
        else:
            t_alfa_id = row_a["id"]
            cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_alfa_id,))
            s_alfa_id = cur.fetchone()["id"]

        # 2. Tenant Beta
        cur.execute("SELECT id FROM tenants WHERE slug = 'beta-config' LIMIT 1;")
        row_b = cur.fetchone()
        if not row_b:
            cur.execute("""
                INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
                VALUES ('Tienda Beta Original', 'beta-config', 'beta@cfg.com', '5522334455', 'starter', 1, ?);
            """, (now,))
            t_beta_id = cur.lastrowid
            cur.execute("""
                INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
                VALUES (?, 'Beta Matriz', 'Calle Beta 2', '5522334455', 1, ?);
            """, (t_beta_id, now))
            s_beta_id = cur.lastrowid
        else:
            t_beta_id = row_b["id"]
            cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_beta_id,))
            s_beta_id = cur.fetchone()["id"]

        # Usuarios
        h_a, s_a = hash_secret("AlfaDueño123.")
        h_v, s_v = hash_secret("AlfaVendedor123.")
        h_b, s_b = hash_secret("BetaDueño123.")

        cur.execute("SELECT id FROM usuarios WHERE username = 'dueno_alfa_cfg' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
                VALUES ('Dueño Alfa', 'dueno_alfa_cfg', ?, ?, 'dueno', 1, ?, ?, ?);
            """, (h_a, s_a, now, t_alfa_id, s_alfa_id))

        cur.execute("SELECT id FROM usuarios WHERE username = 'vend_alfa_cfg' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
                VALUES ('Vendedor Alfa', 'vend_alfa_cfg', ?, ?, 'vendedor', 1, ?, ?, ?);
            """, (h_v, s_v, now, t_alfa_id, s_alfa_id))

        cur.execute("SELECT id FROM usuarios WHERE username = 'dueno_beta_cfg' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
                VALUES ('Dueño Beta', 'dueno_beta_cfg', ?, ?, 'dueno', 1, ?, ?, ?);
            """, (h_b, s_b, now, t_beta_id, s_beta_id))

        conn.commit()
    finally:
        conn.close()

    return {
        "t_alfa_id": t_alfa_id,
        "s_alfa_id": s_alfa_id,
        "t_beta_id": t_beta_id,
        "s_beta_id": s_beta_id
    }


@pytest.mark.anyio
async def test_obtener_y_actualizar_configuracion_dueno():
    """El dueño de Tenant A actualiza su configuración general y de tickets exitosamente."""
    ids = setup_tenants_and_users_config()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Login como dueño Alfa
        login_res = await client.post("/api/auth/login", json={"username": "dueno_alfa_cfg", "password": "AlfaDueño123."})
        assert login_res.status_code == 200

        # Obtener configuración actual
        get_res = await client.get("/api/configuracion")
        assert get_res.status_code == 200
        cfg = get_res.json()
        assert cfg["tenant_id"] == ids["t_alfa_id"]
        assert cfg["slug"] == "alfa-config"

        # Actualizar datos
        payload_update = {
            "nombre_comercial": "Alfa Celulares Pro & Taller",
            "telefono": "5599887766",
            "whatsapp_notificaciones": "5215599887766",
            "direccion": "Av. Insurgentes Sur 1234, CDMX",
            "encabezado_ticket": "ALFA CELULARES PRO | Servicio Técnico Certificado",
            "pie_ticket_garantia": "Garantía de 90 días en mano de obra y piezas originales."
        }
        put_res = await client.put("/api/configuracion", json=payload_update)
        assert put_res.status_code == 200
        data_up = put_res.json()
        assert data_up["nombre_comercial"] == "Alfa Celulares Pro & Taller"
        assert data_up["direccion"] == "Av. Insurgentes Sur 1234, CDMX"
        assert data_up["encabezado_ticket"] == "ALFA CELULARES PRO | Servicio Técnico Certificado"
        assert data_up["pie_ticket_garantia"] == "Garantía de 90 días en mano de obra y piezas originales."


@pytest.mark.anyio
async def test_subida_logotipo_tienda_y_validaciones():
    """Validar subida de logo con formato correcto y rechazo de tipos no permitidos o tamaños excesivos."""
    setup_tenants_and_users_config()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"username": "dueno_alfa_cfg", "password": "AlfaDueño123."})

        # 1. Subida válida de PNG
        fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        files = {"file": ("logo_tienda.png", io.BytesIO(fake_png), "image/png")}
        res_upload = await client.post("/api/configuracion/logo", files=files)
        assert res_upload.status_code == 200
        data_logo = res_upload.json()
        assert "logo_url" in data_logo
        assert "logo.png" in data_logo["logo_url"]

        # 2. Rechazo de tipo MIME inválido (.exe o .txt)
        bad_files = {"file": ("script.sh", io.BytesIO(b"echo hack"), "text/plain")}
        res_bad = await client.post("/api/configuracion/logo", files=bad_files)
        assert res_bad.status_code == 400

        # 3. Rechazo de archivo superior a 2 MB
        huge_bytes = b"0" * (2 * 1024 * 1024 + 100)
        huge_files = {"file": ("huge.png", io.BytesIO(huge_bytes), "image/png")}
        res_huge = await client.post("/api/configuracion/logo", files=huge_files)
        assert res_huge.status_code == 413


@pytest.mark.anyio
async def test_bloqueo_a_rol_vendedor():
    """Un usuario con rol 'vendedor' no tiene permiso para modificar configuración ni subir logo (HTTP 403)."""
    setup_tenants_and_users_config()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Login como vendedor
        await client.post("/api/auth/login", json={"username": "vend_alfa_cfg", "password": "AlfaVendedor123."})

        # Intento de PUT /api/configuracion -> HTTP 403
        res_put = await client.put("/api/configuracion", json={"nombre_comercial": "Hacked Name"})
        assert res_put.status_code == 403

        # Intento de POST /api/configuracion/logo -> HTTP 403
        fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        files = {"file": ("logo.png", io.BytesIO(fake_png), "image/png")}
        res_logo = await client.post("/api/configuracion/logo", files=files)
        assert res_logo.status_code == 403


@pytest.mark.anyio
async def test_aislamiento_configuracion_entre_tenants():
    """Dueño de Tenant A no afecta la configuración de Tenant B, y viceversa."""
    ids = setup_tenants_and_users_config()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_b:
        # Login como Dueño Beta
        await client_b.post("/api/auth/login", json={"username": "dueno_beta_cfg", "password": "BetaDueño123."})

        # Configuración inicial de Beta
        cfg_b = (await client_b.get("/api/configuracion")).json()
        assert cfg_b["tenant_id"] == ids["t_beta_id"]
        assert cfg_b["nombre_comercial"] == "Tienda Beta Original"

        # Beta actualiza sus datos
        await client_b.put("/api/configuracion", json={
            "nombre_comercial": "Beta Motors & Mobiles",
            "encabezado_ticket": "TICKET EXCLUSIVO BETA"
        })

    # Verificar que Tenant Alfa mantiene sus propios datos sin alterarse
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_a:
        await client_a.post("/api/auth/login", json={"username": "dueno_alfa_cfg", "password": "AlfaDueño123."})
        cfg_a = (await client_a.get("/api/configuracion")).json()
        assert cfg_a["tenant_id"] == ids["t_alfa_id"]
        assert cfg_a["nombre_comercial"] != "Beta Motors & Mobiles"
        assert cfg_a["encabezado_ticket"] != "TICKET EXCLUSIVO BETA"


@pytest.mark.anyio
async def test_endpoint_publico_marca_blanca_catalogo():
    """El endpoint público /api/configuracion/publica devuelve la configuración adecuada sin requerir token."""
    setup_tenants_and_users_config()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Consultar por slug de Alfa
        res = await client.get("/api/configuracion/publica?slug=alfa-config")
        assert res.status_code == 200
        data = res.json()
        assert data["slug"] == "alfa-config"
        assert "logo_url" in data
        assert "whatsapp_notificaciones" in data
