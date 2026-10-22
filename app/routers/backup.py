import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, status, Depends
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from app.database import DATABASE_FILE, init_db
from app import crud
from app.security import require_role, get_current_tenant
from app.dependencies import TenantContext

router = APIRouter(prefix="/api/backup", tags=["Respaldos"], dependencies=[Depends(require_role("dueno"))])

MAX_DB_UPLOAD_BYTES = 50 * 1024 * 1024  # Límite de 50 MB para archivos de restauración SQLite

def _verificar_acceso_db_fisica_single_tenant(tenant: TenantContext) -> None:
    """Valida que la base de datos sea single-tenant antes de permitir restauraciones físicas destructivas."""
    if not os.path.exists(DATABASE_FILE):
        return
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tenants;")
        row = cur.fetchone()
        total_tenants = row[0] if row else 0
        if total_tenants > 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operación no permitida: La restauración física de base de datos está deshabilitada en entornos multi-tenant compartidos para proteger la información de otros negocios."
            )
    finally:
        conn.close()

@router.get("/descargar-db")
def descargar_base_de_datos(tenant: TenantContext = Depends(get_current_tenant)):
    """
    Descarga una copia de la base de datos SQLite depurada y aislada para el tenant en sesión.
    Elimina registros pertenecientes a otras empresas y limpia tokens o hashes sensibles.
    """
    if not os.path.exists(DATABASE_FILE):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo de base de datos no encontrado")

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_descarga = f"inventario_respaldo_{tenant.tenant_slug}_{fecha_str}.db"

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    shutil.copy2(DATABASE_FILE, tmp_path)

    try:
        tmp_conn = sqlite3.connect(tmp_path)
        cur = tmp_conn.cursor()
        t_id = tenant.tenant_id

        tablas_con_tenant = [
            "sucursales", "configuracion_tienda", "usuarios", "clientes",
            "equipos", "accesorios", "ventas", "reparaciones", "cortes_caja"
        ]
        for tbl in tablas_con_tenant:
            try:
                cur.execute(f"DELETE FROM {tbl} WHERE tenant_id != ? OR tenant_id IS NULL;", (t_id,))
            except Exception:
                pass

        try:
            cur.execute("DELETE FROM venta_items WHERE venta_id NOT IN (SELECT id FROM ventas WHERE tenant_id = ?);", (t_id,))
        except Exception:
            pass
        try:
            cur.execute("DELETE FROM abonos_ventas_credito WHERE venta_id NOT IN (SELECT id FROM ventas WHERE tenant_id = ?);", (t_id,))
        except Exception:
            pass
        try:
            cur.execute("DELETE FROM garantias WHERE equipo_id NOT IN (SELECT id FROM equipos WHERE tenant_id = ?);", (t_id,))
        except Exception:
            pass
        try:
            cur.execute("DELETE FROM historial_ventas_cambios WHERE venta_id NOT IN (SELECT id FROM ventas WHERE tenant_id = ?);", (t_id,))
        except Exception:
            pass
        try:
            cur.execute("DELETE FROM garantias_historial WHERE garantia_id NOT IN (SELECT id FROM garantias);")
        except Exception:
            pass
        try:
            cur.execute("DELETE FROM movimientos_stock_accesorios WHERE accesorio_id NOT IN (SELECT id FROM accesorios WHERE tenant_id = ?);", (t_id,))
        except Exception:
            pass

        try:
            cur.execute("DELETE FROM tenants WHERE id != ?;", (t_id,))
        except Exception:
            pass

        for tbl in ("revoked_tokens", "login_attempts", "auth_rate_limits"):
            try:
                cur.execute(f"DROP TABLE IF EXISTS {tbl};")
            except Exception:
                pass

        tmp_conn.commit()
        try:
            tmp_conn.execute("VACUUM;")
        except Exception:
            pass
        tmp_conn.close()

        return FileResponse(
            path=tmp_path,
            media_type="application/x-sqlite3",
            filename=nombre_descarga,
            background=BackgroundTask(lambda: os.remove(tmp_path) if os.path.exists(tmp_path) else None)
        )
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al generar el archivo de respaldo SQLite."
        )

@router.get("/exportar-json")
def exportar_todo_json(tenant: TenantContext = Depends(get_current_tenant)):
    """Exporta todas las tablas y registros en formato JSON estructurado aislado por tenant."""
    try:
        data = crud.exportar_todo_json(tenant_id=tenant.tenant_id)
        return JSONResponse(content=data)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al exportar el respaldo en formato JSON."
        )

@router.post("/restaurar-db")
async def restaurar_base_de_datos(
    archivo: UploadFile = File(...),
    tenant: TenantContext = Depends(get_current_tenant)
):
    """
    Restaura la base de datos a partir de un archivo .db respaldado previamente.
    Bloquea la restauración si existen múltiples tenants en la base de datos física activa (HTTP 403).
    Valida cabecera binaria, tamaño máximo e integridad estructural (PRAGMA integrity_check)
    antes de reemplazar el archivo activo.
    """
    _verificar_acceso_db_fisica_single_tenant(tenant)

    if not archivo.filename or not archivo.filename.lower().endswith(".db"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe tener extensión .db")

    contenido = await archivo.read(MAX_DB_UPLOAD_BYTES + 1)
    if len(contenido) > MAX_DB_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="El archivo excede el límite máximo de 50 MB.")

    if not contenido.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo no es una base de datos SQLite válida.")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_f:
            tmp_f.write(contenido)

        check_conn = sqlite3.connect(tmp_path)
        try:
            cur = check_conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            res_integrity = cur.fetchone()
            if not res_integrity or res_integrity[0].lower() != "ok":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo SQLite está corrupto o no superó la prueba de integridad.")
        finally:
            check_conn.close()

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
