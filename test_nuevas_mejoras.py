import os
if "ADMIN_DELETE_PASSWORD" not in os.environ:
    os.environ["ADMIN_DELETE_PASSWORD"] = "piso6bodega606."

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db
from app.security import reset_all_rate_limits

ADMIN_PASSWORD = os.environ["ADMIN_DELETE_PASSWORD"]

async def login_as_admin(client: AsyncClient):
    res = await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert res.status_code == 200
    return res

@pytest.fixture(autouse=True)
def ensure_db():
    init_db()
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()

@pytest.mark.anyio
async def test_reparaciones_flujo_completo():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await login_as_admin(client)
        # 1. Crear nueva orden de reparación
        payload = {
            "cliente_nombre": "Roberto Gómez",
            "cliente_telefono": "5544332211",
            "dispositivo_modelo": "iPhone 12 Pro",
            "color": "Grafito",
            "imei_serie": "358901234567890",
            "falla_reportada": "Centro de carga no responde, no enciende",
            "diagnostico_tecnico": "Flexor de carga sulfatado",
            "condicion_recepcion": "Sin golpes visibles",
            "costo_refaccion": 350.0,
            "precio_servicio": 1200.0,
            "anticipo": 400.0
        }
        res = await client.post("/api/reparaciones", json=payload)
        assert res.status_code in (200, 201)
        data = res.json()
        assert data["folio"].startswith("REP-")
        assert data["estado"] == "Recibido"
        assert data["precio_servicio"] == 1200.0
        assert data["anticipo"] == 400.0
        assert data["saldo_pendiente"] == 800.0
        rep_id = data["id"]

        # 2. Listar y verificar filtros
        res_list = await client.get("/api/reparaciones?search=Roberto")
        assert res_list.status_code == 200
        reps = res_list.json()
        assert len(reps) >= 1
        assert any(r["id"] == rep_id for r in reps)

        # 3. Cambiar estado a 'Listo para Entrega'
        res_st = await client.patch(f"/api/reparaciones/{rep_id}/estado?nuevo_estado=Listo%20para%20Entrega")
        assert res_st.status_code == 200
        assert res_st.json()["estado"] == "Listo para Entrega"

        # 4. Abonar $800 para liquidar la orden
        res_abono = await client.post(f"/api/reparaciones/{rep_id}/abono", json={"monto_abono": 800.0})
        assert res_abono.status_code == 200
        abono_data = res_abono.json()
        assert abono_data["anticipo"] == 1200.0
        assert abono_data["saldo_pendiente"] == 0.0

        # 5. Entregar equipo
        res_entregar = await client.patch(f"/api/reparaciones/{rep_id}/estado?nuevo_estado=Entregado")
        assert res_entregar.status_code == 200
        assert res_entregar.json()["estado"] == "Entregado"

@pytest.mark.anyio
async def test_catalogo_publico_privacidad():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Vista web catalogo.html
        res_web = await client.get("/catalogo")
        assert res_web.status_code == 200
        assert "Samuel Navarrete" in res_web.text

        # 2. API pública de teléfonos
        res_eq = await client.get("/api/catalogo/equipos")
        assert res_eq.status_code == 200
        equipos = res_eq.json()
        assert isinstance(equipos, list)
        if len(equipos) > 0:
            eq = equipos[0]
            # Verificar campos visibles
            assert "modelo" in eq
            assert "precio_venta" in eq
            assert "grado" in eq
            # Verificar estricta privacidad de datos sensibles
            assert "costo_compra" not in eq
            assert "margen_proyectado" not in eq
            assert "imei" not in eq

        # 3. API pública de accesorios
        res_acc = await client.get("/api/catalogo/accesorios")
        assert res_acc.status_code == 200
        accesorios = res_acc.json()
        assert isinstance(accesorios, list)
        if len(accesorios) > 0:
            acc = accesorios[0]
            assert "nombre" in acc
            assert "precio_venta" in acc
            assert "costo_compra" not in acc

@pytest.mark.anyio
async def test_pwa_manifest_and_sw():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Manifest PWA
        res_manifest = await client.get("/manifest.json")
        assert res_manifest.status_code == 200
        manifest = res_manifest.json()
        assert "Mi Inventario" in manifest["name"]
        assert manifest["display"] == "standalone"
        assert len(manifest["icons"]) >= 2

        # Service Worker
        res_sw = await client.get("/service-worker.js")
        assert res_sw.status_code == 200
        assert "CACHE_NAME" in res_sw.text
