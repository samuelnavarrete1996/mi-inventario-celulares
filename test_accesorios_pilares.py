import os
if "ADMIN_DELETE_PASSWORD" not in os.environ:
    os.environ["ADMIN_DELETE_PASSWORD"] = "erYHE7yse"

import pytest
import httpx
from app.main import app
from app.security import reset_all_rate_limits

ADMIN_PASSWORD = os.environ["ADMIN_DELETE_PASSWORD"]

@pytest.fixture(autouse=True)
def cleanup_rl():
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()

@pytest.mark.anyio
async def test_plantilla_stock_excel():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        assert login_res.status_code == 200

        # Formato Excel (.xlsx)
        res = await client.get("/api/accesorios/plantilla-stock")
        assert res.status_code == 200
        assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res.headers["content-type"]
        assert len(res.content) > 1000

        # Formato Google Sheets (.csv)
        res_sheets = await client.get("/api/accesorios/plantilla-stock?formato=sheets")
        assert res_sheets.status_code == 200
        assert "text/csv" in res_sheets.headers["content-type"]
        assert "GoogleSheets.csv" in res_sheets.headers.get("content-disposition", "")
        csv_text = res_sheets.content.decode("utf-8-sig")
        assert "ID" in csv_text and "NUEVO STOCK" in csv_text

        # Endpoint directo plantilla-sheets
        res_direct = await client.get("/api/accesorios/plantilla-sheets")
        assert res_direct.status_code == 200
        assert "text/csv" in res_direct.headers["content-type"]

@pytest.mark.anyio
async def test_sugerido_reabastecimiento():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        assert login_res.status_code == 200

        res = await client.get("/api/accesorios/sugerido-reabastecimiento")
        assert res.status_code == 200
        data = res.json()
        assert "total_items_surtir" in data
        assert "inversion_estimada_total" in data
        assert "mensaje_whatsapp" in data
        assert isinstance(data["sugeridos"], list)

@pytest.mark.anyio
async def test_kardex_general_y_ajuste_stock():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        assert login_res.status_code == 200

        # Obtener lista de accesorios
        acc_res = await client.get("/api/accesorios")
        assert acc_res.status_code == 200
        accesorios = [a for a in acc_res.json() if not a.get("es_servicio")]
        assert len(accesorios) > 0
        target = accesorios[0]
        acc_id = target["id"]
        stock_original = target["stock"]

        # Ajuste de prueba con motivo de auditoría
        nuevo_stock = stock_original + 10
        ajuste_res = await client.post(f"/api/accesorios/{acc_id}/ajuste-stock", json={
            "nuevo_stock": nuevo_stock,
            "tipo_movimiento": "AJUSTE_AUDITORIA",
            "notas": "Prueba unitaria de ajuste"
        })
        assert ajuste_res.status_code == 200
        assert ajuste_res.json()["stock"] == nuevo_stock

        # Verificar Kardex para este accesorio
        kardex_item_res = await client.get(f"/api/accesorios/{acc_id}/kardex")
        assert kardex_item_res.status_code == 200
        kardex_items = kardex_item_res.json()
        assert len(kardex_items) > 0
        ultimo_mov = kardex_items[0]
        assert ultimo_mov["tipo_movimiento"] == "AJUSTE"
        assert ultimo_mov["stock_nuevo"] == nuevo_stock

        # Revertir stock al original para mantener base de datos limpia
        revert_res = await client.post(f"/api/accesorios/{acc_id}/ajuste-stock", json={
            "nuevo_stock": stock_original,
            "tipo_movimiento": "AJUSTE",
            "notas": "Reversión prueba unitaria"
        })
        assert revert_res.status_code == 200
        assert revert_res.json()["stock"] == stock_original

@pytest.mark.anyio
async def test_actualizacion_masiva_rapida():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        assert login_res.status_code == 200

        acc_res = await client.get("/api/accesorios")
        accesorios = [a for a in acc_res.json() if not a.get("es_servicio")]
        target1 = accesorios[0]
        target2 = accesorios[1]

        # Actualización masiva de 2 artículos
        batch_payload = {
            "items": [
                {"id": target1["id"], "nuevo_stock": 7},
                {"id": target2["id"], "nuevo_stock": 12}
            ]
        }
        res = await client.post("/api/accesorios/actualizacion-masiva-rapida", json=batch_payload)
        assert res.status_code == 200
        assert res.json()["total_actualizados"] == 2

        # Revertir a 0
        revert_payload = {
            "items": [
                {"id": target1["id"], "nuevo_stock": 0},
                {"id": target2["id"], "nuevo_stock": 0}
            ]
        }
        res_revert = await client.post("/api/accesorios/actualizacion-masiva-rapida", json=revert_payload)
        assert res_revert.status_code == 200
        assert res_revert.json()["total_actualizados"] == 2

@pytest.mark.anyio
async def test_variantes_color_y_sheets():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        assert login_res.status_code == 200

        # 1. Crear un accesorio con color
        payload = {
            "nombre": "Termo Test Color",
            "categoria": "Vasos y Termos",
            "color": "Lavanda Pastel",
            "costo_compra": 100.0,
            "precio_venta": 250.0,
            "precio_mayoreo": 220.0,
            "stock": 5,
            "es_servicio": False
        }
        create_res = await client.post("/api/accesorios", json=payload)
        assert create_res.status_code == 201
        creado = create_res.json()
        assert creado["color"] == "Lavanda Pastel"
        acc_id = creado["id"]

        # 2. Búsqueda por color
        search_res = await client.get("/api/accesorios?search=Lavanda")
        assert search_res.status_code == 200
        encontrados = search_res.json()
        assert any(x["id"] == acc_id for x in encontrados)

        # 3. Plantilla Google Sheets contiene columna Color
        sheets_res = await client.get("/api/accesorios/plantilla-sheets")
        assert sheets_res.status_code == 200
        csv_content = sheets_res.content.decode("utf-8-sig")
        assert "Color" in csv_content or "COLOR" in csv_content

        # 4. Plantilla Google Sheets para celulares
        sheets_cel_res = await client.get("/api/equipos/plantilla-sheets")
        assert sheets_cel_res.status_code == 200
        assert "text/csv" in sheets_cel_res.headers["content-type"]

        # 5. Eliminar accesorio de prueba
        del_res = await client.delete(f"/api/accesorios/{acc_id}", headers={"X-Admin-Password": ADMIN_PASSWORD})
        assert del_res.status_code == 200
