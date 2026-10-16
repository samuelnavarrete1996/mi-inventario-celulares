from fastapi import APIRouter, Query, HTTPException, status
from typing import List, Optional
from app import crud
from app.database import get_db_connection
from app.models import ClienteResponse

router = APIRouter(prefix="/api/clientes", tags=["Clientes"])

@router.get("", response_model=List[ClienteResponse])
def listar_clientes(limit: int = 50):
    """Lista los clientes registrados."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/buscar-telefono", response_model=Optional[ClienteResponse])
def buscar_por_telefono(telefono: str = Query(..., description="Teléfono a buscar")):
    """Permite autocompletar el nombre del cliente en el POS si ya existe en la base de datos."""
    cliente = crud.get_cliente_by_phone(telefono)
    return cliente
