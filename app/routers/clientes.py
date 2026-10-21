from fastapi import APIRouter, Query, HTTPException, status, Depends
from typing import List, Optional
from app import crud
from app.database import get_db_connection
from app.models import ClienteResponse
from app.security import get_current_user, get_current_tenant
from app.dependencies import TenantContext

router = APIRouter(prefix="/api/clientes", tags=["Clientes"])

@router.get("", response_model=List[ClienteResponse])
def listar_clientes(
    limit: int = Query(50, ge=1, le=500),
    tenant: TenantContext = Depends(get_current_tenant)
):
    """Lista los clientes registrados del tenant en sesión."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE tenant_id = ? ORDER BY id DESC LIMIT ?", (tenant.tenant_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/buscar-telefono", response_model=Optional[ClienteResponse])
def buscar_por_telefono(
    telefono: str = Query(..., min_length=3, max_length=30, description="Teléfono a buscar"),
    tenant: TenantContext = Depends(get_current_tenant)
):
    """Permite autocompletar el nombre del cliente en el POS si ya existe en la base de datos dentro del tenant."""
    cliente = crud.get_cliente_by_phone(telefono, tenant_id=tenant.tenant_id)
    return cliente
