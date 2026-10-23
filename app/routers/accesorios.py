import os
import time
import uuid
import logging
from fastapi import APIRouter, HTTPException, Query, status, Depends, UploadFile, File, Response
from typing import List, Optional, Dict, Any
from app import crud
from app.models import (
    AccesorioCreate, AccesorioUpdate, AccesorioResponse,
    AccesorioAjusteStockRequest, AccesorioActualizacionMasivaRequest, MovimientoStockResponse
)
from app.security import get_current_user, require_role, sanitizar_datos_sensibles, get_current_tenant
from app.dependencies import TenantContext
from app.excel_importer import (
    generar_plantilla_stock_accesorios_excel,
    generar_plantilla_stock_accesorios_csv,
    importar_stock_accesorios_excel
)
from app.routers.configuracion import validar_y_sanitizar_imagen

logger = logging.getLogger("inventario.accesorios")

router = APIRouter(prefix="/api/accesorios", tags=["Accesorios y Servicios"])

MAX_STOCK_EXCEL_BYTES = 25 * 1024 * 1024  # Límite de 25 MB para archivos de stock
MAX_ARTICULO_FOTO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_FOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_FOTO_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

@router.get("", response_model=List[AccesorioResponse])
def listar_accesorios(
    categoria: Optional[str] = Query(None, max_length=80, description="Filtrar por categoría"),
    solo_con_stock: bool = Query(False, description="Mostrar solo items con stock disponible o servicios"),
    search: Optional[str] = Query(None, max_length=100, description="Búsqueda por nombre"),
    q: Optional[str] = Query(None, max_length=100, description="Alias de búsqueda por código o nombre"),
    tenant: TenantContext = Depends(get_current_tenant)
):
    """Obtiene el catálogo de accesorios y servicios/reparaciones del tenant en sesión. Oculta costos si no es dueño."""
    termino = search if search is not None else q
    items = crud.get_accesorios(categoria=categoria, solo_con_stock=solo_con_stock, search=termino, tenant_id=tenant.tenant_id)
    return sanitizar_datos_sensibles(items, tenant.user)

# --- CARGA MASIVA Y EXCEL (PILAR 1) ---

