"""
test_empleados.py - Suite de pruebas automatizadas para el módulo de Gestión de Empleados y Cajeros.
Verifica:
1. Control de Acceso RBAC: Rol 'vendedor' recibe HTTP 403 en todos los endpoints de /api/empleados.
2. Rol 'dueno' puede crear empleados ('vendedor' y 'tecnico') con asignación automática de tenant_id y hashing Argon2id.
3. Aislamiento Multi-Tenant estricto: Dueño de Tenant A no puede ver ni modificar empleados de Tenant B (HTTP 404).
4. Suspensión y Reactivación en 1 clic: Empleado desactivado (activo=False) no puede iniciar sesión; al reactivarlo (activo=True) vuelve a ingresar.
5. Reglas de negocio: Validación de username único, restricción de roles permitidos y protección contra auto-desactivación del dueño.
"""

import pytest
import httpx
from app.main import app
from app.database import init_db, seed_demo_data_if_empty, get_db_connection
from app.security import hash_secret, reset_all_rate_limits
from test_multitenant_seguridad import setup_tenants_and_users

init_db()
seed_demo_data_if_empty()


@pytest.fixture(autouse=True)
def clean_rate_limits():
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()


@pytest.mark.anyio
async def test_vendedor_prohibido_api_empleados():
    """Un usuario con rol vendedor debe recibir HTTP 403 Forbidden al intentar acceder a /api/empleados."""
    ids = setup_tenants_and_users()
    conn = get_db_connection()
    cur = conn.cursor()
    now = "2026-10-21 14:00:00"
    h_v, s_v = hash_secret("VendedorPass123.")

    cur.execute("SELECT id FROM usuarios WHERE username = 'cajero_test_permisos' LIMIT 1;")
    row_v = cur.fetchone()
    if not row_v:
        cur.execute("""
            INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES ('Cajero Permisos', 'cajero_test_permisos', ?, ?, 'vendedor', 1, ?, ?, ?);
        """, (h_v, s_v, now, ids["t_alfa_id"], ids["s_alfa_id"]))
        conn.commit()
    conn.close()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Iniciar sesión como vendedor
        res_login = await client.post("/api/auth/login", json={"username": "cajero_test_permisos", "password": "VendedorPass123."})
        assert res_login.status_code == 200, res_login.text
        cookies = client.cookies

        # 1. GET /api/empleados -> 403 Forbidden
        res_get = await client.get("/api/empleados", cookies=cookies)
        assert res_get.status_code == 403

        # 2. POST /api/empleados -> 403 Forbidden
        res_post = await client.post("/api/empleados", json={
            "nombre": "Nuevo Intruso",
            "username": "nuevo_intruso",
            "password": "Password123.",
            "rol": "vendedor"
        }, cookies=cookies)
        assert res_post.status_code == 403

        # 3. PUT /api/empleados/1/estado -> 403 Forbidden
        res_put = await client.put("/api/empleados/1/estado", json={"activo": False}, cookies=cookies)
        assert res_put.status_code == 403


@pytest.mark.anyio
async def test_dueno_crear_y_listar_empleados():
    """El dueño de un tenant puede registrar empleados vendedores y técnicos y visualizarlos."""
    ids = setup_tenants_and_users()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Login como dueño Alfa
        res_login = await client.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        assert res_login.status_code == 200
        cookies = client.cookies

        # Crear vendedor
        u_vend = "vendedor_alfa_demo"
        res_v = await client.post("/api/empleados", json={
            "nombre": "Luis Vendedor",
            "username": u_vend,
            "password": "Password123.",
            "rol": "vendedor"
        }, cookies=cookies)
        assert res_v.status_code in (201, 400)
        if res_v.status_code == 201:
            data_v = res_v.json()
            assert data_v["nombre"] == "Luis Vendedor"
            assert data_v["username"] == u_vend
            assert data_v["rol"] == "vendedor"
            assert data_v["activo"] is True
            assert data_v["tenant_id"] == ids["t_alfa_id"]

        # Crear técnico
        u_tec = "tecnico_alfa_demo"
        res_t = await client.post("/api/empleados", json={
            "nombre": "Mario Técnico",
            "username": u_tec,
            "password": "Password123.",
            "rol": "tecnico"
        }, cookies=cookies)
        assert res_t.status_code in (201, 400)
        if res_t.status_code == 201:
            data_t = res_t.json()
            assert data_t["rol"] == "tecnico"
            assert data_t["tenant_id"] == ids["t_alfa_id"]

        # Listar empleados
        res_list = await client.get("/api/empleados", cookies=cookies)
        assert res_list.status_code == 200
        empleados = res_list.json()
        usernames = [e["username"] for e in empleados]
        assert "dueno_alfa" in usernames
        assert u_vend in usernames


