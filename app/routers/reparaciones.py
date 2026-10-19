from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional
from app import crud
from app.models import ReparacionCreate, ReparacionUpdate, ReparacionResponse, ReparacionAbono
from app.security import get_current_user, require_role, sanitizar_datos_sensibles

router = APIRouter(prefix="/api/reparaciones", tags=["Reparaciones y Taller"])

@router.get("", response_model=List[ReparacionResponse])
def listar_reparaciones(
    estado: Optional[str] = Query(None, max_length=40, description="Filtrar por estado: Recibido, En Revision, Esperando Refaccion, Listo para Entrega, Entregado, Cancelado"),
    search: Optional[str] = Query(None, max_length=100, description="Búsqueda por folio, cliente, teléfono, modelo o IMEI"),
    user: dict = Depends(get_current_user)
):
    """Obtiene la lista de órdenes de servicio / reparaciones del taller. Oculta costos de refacción si no es dueño."""
    items = crud.get_reparaciones(estado=estado, search=search)
    return sanitizar_datos_sensibles(items, user)

@router.get("/{rep_id}", response_model=ReparacionResponse)
def obtener_reparacion(rep_id: int, user: dict = Depends(get_current_user)):
    rep = crud.get_reparacion_by_id(rep_id)
    if not rep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
    return sanitizar_datos_sensibles(rep, user)

@router.post("", response_model=ReparacionResponse, status_code=status.HTTP_201_CREATED)
def registrar_reparacion(datos: ReparacionCreate, user: dict = Depends(get_current_user)):
    try:
        nueva = crud.create_reparacion(datos.model_dump())
        return sanitizar_datos_sensibles(nueva, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al registrar la orden de reparación.")

@router.put("/{rep_id}", response_model=ReparacionResponse)
def actualizar_reparacion(rep_id: int, datos: ReparacionUpdate, user: dict = Depends(require_role("dueno"))):
    try:
        actualizada = crud.update_reparacion(rep_id, datos.model_dump(exclude_unset=True))
        if not actualizada:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
        return sanitizar_datos_sensibles(actualizada, user)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al actualizar la orden de reparación.")

@router.patch("/{rep_id}/estado", response_model=ReparacionResponse)
def cambiar_estado(rep_id: int, nuevo_estado: str = Query(..., max_length=40, description="Nuevo estado del equipo"), user: dict = Depends(get_current_user)):
    try:
        actualizada = crud.cambiar_estado_reparacion(rep_id, nuevo_estado)
        if not actualizada:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
        return sanitizar_datos_sensibles(actualizada, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{rep_id}/abono", response_model=ReparacionResponse)
def registrar_abono(rep_id: int, datos: ReparacionAbono, user: dict = Depends(get_current_user)):
    try:
        actualizada = crud.abonar_reparacion(rep_id, datos.monto_abono)
        if not actualizada:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
        return sanitizar_datos_sensibles(actualizada, user)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al registrar el abono.")

@router.delete("/{rep_id}", status_code=status.HTTP_200_OK)
def eliminar_reparacion(rep_id: int, user: dict = Depends(require_role("dueno"))):
    exito = crud.delete_reparacion(rep_id)
    if not exito:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
    return {"mensaje": "Orden de reparación eliminada con éxito"}
