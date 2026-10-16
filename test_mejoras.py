import pytest
import time
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db

@pytest.fixture(autouse=True)
def setup_database():
    init_db()

@pytest.mark.anyio
async def test_accesorios_crud():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        suffix = str(int(time.time() * 1000))[-5:]
        # 1. Listar catálogo inicial
        res = await ac.get("/api/accesorios")
        assert res.status_code == 200
        iniciales = res.json()
        assert len(iniciales) >= 1

        # 2. Crear nuevo accesorio
        nuevo = {
            "nombre": f"Cargador Rápido 20W {suffix}",
            "categoria": "Cargadores",
            "codigo_barras": f"750{suffix}12345",
            "costo_compra": 90.0,
            "precio_venta": 250.0,
            "stock": 15,
            "es_servicio": False
        }
        res_post = await ac.post("/api/accesorios", json=nuevo)
        assert res_post.status_code == 201
        acc_creado = res_post.json()
        assert acc_creado["id"] is not None
        assert acc_creado["nombre"] == nuevo["nombre"]
        assert acc_creado["margen_unitario"] == 160.0
        assert acc_creado["codigo_barras"] == nuevo["codigo_barras"]

        acc_id = acc_creado["id"]

        # 3. Actualizar accesorio
        res_put = await ac.put(f"/api/accesorios/{acc_id}", json={
            "nombre": f"Cargador Rápido 25W {suffix}",
            "categoria": "Cargadores",
            "costo_compra": 95.0,
            "precio_venta": 280.0,
            "stock": 20,
            "es_servicio": False
        })
        assert res_put.status_code == 200
        assert res_put.json()["nombre"] == f"Cargador Rápido 25W {suffix}"
        assert res_put.json()["stock"] == 20

        # 4. Eliminar accesorio
        res_del = await ac.delete(f"/api/accesorios/{acc_id}")
        assert res_del.status_code == 200
        assert "eliminado" in res_del.json()["mensaje"]

@pytest.mark.anyio
async def test_venta_combinada_equipo_y_accesorio():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        suffix = str(int(time.time() * 1000))[-6:]
        imei = f"88123456{suffix}"

        # 1. Registrar equipo para la prueba
        equipo_data = {
            "modelo": "Samsung S22 Ultra Test",
            "capacidad_gb": 256,
            "color": "Verde",
            "imei": imei,
            "costo_compra": 7000.0,
            "precio_venta": 9500.0,
            "grado": "A"
        }
        res_eq = await ac.post("/api/equipos", json=equipo_data)
        assert res_eq.status_code == 201
        eq_id = res_eq.json()["id"]

        # 2. Registrar accesorio con stock
        acc_data = {
            "nombre": f"Mica Cristal Templado {suffix}",
            "categoria": "Micas y Micas 9D",
            "costo_compra": 30.0,
            "precio_venta": 150.0,
            "stock": 5,
            "es_servicio": False
        }
        res_acc = await ac.post("/api/accesorios", json=acc_data)
        assert res_acc.status_code == 201
        acc_id = res_acc.json()["id"]

        # 3. Vender carrito mixto: Celular ($9500) + 2 Micas ($300) = $9800
        payload_venta = {
            "cliente_nombre": "Carlos Slim",
            "cliente_telefono": f"55{suffix}",
            "metodo_pago": "Efectivo",
            "monto_efectivo": 9800.0,
            "monto_transferencia": 0.0,
            "monto_garantia": 0.0,
            "items": [
                {
                    "tipo_item": "equipo",
                    "equipo_id": eq_id,
                    "nombre_item": "Samsung S22 Ultra Test",
                    "cantidad": 1,
                    "precio_final": 9500.0
                },
                {
                    "tipo_item": "accesorio",
                    "accesorio_id": acc_id,
                    "nombre_item": f"Mica Cristal Templado {suffix}",
                    "cantidad": 2,
                    "precio_final": 300.0
                }
            ]
        }
        res_v = await ac.post("/api/pos/vender", json=payload_venta)
        assert res_v.status_code == 201
        venta = res_v.json()
        assert venta["precio_final"] == 9800.0
        assert len(venta["items"]) == 2

        # 4. Verificar que el stock de accesorio decrementó de 5 a 3
        res_acc_after = await ac.get("/api/accesorios")
        acc_actualizado = next(a for a in res_acc_after.json() if a["id"] == acc_id)
        assert acc_actualizado["stock"] == 3

@pytest.mark.anyio
async def test_corte_de_caja_arqueo():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Obtener balance actual sugerido
        res_balance = await ac.get("/api/caja/resumen-actual")
        assert res_balance.status_code == 200
        bal = res_balance.json()
        assert "total_efectivo" in bal
        assert "total_transferencia" in bal

        # 2. Registrar corte declarando efectivo
        efectivo_sistema = bal["total_efectivo"]
        efectivo_contado = efectivo_sistema + 50.0 # Sobrante de 50 pesos

        corte_payload = {
            "efectivo_declarado": efectivo_contado,
            "notas": "Turno vespertino cerrado correctamente"
        }
        res_corte = await ac.post("/api/caja/corte", json=corte_payload)
        assert res_corte.status_code == 201
        corte = res_corte.json()
        assert corte["id"] is not None
        assert abs(corte["diferencia"] - 50.0) < 0.01

        # 3. Consultar historial de cortes
        res_hist = await ac.get("/api/caja/historial")
        assert res_hist.status_code == 200
        historial = res_hist.json()
        assert len(historial) >= 1
        assert any(c["id"] == corte["id"] for c in historial)

@pytest.mark.anyio
async def test_historial_imei_timeline():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        suffix = str(int(time.time() * 1000))[-6:]
        imei_test = f"77665544{suffix}"
        res_eq = await ac.post("/api/equipos", json={
            "modelo": "Google Pixel 8 Pro",
            "capacidad_gb": 128,
            "color": "Obsidian",
            "imei": imei_test,
            "costo_compra": 8000.0,
            "precio_venta": 11000.0,
            "grado": "A"
        })
        assert res_eq.status_code == 201

        # Consultar historial 360° del IMEI
        res_hist = await ac.get(f"/api/garantias/historial-imei/{imei_test}")
        assert res_hist.status_code == 200
        data = res_hist.json()
        assert data["imei"] == imei_test
        assert data["modelo"] == "Google Pixel 8 Pro"
        assert len(data["eventos"]) >= 1
        assert any(ev["tipo"] == "INGRESO" for ev in data["eventos"])

@pytest.mark.anyio
async def test_antiguedad_stock_calculada():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/equipos")
        assert res.status_code == 200
        equipos = res.json()
        if len(equipos) > 0:
            eq = equipos[0]
            assert "dias_en_stock" in eq
            assert "estado_antiguedad" in eq
            assert eq["estado_antiguedad"] in ["Fresco", "Normal", "Lento", "Remate"]

@pytest.mark.anyio
async def test_backup_export_json_y_db():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # JSON export
        res_json = await ac.get("/api/backup/exportar-json")
        assert res_json.status_code == 200
        datos = res_json.json()
        assert "equipos" in datos["datos"]
        assert "ventas" in datos["datos"]
        assert "accesorios" in datos["datos"]

        # DB file download
        res_db = await ac.get("/api/backup/descargar-db")
        assert res_db.status_code == 200
        assert res_db.headers.get("content-type") == "application/x-sqlite3"
        assert len(res_db.content) > 1000
