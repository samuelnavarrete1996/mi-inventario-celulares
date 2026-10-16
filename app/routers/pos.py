from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
from app import crud
from app.models import VentaCreate, VentaDetalleResponse, EquipoResponse

router = APIRouter(prefix="/api/pos", tags=["Punto de Venta"])

@router.get("/buscar", response_model=List[EquipoResponse])
def buscar_equipos_disponibles(
    q: Optional[str] = Query(None, description="Búsqueda en tiempo real por IMEI o Modelo")
):
    """
    Buscador en tiempo real para el POS:
    Retorna únicamente equipos con estado 'Disponible' que coincidan con el IMEI o Modelo.
    """
    return crud.get_equipos(solo_disponibles=True, search=q)

@router.post("/vender", response_model=VentaDetalleResponse, status_code=status.HTTP_201_CREATED)
def realizar_venta(venta: VentaCreate):
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
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error procesando la venta: {str(e)}")

@router.get("/recibo/{venta_id}", response_model=VentaDetalleResponse)
def obtener_recibo(venta_id: int):
    """Obtiene los datos completos de una venta para generar o reimprimir el recibo."""
    recibo = crud.get_venta_detalle(venta_id)
    if not recibo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    return recibo
