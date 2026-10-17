from fastapi import APIRouter, Query, Request, HTTPException, status
from typing import List, Optional, Dict, Any
from app import crud
from app.models import VentaDetalleResponse
from app.security import get_current_user_optional, is_user_dueno

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

@router.get("/dashboard")
def obtener_metricas_dashboard(request: Request) -> Dict[str, Any]:
    """
    Dashboard de ganancias y métricas del mes actual.
    Si el usuario no es Dueño, se omiten confidencialmente los totales financieros
    (ganancias, capital y ventas diarias).
    """
    metrics = crud.get_dashboard_metrics()
    user = get_current_user_optional(request)
    if not is_user_dueno(user):
        metrics["total_ganancias_mes"] = None
        metrics["total_ventas_mes"] = None
        metrics["cantidad_equipos_vendidos"] = None
        metrics["capital_inventario"] = None
        metrics["valor_venta_inventario"] = None
        metrics["margen_promedio_mes"] = None
        metrics["ventas_por_dia"] = []
    return metrics

@router.get("/ventas", response_model=List[VentaDetalleResponse])
def historial_ventas(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
    fecha_inicio: Optional[str] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[str] = Query(None, description="Fecha de fin (YYYY-MM-DD)")
):
    """
    Historial detallado de ventas con cálculo de margen de ganancia real,
    datos del cliente y especificaciones del equipo.
    Requiere obligatoriamente rol de Dueño.
    """
    user = get_current_user_optional(request)
    if not is_user_dueno(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: El historial financiero y reporte de ventas requiere permisos de Dueño."
        )
    return crud.get_historial_ventas(limit=limit, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
