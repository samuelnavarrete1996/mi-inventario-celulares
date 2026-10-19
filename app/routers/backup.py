import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, status, Response, Depends
from fastapi.responses import FileResponse, JSONResponse
from app.database import DATABASE_FILE, init_db
from app import crud
from app.security import require_role

router = APIRouter(prefix="/api/backup", tags=["Respaldos"], dependencies=[Depends(require_role("dueno"))])

MAX_DB_UPLOAD_BYTES = 50 * 1024 * 1024  # Límite de 50 MB para archivos de restauración SQLite

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
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al exportar el respaldo en formato JSON."
        )

@router.post("/restaurar-db")
async def restaurar_base_de_datos(archivo: UploadFile = File(...)):
    """
    Restaura la base de datos a partir de un archivo .db respaldado previamente.
    Valida cabecera binaria, tamaño máximo e integridad estructural (PRAGMA integrity_check)
    antes de reemplazar el archivo activo.
    """
    if not archivo.filename or not archivo.filename.lower().endswith(".db"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe tener extensión .db")

    contenido = await archivo.read(MAX_DB_UPLOAD_BYTES + 1)
    if len(contenido) > MAX_DB_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="El archivo excede el límite máximo de 50 MB.")

    # Validar cabecera SQLite
    if not contenido.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo no es una base de datos SQLite válida.")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_f:
            tmp_f.write(contenido)

        # Verificar integridad estructural de la base de datos subida antes de pisar producción
        check_conn = sqlite3.connect(tmp_path)
        try:
            cur = check_conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            res_integrity = cur.fetchone()
            if not res_integrity or res_integrity[0].lower() != "ok":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo SQLite está corrupto o no superó la prueba de integridad.")
        finally:
            check_conn.close()

        # Copia de seguridad antes de restaurar
        if os.path.exists(DATABASE_FILE):
            backup_previo = f"{DATABASE_FILE}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(DATABASE_FILE, backup_previo)

        for suffix in ("-wal", "-shm"):
            wal_file = f"{DATABASE_FILE}{suffix}"
            if os.path.exists(wal_file):
                try:
                    os.remove(wal_file)
                except Exception:
                    pass

        shutil.copy2(tmp_path, DATABASE_FILE)
        init_db()

        return {"mensaje": "Base de datos restaurada exitosamente."}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al restaurar la base de datos."
        )
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
