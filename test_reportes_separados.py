import os
if "ADMIN_DELETE_PASSWORD" not in os.environ:
    os.environ["ADMIN_DELETE_PASSWORD"] = "samuelykim."

import pytest
import httpx
from app.main import app

@pytest.mark.anyio
async def test_dashboard_metricas_separadas_dueno():
    """Verifica que el dashboard entregue métricas separadas de celulares y accesorios para el dueño."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Login como dueño
        login_res = await client.post("/api/auth/login", json={"pin": "samuelykim."})
        assert login_res.status_code == 200

        res = await client.get("/api/reportes/dashboard")
        assert res.status_code == 200
        data = res.json()

        # Métricas de Celulares
        assert "celulares_ventas_mes" in data
        assert "celulares_ganancias_mes" in data
        assert "celulares_unidades_mes" in data
        assert "celulares_margen_pct" in data
        assert "celulares_stock_disponible" in data
        assert "celulares_capital_inventario" in data
        assert "celulares_valor_venta_inventario" in data

        # Métricas de Accesorios
        assert "accesorios_ventas_mes" in data
        assert "accesorios_ganancias_mes" in data
        assert "accesorios_unidades_mes" in data
        assert "accesorios_margen_pct" in data
        assert "accesorios_stock_disponible" in data
        assert "accesorios_capital_inventario" in data
        assert "accesorios_valor_venta_inventario" in data

        # Métricas Consolidadas
        assert "total_ganancias_mes" in data
        assert "total_ventas_mes" in data
        assert "capital_inventario_total" in data

        # Validar consistencia matemática
        assert round(data["total_ventas_mes"], 2) == round(data["celulares_ventas_mes"] + data["accesorios_ventas_mes"], 2)
        assert round(data["total_ganancias_mes"], 2) == round(data["celulares_ganancias_mes"] + data["accesorios_ganancias_mes"], 2)

@pytest.mark.anyio
async def test_historial_ventas_filtro_tipo():
    """Verifica el filtrado y cálculo desglosado en el historial de ventas."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"pin": "samuelykim."})

        # Todas las ventas
        res_todos = await client.get("/api/reportes/ventas?tipo=todos")
        assert res_todos.status_code == 200
        ventas_todos = res_todos.json()
        assert isinstance(ventas_todos, list)

        for v in ventas_todos:
            assert "tipo_venta" in v
            assert "ganancia_celulares" in v
            assert "ganancia_accesorios" in v
            assert "total_equipos" in v
            assert "total_accesorios" in v

        # Solo celulares
        res_cel = await client.get("/api/reportes/ventas?tipo=celulares")
        assert res_cel.status_code == 200
        ventas_cel = res_cel.json()
        for v in ventas_cel:
            assert v["total_equipos"] > 0

        # Solo accesorios
        res_acc = await client.get("/api/reportes/ventas?tipo=accesorios")
        assert res_acc.status_code == 200
        ventas_acc = res_acc.json()
        for v in ventas_acc:
            assert v["total_accesorios"] > 0

@pytest.mark.anyio
async def test_dashboard_separado_sanitizado_vendedor():
    """Verifica que un vendedor no reciba las métricas financieras separadas."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/login", json={"pin": "piso6bodega606."})

        res = await client.get("/api/reportes/dashboard")
        assert res.status_code == 200
        data = res.json()

        # Confidencialidad
        assert data["celulares_ganancias_mes"] is None
        assert data["accesorios_ganancias_mes"] is None
        assert data["celulares_capital_inventario"] is None
        assert data["accesorios_capital_inventario"] is None
        assert data["capital_inventario_total"] is None
        assert data["total_ganancias_mes"] is None

def test_postgres_sql_conversion_strftime():
    from app.postgres_client import _convert_sql_for_postgres
    sql_sqlite = "SELECT * FROM ventas v WHERE strftime('%Y-%m', v.fecha_venta) = ?"
    converted = _convert_sql_for_postgres(sql_sqlite)
    assert "strftime" not in converted.lower()
    assert "SUBSTR" in converted

