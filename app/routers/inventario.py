from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Response, status
from typing import List, Optional, Dict, Any
from app import crud
from app.models import EquipoCreate, EquipoUpdate, EquipoResponse
from app.excel_importer import procesar_archivo_excel_o_csv, guardar_equipos_importados, generar_plantilla_excel_bytes

router = APIRouter(prefix="/api/equipos", tags=["Inventario"])

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
def eliminar_equipo(equipo_id: int):
    """Elimina un equipo si aún no ha sido vendido."""
    try:
        exito = crud.delete_equipo(equipo_id)
        if not exito:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipo no encontrado.")
        return {"mensaje": "Equipo eliminado exitosamente."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
