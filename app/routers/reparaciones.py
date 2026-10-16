from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
from app import crud
from app.models import ReparacionCreate, ReparacionUpdate, ReparacionResponse, ReparacionAbono

router = APIRouter(prefix="/api/reparaciones", tags=["Reparaciones y Taller"])

@router.get("", response_model=List[ReparacionResponse])
def listar_reparaciones(
    estado: Optional[str] = Query(None, description="Filtrar por estado: Recibido, En Revision, Esperando Refaccion, Listo para Entrega, Entregado, Cancelado"),
    search: Optional[str] = Query(None, description="Búsqueda por folio, cliente, teléfono, modelo o IMEI")
):
    """Obtiene la lista de órdenes de servicio / reparaciones del taller."""
    return crud.get_reparaciones(estado=estado, search=search)

@router.get("/{rep_id}", response_model=ReparacionResponse)
def obtener_reparacion(rep_id: int):
    rep = crud.get_reparacion_by_id(rep_id)
    if not rep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
    return rep

@router.post("", response_model=ReparacionResponse, status_code=status.HTTP_201_CREATED)
def registrar_reparacion(datos: ReparacionCreate):
    try:
        nueva = crud.create_reparacion(datos.model_dump())
        return nueva
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.put("/{rep_id}", response_model=ReparacionResponse)
def actualizar_reparacion(rep_id: int, datos: ReparacionUpdate):
    actualizada = crud.update_reparacion(rep_id, datos.model_dump(exclude_unset=True))
    if not actualizada:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
    return actualizada

@router.patch("/{rep_id}/estado", response_model=ReparacionResponse)
def cambiar_estado(rep_id: int, nuevo_estado: str = Query(..., description="Nuevo estado del equipo")):
    try:
        actualizada = crud.cambiar_estado_reparacion(rep_id, nuevo_estado)
        if not actualizada:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
        return actualizada
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{rep_id}/abono", response_model=ReparacionResponse)
def registrar_abono(rep_id: int, datos: ReparacionAbono):
    actualizada = crud.abonar_reparacion(rep_id, datos.monto_abono)
    if not actualizada:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
    return actualizada

@router.delete("/{rep_id}", status_code=status.HTTP_200_OK)
def eliminar_reparacion(rep_id: int):
    exito = crud.delete_reparacion(rep_id)
    if not exito:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de reparación no encontrada")
    return {"mensaje": "Orden de reparación eliminada con éxito"}
