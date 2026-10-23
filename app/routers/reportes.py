from fastapi import APIRouter, Query, HTTPException, status, Depends
from typing import List, Optional, Dict, Any
from app import crud
from app.models import VentaDetalleResponse
from app.security import get_current_user, require_role, is_user_dueno, sanitizar_datos_sensibles, get_current_tenant
from app.dependencies import TenantContext

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

@router.get("/dashboard")
def obtener_metricas_dashboard(tenant: TenantContext = Depends(get_current_tenant)) -> Dict[str, Any]:
    """
    Dashboard de ganancias y métricas del mes actual para el tenant en sesión.
    Si el usuario no es Dueño, se omiten confidencialmente los totales financieros
    (ganancias, capital, ventas diarias y desglose monetario por método de pago).
    """
    metrics = crud.get_dashboard_metrics(tenant_id=tenant.tenant_id)
    if not is_user_dueno(tenant.user):
        campos_a_ocultar = [
            "total_ganancias_mes", "total_ventas_mes", "equipos_vendidos_mes",
            "cantidad_equipos_vendidos", "capital_inventario", "valor_venta_inventario",
            "capital_inventario_total", "margen_promedio_mes", "ventas_por_dia",
            "desglose_metodos_pago", "celulares_ventas_mes", "celulares_ganancias_mes",
            "celulares_unidades_mes", "celulares_margen_pct", "celulares_capital_inventario",
            "celulares_valor_venta_inventario", "celulares_top_vendidos",
            "accesorios_ventas_mes", "accesorios_ganancias_mes", "accesorios_unidades_mes",
            "accesorios_margen_pct", "accesorios_capital_inventario",
            "accesorios_valor_venta_inventario", "accesorios_top_vendidos",
            "reparaciones_ventas_mes", "reparaciones_ganancias_mes", "reparaciones_unidades_mes",
            "reparaciones_margen_pct"
        ]
        for k in campos_a_ocultar:
            if k == "ventas_por_dia":
                metrics[k] = []
            elif k == "desglose_metodos_pago":
                metrics[k] = {}
            elif k in ("celulares_top_vendidos", "accesorios_top_vendidos"):
                metrics[k] = []
            else:
                metrics[k] = None
    return sanitizar_datos_sensibles(metrics, tenant.user)

@router.get("/ventas", response_model=List[VentaDetalleResponse])
def historial_ventas(
    limit: int = Query(200, ge=1, le=1000),
    fecha_inicio: Optional[str] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[str] = Query(None, description="Fecha de fin (YYYY-MM-DD)"),
    tipo: Optional[str] = Query("todos", description="Filtro por tipo: todos, celulares, accesorios"),
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Historial detallado de ventas con cálculo de margen de ganancia real,
    desglose por celulares y accesorios, datos del cliente y forma de pago del tenant en sesión.
    Requiere obligatoriamente rol de Dueño.
    """
    return crud.get_historial_ventas(
        limit=limit,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        tipo=tipo,
        tenant_id=tenant.tenant_id
    )
