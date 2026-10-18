"""
test_seguridad_rbac.py - Suite de pruebas automatizadas de seguridad, RBAC y anti-fuga en F12.
Verifica:
1. Login por PIN y contraseña con emisión de cookie HttpOnly.
2. Rate-limiting contra ataques de fuerza bruta (bloqueo tras 5 intentos fallidos con HTTP 429).
3. Ocultamiento garantizado en backend de costo_compra y márgenes para perfil de vendedor.
4. Entrega completa de costos e indicadores financieros para perfil de dueño.
5. Bloqueo estricto con HTTP 403 / 401 en endpoints administrativos (reportes de ventas y backups).
6. Cierre de sesión y revocación de cookie.
"""

import os
import time
import pytest
import httpx
from app.main import app
from app.database import init_db, seed_demo_data_if_empty
from app.security import reset_all_rate_limits

init_db()
seed_demo_data_if_empty()

ADMIN_PASSWORD = os.environ.get("ADMIN_DELETE_PASSWORD", "piso6bodega606.")

@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Limpia los contadores de intentos fallidos antes de cada test."""
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()


@pytest.mark.anyio
async def test_login_vendedor_con_pin():
    """El vendedor puede autenticarse de manera ultrarrápida usando su PIN de 4 dígitos."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/auth/login", json={"pin": "1234"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["user"]["rol"] == "vendedor"
        assert "sid" in client.cookies

        # Verificar /api/auth/me
        res_me = await client.get("/api/auth/me")
        assert res_me.status_code == 200
        me = res_me.json()
        assert me["authenticated"] is True
        assert me["user"]["rol"] == "vendedor"


@pytest.mark.anyio
async def test_login_dueno_con_credenciales():
    """El dueño se autentica con sus credenciales de administrador."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["user"]["rol"] == "dueno"
        assert "sid" in client.cookies

        # Verificar /api/auth/me
        res_me = await client.get("/api/auth/me")
        assert res_me.status_code == 200
        assert res_me.json()["user"]["rol"] == "dueno"


@pytest.mark.anyio
async def test_rate_limiting_fuerza_bruta():
    """Tras 5 intentos fallidos consecutivos, el sistema bloquea con HTTP 429."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 5 intentos fallidos
        for i in range(5):
            res_fail = await client.post("/api/auth/login", json={"pin": f"999{i}"})
            assert res_fail.status_code == 401

        # El 6to intento debe ser rechazado inmediatamente con HTTP 429 Too Many Requests
        res_bloqueado = await client.post("/api/auth/login", json={"pin": "1234"})
        assert res_bloqueado.status_code == 429
        assert "bloqueado" in res_bloqueado.json()["detail"].lower()


@pytest.mark.anyio
async def test_anti_fuga_f12_equipos_vendedor():
    """
    PRUEBA CRÍTICA DE SEGURIDAD (Claude Hallazgo #1):
    Un vendedor que inspeccione la red o modifique el DOM jamás recibe
    costo_compra ni margen_proyectado en el JSON de /api/equipos.
    """
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Login como vendedor
        await client.post("/api/auth/login", json={"pin": "1234"})

        # Consultar inventario
        res = await client.get("/api/equipos?solo_disponibles=true")
        assert res.status_code == 200
        equipos = res.json()
        assert len(equipos) > 0

        for eq in equipos:
            assert eq["costo_compra"] is None, f"Fuga de costo_compra detectada en equipo {eq['id']}"
            assert eq["margen_proyectado"] is None, f"Fuga de margen detectada en equipo {eq['id']}"
            assert eq["porcentaje_margen"] is None
            # El precio de venta sí debe estar visible para poder cobrar
            assert eq["precio_venta"] > 0


@pytest.mark.anyio
async def test_dueno_recibe_costos_completos():
    """El dueño autenticado sí recibe todos los costos y cálculos de margen."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Login como dueño
        await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})

        res = await client.get("/api/equipos?solo_disponibles=true")
        assert res.status_code == 200
        equipos = res.json()
        assert len(equipos) > 0

        # Verificar que al menos los equipos con costo registrado lo devuelvan
        equipos_con_costo = [e for e in equipos if e["costo_compra"] is not None]
        assert len(equipos_con_costo) > 0
        for eq in equipos_con_costo:
            assert eq["costo_compra"] > 0
            assert eq["margen_proyectado"] is not None


@pytest.mark.anyio
async def test_vendedor_bloqueado_reportes_ventas():
    """Un vendedor que intente acceder a /api/reportes/ventas es bloqueado con HTTP 403."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Login como vendedor
        await client.post("/api/auth/login", json={"pin": "1234"})

        res = await client.get("/api/reportes/ventas")
        assert res.status_code == 403
        assert "permisos de dueño" in res.json()["detail"].lower()


@pytest.mark.anyio
async def test_dueno_accede_reportes_ventas():
    """El dueño sí puede consultar el historial completo de ventas con ganancias."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})

        res = await client.get("/api/reportes/ventas")
        assert res.status_code == 200
        ventas = res.json()
        assert isinstance(ventas, list)


@pytest.mark.anyio
async def test_dashboard_sanitizado_para_vendedor():
    """
    El dashboard muestra el contador de stock al vendedor,
    pero oculta totalmente ganancias, capital y ventas diarias.
    """
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"pin": "1234"})

        res = await client.get("/api/reportes/dashboard")
        assert res.status_code == 200
        dash = res.json()

        # Datos seguros públicos
        assert dash["equipos_disponibles"] >= 0
        assert dash["mes_actual_nombre"] is not None

        # Datos financieros confidenciales estrictamente nulos
        assert dash["total_ganancias_mes"] is None
        assert dash["capital_inventario"] is None
        assert dash["total_ventas_mes"] is None
        assert dash["ventas_por_dia"] == []


@pytest.mark.anyio
async def test_backups_restringidos_solo_dueno():
    """Los endpoints de backup /api/backup/* exigen sesión de dueño."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Sin autenticar: HTTP 401
        res_anon = await client.get("/api/backup/exportar-json")
        assert res_anon.status_code == 401

        # 2. Vendedor: HTTP 403
        await client.post("/api/auth/login", json={"pin": "1234"})
        res_vendedor = await client.get("/api/backup/exportar-json")
        assert res_vendedor.status_code == 403

        # 3. Dueño: HTTP 200
        await client.post("/api/auth/logout")
        await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        res_dueno = await client.get("/api/backup/exportar-json")
        assert res_dueno.status_code == 200


@pytest.mark.anyio
async def test_logout_cierra_sesion():
    """El logout elimina la cookie y restablece el estado a no autenticado."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"pin": "1234"})
        assert (await client.get("/api/auth/me")).json()["authenticated"] is True

        res_logout = await client.post("/api/auth/logout")
        assert res_logout.status_code == 200

        res_me = await client.get("/api/auth/me")
        assert res_me.json()["authenticated"] is False
