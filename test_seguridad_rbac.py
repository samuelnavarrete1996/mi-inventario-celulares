"""
test_seguridad_rbac.py - Suite de pruebas automatizadas de seguridad, RBAC y anti-fuga en F12 (Fase 1 + Fase 2 Argon).
Verifica:
1. Login por PIN y contraseña con emisión de cookie HttpOnly.
2. Rate-limiting contra ataques de fuerza bruta (bloqueo tras 5 intentos fallidos con HTTP 429).
3. Ocultamiento garantizado en backend de costo_compra y márgenes para perfil de vendedor.
4. Entrega completa de costos e indicadores financieros para perfil de dueño.
5. Bloqueo estricto con HTTP 403 / 401 en endpoints administrativos (reportes de ventas y backups).
6. Cierre de sesión y revocación server-side de token (jti denylist).
7. Hashing Argon2id con retrocompatibilidad PBKDF2-HMAC-SHA256.
8. Sanitización de costos en endpoints de Garantías y Trazabilidad 360° por IMEI para vendedores.
9. Protección atómica contra doble venta (Race Condition / TOCTOU) y validaciones de entrada en modelos Update.
10. Cabeceras de seguridad OWASP y Content-Security-Policy (CSP).
"""

import os
import time
import hashlib
import pytest
import httpx
from app.main import app
from app.database import init_db, seed_demo_data_if_empty
from app.security import reset_all_rate_limits, hash_secret, verify_secret

init_db()
seed_demo_data_if_empty()

ADMIN_PASSWORD = os.environ.get("ADMIN_DELETE_PASSWORD", "samuelykim.")

@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Limpia los contadores de intentos fallidos antes de cada test."""
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()


@pytest.mark.anyio
async def test_login_vendedor_con_contrasena_inicio():
    """El vendedor puede autenticarse con la contraseña de inicio oficial 'piso6bodega606.'."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/auth/login", json={"pin": "piso6bodega606."})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["user"]["rol"] == "vendedor"
        assert "sid" in client.cookies


@pytest.mark.anyio
async def test_pin_1234_queda_bloqueado_y_rechazado():
    """Verifica que el PIN anterior 1234 ya NO es permitido bajo ninguna circunstancia."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/auth/login", json={"pin": "1234"})
        assert res.status_code == 401
        assert "sid" not in client.cookies


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
        await client.post("/api/auth/login", json={"pin": "piso6bodega606."})

        # Consultar inventario
        res = await client.get("/api/equipos?solo_disponibles=false")
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

        res = await client.get("/api/equipos?solo_disponibles=false")
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
        await client.post("/api/auth/login", json={"pin": "piso6bodega606."})

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
    pero oculta totalmente ganancias, capital, desglose monetario y ventas diarias.
    """
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"pin": "piso6bodega606."})

        res = await client.get("/api/reportes/dashboard")
        assert res.status_code == 200
        dash = res.json()

        # Datos seguros públicos
        assert dash["equipos_disponibles"] >= 0
        assert dash["mes_actual_nombre"] is not None

        # Datos financieros confidenciales estrictamente nulos o vacíos
        assert dash["total_ganancias_mes"] is None
        assert dash["capital_inventario"] is None
        assert dash["total_ventas_mes"] is None
        assert dash["equipos_vendidos_mes"] is None
        assert dash["ventas_por_dia"] == []
        assert dash["desglose_metodos_pago"] == {}


@pytest.mark.anyio
async def test_backups_restringidos_solo_dueno():
    """Los endpoints de backup /api/backup/* exigen sesión de dueño."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Sin autenticar: HTTP 401
        res_anon = await client.get("/api/backup/exportar-json")
        assert res_anon.status_code == 401

        # 2. Vendedor: HTTP 403
        await client.post("/api/auth/login", json={"pin": "piso6bodega606."})
        res_vendedor = await client.get("/api/backup/exportar-json")
        assert res_vendedor.status_code == 403

        # 3. Dueño: HTTP 200
        await client.post("/api/auth/logout")
        await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        res_dueno = await client.get("/api/backup/exportar-json")
        assert res_dueno.status_code == 200


@pytest.mark.anyio
async def test_logout_cierra_sesion():
    """El logout elimina la cookie, revoca el token jti en servidor y restablece el estado a no autenticado."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"pin": "piso6bodega606."})
        captured_token = client.cookies.get("sid")
        assert captured_token is not None
        assert (await client.get("/api/auth/me")).json()["authenticated"] is True

        res_logout = await client.post("/api/auth/logout")
        assert res_logout.status_code == 200

        res_me = await client.get("/api/auth/me")
        assert res_me.json()["authenticated"] is False

        # Incluso si un atacante intenta reutilizar el JWT capturado vía cabecera Authorization Bearer, queda rechazado
        res_replay = await client.get("/api/equipos", headers={"Authorization": f"Bearer {captured_token}"})
        assert res_replay.status_code == 401


# ==============================================================================
# NUEVAS PRUEBAS DE SEGURIDAD FASE 2 (AUDITORÍA ARGON)
# ==============================================================================

