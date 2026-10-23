import os
if "ADMIN_DELETE_PASSWORD" not in os.environ:
    os.environ["ADMIN_DELETE_PASSWORD"] = "samuelykim."

import pytest
import httpx
from datetime import datetime
from app.main import app
from app import crud

@pytest.mark.anyio
async def test_flujo_completo_gastos_operativos_y_dashboard():
    """
    Verifica:
    1. Registro de gasto operativo (ej: Renta).
    2. Consulta de lista de gastos y resumen mensual.
    3. Reflejo del gasto en el dashboard y cálculo de ganancia neta.
    4. Formato y serialización de fechas sin error.
    5. Eliminación de gasto.
    """
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login como Dueño
        login_dueno = await client.post("/api/auth/login", json={"pin": "samuelykim."})
        assert login_dueno.status_code == 200, "Login de dueño falló"

        # 2. Registrar gasto de Renta
        mes_actual = datetime.now().strftime("%Y-%m")
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
        gasto_payload = {
            "concepto": "Renta de Local Comercial",
            "categoria": "Renta",
            "monto": 8500.0,
            "metodo_pago": "Transferencia",
            "fecha": fecha_hoy,
            "notas": "Pago de renta correspondiente a mes corriente"
        }
        res_gasto = await client.post("/api/gastos", json=gasto_payload)
        assert res_gasto.status_code == 201, f"Error al crear gasto: {res_gasto.text}"
        gasto_data = res_gasto.json()
        assert gasto_data["id"] is not None
        assert gasto_data["concepto"] == "Renta de Local Comercial"
        assert gasto_data["monto"] == 8500.0
        assert gasto_data["categoria"] == "Renta"
        gasto_id = gasto_data["id"]

        # 3. Listar gastos
        res_lista = await client.get(f"/api/gastos?mes={mes_actual}")
        assert res_lista.status_code == 200
        lista = res_lista.json()
        assert any(g["id"] == gasto_id for g in lista)

        # 4. Resumen de gastos
        res_resumen = await client.get(f"/api/gastos/resumen?mes={mes_actual}")
        assert res_resumen.status_code == 200
        resumen = res_resumen.json()
        assert resumen["total_mes"] >= 8500.0
        assert "Renta" in resumen["desglose_por_categoria"]
        assert resumen["desglose_por_categoria"]["Renta"] >= 8500.0

        # 5. Métricas del Dashboard reflejan el gasto
        res_dash = await client.get("/api/reportes/dashboard")
        assert res_dash.status_code == 200
        dash_data = res_dash.json()
        assert "total_gastos_mes" in dash_data
        assert dash_data["total_gastos_mes"] >= 8500.0
        assert "ganancia_neta_mes" in dash_data

        # 6. Eliminar gasto
        res_del = await client.delete(f"/api/gastos/{gasto_id}")
        assert res_del.status_code == 200

        # Verificar que ya no aparece
        res_lista_after = await client.get(f"/api/gastos?mes={mes_actual}")
        assert res_lista_after.status_code == 200
        assert not any(g["id"] == gasto_id for g in res_lista_after.json())
