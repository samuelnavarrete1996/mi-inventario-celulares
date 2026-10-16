from fastapi import APIRouter, Query
from typing import List, Optional, Dict, Any
from app import crud
from app.models import VentaDetalleResponse

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

@router.get("/dashboard")
def obtener_metricas_dashboard() -> Dict[str, Any]:
    """
    Dashboard de ganancias y métricas del mes actual:
    - Total de ganancias (suma de margen_ganancia) en el mes actual.
    - Total de ventas del mes ($).
    - Cantidad de equipos vendidos.
    - Equipos disponibles y capital invertido.
    - Ventas por día para visualización gráfica.
    """
    return crud.get_dashboard_metrics()

@router.get("/ventas", response_model=List[VentaDetalleResponse])
def historial_ventas(
    limit: int = Query(200, ge=1, le=1000),
    fecha_inicio: Optional[str] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[str] = Query(None, description="Fecha de fin (YYYY-MM-DD)")
):
    """
    Historial detallado de ventas con cálculo de margen de ganancia real,
    datos del cliente y especificaciones del equipo.
    """
    return crud.get_historial_ventas(limit=limit, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
