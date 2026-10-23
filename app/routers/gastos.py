"""
app/routers/gastos.py - Control de Gastos Operativos y Ganancia Neta Real.
Aislamiento estricto Multi-Tenant y acceso exclusivo para rol 'dueno'.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, status, Depends
from app import crud
from app.models import GastoCreate, GastoResponse
from app.security import require_role, get_current_tenant
from app.dependencies import TenantContext

router = APIRouter(prefix="/api/gastos", tags=["Gastos Operativos"])


@router.get("", response_model=List[GastoResponse])
def listar_gastos(
    mes: Optional[str] = Query(None, description="Filtrar por mes en formato YYYY-MM"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Lista todos los gastos operativos del tenant_id en sesión con filtros opcionales.
    Exclusivo para Dueño.
    """
    try:
        return crud.get_gastos(
            tenant_id=tenant.tenant_id,
            mes=mes,
            categoria=categoria,
            sucursal_id=tenant.sucursal_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener gastos: {str(e)}"
        )


@router.get("/resumen")
def resumen_gastos(
    mes: Optional[str] = Query(None, description="Mes en formato YYYY-MM"),
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
) -> Dict[str, Any]:
    """
    Retorna el resumen mensual de gastos y su desglose por categoría.
    Exclusivo para Dueño.
    """
    try:
        return crud.get_resumen_gastos(tenant_id=tenant.tenant_id, mes=mes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener resumen de gastos: {str(e)}"
        )


@router.post("", response_model=GastoResponse, status_code=status.HTTP_201_CREATED)
def registrar_gasto(
    datos: GastoCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Registra un nuevo gasto operativo asignando el tenant_id de la sesión.
    Exclusivo para Dueño.
    """
    try:
        nuevo = crud.crear_gasto(
            datos=datos.model_dump(),
            usuario_nombre=user.get("nombre") or user.get("username", "Admin"),
            tenant_id=tenant.tenant_id,
            sucursal_id=tenant.sucursal_id
        )
        return nuevo
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar gasto: {str(e)}"
        )


@router.delete("/{gasto_id}", status_code=status.HTTP_200_OK)
def borrar_gasto(
    gasto_id: int,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Elimina un gasto operativo previa verificación de pertenencia al tenant.
    Exclusivo para Dueño.
    """
    try:
        eliminado = crud.eliminar_gasto(gasto_id, tenant_id=tenant.tenant_id)
        if not eliminado:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Gasto no encontrado o no pertenece a su sucursal."
            )
        return {"ok": True, "mensaje": "Gasto eliminado correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar gasto: {str(e)}"
        )
