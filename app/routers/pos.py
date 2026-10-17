from fastapi import APIRouter, HTTPException, Query, status, Request
from typing import List, Optional
from app import crud
from app.models import VentaCreate, VentaDetalleResponse, EquipoResponse
from app.security import get_current_user_optional, is_user_dueno

router = APIRouter(prefix="/api/pos", tags=["Punto de Venta"])

def sanitizar_venta_para_vendedor(venta_dict: dict) -> dict:
    """Oculta costos de compra y márgenes de ganancia para usuarios que no sean Dueño."""
    venta_dict["costo_compra"] = None
    venta_dict["margen_ganancia"] = None
    if "items" in venta_dict and isinstance(venta_dict["items"], list):
        for it in venta_dict["items"]:
            if isinstance(it, dict):
                it["costo_compra"] = None
                it["margen_ganancia"] = None
    return venta_dict

@router.get("/buscar", response_model=List[EquipoResponse])
def buscar_equipos_disponibles(
    request: Request,
    q: Optional[str] = Query(None, description="Búsqueda en tiempo real por IMEI o Modelo")
):
    """
    Buscador en tiempo real para el POS:
    Retorna únicamente equipos con estado 'Disponible' que coincidan con el IMEI o Modelo.
    Oculta el costo de compra y margen si el usuario no es Dueño.
    """
    equipos = crud.get_equipos(solo_disponibles=True, search=q)
    user = get_current_user_optional(request)
    if not is_user_dueno(user):
        for eq in equipos:
            eq["costo_compra"] = None
            eq["margen_proyectado"] = None
            eq["porcentaje_margen"] = None
    return equipos

@router.post("/vender", response_model=VentaDetalleResponse, status_code=status.HTTP_201_CREATED)
def realizar_venta(venta: VentaCreate, request: Request):
    """
    Procesa la venta en el POS con soporte para múltiples equipos (carrito)
    y tipos de pago (Efectivo, Transferencia, Tarjeta o Combinado).
    """
    try:
        resultado = crud.registrar_venta_carrito(
            items=venta.items,
            cliente_nombre=venta.cliente_nombre,
            cliente_telefono=venta.cliente_telefono,
            metodo_pago=venta.metodo_pago,
            monto_efectivo=venta.monto_efectivo,
            monto_transferencia=venta.monto_transferencia,
            monto_tarjeta=venta.monto_tarjeta,
            monto_garantia=venta.monto_garantia,
            notas=venta.notas
        )
        user = get_current_user_optional(request)
        if not is_user_dueno(user):
            sanitizar_venta_para_vendedor(resultado)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error procesando la venta: {str(e)}")

@router.get("/recibo/{venta_id}", response_model=VentaDetalleResponse)
def obtener_recibo(venta_id: int, request: Request):
    """Obtiene los datos completos de una venta para generar o reimprimir el recibo."""
    recibo = crud.get_venta_detalle(venta_id)
    if not recibo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    user = get_current_user_optional(request)
    if not is_user_dueno(user):
        sanitizar_venta_para_vendedor(recibo)
    return recibo
