from fastapi import APIRouter, HTTPException, Query, status, Depends, UploadFile, File, Response
from typing import List, Optional, Dict, Any
from app import crud
from app.models import (
    AccesorioCreate, AccesorioUpdate, AccesorioResponse,
    AccesorioAjusteStockRequest, AccesorioActualizacionMasivaRequest, MovimientoStockResponse
)
from app.security import get_current_user, require_role, sanitizar_datos_sensibles
from app.excel_importer import generar_plantilla_stock_accesorios_excel, importar_stock_accesorios_excel

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

# --- CARGA MASIVA Y EXCEL (PILAR 1) ---

@router.get("/plantilla-stock")
def descargar_plantilla_stock(user: dict = Depends(require_role("dueno"))):
    """Descarga un archivo Excel (.xlsx) con los 283 accesorios para conteo y carga masiva de stock."""
    try:
        excel_bytes = generar_plantilla_stock_accesorios_excel()
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=Carga_Stock_Accesorios_SamuelNavarrete.xlsx"}
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error generando plantilla Excel: {str(e)}")

@router.post("/importar-stock-excel")
async def importar_stock_excel(archivo: UploadFile = File(...), user: dict = Depends(require_role("dueno"))):
    """Procesa el Excel cargado con nuevo stock y actualiza de forma masiva registrando el Kardex."""
    if not archivo.filename or not archivo.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe ser un libro de Excel (.xlsx)")
    
    contenido = await archivo.read()
    if len(contenido) > 25 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="El archivo supera el límite de 25 MB.")

    try:
        res = importar_stock_accesorios_excel(contenido, usuario=user.get("nombre") or user.get("username") or "Dueño")
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al procesar el archivo Excel: {str(e)}")

@router.post("/actualizacion-masiva-rapida")
def actualizacion_masiva_rapida(datos: AccesorioActualizacionMasivaRequest, user: dict = Depends(require_role("dueno"))):
    """Actualización masiva directa desde la interfaz interactiva web / tabla rápida."""
    items = [it.model_dump() for it in datos.items]
    res = crud.actualizar_stock_masivo(
        items=items,
        motivo_general=datos.motivo or "Actualización masiva rápida",
        usuario=user.get("nombre") or user.get("username") or "Dueño"
    )
    return res

# --- INTELIGENCIA DE COMPRAS Y REABASTECIMIENTO (PILAR 4) ---

@router.get("/sugerido-reabastecimiento")
def obtener_sugerido_reabastecimiento(
    stock_objetivo: int = Query(10, ge=1, le=1000, description="Nivel de stock deseado al reordenar"),
    stock_minimo: int = Query(3, ge=0, le=500, description="Umbral de stock bajo"),
    user: dict = Depends(require_role("dueno"))
):
    """Analiza accesorios con stock bajo o agotados y genera lista de compras sugeridas y formato para WhatsApp."""
    return crud.generar_sugerido_reabastecimiento(stock_objetivo=stock_objetivo, stock_minimo=stock_minimo)

# --- KARDEX Y AUDITORÍA DE MOVIMIENTOS (PILAR 5) ---

@router.get("/kardex", response_model=List[MovimientoStockResponse])
def obtener_kardex_general(
    tipo: Optional[str] = Query(None, description="Filtrar por ENTRADA, VENTA, MERMA, AJUSTE, MUESTRA"),
    limit: int = Query(150, ge=1, le=500),
    user: dict = Depends(get_current_user)
):
    """Obtiene la bitácora de movimientos de stock para auditoría y prevención de robo hormiga."""
    return crud.get_historial_kardex_accesorios(acc_id=None, tipo=tipo, limit=limit)

@router.post("/{acc_id}/ajuste-stock", response_model=AccesorioResponse)
def ajustar_stock_individual(acc_id: int, datos: AccesorioAjusteStockRequest, user: dict = Depends(require_role("dueno"))):
    """Ajusta el stock de un accesorio con motivo obligatorio para control de mermas y auditoría."""
    try:
        acc = crud.ajustar_stock_accesorio(
            acc_id=acc_id,
            nuevo_stock=datos.nuevo_stock,
            tipo_movimiento=datos.tipo_movimiento,
            motivo=datos.motivo,
            usuario=user.get("nombre") or user.get("username") or "Dueño"
        )
        return sanitizar_datos_sensibles(acc, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno al ajustar el stock: {str(e)}")

@router.get("/{acc_id}/kardex", response_model=List[MovimientoStockResponse])
def obtener_kardex_accesorio(acc_id: int, user: dict = Depends(get_current_user)):
    """Obtiene la bitácora de movimientos específica de un accesorio."""
    return crud.get_historial_kardex_accesorios(acc_id=acc_id, limit=50)

# --- CRUD BÁSICO DE ACCESORIOS ---

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