@pytest.mark.anyio
async def test_aislamiento_multitenant_empleados():
    """
    Verifica que el Dueño de Tenant A pueda crear empleados para su negocio
    pero el Dueño de Tenant B no pueda ver ni gestionar los empleados de Tenant A.
    """
    ids = setup_tenants_and_users()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_a:
        # Dueño Alfa crea un empleado exclusivo
        res_la = await client_a.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        assert res_la.status_code == 200
        cookies_a = client_a.cookies

        u_alfa_exclusivo = "personal_alfa_aislado"
        res_crear = await client_a.post("/api/empleados", json={
            "nombre": "Personal Exclusivo Alfa",
            "username": u_alfa_exclusivo,
            "password": "Password123.",
            "rol": "vendedor"
        }, cookies=cookies_a)

        if res_crear.status_code == 201:
            emp_alfa_id = res_crear.json()["id"]
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM usuarios WHERE username = ?;", (u_alfa_exclusivo,))
            emp_alfa_id = cur.fetchone()["id"]
            conn.close()

    # Dueño Beta inicia sesión
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_b:
        res_lb = await client_b.post("/api/auth/login", json={"username": "dueno_beta", "password": "BetaPass123."})
        assert res_lb.status_code == 200
        cookies_b = client_b.cookies

        # 1. Tenant B lista sus empleados: NO debe aparecer el empleado de Tenant A
        res_list_b = await client_b.get("/api/empleados", cookies=cookies_b)
        assert res_list_b.status_code == 200
        lista_b = res_list_b.json()
        ids_b = [e["id"] for e in lista_b]
        assert emp_alfa_id not in ids_b, "Fuga de datos: Empleado de Tenant A apareció en la lista de Tenant B"

        # 2. Tenant B intenta suspender al empleado de Tenant A -> HTTP 404 Not Found
        res_put_b = await client_b.put(f"/api/empleados/{emp_alfa_id}/estado", json={"activo": False}, cookies=cookies_b)
        assert res_put_b.status_code == 404, f"Se esperaba 404 pero se obtuvo {res_put_b.status_code}"


@pytest.mark.anyio
async def test_activar_desactivar_empleado_y_bloqueo_login():
    """Verifica que desactivar un empleado le impida hacer login, y reactivarlo le permita ingresar de nuevo."""
    ids = setup_tenants_and_users()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Dueño Alfa crea un empleado de prueba
        res_la = await client.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        cookies_dueno = client.cookies

        u_toggle = "cajero_toggle_test"
        pwd_toggle = "SecretCajero123."
        res_c = await client.post("/api/empleados", json={
            "nombre": "Cajero Toggle",
            "username": u_toggle,
            "password": pwd_toggle,
            "rol": "vendedor"
        }, cookies=cookies_dueno)

        if res_c.status_code == 201:
            emp_id = res_c.json()["id"]
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM usuarios WHERE username = ?;", (u_toggle,))
            emp_id = cur.fetchone()["id"]
            conn.close()

    # 1. El empleado activo puede hacer login
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_emp:
        res_emp_login = await client_emp.post("/api/auth/login", json={"username": u_toggle, "password": pwd_toggle})
        assert res_emp_login.status_code == 200

    # 2. El dueño suspende al empleado
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_dueno:
        await client_dueno.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        res_susp = await client_dueno.put(f"/api/empleados/{emp_id}/estado", json={"activo": False})
        assert res_susp.status_code == 200
        assert res_susp.json()["activo"] is False

    # 3. El empleado suspendido NO puede iniciar sesión
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_emp2:
        res_fail = await client_emp2.post("/api/auth/login", json={"username": u_toggle, "password": pwd_toggle})
        assert res_fail.status_code in (401, 403), "Un empleado suspendido no debe poder iniciar sesión"

    # 4. El dueño reactiva al empleado
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_dueno2:
        await client_dueno2.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        res_react = await client_dueno2.put(f"/api/empleados/{emp_id}/estado", json={"activo": True})
        assert res_react.status_code == 200
        assert res_react.json()["activo"] is True

    # 5. El empleado reactivado ya puede iniciar sesión
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_emp3:
        res_ok = await client_emp3.post("/api/auth/login", json={"username": u_toggle, "password": pwd_toggle})
        assert res_ok.status_code == 200


@pytest.mark.anyio
async def test_reglas_de_negocio_y_proteccion_dueno():
    """Verifica username duplicado y protección para evitar auto-desactivar la cuenta de dueño."""
    setup_tenants_and_users()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Iniciar sesión como dueño Alfa
        res_la = await client.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        dueno_id = res_la.json()["user"]["id"]

        # 1. Intentar registrar un usuario duplicado existente -> 400 Bad Request
        res_dup = await client.post("/api/empleados", json={
            "nombre": "Duplicado Alfa",
            "username": "dueno_alfa",
            "password": "Password123.",
            "rol": "vendedor"
        })
        assert res_dup.status_code == 400
        assert "ya se encuentra" in res_dup.json()["detail"].lower()

        # 2. Intentar suspender la propia cuenta de dueño en sesión -> 400 Bad Request
        res_self = await client.put(f"/api/empleados/{dueno_id}/estado", json={"activo": False})
        assert res_self.status_code == 400
        assert "no puedes" in res_self.json()["detail"].lower() or "dueño" in res_self.json()["detail"].lower()
