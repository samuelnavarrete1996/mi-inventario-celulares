"""
test_cli_y_despliegue.py - Pruebas Automatizadas para CLI de Aprovisionamiento y Despliegue en Render / Cloud.
Verifica:
1. El comando CLI `crear-tienda` registra exitosamente tenant, sucursal matriz, configuración inicial y usuario dueño.
2. La contraseña del nuevo dueño se almacena de forma segura con Argon2id/PBKDF2 y permite autenticación en /api/auth/login.
3. El CLI bloquea la creación de tiendas con slugs duplicados o nombres de usuario duplicados.
4. El comando `listar-tiendas` lista los tenants existentes.
5. El endpoint de monitoreo cloud `/healthz` responde HTTP 200 con status 'ok' y conectividad a base de datos.
"""

import sys
import pytest
import httpx
from app.main import app
from app.database import init_db, get_db_connection
from app.security import verify_secret, reset_all_rate_limits
from app.cli import crear_tienda, listar_tiendas, main as cli_main

init_db()

@pytest.fixture(autouse=True)
def clean_rate_limits():
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()


@pytest.mark.anyio
async def test_endpoint_healthz_despliegue():
    """El endpoint /healthz debe responder HTTP 200 y reportar el estado de la BD y motor activo."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/healthz")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"
        assert data["engine"] in ("postgresql", "sqlite")


@pytest.mark.anyio
async def test_cli_crear_tienda_exitoso_y_login():
    """El CLI crear-tienda debe dar de alta todas las entidades maestras y permitir login inmediato."""
    unique_slug = "cli-test-store"
    admin_user = "cli_dueno_test"
    admin_pass = "ClaveSecreta2026."

    # Limpieza previa por si existe de corridas anteriores
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM usuarios WHERE username = ?;", (admin_user,))
        cur.execute("DELETE FROM sucursales WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = ?);", (unique_slug,))
        cur.execute("DELETE FROM configuracion_tienda WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = ?);", (unique_slug,))
        cur.execute("DELETE FROM tenants WHERE slug = ?;", (unique_slug,))
        conn.commit()
    finally:
        conn.close()

    # 1. Crear tienda vía función CLI
    res = crear_tienda(
        nombre="Store CLI Testing",
        slug=unique_slug,
        admin=admin_user,
        password=admin_pass,
        email="cli_test@store.com",
        telefono="5588776655",
        direccion="Av. Principal #999",
        plan="pro"
    )

    assert res["tenant_id"] is not None
    assert res["slug"] == unique_slug
    assert res["nombre_comercial"] == "Store CLI Testing"
    assert res["plan"] == "pro"
    assert res["activo"] is True
    assert res["sucursal_id"] is not None
    assert res["user_id"] is not None

    # 2. Verificar persistencia en base de datos
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Verificar tenant
        cur.execute("SELECT * FROM tenants WHERE id = ?;", (res["tenant_id"],))
        t_row = cur.fetchone()
        assert t_row is not None
        assert t_row["slug"] == unique_slug
        assert t_row["plan"] == "pro"

        # Verificar sucursal matriz
        cur.execute("SELECT * FROM sucursales WHERE tenant_id = ? AND es_matriz = 1;", (res["tenant_id"],))
        s_row = cur.fetchone()
        assert s_row is not None
        assert s_row["id"] == res["sucursal_id"]

        # Verificar configuracion_tienda
        cur.execute("SELECT * FROM configuracion_tienda WHERE tenant_id = ?;", (res["tenant_id"],))
        c_row = cur.fetchone()
        assert c_row is not None
        assert "Store CLI Testing" in c_row["encabezado_ticket"]

        # Verificar usuario dueno y hash
        cur.execute("SELECT * FROM usuarios WHERE id = ?;", (res["user_id"],))
        u_row = cur.fetchone()
        assert u_row is not None
        assert u_row["username"] == admin_user
        assert u_row["rol"] == "dueno"
        assert u_row["tenant_id"] == res["tenant_id"]
        assert u_row["sucursal_id"] == res["sucursal_id"]
        assert verify_secret(admin_pass, u_row["pin_hash"], u_row["salt"]) is True
    finally:
        conn.close()

    # 3. Validar login HTTP del nuevo dueño
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        login_res = await client.post("/api/auth/login", json={
            "username": admin_user,
            "password": admin_pass
        })
        assert login_res.status_code == 200
        auth_data = login_res.json()
        assert auth_data["success"] is True
        assert auth_data["user"]["tenant_id"] == res["tenant_id"]
        assert auth_data["user"]["rol"] == "dueno"
        assert auth_data["user"]["tenant_slug"] == unique_slug

        # Validar verificación de sesión con la cookie obtenida
        me_res = await client.get("/api/auth/me")
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["authenticated"] is True
        assert me_data["user"]["username"] == admin_user


def test_cli_rechazo_slug_duplicado():
    """El CLI debe lanzar error si se intenta registrar un slug ya existente."""
    with pytest.raises(ValueError) as exc:
        crear_tienda(
            nombre="Tienda Duplicada",
            slug="demo-celulares", # Slug de demostración ya existente
            admin="dueno_intruso",
            password="Password123."
        )
    assert "ya está registrado" in str(exc.value)


def test_cli_rechazo_admin_duplicado():
    """El CLI debe lanzar error si el username de admin ya existe en otro tenant."""
    unique_slug = "store-unique-slug-99"
    # Asegurar que el slug no exista
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tenants WHERE slug = ?;", (unique_slug,))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError) as exc:
        crear_tienda(
            nombre="Tienda Con Admin Duplicado",
            slug=unique_slug,
            admin="admin", # Usuario admin principal ya existente
            password="Password123."
        )
    assert "ya se encuentra en uso" in str(exc.value)


def test_cli_listar_tiendas():
    """La función listar_tiendas debe retornar al menos un tenant registrado."""
    tiendas = listar_tiendas()
    assert isinstance(tiendas, list)
    assert len(tiendas) >= 1
    slugs = [t["slug"] for t in tiendas]
    assert "demo-celulares" in slugs


def test_cli_main_argumentos_y_help(capsys):
    """El entrypoint main() del CLI debe procesar flags correctamente."""
    with pytest.raises(SystemExit) as exc:
        cli_main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "crear-tienda" in captured.out
    assert "listar-tiendas" in captured.out

    # Invocar sin argumentos debe mostrar ayuda y retornar 0 sin excepción
    code_no_args = cli_main([])
    assert code_no_args == 0
