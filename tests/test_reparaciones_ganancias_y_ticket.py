import os
if "ADMIN_DELETE_PASSWORD" not in os.environ:
    os.environ["ADMIN_DELETE_PASSWORD"] = "samuelykim."

import pytest
import httpx
from datetime import datetime
from app.main import app

@pytest.mark.anyio
async def test_reparacion_en_ticket_ganancias_e_historial():
    """
    Valida integralmente:
    1. Registro de reparación con diagnóstico y refacción/calidad.
    2. Visualización del diagnóstico para ticket y cliente.
    3. Reflejo de la reparación en el dashboard de métricas del mes (ventas y ganancias).
    4. Inclusión de la reparación en el historial unificado de ventas y filtro por tipo=reparaciones.
    5. Sanitización y confidencialidad para usuarios no dueños.
    """
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login como Dueño
        login_dueno = await client.post("/api/auth/login", json={"pin": "samuelykim."})
        assert login_dueno.status_code == 200, "Login dueño falló"

        # 2. Registrar orden de reparación con diagnóstico técnico y calidad
        rep_payload = {
            "cliente_nombre": "Carlos Mendoza",
            "cliente_telefono": "5512345678",
            "dispositivo_modelo": "iPhone 13 Pro",
            "color": "Azul Sierra",
            "imei_serie": "358912345678901",
            "codigo_patron": "1994",
            "falla_reportada": "Pantalla rota sin touch",
            "diagnostico_tecnico": "Cambio de pantalla OLED GX + Reprogramación TrueTone",
            "condicion_recepcion": "Bordes con desgaste leve",
            "costo_refaccion": 1200.0,
            "precio_servicio": 2600.0,
            "anticipo": 1000.0,
            "tecnico_responsable": "Samuel Navarrete"
        }
        res_crear = await client.post("/api/reparaciones", json=rep_payload)
        assert res_crear.status_code == 201, f"Error al crear reparación: {res_crear.text}"
        rep_creada = res_crear.json()
        rep_id = rep_creada["id"]
        folio = rep_creada["folio"]

        # Cambiar estado a Listo para Entrega
        res_est = await client.patch(f"/api/reparaciones/{rep_id}/estado?nuevo_estado=Listo para Entrega")
        assert res_est.status_code == 200

        assert rep_creada["diagnostico_tecnico"] == "Cambio de pantalla OLED GX + Reprogramación TrueTone"
        assert rep_creada["precio_servicio"] == 2600.0
        assert rep_creada["costo_refaccion"] == 1200.0
        assert rep_creada["saldo_pendiente"] == 1600.0

        # 3. Consultar detalle de la orden (para boleta / ticket)
        res_detalle = await client.get(f"/api/reparaciones/{rep_id}")
        assert res_detalle.status_code == 200
        rep_detalle = res_detalle.json()
        assert rep_detalle["diagnostico_tecnico"] == "Cambio de pantalla OLED GX + Reprogramación TrueTone"
        assert rep_detalle["folio"] == folio

        # 4. Verificar métricas del Dashboard (Dueño)
        res_dash = await client.get("/api/reportes/dashboard")
        assert res_dash.status_code == 200
        dash_data = res_dash.json()

        assert "reparaciones_ventas_mes" in dash_data
        assert "reparaciones_ganancias_mes" in dash_data
        assert dash_data["reparaciones_ventas_mes"] >= 2600.0
        # Ganancia calculada: 2600 - 1200 = 1400
        assert dash_data["reparaciones_ganancias_mes"] >= 1400.0

        # Consistencia matemática consolidada: Celulares + Accesorios + Taller
        total_v = dash_data["total_ventas_mes"]
        total_g = dash_data["total_ganancias_mes"]
        esperado_v = round(dash_data["celulares_ventas_mes"] + dash_data["accesorios_ventas_mes"] + dash_data["reparaciones_ventas_mes"], 2)
        esperado_g = round(dash_data["celulares_ganancias_mes"] + dash_data["accesorios_ganancias_mes"] + dash_data["reparaciones_ganancias_mes"], 2)
        assert round(total_v, 2) == esperado_v
        assert round(total_g, 2) == esperado_g

        # 5. Verificar Historial de Ventas (tipo=todos)
        res_historial_todos = await client.get("/api/reportes/ventas?tipo=todos")
        assert res_historial_todos.status_code == 200
        ventas_todos = res_historial_todos.json()

        item_rep = next((v for v in ventas_todos if v.get("folio") == folio), None)
        assert item_rep is not None, f"La reparación con folio {folio} no apareció en el historial de ventas."
        assert item_rep["tipo_venta"] == "reparacion"
        assert item_rep["precio_final"] == 2600.0
        assert item_rep["margen_ganancia"] == 1400.0
        assert item_rep["diagnostico_tecnico"] == "Cambio de pantalla OLED GX + Reprogramación TrueTone"
        assert item_rep["reparacion_id"] == rep_id
        assert "iPhone 13 Pro" in item_rep["resumen_modelos"]

        # 6. Verificar Historial de Ventas filtrado por tipo=reparaciones
        res_historial_rep = await client.get("/api/reportes/ventas?tipo=reparaciones")
        assert res_historial_rep.status_code == 200
        ventas_rep = res_historial_rep.json()
        assert any(v.get("folio") == folio for v in ventas_rep)
        for v in ventas_rep:
            assert v["tipo_venta"] == "reparacion"

        # 7. Verificar que tipo=celulares no contenga reparaciones
        res_historial_cel = await client.get("/api/reportes/ventas?tipo=celulares")
        assert res_historial_cel.status_code == 200
        ventas_cel = res_historial_cel.json()
        assert not any(v.get("folio") == folio for v in ventas_cel)

        # 8. Verificar confidencialidad del dashboard para Vendedor
        login_vendedor = await client.post("/api/auth/login", json={"pin": "piso6bodega606."})
        assert login_vendedor.status_code == 200

        res_dash_vend = await client.get("/api/reportes/dashboard")
        assert res_dash_vend.status_code == 200
        dash_vend_data = res_dash_vend.json()
        assert dash_vend_data["reparaciones_ganancias_mes"] is None
        assert dash_vend_data["total_ganancias_mes"] is None
