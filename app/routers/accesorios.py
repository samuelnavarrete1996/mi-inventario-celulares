from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional
from app import crud
from app.models import AccesorioCreate, AccesorioUpdate, AccesorioResponse
from app.security import get_current_user, require_role, sanitizar_datos_sensibles

router = APIRouter(prefix="/api/accesorios", tags=["Accesorios y Servicios"])

@router.get("", response_model=List[AccesorioResponse])
def listar_accesorios(
    categoria: Optional[str] = Query(None, max_length=80, description="Filtrar por categoría"),
    solo_con_stock: bool = Query(False, description="Mostrar solo items con stock disponible o servicios"),
    search: Optional[str] = Query(None, max_length=100, description="Búsqueda por nombre"),
    q: Optional[str] = Query(None, max_length=100, description="Alias de búsqueda por código o nombre"),
    user: dict = Depends(get_current_user)
):
    """Obtiene el catálogo de accesorios y servicios/reparaciones. Oculta costos si no es dueño."""
    termino = search if search is not None else q
    items = crud.get_accesorios(categoria=categoria, solo_con_stock=solo_con_stock, search=termino)
    return sanitizar_datos_sensibles(items, user)

@router.get("/{acc_id}", response_model=AccesorioResponse)
def obtener_accesorio(acc_id: int, user: dict = Depends(get_current_user)):
    acc = crud.get_accesorio_by_id(acc_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
    return sanitizar_datos_sensibles(acc, user)

@router.post("", response_model=AccesorioResponse, status_code=status.HTTP_201_CREATED)
def crear_accesorio(datos: AccesorioCreate, user: dict = Depends(require_role("dueno"))):
    try:
        nuevo = crud.create_accesorio(
            nombre=datos.nombre,
            categoria=datos.categoria,
            costo_compra=datos.costo_compra,
            precio_venta=datos.precio_venta,
            stock=datos.stock,
            es_servicio=datos.es_servicio,
            codigo_barras=datos.codigo_barras,
            precio_mayoreo=datos.precio_mayoreo or datos.precio_venta,
            precio_20_pzs=datos.precio_20_pzs or datos.precio_mayoreo or datos.precio_venta,
            precio_caja=datos.precio_caja or datos.costo_compra,
            imagen_url=datos.imagen_url
        )
        return sanitizar_datos_sensibles(nuevo, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al registrar el accesorio.")

@router.put("/{acc_id}", response_model=AccesorioResponse)
def actualizar_accesorio(acc_id: int, datos: AccesorioUpdate, user: dict = Depends(require_role("dueno"))):
    try:
        actualizado = crud.update_accesorio(acc_id, datos.model_dump(exclude_unset=True))
        if not actualizado:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
        return sanitizar_datos_sensibles(actualizado, user)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al actualizar el accesorio.")

@router.delete("/{acc_id}", status_code=status.HTTP_200_OK)
def eliminar_accesorio(acc_id: int, user: dict = Depends(require_role("dueno"))):
    exito = crud.delete_accesorio(acc_id)
    if not exito:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
    return {"mensaje": "Accesorio eliminado con éxito"}