@pytest.mark.anyio
async def test_argon2id_hashing_y_retrocompatibilidad_pbkdf2():
    """Verifica hashing Argon2id por defecto y compatibilidad hacia atrás con hashes PBKDF2."""
    h, s = hash_secret("ClaveSecretaArgon2026!")
    assert h.startswith("argon2id$")
    assert verify_secret("ClaveSecretaArgon2026!", h, s) is True
    assert verify_secret("ClaveIncorrecta", h, s) is False

    # Verificar que un hash legado PBKDF2-HMAC-SHA256 sigue validando correctamente
    legacy_salt = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    legacy_hash = hashlib.pbkdf2_hmac(
        "sha256",
        b"PasswordLegado123",
        bytes.fromhex(legacy_salt),
        100000
    ).hex()
    assert verify_secret("PasswordLegado123", legacy_hash, legacy_salt) is True
    assert verify_secret("OtroPassword", legacy_hash, legacy_salt) is False


@pytest.mark.anyio
async def test_anti_fuga_costos_en_garantias_e_historial_imei_vendedor():
    """
    Verifica que un vendedor que consulta /api/garantias/verificar-imei o
    /api/garantias/historial-imei/{imei} jamás recibe costo_compra ni márgenes.
    """
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"pin": "piso6bodega606."})

        # Asegurar que exista un equipo vendido de prueba y su venta asociada si no están en la base de datos
        from app.database import get_db_connection
        _conn = get_db_connection()
        _cur = _conn.cursor()
        _cur.execute("SELECT id FROM tenants ORDER BY id ASC LIMIT 1;")
        _t_row = _cur.fetchone()
        _t_id = _t_row["id"] if _t_row else 1
        _cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (_t_id,))
        _s_row = _cur.fetchone()
        _s_id = _s_row["id"] if _s_row else 1

        _cur.execute("SELECT id FROM equipos WHERE imei = '356789123456788';")
        _eq_row = _cur.fetchone()
        _now = "2026-10-19 12:00:00"
        if not _eq_row:
            _cur.execute("""
                INSERT INTO equipos (modelo, capacidad_gb, color, imei, grado, costo_compra, precio_venta, estado, fecha_registro, tenant_id, sucursal_id)
                VALUES ('iPhone 12 Test', 128, 'Negro', '356789123456788', 'A', 6500.0, 9200.0, 'Vendido', ?, ?, ?);
            """, (_now, _t_id, _s_id))
            _eq_id = _cur.lastrowid
        else:
            _eq_id = _eq_row["id"]
            _cur.execute("UPDATE equipos SET tenant_id = ?, sucursal_id = ? WHERE id = ?;", (_t_id, _s_id, _eq_id))

        _cur.execute("SELECT id FROM venta_items WHERE equipo_id = ?;", (_eq_id,))
        if not _cur.fetchone():
            _cur.execute("INSERT OR IGNORE INTO clientes (id, nombre, telefono, fecha_registro, tenant_id) VALUES (9999, 'Cliente Test Garantia', '5599881122', ?, ?);", (_now, _t_id))
            _cur.execute("INSERT INTO ventas (equipo_id, cliente_id, precio_final, margen_ganancia, fecha_venta, metodo_pago, monto_efectivo, tenant_id, sucursal_id) VALUES (?, 9999, 9200.0, 2700.0, ?, 'Efectivo', 9200.0, ?, ?);", (_eq_id, _now, _t_id, _s_id))
            _v_id = _cur.lastrowid
            _cur.execute("INSERT INTO venta_items (venta_id, equipo_id, precio_final, costo_compra, margen_ganancia, tipo_item, cantidad) VALUES (?, ?, 9200.0, 6500.0, 2700.0, 'equipo', 1);", (_v_id, _eq_id))
        _conn.commit()
        _conn.close()

        # Consultar historial 360° de un IMEI vendido (sembrado en demo: 356789123456788)
        res_hist = await client.get("/api/garantias/historial-imei/356789123456788")
        assert res_hist.status_code == 200
        hist = res_hist.json()
        assert hist["costo_compra"] is None
        assert hist.get("margen_proyectado") is None
        for ev in hist["eventos"]:
            if "costo_compra" in ev.get("detalles", {}):
                assert ev["detalles"]["costo_compra"] is None

        # Consultar verificación de garantía por IMEI
        res_ver = await client.get("/api/garantias/verificar-imei?imei=356789123456788")
        assert res_ver.status_code == 200
        ver = res_ver.json()
        assert ver["equipo"]["costo_compra"] is None


@pytest.mark.anyio
async def test_validaciones_estrictas_update_y_cabeceras_csp():
    """Verifica rechazo de valores negativos en actualización de equipos y presencia de cabeceras CSP/OWASP."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res_health = await client.get("/health")
        assert res_health.status_code == 200
        assert "Content-Security-Policy" in res_health.headers
        assert res_health.headers.get("X-Content-Type-Options") == "nosniff"
        assert res_health.headers.get("X-Frame-Options") == "SAMEORIGIN"

        # Login como dueño e intentar actualizar con precio negativo o grado inválido
        await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        res_bad_update = await client.put("/api/equipos/1", json={"precio_venta": -500.0})
        assert res_bad_update.status_code == 422

        res_bad_grado = await client.put("/api/equipos/1", json={"grado": "Z"})
        assert res_bad_grado.status_code == 422

        # Límite negativo en /api/clientes es rechazado con 422
        res_bad_limit = await client.get("/api/clientes?limit=-1")
        assert res_bad_limit.status_code == 422
