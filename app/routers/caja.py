from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional, Dict, Any
from app import crud
from app.models import CorteCajaCreate, CorteCajaResponse
from app.security import get_current_user, require_role

router = APIRouter(prefix="/api/caja", tags=["Caja y Cortes"])

@router.get("/resumen-actual", response_model=Dict[str, Any])
def obtener_resumen_corte(user: dict = Depends(get_current_user)):
    """Obtiene el acumulado de ventas del turno actual (requiere sesión activa)."""
    try:
        return crud.obtener_resumen_corte_actual()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al calcular el resumen de corte de caja."
        )

@router.post("/corte", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def realizar_corte_caja(datos: CorteCajaCreate, user: dict = Depends(get_current_user)):
    """Guarda el corte de caja con el efectivo contado y calcula la diferencia (requiere sesión activa)."""
    try:
        return crud.guardar_corte_caja(
            efectivo_declarado=datos.efectivo_declarado,
            notas=datos.notas
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al registrar el corte de caja."
        )

@router.get("/historial", response_model=List[Dict[str, Any]])
def historial_cortes(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_role("dueno"))
):
    """Lista los cortes de caja previos (exclusivo para rol Dueño)."""
    return crud.get_cortes_caja(limit=limit)
