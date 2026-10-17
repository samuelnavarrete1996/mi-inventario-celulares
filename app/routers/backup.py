import os
import shutil
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, status, Response, Depends
from fastapi.responses import FileResponse, JSONResponse
from app.database import DATABASE_FILE, init_db
from app import crud
from app.security import require_role

router = APIRouter(prefix="/api/backup", tags=["Respaldos"], dependencies=[Depends(require_role("dueno"))])

@router.get("/descargar-db")
def descargar_base_de_datos():
    """Descarga una copia completa del archivo de base de datos SQLite (.db)."""
    if not os.path.exists(DATABASE_FILE):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo de base de datos no encontrado")

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_descarga = f"inventario_samuel_respaldo_{fecha_str}.db"

    return FileResponse(
        path=DATABASE_FILE,
        media_type="application/x-sqlite3",
        filename=nombre_descarga
    )

@router.get("/exportar-json")
def exportar_todo_json():
    """Exporta todas las tablas y registros en formato JSON estructurado."""
    try:
        data = crud.exportar_todo_json()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/restaurar-db")
async def restaurar_base_de_datos(archivo: UploadFile = File(...)):
    """
    Restaura la base de datos a partir de un archivo .db respaldado previamente.
    Crea una copia de seguridad automática del estado actual antes de sobreescribir.
    """
    if not archivo.filename.endswith(".db"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe tener extensión .db")

    contenido = await archivo.read()
    # Validar cabecera SQLite
    if not contenido.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo no es una base de datos SQLite válida.")

    try:
        # Copia de seguridad antes de restaurar
        if os.path.exists(DATABASE_FILE):
            backup_previo = f"{DATABASE_FILE}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(DATABASE_FILE, backup_previo)

        with open(DATABASE_FILE, "wb") as f:
            f.write(contenido)

        init_db()

        return {"mensaje": "Base de datos restaurada exitosamente."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error restaurando base de datos: {str(e)}")
