from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
from app import crud
from app.models import AccesorioCreate, AccesorioUpdate, AccesorioResponse

router = APIRouter(prefix="/api/accesorios", tags=["Accesorios y Servicios"])

@router.get("", response_model=List[AccesorioResponse])
def listar_accesorios(
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    solo_con_stock: bool = Query(False, description="Mostrar solo items con stock disponible o servicios"),
    search: Optional[str] = Query(None, description="Búsqueda por nombre")
):
    """Obtiene el catálogo de accesorios y servicios/reparaciones."""
    return crud.get_accesorios(categoria=categoria, solo_con_stock=solo_con_stock, search=search)

@router.get("/{acc_id}", response_model=AccesorioResponse)
def obtener_accesorio(acc_id: int):
    acc = crud.get_accesorio_by_id(acc_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
    return acc

@router.post("", response_model=AccesorioResponse, status_code=status.HTTP_201_CREATED)
def crear_accesorio(datos: AccesorioCreate):
    try:
        nuevo = crud.create_accesorio(
            nombre=datos.nombre,
            categoria=datos.categoria,
            costo_compra=datos.costo_compra,
            precio_venta=datos.precio_venta,
            stock=datos.stock,
            es_servicio=datos.es_servicio,
            codigo_barras=datos.codigo_barras
        )
        return nuevo
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.put("/{acc_id}", response_model=AccesorioResponse)
def actualizar_accesorio(acc_id: int, datos: AccesorioUpdate):
    actualizado = crud.update_accesorio(acc_id, datos.model_dump(exclude_unset=True))
    if not actualizado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
    return actualizado

@router.delete("/{acc_id}", status_code=status.HTTP_200_OK)
def eliminar_accesorio(acc_id: int):
    exito = crud.delete_accesorio(acc_id)
    if not exito:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
    return {"mensaje": "Accesorio eliminado con éxito"}
