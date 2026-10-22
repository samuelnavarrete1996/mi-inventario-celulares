"""
app/routers/empleados.py - Gestión de Empleados y Cajeros Multi-Tenant.
Control de acceso exclusivo para rol 'dueno'.
Permite crear cuentas para vendedores y técnicos, listarlas y suspender/reactivar accesos.
"""

from typing import List
from fastapi import APIRouter, HTTPException, status, Depends
from app import crud
from app.models import EmpleadoCreate, EmpleadoEstadoUpdate, EmpleadoResponse
from app.security import require_role, get_current_tenant
from app.dependencies import TenantContext

router = APIRouter(prefix="/api/empleados", tags=["Gestión de Empleados y Cajeros"])


@router.get("", response_model=List[EmpleadoResponse])
def listar_empleados(
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Lista todos los empleados y usuarios pertenecientes al tenant_id en sesión.
    Exclusivo para rol 'dueno'.
    """
    try:
        return crud.get_empleados(tenant.tenant_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar empleados: {str(e)}"
        )


@router.post("", response_model=EmpleadoResponse, status_code=status.HTTP_201_CREATED)
def crear_empleado(
    datos: EmpleadoCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Crea un nuevo usuario con rol 'vendedor' o 'tecnico'.
    Valida username único, asigna automáticamente tenant_id y sucursal_id de la sesión,
    y genera hash Argon2id seguro.
    """
    try:
        nuevo = crud.create_empleado(
            nombre=datos.nombre,
            username=datos.username,
            password=datos.password,
            rol=datos.rol,
            tenant_id=tenant.tenant_id,
            sucursal_id=tenant.sucursal_id
        )
        return nuevo
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar empleado: {str(e)}"
        )


@router.put("/{empleado_id}/estado", response_model=EmpleadoResponse)
def cambiar_estado_empleado(
    empleado_id: int,
    datos: EmpleadoEstadoUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Permite activar o desactivar un empleado (activo=True/False) sin eliminar su registro,
    garantizando el historial de ventas y reparaciones.
    Valida pertenencia al tenant en sesión y evita la auto-desactivación de la cuenta de dueño.
    """
    # Evitar auto-desactivación de la cuenta con la que se tiene sesión activa
    current_uid = user.get("id") or user.get("user_id")
    if current_uid == empleado_id and not datos.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes suspender tu propia cuenta de dueño en sesión."
        )

    # Verificar existencia y aislamiento del empleado
    empleado = crud.get_empleado_by_id(empleado_id, tenant.tenant_id)
    if not empleado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El empleado no fue encontrado en su empresa o pertenece a otro negocio."
        )

    # Evitar desactivar cualquier cuenta con rol dueno
    if empleado.get("rol") == "dueno" and not datos.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede suspender una cuenta principal con rol Dueño."
        )

    try:
        actualizado = crud.update_empleado_estado(empleado_id, datos.activo, tenant.tenant_id)
        if not actualizado:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El empleado no fue encontrado."
            )
        return actualizado
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al modificar el estado del empleado: {str(e)}"
        )
