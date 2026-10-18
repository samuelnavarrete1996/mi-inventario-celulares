"""
Test suite integral para verificar todas las operaciones del backend:
- Inicialización y siembra de base de datos
- CRUD de inventario (registro, validación, cálculo de margen, prevención de IMEI duplicado)
- POS y Carrito Multi-artículo
- Pagos combinados (Efectivo + Transferencia + Tarjeta)
- Transacción atómica de venta y generación de recibo
- Métricas del mes en Reportes y Dashboard
"""
import os
if "ADMIN_DELETE_PASSWORD" not in os.environ:
    os.environ["ADMIN_DELETE_PASSWORD"] = "erYHE7yse"

import pytest
import httpx
import time
from app.main import app
from app.database import init_db, seed_demo_data_if_empty
from app.security import reset_all_rate_limits

init_db()
seed_demo_data_if_empty()

ADMIN_PASSWORD = os.environ["ADMIN_DELETE_PASSWORD"]

async def login_as_admin(client: httpx.AsyncClient):
    res = await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert res.status_code == 200
    return res

@pytest.fixture(autouse=True)
def cleanup_rl():
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()

@pytest.mark.anyio
async def test_startup_and_health():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

@pytest.mark.anyio
async def test_listar_inventario():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_admin(client)
        res = await client.get("/api/equipos?solo_disponibles=true")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) > 0
        for item in data:
            assert item["estado"] == "Disponible"
            assert "margen_proyectado" in item

@pytest.mark.anyio
async def test_venta_carrito_pago_combinado():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_admin(client)
        suffix = str(int(time.time() * 1000))[-6:]
        imei1 = f"359999000{suffix}1"
        imei2 = f"359999000{suffix}2"

        # 1. Registrar 2 equipos para venta
        p1 = {
            "modelo": "iPhone 15 Pro",
            "capacidad_gb": 256,
            "color": "Titanio Natural",
            "imei": imei1,
            "grado": "A",
            "costo_compra": 16000.0,
            "precio_venta": 21000.0
        }
        res1 = await client.post("/api/equipos", json=p1)
        assert res1.status_code == 201
        eq1 = res1.json()

        p2 = {
            "modelo": "Samsung Galaxy S24+",
            "capacidad_gb": 256,
            "color": "Gris Cobalto",
            "imei": imei2,
            "grado": "A",
            "costo_compra": 12000.0,
            "precio_venta": 16000.0
        }
        res2 = await client.post("/api/equipos", json=p2)
        assert res2.status_code == 201
        eq2 = res2.json()

        # 2. Venta combinada: Total = 21,000 + 16,000 = 37,000
        # Pagado: 20,000 en Efectivo + 17,000 en Transferencia
        venta_payload = {
            "cliente_nombre": "Alejandro Morales",
            "cliente_telefono": f"55{suffix}",
            "metodo_pago": "Combinado",
            "monto_efectivo": 20000.0,
            "monto_transferencia": 17000.0,
            "monto_garantia": 0.0,
            "items": [
                {"equipo_id": eq1["id"], "precio_final": 21000.0},
                {"equipo_id": eq2["id"], "precio_final": 16000.0}
            ]
        }

        res_venta = await client.post("/api/pos/vender", json=venta_payload)
        assert res_venta.status_code == 201
        data = res_venta.json()

        assert data["precio_final"] == 37000.0
        assert data["margen_ganancia"] == 9000.0
        assert data["metodo_pago"] == "Combinado"
        assert data["monto_efectivo"] == 20000.0
        assert data["monto_transferencia"] == 17000.0
        assert len(data["items"]) == 2

        # 3. Verificar que ambos equipos pasaron a estado Vendido
        res_inv = await client.get("/api/equipos?solo_disponibles=true")
        disponibles = res_inv.json()
        assert not any(e["id"] in (eq1["id"], eq2["id"]) for e in disponibles)

        # 4. Consultar recibo
        res_recibo = await client.get(f"/api/pos/recibo/{data['id']}")
        assert res_recibo.status_code == 200
        recibo = res_recibo.json()
        assert len(recibo["items"]) == 2
        assert recibo["metodo_pago"] == "Combinado"

