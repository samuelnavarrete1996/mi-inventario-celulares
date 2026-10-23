from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional, Dict, Any
from app import crud
from app.models import CorteCajaCreate, CorteCajaResponse
from app.security import get_current_user, require_role, get_current_tenant
from app.dependencies import TenantContext

router = APIRouter(prefix="/api/caja", tags=["Caja y Cortes"])

@router.get("/resumen-actual", response_model=Dict[str, Any])
def obtener_resumen_corte(tenant: TenantContext = Depends(get_current_tenant)):
    """Obtiene el acumulado de ventas del turno actual para el tenant en sesión."""
    try:
        return crud.obtener_resumen_corte_actual(tenant_id=tenant.tenant_id)
    except Exception as e:
        import logging
        logging.exception("Error al calcular resumen de corte de caja: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al calcular resumen de corte: {str(e)}"
        )

@router.post("/corte", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def realizar_corte_caja(datos: CorteCajaCreate, tenant: TenantContext = Depends(get_current_tenant)):
    """Guarda el corte de caja con el efectivo contado e inyecta tenant_id y sucursal_id."""
    try:
        return crud.guardar_corte_caja(
            efectivo_declarado=datos.efectivo_declarado,
            notas=datos.notas,
            tenant_id=tenant.tenant_id,
            sucursal_id=tenant.sucursal_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        import logging
        logging.exception("Error al registrar corte de caja: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar corte de caja: {str(e)}"
        )

@router.get("/historial", response_model=List[Dict[str, Any]])
def historial_cortes(
    limit: int = Query(50, ge=1, le=200),
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """Lista los cortes de caja previos del tenant en sesión (exclusivo para rol Dueño)."""
    return crud.get_cortes_caja(limit=limit, tenant_id=tenant.tenant_id)
