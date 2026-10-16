from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional, Dict, Any
from app import crud
from app.models import CorteCajaCreate, CorteCajaResponse

router = APIRouter(prefix="/api/caja", tags=["Caja y Cortes"])

@router.get("/resumen-actual", response_model=Dict[str, Any])
def obtener_resumen_corte():
    """Obtiene el acumulado de ventas del turno actual (desde el último corte o inicio del día)."""
    try:
        return crud.obtener_resumen_corte_actual()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/corte", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def realizar_corte_caja(datos: CorteCajaCreate):
    """Guarda el corte de caja con el efectivo contado y calcula la diferencia (sobrante/faltante)."""
    try:
        return crud.guardar_corte_caja(
            efectivo_declarado=datos.efectivo_declarado,
            notas=datos.notas
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/historial", response_model=List[Dict[str, Any]])
def historial_cortes(limit: int = Query(50, ge=1, le=200)):
    """Lista los cortes de caja previos."""
    return crud.get_cortes_caja(limit=limit)