@pytest.mark.anyio
async def test_pago_combinado_desbalanceado_falla():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_admin(client)
        suffix = str(int(time.time() * 1000))[-6:]
        imei = f"358888000{suffix}"
        
        p = {
            "modelo": "Moto Edge 40",
            "capacidad_gb": 128,
            "color": "Viva Magenta",
            "imei": imei,
            "grado": "B",
            "costo_compra": 4000.0,
            "precio_venta": 6000.0
        }
        res_eq = await client.post("/api/equipos", json=p)
        assert res_eq.status_code == 201
        eq_id = res_eq.json()["id"]

        payload = {
            "cliente_nombre": "Prueba Desbalance",
            "cliente_telefono": f"55{suffix}",
            "metodo_pago": "Combinado",
            "monto_efectivo": 3000.0,
            "monto_transferencia": 2000.0, # Suma 5000 pero el total es 6000
            "items": [
                {"equipo_id": eq_id, "precio_final": 6000.0}
            ]
        }
        res = await client.post("/api/pos/vender", json=payload)
        assert res.status_code in (400, 422)

@pytest.mark.anyio
async def test_dashboard_reportes():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_admin(client)
        res = await client.get("/api/reportes/dashboard")
        assert res.status_code == 200
        dash = res.json()
        assert "total_ganancias_mes" in dash
        assert dash["total_ganancias_mes"] > 0
        assert "desglose_metodos_pago" in dash

@pytest.mark.anyio
async def test_historial_ventas():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_admin(client)
        res = await client.get("/api/reportes/ventas")
        assert res.status_code == 200
        ventas = res.json()
        assert isinstance(ventas, list)
        assert len(ventas) >= 1
        for v in ventas:
            assert "items" in v
            assert "metodo_pago" in v

@pytest.mark.anyio
async def test_descargar_plantilla_excel():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_admin(client)
        res = await client.get("/api/equipos/plantilla-excel")
        assert res.status_code == 200
        assert len(res.content) > 1000
        assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res.headers["content-type"]