@router.get("/plantilla-stock")
def descargar_plantilla_stock(
    formato: Optional[str] = Query(None, description="Formato: 'sheets' o 'csv' para Google Sheets, 'xlsx' para Excel"),
    con_catalogo: bool = Query(False, description="Si es True, incluye el catálogo completo. Por defecto False (solo encabezados)"),
    user: dict = Depends(require_role("dueno")),
    tenant: TenantContext = Depends(get_current_tenant)
):
    """Descarga la plantilla de accesorios con los 9 encabezados solicitados (ID, Nombre, Color, Categoría, Stock Actual, NUEVO STOCK, Menudeo, Mayoreo, Caja)."""
    try:
        solo_enc = not con_catalogo
        if formato in ("sheets", "csv"):
            contenido = generar_plantilla_stock_accesorios_csv(solo_encabezados=solo_enc, tenant_id=tenant.tenant_id)
            return Response(
                content=contenido,
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=Plantilla_Accesorios_GoogleSheets.csv"}
            )
        else:
            excel_bytes = generar_plantilla_stock_accesorios_excel(solo_encabezados=solo_enc, tenant_id=tenant.tenant_id)
            return Response(
                content=excel_bytes,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=Plantilla_Accesorios_Excel.xlsx"}
            )
    except Exception as e:
        logger.error("Error generando plantilla: %s", repr(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error generando plantilla.")

@router.get("/plantilla-sheets")
def descargar_plantilla_stock_sheets(
    con_catalogo: bool = Query(False, description="Si es True, incluye el catálogo completo. Por defecto False (solo encabezados)"),
    user: dict = Depends(require_role("dueno")),
    tenant: TenantContext = Depends(get_current_tenant)
):
    """Descarga la plantilla de accesorios optimizada directamente para Google Sheets (.csv UTF-8 con BOM)."""
    try:
        solo_enc = not con_catalogo
        contenido = generar_plantilla_stock_accesorios_csv(solo_encabezados=solo_enc, tenant_id=tenant.tenant_id)
        return Response(
            content=contenido,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=Plantilla_Accesorios_GoogleSheets.csv"}
        )
    except Exception as e:
        logger.error("Error generando plantilla Google Sheets: %s", repr(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error generando plantilla Google Sheets.")

@router.post("/importar-stock-excel")
async def importar_stock_excel(
    archivo: Optional[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """Procesa el archivo de Google Sheets (.csv) o Excel (.xlsx) cargado con nuevo stock y actualiza registrando Kardex."""
    target_file = archivo or file
    if not target_file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se recibió ningún archivo para procesar.")

    if not target_file.filename or not target_file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe ser una hoja de Google Sheets (.csv) o Excel (.xlsx)")
    
    contenido = await target_file.read(MAX_STOCK_EXCEL_BYTES + 1)
    if len(contenido) > MAX_STOCK_EXCEL_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="El archivo supera el límite de 25 MB.")

    try:
        res = importar_stock_accesorios_excel(
            contenido,
            filename=target_file.filename,
            usuario=user.get("nombre") or user.get("username") or "Dueño",
            tenant_id=tenant.tenant_id,
            sucursal_id=tenant.sucursal_id
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al procesar archivo de stock: %s", repr(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al procesar el archivo.")

@router.post("/actualizacion-masiva-rapida")
def actualizacion_masiva_rapida(
    datos: AccesorioActualizacionMasivaRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """Actualización masiva directa desde la interfaz interactiva web / tabla rápida."""
    items = [it.model_dump() for it in datos.items]
    res = crud.actualizar_stock_masivo(
        items=items,
        motivo_general=datos.motivo or "Actualización masiva rápida",
        usuario=user.get("nombre") or user.get("username") or "Dueño",
        tenant_id=tenant.tenant_id
    )
    return res

# --- INTELIGENCIA DE COMPRAS Y REABASTECIMIENTO (PILAR 4) ---

@router.get("/sugerido-reabastecimiento")
def obtener_sugerido_reabastecimiento(
    stock_objetivo: int = Query(10, ge=1, le=1000, description="Nivel de stock deseado al reordenar"),
    stock_minimo: int = Query(3, ge=0, le=500, description="Umbral de stock bajo"),
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """Analiza accesorios con stock bajo o agotados y genera lista de compras sugeridas y formato para WhatsApp."""
    return crud.generar_sugerido_reabastecimiento(stock_objetivo=stock_objetivo, stock_minimo=stock_minimo, tenant_id=tenant.tenant_id)

# --- KARDEX Y AUDITORÍA DE MOVIMIENTOS (PILAR 5) ---

@router.get("/kardex", response_model=List[MovimientoStockResponse])
def obtener_kardex_general(
    tipo: Optional[str] = Query(None, description="Filtrar por ENTRADA, VENTA, MERMA, AJUSTE, MUESTRA"),
    limit: int = Query(150, ge=1, le=500),
    tenant: TenantContext = Depends(get_current_tenant)
):
    """Obtiene la bitácora de movimientos de stock para auditoría y prevención de robo hormiga."""
    return crud.get_historial_kardex_accesorios(acc_id=None, tipo=tipo, limit=limit, tenant_id=tenant.tenant_id)

@router.post("/{acc_id}/ajuste-stock", response_model=AccesorioResponse)
def ajustar_stock_individual(
    acc_id: int,
    datos: AccesorioAjusteStockRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """Ajusta el stock de un accesorio con motivo obligatorio para control de mermas y auditoría."""
    try:
        acc = crud.ajustar_stock_accesorio(
            acc_id=acc_id,
            nuevo_stock=datos.nuevo_stock,
            tipo_movimiento=datos.tipo_movimiento,
            motivo=datos.motivo,
            usuario=user.get("nombre") or user.get("username") or "Dueño",
            tenant_id=tenant.tenant_id
        )
        if not acc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
        return sanitizar_datos_sensibles(acc, user)
    except HTTPException:
        raise
    except ValueError as e:
        msg = str(e)
        if "no encontrado o no pertenece" in msg or "no existe" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except Exception as e:
        logger.error("Error interno al ajustar stock: %s", repr(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al ajustar el stock.")

@router.get("/{acc_id}/kardex", response_model=List[MovimientoStockResponse])
def obtener_kardex_accesorio(
    acc_id: int,
    tenant: TenantContext = Depends(get_current_tenant)
):
    """Obtiene la bitácora de movimientos específica de un accesorio."""
    return crud.get_historial_kardex_accesorios(acc_id=acc_id, limit=50, tenant_id=tenant.tenant_id)

# --- CRUD BÁSICO DE ACCESORIOS ---

@router.get("/{acc_id}", response_model=AccesorioResponse)
def obtener_accesorio(
    acc_id: int,
    tenant: TenantContext = Depends(get_current_tenant)
):
    acc = crud.get_accesorio_by_id(acc_id, tenant_id=tenant.tenant_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
    return sanitizar_datos_sensibles(acc, tenant.user)

MAX_ARTICULO_FOTO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_FOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_FOTO_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}

@router.post("/foto")
async def subir_foto_accesorio(
    file: UploadFile = File(...),
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Sube una fotografía de accesorio o artículo.
    Valida formato (PNG, JPG, JPEG, WEBP), tamaño (máx 5 MB) y la guarda de forma segura en:
    app/static/uploads/articulos/{tenant_id}_{uuid}.ext
    Retorna la URL relativa para almacenar en el campo imagen_url del artículo.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se seleccionó ningún archivo.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext == ".jpeg":
        ext = ".jpg"
    content_type = (file.content_type or "").lower()

    if ext not in ALLOWED_FOTO_EXTENSIONS or (content_type and content_type not in ALLOWED_FOTO_MIME_TYPES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de imagen no permitido. Solo se aceptan archivos PNG, JPG o WEBP."
        )

    contenido = await file.read(MAX_ARTICULO_FOTO_SIZE_BYTES + 1)
    if not contenido:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío.")

    if len(contenido) > MAX_ARTICULO_FOTO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="La imagen excede el tamaño máximo permitido de 5 MB."
        )

    try:
        contenido_limpio = validar_y_sanitizar_imagen(
            contenido=contenido,
            ext=ext,
            content_type=content_type,
            target_format="PNG" if ext == ".png" else "JPEG"
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error("Error sanitizando imagen de accesorio: %s", repr(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al procesar la imagen.")

    # Crear carpeta uploads/articulos si no existe
    uploads_articulos_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "uploads", "articulos"
    )
    os.makedirs(uploads_articulos_dir, exist_ok=True)

    unique_suffix = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    filename_guardado = f"{tenant.tenant_id}_{unique_suffix}{ext}"
    filepath = os.path.join(uploads_articulos_dir, filename_guardado)

    with open(filepath, "wb") as f:
        f.write(contenido_limpio)

    imagen_url = f"/static/uploads/articulos/{filename_guardado}"
    return {
        "success": True,
        "imagen_url": imagen_url,
        "mensaje": "Fotografía subida exitosamente."
    }

@router.post("", response_model=AccesorioResponse, status_code=status.HTTP_201_CREATED)
def crear_accesorio(
    datos: AccesorioCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
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
            imagen_url=datos.imagen_url,
            color=datos.color,
            tenant_id=tenant.tenant_id,
            sucursal_id=tenant.sucursal_id
        )
        return sanitizar_datos_sensibles(nuevo, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al registrar accesorio: %s", repr(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al registrar el accesorio.")

@router.put("/{acc_id}", response_model=AccesorioResponse)
def actualizar_accesorio(
    acc_id: int,
    datos: AccesorioUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    try:
        actualizado = crud.update_accesorio(
            acc_id,
            datos.model_dump(exclude_unset=True),
            tenant_id=tenant.tenant_id
        )
        if not actualizado:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
        return sanitizar_datos_sensibles(actualizado, user)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al actualizar accesorio %s: %s", acc_id, repr(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al actualizar el accesorio.")

@router.delete("/{acc_id}", status_code=status.HTTP_200_OK)
def eliminar_accesorio(
    acc_id: int,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    exito = crud.delete_accesorio(acc_id, tenant_id=tenant.tenant_id)
    if not exito:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accesorio no encontrado")
    return {"mensaje": "Accesorio eliminado con éxito"}
