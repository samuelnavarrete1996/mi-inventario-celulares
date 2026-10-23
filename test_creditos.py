import os
if "ADMIN_DELETE_PASSWORD" not in os.environ:
    os.environ["ADMIN_DELETE_PASSWORD"] = "samuelykim."

import pytest
import httpx
from datetime import datetime, timedelta
from app.main import app
from app import crud, database
from app.models import ItemCarrito, VentaCreate

@pytest.fixture(autouse=True)
def setup_db():
    database.init_db()

def test_modelo_venta_credito_validacion():
    # Plazo válido 15 días
    v1 = VentaCreate(
        items=[ItemCarrito(tipo_item="accesorio", accesorio_id=1, nombre_item="Funda", cantidad=1, precio_final=250.0)],
        cliente_nombre="Juan Perez",
        cliente_telefono="5551234567",
        metodo_pago="Nota de Crédito",
        es_credito=True,
        plazo_dias=15,
        monto_anticipo=50.0
    )
    assert v1.es_credito is True
    assert v1.plazo_dias == 15
    assert v1.fecha_vencimiento == (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")

    # Plazo válido 30 días
    v2 = VentaCreate(
        items=[ItemCarrito(tipo_item="accesorio", accesorio_id=1, nombre_item="Funda", cantidad=1, precio_final=300.0)],
        cliente_nombre="Maria Gomez",
        cliente_telefono="5559876543",
        metodo_pago="Nota de Crédito",
        es_credito=True,
        plazo_dias=30
    )
    assert v2.plazo_dias == 30
    assert v2.fecha_vencimiento == (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    # Plazo inválido lanza ValueError
    with pytest.raises(ValueError, match="15 o 30 días"):
        VentaCreate(
            items=[ItemCarrito(tipo_item="accesorio", accesorio_id=1, nombre_item="Funda", cantidad=1, precio_final=100.0)],
            cliente_nombre="Carlos",
            cliente_telefono="5550000000",
            metodo_pago="Nota de Crédito",
            es_credito=True,
            plazo_dias=45
        )

@pytest.mark.anyio
async def test_flujo_completo_nota_credito():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Login como dueño
        login_res = await client.post("/api/auth/login", json={"pin": "samuelykim."})
        assert login_res.status_code == 200

        # Crear un accesorio para vender
        acc = crud.create_accesorio(
            nombre="Funda Case Test Credito",
            categoria="Fundas",
            costo_compra=50.0,
            precio_venta=200.0,
            stock=10,
            es_servicio=False
        )
        acc_id = acc["id"]

        # 1. Registrar venta a crédito (15 días con anticipo de $50)
        items = [{"tipo_item": "accesorio", "accesorio_id": acc_id, "nombre_item": "Funda Case Test Credito", "cantidad": 1, "precio_final": 200.0}]
        payload = {
            "items": items,
            "cliente_nombre": "Cliente Credito 15D",
            "cliente_telefono": "5551112233",
            "metodo_pago": "Nota de Crédito",
            "es_credito": True,
            "plazo_dias": 15,
            "monto_anticipo": 50.0,
            "notas": "Venta prueba credito 15 dias"
        }

        res = await client.post("/api/pos/vender", json=payload)
        assert res.status_code == 201, res.text
        data = res.json()
        venta_id = data["id"]
        assert data["es_credito"] == 1
        assert data["plazo_dias"] == 15
        assert data["monto_credito"] == 200.0
        assert data["monto_anticipo"] == 50.0
        assert data["saldo_pendiente"] == 150.0
        assert data["estado_credito"] == "Pendiente"
        assert len(data.get("abonos", [])) == 1
        assert data["abonos"][0]["monto"] == 50.0

        # 2. Consultar recibo
        res_recibo = await client.get(f"/api/pos/recibo/{venta_id}")
        assert res_recibo.status_code == 200
        recibo_data = res_recibo.json()
        assert recibo_data["saldo_pendiente"] == 150.0
        assert recibo_data["es_credito"] == 1

        # 3. Consultar endpoint de notas de crédito y alertas
        res_creditos = await client.get("/api/pos/creditos")
        assert res_creditos.status_code == 200
        creditos_data = res_creditos.json()
        assert creditos_data["total_pendientes"] >= 1
        assert creditos_data["monto_total_por_cobrar"] >= 150.0

        res_alertas = await client.get("/api/pos/creditos/alertas")
        assert res_alertas.status_code == 200
        alertas_data = res_alertas.json()
        assert "total_vencidas" in alertas_data
        assert "total_por_vencer" in alertas_data

        # 4. Registrar abono parcial de $50
        res_abono1 = await client.post(
            f"/api/pos/creditos/{venta_id}/abono",
            json={"monto": 50.0, "metodo_pago": "Efectivo", "notas": "Primer abono"}
        )
        assert res_abono1.status_code == 200, res_abono1.text
        abono_res1 = res_abono1.json()
        assert abono_res1["nuevo_saldo"] == 100.0
        assert abono_res1["estado"] == "Pendiente"

        # 5. Intentar abonar más del saldo pendiente (debe fallar)
        res_exceso = await client.post(
            f"/api/pos/creditos/{venta_id}/abono",
            json={"monto": 500.0, "metodo_pago": "Efectivo"}
        )
        assert res_exceso.status_code == 400

        # 6. Liquidar la nota abonando los $100 restantes
        res_abono2 = await client.post(
            f"/api/pos/creditos/{venta_id}/abono",
            json={"monto": 100.0, "metodo_pago": "Transferencia", "notas": "Liquidación total"}
        )
        assert res_abono2.status_code == 200
        abono_res2 = res_abono2.json()
        assert abono_res2["nuevo_saldo"] == 0.0
        assert abono_res2["estado"] == "Liquidada"

        # 7. Verificar que el recibo actualizado refleja liquidación
        res_recibo2 = await client.get(f"/api/pos/recibo/{venta_id}")
        assert res_recibo2.status_code == 200
        data_final = res_recibo2.json()
        assert data_final["saldo_pendiente"] == 0.0
        assert data_final["estado_credito"] == "Liquidada"
        assert len(data_final["abonos"]) == 3  # Anticipo + Abono 1 + Abono 2

def test_postgres_sql_conversion_julianday():
    from app.postgres_client import _convert_sql_for_postgres
    sql_sqlite = """
        SELECT v.id,
        CAST(ROUND(julianday(date(v.fecha_vencimiento)) - julianday(date('now', 'localtime'))) AS INTEGER) as dias_restantes
        FROM ventas v
        WHERE v.es_credito = 1
    """
    converted = _convert_sql_for_postgres(sql_sqlite)
    assert "julianday" not in converted.lower()
    assert "CURRENT_DATE" in converted