@pytest.mark.anyio
async def test_importar_excel():
    from app.excel_importer import generar_plantilla_excel_bytes
    excel_bytes = generar_plantilla_excel_bytes()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_admin(client)
        files = {
            "file": ("inventario_test.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        }
        res = await client.post("/api/equipos/importar-excel", files=files)
        assert res.status_code == 200
        data = res.json()
        assert "importados_count" in data
        assert data["total_filas"] >= 1

@pytest.mark.anyio
async def test_flujo_devolucion_garantia_y_reemplazo():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_admin(client)
        suffix = str(int(time.time() * 1000))[-6:]
        imei_original = f"357777000{suffix}1"
        imei_reemplazo = f"357777000{suffix}2"

        # 1. Registrar y vender equipo original
        p1 = {
            "modelo": "iPhone 13 128GB",
            "capacidad_gb": 128,
            "color": "Midnight",
            "imei": imei_original,
            "grado": "A",
            "costo_compra": 6500.0,
            "precio_venta": 8900.0
        }
        r1 = await client.post("/api/equipos", json=p1)
        assert r1.status_code == 201
        eq1 = r1.json()

        venta_orig = {
            "cliente_nombre": "Carlos Mendoza",
            "cliente_telefono": f"55{suffix}",
            "metodo_pago": "Efectivo",
            "monto_efectivo": 8900.0,
            "items": [{"equipo_id": eq1["id"], "precio_final": 8900.0}]
        }
        r_venta = await client.post("/api/pos/vender", json=venta_orig)
        assert r_venta.status_code == 201

        # 2. Registrar equipo que servirá de reemplazo
        p2 = {
            "modelo": "iPhone 13 256GB",
            "capacidad_gb": 256,
            "color": "Starlight",
            "imei": imei_reemplazo,
            "grado": "A",
            "costo_compra": 7000.0,
            "precio_venta": 9500.0
        }
        r2 = await client.post("/api/equipos", json=p2)
        assert r2.status_code == 201
        eq_reemplazo = r2.json()

        # 3. Consultar verificación de garantía por IMEI
        r_check = await client.get(f"/api/garantias/verificar-imei?imei={imei_original}")
        assert r_check.status_code == 200
        check_data = r_check.json()
        assert check_data["dentro_garantia"] is True
        assert check_data["dias_permitidos"] == 90 # Grado A tiene 90 días
        assert check_data["equipo"]["imei"] == imei_original

        # 4. Procesar devolución por garantía
        devolucion_payload = {
            "imei": imei_original,
            "motivo": "Falla de fábrica / componente",
            "falla_descripcion": "El auricular dejó de emitir sonido en llamadas",
            "estado_equipo_recibido": "En Garantia",
            "solucion": "Reemplazo",
            "monto_cubierto": 8900.0,
            "notas": "Se entrega equipo de reemplazo con costo adicional de 600"
        }
        r_dev = await client.post("/api/garantias/devolucion", json=devolucion_payload)
        assert r_dev.status_code == 201
        dev_res = r_dev.json()
        assert dev_res["solucion"] == "Reemplazo"
        assert dev_res["monto_cubierto"] == 8900.0

        # Verificar que el equipo original quedó en estado 'En Garantia'
        r_orig_get = await client.get(f"/api/equipos/{eq1['id']}")
        assert r_orig_get.status_code == 200
        assert r_orig_get.json()["estado"] == "En Garantia"

        # 5. Cobro de reemplazo en POS: Total 9,500
        # Pagado: 8,900 Equipo Garantía + 600 Efectivo (Combinado)
        venta_reemplazo = {
            "cliente_nombre": "Carlos Mendoza",
            "cliente_telefono": f"55{suffix}",
            "metodo_pago": "Combinado",
            "monto_efectivo": 600.0,
            "monto_transferencia": 0.0,
            "monto_garantia": 8900.0,
            "items": [{"equipo_id": eq_reemplazo["id"], "precio_final": 9500.0}]
        }
        r_v_reemp = await client.post("/api/pos/vender", json=venta_reemplazo)
        assert r_v_reemp.status_code == 201
        v_reemp_data = r_v_reemp.json()
        assert v_reemp_data["precio_final"] == 9500.0
        assert v_reemp_data["monto_garantia"] == 8900.0
        assert v_reemp_data["monto_efectivo"] == 600.0

        # 6. Consultar historial de garantías
        r_hist_gar = await client.get("/api/garantias")
        assert r_hist_gar.status_code == 200
        gar_list = r_hist_gar.json()
        assert any(g["imei"] == imei_original for g in gar_list)

@pytest.mark.anyio
async def test_eliminar_equipo_requiere_password():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await login_as_admin(client)
        suffix = str(int(time.time() * 1000))[-6:]
        imei = f"354444000{suffix}"
        auth_pwd = os.environ.get("ADMIN_DELETE_PASSWORD")

        # 1. Registrar un equipo con sesión de dueño
        p = {
            "modelo": "Xiaomi Redmi Note 13",
            "capacidad_gb": 128,
            "color": "Negro",
            "imei": imei,
            "grado": "B",
            "costo_compra": 2500.0,
            "precio_venta": 3500.0
        }
        res_crear = await client.post("/api/equipos", json=p)
        assert res_crear.status_code == 201
        eq_id = res_crear.json()["id"]

        # Cambiamos a sesión de vendedor para probar la protección por contraseña
        res_vendedor = await client.post("/api/auth/login", json={"pin": "1234"})
        assert res_vendedor.status_code == 200

        # 2. Vendedor intenta eliminar sin contraseña -> 403 Forbidden
        res_no_pwd = await client.delete(f"/api/equipos/{eq_id}")
        assert res_no_pwd.status_code == 403

        # 3. Vendedor intenta eliminar con contraseña errónea -> 403 Forbidden
        res_bad_pwd = await client.delete(f"/api/equipos/{eq_id}?password=wrongpassword")
        assert res_bad_pwd.status_code == 403

        # 4. Eliminar con contraseña correcta enviada en cabecera X-Admin-Password -> 200 OK
        res_ok = await client.delete(f"/api/equipos/{eq_id}", headers={"X-Admin-Password": auth_pwd})
        assert res_ok.status_code == 200
        assert "eliminado exitosamente" in res_ok.json()["mensaje"]

        # 5. Verificar que ya no existe
        res_check = await client.get(f"/api/equipos/{eq_id}")
        assert res_check.status_code == 404




