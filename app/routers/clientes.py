from fastapi import APIRouter, Query, HTTPException, status, Depends
from typing import List, Optional
from app import crud
from app.database import get_db_connection
from app.models import ClienteResponse
from app.security import get_current_user

router = APIRouter(prefix="/api/clientes", tags=["Clientes"])

@router.get("", response_model=List[ClienteResponse])
def listar_clientes(
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user)
):
    """Lista los clientes registrados (requiere sesión activa)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/buscar-telefono", response_model=Optional[ClienteResponse])
def buscar_por_telefono(
    telefono: str = Query(..., min_length=3, max_length=30, description="Teléfono a buscar"),
    user: dict = Depends(get_current_user)
):
    """Permite autocompletar el nombre del cliente en el POS si ya existe en la base de datos (requiere sesión activa)."""
    cliente = crud.get_cliente_by_phone(telefono)
    return cliente
