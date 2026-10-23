"""
test_garantias_reingreso.py - Pruebas para reingreso de equipos por garantía,
puesta a punto funcional y trazabilidad 360° en historial IMEI.
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

ADMIN_PASSWORD = os.environ.get("ADMIN_DELETE_PASSWORD", "AdminPassword123!")

@pytest.fixture(autouse=True)
def clean_rate_limits():
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()

async def login_as_dueno(client: httpx.AsyncClient):
    res = await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert res.status_code == 200
    token = res.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return token

async def login_as_vendedor(client: httpx.AsyncClient):
    res = await client.post("/api/auth/login", json={"pin": "piso6bodega606."})
    assert res.status_code == 200
    token = res.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return token

@pytest.mark.anyio
async def test_flujo_completo_garantia_reingreso_y_funcional():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_dueno(client)
        suffix = str(int(time.time() * 1000))[-6:]
        imei_test = f"359999000{suffix}"

        # 1. Registrar teléfono
        eq_payload = {
            "modelo": "iPhone 14 Pro 128GB",
            "capacidad_gb": 128,
            "color": "Morado Oscuro",
            "imei": imei_test,
            "grado": "A",
            "costo_compra": 11000.0,
            "precio_venta": 14500.0
        }
        res_eq = await client.post("/api/equipos", json=eq_payload)
        assert res_eq.status_code == 201
        equipo = res_eq.json()
        equipo_id = equipo["id"]

        # 2. Vender el teléfono
        venta_payload = {
            "cliente_nombre": "Laura Valenzuela",
            "cliente_telefono": f"55{suffix}",
            "metodo_pago": "Efectivo",
            "monto_efectivo": 14500.0,
            "items": [{"equipo_id": equipo_id, "precio_final": 14500.0}]
        }
        res_v = await client.post("/api/pos/vender", json=venta_payload)
        assert res_v.status_code == 201

        # 3. Validar que el equipo ahora está vendido y no aparece en disponibles
        res_disp = await client.get("/api/equipos?solo_disponibles=true")
        assert res_disp.status_code == 200
        disponibles_ids = [e["id"] for e in res_disp.json()]
        assert equipo_id not in disponibles_ids

        # 4. Cliente regresa por garantía (Falla de puerto de carga)
        garantia_payload = {
            "imei": imei_test,
            "motivo": "Falla de fábrica / componente",
            "falla_descripcion": "No retiene la carga y pin falsea",
            "estado_equipo_recibido": "En Garantia",
            "solucion": "Reparación",
            "monto_cubierto": 14500.0,
            "notas": "Se envía a revisión técnica de laboratorio"
        }
        res_gar = await client.post("/api/garantias/devolucion", json=garantia_payload)
        assert res_gar.status_code == 201
        gar_data = res_gar.json()
        assert gar_data["estado_equipo_recibido"] == "En Garantia"

        # 5. Verificar filtros de inventario
        # A) No debe aparecer en solo_disponibles
        res_disp2 = await client.get("/api/equipos?solo_disponibles=true")
        assert equipo_id not in [e["id"] for e in res_disp2.json()]

        # B) Sí debe aparecer al filtrar por estado=En Garantia
        res_en_gar = await client.get("/api/equipos?estado=En Garantia")
        assert res_en_gar.status_code == 200
        gar_ids = [e["id"] for e in res_en_gar.json()]
        assert equipo_id in gar_ids

        # C) Sí debe aparecer al filtrar por estado=todos
        res_todos = await client.get("/api/equipos?estado=todos")
        assert res_todos.status_code == 200
        todos_ids = [e["id"] for e in res_todos.json()]
        assert equipo_id in todos_ids

        # 6. Técnico repara el equipo y lo pone funcional nuevamente
        restablecer_payload = {
            "nuevo_grado": "B",
            "nuevo_precio_venta": 13900.0,
            "costo_adicional": 450.0,
            "notas": "Se sustituyó flex de carga original, probado con amperímetro OK"
        }
        res_restablecer = await client.post(
            f"/api/garantias/restablecer-equipo/{equipo_id}",
            json=restablecer_payload
        )
        assert res_restablecer.status_code == 200
        restaurado = res_restablecer.json()
        assert restaurado["estado"] == "Disponible"
        assert restaurado["grado"] == "B"
        assert restaurado["precio_venta"] == 13900.0
        assert restaurado["costo_compra"] == 11450.0 # 11000 + 450 costo refacción

        # 7. Ahora el equipo debe estar visible en stock disponible
        res_disp3 = await client.get("/api/equipos?solo_disponibles=true")
        assert equipo_id in [e["id"] for e in res_disp3.json()]

        # 8. Consultar la línea de tiempo e historial 360° del IMEI
        res_hist = await client.get(f"/api/garantias/historial-imei/{imei_test}")
        assert res_hist.status_code == 200
        hist_data = res_hist.json()
        assert hist_data["estado_actual"] == "Disponible"
        assert hist_data["grado"] == "B"
        assert len(hist_data["eventos"]) >= 4

        tipos_eventos = [ev["tipo"] for ev in hist_data["eventos"]]
        assert "INGRESO" in tipos_eventos
        assert "VENTA" in tipos_eventos
        assert "GARANTIA_RECLAMO" in tipos_eventos
        assert "RESTAURADO" in tipos_eventos

        # Verificar que el evento RESTAURADO contiene las notas técnicas
        ev_restaurado = next(ev for ev in hist_data["eventos"] if ev["tipo"] == "RESTAURADO")
        assert "reparado y reingresado" in ev_restaurado["descripcion"].lower() or "puesto funcional" in ev_restaurado["descripcion"].lower()

@pytest.mark.anyio
async def test_seguridad_vendedor_sanitizado_en_historial_imei():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Registrar equipo con sesión de dueño
        await login_as_dueno(client)
        suffix = str(int(time.time() * 1000))[-6:]
        imei_test = f"358888000{suffix}"
        await client.post("/api/equipos", json={
            "modelo": "Samsung Galaxy S22",
            "capacidad_gb": 128,
            "color": "Verde",
            "imei": imei_test,
            "grado": "A",
            "costo_compra": 5800.0,
            "precio_venta": 8200.0
        })

        # Ahora hacer login como vendedor
        await login_as_vendedor(client)
        res_hist = await client.get(f"/api/garantias/historial-imei/{imei_test}")
        assert res_hist.status_code == 200
        data = res_hist.json()

        # Confidencialidad: vendedor no puede ver costo_compra ni margen_proyectado
        assert data.get("costo_compra") is None
        assert data.get("margen_proyectado") is None
        for ev in data.get("eventos", []):
            if "detalles" in ev:
                assert ev["detalles"].get("costo_compra") is None
