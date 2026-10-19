from fastapi import APIRouter, Query, HTTPException, status, Depends
from typing import List, Optional, Dict, Any
from app import crud
from app.models import VentaDetalleResponse
from app.security import get_current_user, require_role, is_user_dueno, sanitizar_datos_sensibles

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

@router.get("/dashboard")
def obtener_metricas_dashboard(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Dashboard de ganancias y métricas del mes actual.
    Si el usuario no es Dueño, se omiten confidencialmente los totales financieros
    (ganancias, capital, ventas diarias y desglose monetario por método de pago).
    """
    metrics = crud.get_dashboard_metrics()
    if not is_user_dueno(user):
        metrics["total_ganancias_mes"] = None
        metrics["total_ventas_mes"] = None
        metrics["equipos_vendidos_mes"] = None
        metrics["cantidad_equipos_vendidos"] = None
        metrics["capital_inventario"] = None
        metrics["valor_venta_inventario"] = None
        metrics["margen_promedio_mes"] = None
        metrics["ventas_por_dia"] = []
        metrics["desglose_metodos_pago"] = {}
    return sanitizar_datos_sensibles(metrics, user)

@router.get("/ventas", response_model=List[VentaDetalleResponse])
def historial_ventas(
    limit: int = Query(200, ge=1, le=1000),
    fecha_inicio: Optional[str] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[str] = Query(None, description="Fecha de fin (YYYY-MM-DD)"),
    user: dict = Depends(require_role("dueno"))
):
    """
    Historial detallado de ventas con cálculo de margen de ganancia real,
    datos del cliente y especificaciones del equipo.
    Requiere obligatoriamente rol de Dueño.
    """
    return crud.get_historial_ventas(limit=limit, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
