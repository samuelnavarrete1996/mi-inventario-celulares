import os
from fastapi import APIRouter, HTTPException, Query, Header, UploadFile, File, Response, status
from typing import List, Optional, Dict, Any
from app import crud
from app.models import EquipoCreate, EquipoUpdate, EquipoResponse
from app.excel_importer import procesar_archivo_excel_o_csv, guardar_equipos_importados, generar_plantilla_excel_bytes

router = APIRouter(prefix="/api/equipos", tags=["Inventario"])

def load_env_file():
    """Carga variables desde archivo .env local si existe."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_env_file()

def get_admin_delete_password() -> str:
    """Obtiene la contraseña de administración desde variables de entorno."""
    load_env_file()
    return os.environ.get("ADMIN_DELETE_PASSWORD", "")


@router.get("", response_model=List[EquipoResponse])
def listar_equipos(
    solo_disponibles: bool = Query(True, description="Mostrar solo equipos con estado 'Disponible'"),
    search: Optional[str] = Query(None, description="Búsqueda por modelo, IMEI o color"),
    grado: Optional[str] = Query(None, description="Filtrar por grado: A, B o C")
):
    """Obtiene la lista de equipos en inventario según filtros."""
    return crud.get_equipos(solo_disponibles=solo_disponibles, search=search, grado=grado)

@router.post("", response_model=EquipoResponse, status_code=status.HTTP_201_CREATED)
def registrar_equipo(equipo: EquipoCreate):
    """
    Registra un nuevo teléfono en el inventario.
    Calcula automáticamente el margen proyectado.
    """
    try:
        nuevo = crud.create_equipo(equipo)
        return nuevo
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al registrar equipo: " + str(e))

@router.get("/plantilla-excel")
def descargar_plantilla_excel():
    """Descarga una plantilla de Excel (.xlsx) preformateada para carga masiva de celulares."""
    contenido = generar_plantilla_excel_bytes()
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=plantilla_inventario_celulares.xlsx"}
    )

@router.post("/importar-excel")
async def importar_equipos_excel(file: UploadFile = File(...)):
    """
    Sube y procesa una hoja de Excel (.xlsx) o CSV con celulares.
    Valida campos obligatorios, IMEI único, formato de números y grados estéticos.
    """
    try:
        contenido = await file.read()
        if not contenido:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo subido está vacío.")

        resultado = procesar_archivo_excel_o_csv(contenido, file.filename)
        validos = resultado["validos"]
        errores = resultado["errores"]

        guardados = []
        if validos:
            guardados = guardar_equipos_importados(validos)

        return {
            "mensaje": f"Se importaron {len(guardados)} teléfonos exitosamente.",
            "total_filas": resultado["total_filas"],
            "importados_count": len(guardados),
            "errores_count": len(errores),
            "errores": errores,
            "equipos": guardados
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al procesar archivo: {str(e)}")

@router.get("/{equipo_id}", response_model=EquipoResponse)
def obtener_equipo(equipo_id: int):
    """Obtiene los detalles de un equipo por su ID."""
    equipo = crud.get_equipo_by_id(equipo_id)
    if not equipo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipo no encontrado.")
    return equipo

@router.put("/{equipo_id}", response_model=EquipoResponse)
def actualizar_equipo(equipo_id: int, datos: EquipoUpdate):
    """Actualiza datos de un equipo."""
    actualizado = crud.update_equipo(equipo_id, datos)
    if not actualizado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipo no encontrado.")
    return actualizado

@router.delete("/{equipo_id}", status_code=status.HTTP_200_OK)
def eliminar_equipo(
    equipo_id: int,
    password: Optional[str] = Query(None, description="Contraseña de autorización para eliminar"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")
):
    """
    Elimina un equipo si aún no ha sido vendido.
    Requiere obligatoriamente la contraseña de autorización del administrador.
    """
    admin_password = get_admin_delete_password()
    if not admin_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La contraseña de administrador no ha sido configurada en el servidor (variable ADMIN_DELETE_PASSWORD)."
        )

    token = password or x_admin_password
    if not token or token != admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña de autorización incorrecta. No se permite eliminar el artículo."
        )

    try:
        exito = crud.delete_equipo(equipo_id)
        if not exito:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipo no encontrado.")
        return {"mensaje": "Equipo eliminado exitosamente."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

