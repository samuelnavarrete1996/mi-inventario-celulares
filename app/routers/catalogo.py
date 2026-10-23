import os
from fastapi import APIRouter, Query, HTTPException, status
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
from app.database import get_db_connection

router = APIRouter(tags=["Catálogo Público Digital"])


def _resolve_public_catalog_tenant_id(
    cursor,
    slug: Optional[str] = None,
    tenant_param: Optional[str] = None,
    tenant_id: Optional[int] = None
) -> int:
    """
    Resuelve el tenant_id para las consultas de catálogo público.
    Valida que el tenant exista y se encuentre activo (HTTP 404 en caso contrario).
    Si no se especifica tenant, toma el primer tenant activo para compatibilidad.
    """
    if slug:
        cursor.execute("SELECT id, activo FROM tenants WHERE slug = ? LIMIT 1;", (slug.strip(),))
        row = cursor.fetchone()
        if not row or not row["activo"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El catálogo solicitado no existe o no se encuentra disponible."
            )
        return int(row["id"])

    if tenant_param:
        val = tenant_param.strip()
        if val.isdigit():
            cursor.execute("SELECT id, activo FROM tenants WHERE id = ? LIMIT 1;", (int(val),))
        else:
            cursor.execute("SELECT id, activo FROM tenants WHERE slug = ? LIMIT 1;", (val,))
        row = cursor.fetchone()
        if not row or not row["activo"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El catálogo solicitado no existe o no se encuentra disponible."
            )
        return int(row["id"])

    if tenant_id is not None:
        cursor.execute("SELECT id, activo FROM tenants WHERE id = ? LIMIT 1;", (tenant_id,))
        row = cursor.fetchone()
        if not row or not row["activo"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El catálogo solicitado no existe o no se encuentra disponible."
            )
        return int(row["id"])

    # Fallback predeterminado para primer tenant activo
    cursor.execute("SELECT id FROM tenants WHERE (activo IS TRUE OR activo = TRUE) ORDER BY id ASC LIMIT 1;")
    row = cursor.fetchone()
    if row:
        return int(row["id"])

    return 1


@router.get("/catalogo", response_class=FileResponse)
def ver_catalogo_publico():
    """Sirve la vitrina digital pública para clientes."""
    ruta_html = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "catalogo.html")
    return FileResponse(
        ruta_html,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    )


@router.get("/api/catalogo/equipos")
def obtener_equipos_catalogo(
    marca: Optional[str] = Query(None, max_length=60, description="Filtrar por marca (iPhone, Samsung, Xiaomi, etc.)"),
    grado: Optional[str] = Query(None, max_length=10, description="Filtrar por grado estético (A, B, C)"),
    search: Optional[str] = Query(None, max_length=100, description="Búsqueda por modelo o color"),
    slug: Optional[str] = Query(None, max_length=80, description="Slug de la tienda"),
    tenant: Optional[str] = Query(None, max_length=80, description="Slug o ID de la tienda"),
    tenant_id: Optional[int] = Query(None, description="ID numérico de la tienda")
) -> List[Dict[str, Any]]:
    """
    Retorna el catálogo público de celulares DISPONIBLES para clientes filtrado por tenant_id.
    NO expone costos de compra, márgenes ni el IMEI confidencial.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        target_tenant_id = _resolve_public_catalog_tenant_id(
            cursor, slug=slug, tenant_param=tenant, tenant_id=tenant_id
        )

        query = """
        SELECT id, modelo, capacidad_gb, color, grado, precio_venta, fecha_registro
        FROM equipos
        WHERE estado = 'Disponible' AND tenant_id = ?
        """
        params: List[Any] = [target_tenant_id]

        if marca:
            query += " AND modelo LIKE ?"
            params.append(f"%{marca.strip()}%")

        if grado and grado != "Todos":
            query += " AND grado = ?"
            params.append(grado.strip().upper())

        if search:
            s = f"%{search.strip()}%"
            query += " AND (modelo LIKE ? OR color LIKE ?)"
            params.extend([s, s])

        query += " ORDER BY precio_venta DESC"
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        return rows
    finally:
        conn.close()


@router.get("/api/catalogo/accesorios")
def obtener_accesorios_catalogo(
    categoria: Optional[str] = Query(None, max_length=80, description="Categoría de accesorios"),
    search: Optional[str] = Query(None, max_length=100, description="Búsqueda por nombre"),
    slug: Optional[str] = Query(None, max_length=80, description="Slug de la tienda"),
    tenant: Optional[str] = Query(None, max_length=80, description="Slug o ID de la tienda"),
    tenant_id: Optional[int] = Query(None, description="ID numérico de la tienda")
) -> List[Dict[str, Any]]:
    """
    Retorna el catálogo público de accesorios y servicios disponibles filtrado por tenant_id.
    NO expone costos de compra ni márgenes de ganancia.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        target_tenant_id = _resolve_public_catalog_tenant_id(
            cursor, slug=slug, tenant_param=tenant, tenant_id=tenant_id
        )

        query = """
        SELECT id, nombre, categoria, precio_venta, precio_mayoreo, precio_20_pzs, precio_caja, imagen_url, stock, es_servicio
        FROM accesorios
        WHERE tenant_id = ?
        """
        params: List[Any] = [target_tenant_id]

        if categoria and categoria != "Todos":
            cat_clean = categoria.rstrip('s').rstrip('es')
            query += " AND (categoria = ? OR categoria LIKE ?)"
            params.extend([categoria, f"{cat_clean}%"])

        if search:
            query += " AND (nombre LIKE ? OR categoria LIKE ?)"
            params.extend([f"%{search.strip()}%", f"%{search.strip()}%"])

        query += " ORDER BY id ASC"
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        return rows
    finally:
        conn.close()


@router.get("/api/catalogo/reparacion/{folio}")
def rastrear_reparacion_publica(folio: str):
    """
    Permite a los clientes rastrear el estado en tiempo real de su equipo en reparación
    usando su número de folio (ej. REP-202610-001) o escaneando el código QR de su boleta.
    Muestra únicamente información segura y no confidencial.
    """
    from app import crud
    rep = crud.get_reparacion_publica_by_folio(folio)
    if not rep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró ninguna orden de servicio con el folio proporcionado. Verifique el número e intente de nuevo."
        )
    return rep

