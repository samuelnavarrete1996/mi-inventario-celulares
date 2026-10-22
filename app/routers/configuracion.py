import os
import time
from fastapi import APIRouter, HTTPException, UploadFile, File, status, Depends, Query
from typing import Dict, Any, Optional
from app import crud
from app.models import ConfiguracionGeneralUpdate, ConfiguracionGeneralResponse
from app.security import get_current_user, require_role, get_current_tenant
from app.dependencies import TenantContext
from app.database import get_db_connection

router = APIRouter(prefix="/api/configuracion", tags=["Configuración y Marca Blanca"])

MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "uploads", "logos")

@router.get("", response_model=ConfiguracionGeneralResponse)
def obtener_configuracion_tienda(tenant: TenantContext = Depends(get_current_tenant)):
    """
    Obtiene los datos de 'configuracion_tienda', datos generales del tenant y sucursal matriz.
    Accesible para usuarios autenticados de la empresa.
    """
    try:
        return crud.get_configuracion_general(tenant.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al obtener configuración: {str(e)}")

@router.get("/publica")
def obtener_configuracion_publica(slug: Optional[str] = Query(None, description="Slug del tenant")):
    """
    Endpoint público consumido por el catálogo web (catalogo.html) para marca blanca sin autenticación.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if slug:
            cur.execute("SELECT id FROM tenants WHERE slug = ? AND (activo IS TRUE OR activo = TRUE) LIMIT 1;", (slug.strip(),))
            t_row = cur.fetchone()
            tenant_id = t_row["id"] if t_row else None
        else:
            cur.execute("SELECT id FROM tenants WHERE (activo IS TRUE OR activo = TRUE) ORDER BY id ASC LIMIT 1;")
            t_row = cur.fetchone()
            tenant_id = t_row["id"] if t_row else 1

        if not tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tienda no encontrada.")

        return crud.get_configuracion_general(tenant_id)
    finally:
        conn.close()

@router.put("", response_model=ConfiguracionGeneralResponse)
def actualizar_configuracion_tienda(
    datos: ConfiguracionGeneralUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Actualiza nombre comercial, teléfono/WhatsApp, dirección física, encabezado de ticket y texto de políticas de garantía.
    Exclusivo para rol 'dueno' del tenant en sesión.
    """
    try:
        actualizada = crud.update_configuracion_general(tenant.tenant_id, datos.model_dump(exclude_unset=True))
        return actualizada
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al actualizar configuración: {str(e)}")

@router.post("/logo")
async def subir_logotipo_tienda(
    file: UploadFile = File(...),
    tenant: TenantContext = Depends(get_current_tenant),
    user: dict = Depends(require_role("dueno"))
):
    """
    Sube el logotipo de la tienda. Valida tipo MIME (PNG, JPG, WEBP), tamaño máximo de 2 MB
    y lo almacena de forma segura en app/static/uploads/logos/{tenant_id}_logo.png, actualizando 'logo_url'.
    Exclusivo para rol 'dueno'.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se recibió ningún archivo.")

    # 1. Validar extensión y MIME type
    ext = os.path.splitext(file.filename)[1].lower()
    content_type = (file.content_type or "").lower()

    if ext not in ALLOWED_EXTENSIONS or (content_type and content_type not in ALLOWED_MIME_TYPES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de imagen no permitido. Solo se aceptan archivos PNG, JPG o WEBP."
        )

    # 2. Validar tamaño máximo (2 MB)
    contenido = await file.read(MAX_LOGO_SIZE_BYTES + 1)
    if not contenido:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo subido está vacío.")

    if len(contenido) > MAX_LOGO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El logotipo excede el tamaño máximo permitido de 2 MB."
        )

    # 3. Guardar archivo en disco
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename_guardado = f"{tenant.tenant_id}_logo.png"
    filepath = os.path.join(UPLOAD_DIR, filename_guardado)

    with open(filepath, "wb") as f:
        f.write(contenido)

    # 4. Actualizar logo_url con parámetro de versión anti-caché
    logo_url = f"/static/uploads/logos/{filename_guardado}?v={int(time.time())}"
    crud.update_logo_tienda(tenant.tenant_id, logo_url)

    return {
        "mensaje": "Logotipo de tienda actualizado exitosamente.",
        "logo_url": logo_url
    }
