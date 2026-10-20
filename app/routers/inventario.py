import os
import hmac
from fastapi import APIRouter, HTTPException, Query, Header, UploadFile, File, Response, status, Depends
from typing import List, Optional
from app import crud
from app.models import EquipoCreate, EquipoUpdate, EquipoResponse
from app.excel_importer import (
    procesar_archivo_excel_o_csv,
    guardar_equipos_importados,
    generar_plantilla_excel_bytes,
    generar_plantilla_celulares_csv
)
from app.security import (
    get_current_user,
    require_role,
    is_user_dueno,
    sanitizar_datos_sensibles
)

router = APIRouter(prefix="/api/equipos", tags=["Inventario"])

MAX_EXCEL_UPLOAD_BYTES = 10 * 1024 * 1024  # Límite de 10 MB para evitar DoS por agotamiento de memoria

def verify_delete_password(entered_token: Optional[str]) -> bool:
    """Verifica en tiempo constante si el token ingresado coincide con ADMIN_DELETE_PASSWORD."""
    if not entered_token:
        return False
    env_pwd = os.environ.get("ADMIN_DELETE_PASSWORD", "samuelykim.")
    token_clean = entered_token.strip()
    c1 = hmac.compare_digest(token_clean.encode("utf-8"), env_pwd.encode("utf-8"))
    c2 = hmac.compare_digest(token_clean.encode("utf-8"), env_pwd.rstrip(".").encode("utf-8"))
    c3 = hmac.compare_digest((token_clean + ".").encode("utf-8"), env_pwd.encode("utf-8"))
    return c1 or c2 or c3

@router.get("", response_model=List[EquipoResponse])
def listar_equipos(
    solo_disponibles: bool = Query(True, description="Mostrar solo equipos con estado 'Disponible'"),
    search: Optional[str] = Query(None, max_length=100, description="Búsqueda por modelo, IMEI o color"),
    grado: Optional[str] = Query(None, max_length=5, description="Filtrar por grado: A, B o C"),
    user: dict = Depends(get_current_user)
):
    """Obtiene la lista de equipos en inventario. Oculta costos confidenciales si no es dueño."""
    equipos = crud.get_equipos(solo_disponibles=solo_disponibles, search=search, grado=grado)
    return sanitizar_datos_sensibles(equipos, user)

@router.post("", response_model=EquipoResponse, status_code=status.HTTP_201_CREATED)
def registrar_equipo(
    equipo: EquipoCreate,
    user: dict = Depends(require_role("dueno"))
):
    """Registra un nuevo teléfono en el inventario. Exclusivo para rol Dueño."""
    try:
        nuevo = crud.create_equipo(equipo)
        return sanitizar_datos_sensibles(nuevo, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al registrar el equipo.")

@router.get("/plantilla-excel")
def descargar_plantilla_excel(
    formato: Optional[str] = Query(None, description="Formato: 'sheets' o 'csv' para Google Sheets, 'xlsx' para Excel"),
    user: dict = Depends(require_role("dueno"))
):
    """Descarga una plantilla preformateada para carga masiva de celulares compatible con Google Sheets y Excel."""
    if formato in ("sheets", "csv"):
        contenido = generar_plantilla_celulares_csv()
        return Response(
            content=contenido,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=plantilla_celulares_google_sheets.csv"}
        )
    else:
        contenido = generar_plantilla_excel_bytes()
        return Response(
            content=contenido,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=plantilla_inventario_celulares_Excel.xlsx"}
        )

@router.get("/plantilla-sheets")
def descargar_plantilla_sheets(user: dict = Depends(require_role("dueno"))):
    """Descarga la plantilla de celulares optimizada directamente para Google Sheets (.csv UTF-8 con BOM)."""
    contenido = generar_plantilla_celulares_csv()
    return Response(
        content=contenido,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=plantilla_celulares_google_sheets.csv"}
    )

@router.post("/importar-excel")
async def importar_equipos_excel(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("dueno"))
):
    """Sube y procesa una hoja de Excel (.xlsx) o CSV con celulares. Exclusivo para rol Dueño."""
    try:
        contenido = await file.read(MAX_EXCEL_UPLOAD_BYTES + 1)
        if not contenido:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo subido está vacío.")
        if len(contenido) > MAX_EXCEL_UPLOAD_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="El archivo excede el tamaño máximo permitido (10 MB).")

        resultado = procesar_archivo_excel_o_csv(contenido, file.filename or "")
        validos = resultado["validos"]
        errores = resultado["errores"]

        guardados = guardar_equipos_importados(validos) if validos else []

        return {
            "mensaje": f"Se importaron {len(guardados)} teléfonos exitosamente.",
            "total_filas": resultado["total_filas"],
            "importados_count": len(guardados),
            "errores_count": len(errores),
            "errores": errores,
            "equipos": sanitizar_datos_sensibles(guardados, user)
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al procesar el archivo.")

@router.get("/{equipo_id}", response_model=EquipoResponse)
def obtener_equipo(
    equipo_id: int,
    user: dict = Depends(get_current_user)
):
    """Obtiene los detalles de un equipo por su ID. Oculta costos confidenciales si no es dueño."""
    equipo = crud.get_equipo_by_id(equipo_id)
    if not equipo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipo no encontrado.")
    return sanitizar_datos_sensibles(equipo, user)

@router.put("/{equipo_id}", response_model=EquipoResponse)
def actualizar_equipo(
    equipo_id: int,
    datos: EquipoUpdate,
    user: dict = Depends(require_role("dueno"))
):
    """Actualiza datos de un equipo. Exclusivo para rol Dueño y con respuesta sanitizada."""
    try:
        actualizado = crud.update_equipo(equipo_id, datos)
        if not actualizado:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipo no encontrado.")
        return sanitizar_datos_sensibles(actualizado, user)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al actualizar el equipo.")

@router.delete("/{equipo_id}", status_code=status.HTTP_200_OK)
def eliminar_equipo(
    equipo_id: int,
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password"),
    user: dict = Depends(get_current_user)
):
    """
    Elimina un equipo si aún no ha sido vendido.
    Requiere sesión activa de Dueño o cabecera 'X-Admin-Password' con contraseña válida.
    No se permite el envío de contraseñas por URL (query parameters) por seguridad.
    """
    if not (is_user_dueno(user) or verify_delete_password(x_admin_password)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de Dueño o cabecera X-Admin-Password válida."
        )

    try:
        exito = crud.delete_equipo(equipo_id)
        if not exito:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipo no encontrado.")
        return {"mensaje": "Equipo eliminado exitosamente."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
