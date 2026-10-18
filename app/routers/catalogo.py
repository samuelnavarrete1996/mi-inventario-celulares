from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
import os
from app.database import get_db_connection

router = APIRouter(tags=["Catálogo Público Digital"])

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
    marca: Optional[str] = Query(None, description="Filtrar por marca (iPhone, Samsung, Xiaomi, etc.)"),
    grado: Optional[str] = Query(None, description="Filtrar por grado estético (A, B, C)"),
    search: Optional[str] = Query(None, description="Búsqueda por modelo o color")
) -> List[Dict[str, Any]]:
    """
    Retorna el catálogo público de celulares DISPONIBLES para clientes.
    NO expone costos de compra, márgenes ni el IMEI confidencial.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT id, modelo, capacidad_gb, color, grado, precio_venta, fecha_registro
    FROM equipos
    WHERE estado = 'Disponible'
    """
    params = []

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
    conn.close()
    return rows

@router.get("/api/catalogo/accesorios")
def obtener_accesorios_catalogo(
    categoria: Optional[str] = Query(None, description="Categoría de accesorios"),
    search: Optional[str] = Query(None, description="Búsqueda por nombre")
) -> List[Dict[str, Any]]:
    """
    Retorna el catálogo público de accesorios y servicios disponibles.
    NO expone costos de compra ni márgenes de ganancia.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT id, nombre, categoria, precio_venta, precio_mayoreo, precio_20_pzs, precio_caja, imagen_url, stock, es_servicio
    FROM accesorios
    WHERE 1=1
    """
    params = []

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
    conn.close()
    return rows
