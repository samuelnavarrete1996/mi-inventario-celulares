from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional
from app import crud
from app.models import VentaCreate, VentaDetalleResponse, EquipoResponse
from app.security import get_current_user, sanitizar_datos_sensibles

router = APIRouter(prefix="/api/pos", tags=["Punto de Venta"])

@router.get("/buscar", response_model=List[EquipoResponse])
def buscar_equipos_disponibles(
    q: Optional[str] = Query(None, description="Búsqueda en tiempo real por IMEI o Modelo"),
    user: dict = Depends(get_current_user)
):
    """
    Buscador en tiempo real para el POS:
    Retorna únicamente equipos con estado 'Disponible'. Oculta costos si no es Dueño.
    Requiere sesión activa.
    """
    equipos = crud.get_equipos(solo_disponibles=True, search=q)
    return sanitizar_datos_sensibles(equipos, user)

@router.post("/vender", response_model=VentaDetalleResponse, status_code=status.HTTP_201_CREATED)
def realizar_venta(
    venta: VentaCreate,
    user: dict = Depends(get_current_user)
):
    """
    Procesa la venta en el POS validando montos no negativos y recalculando totales en BD.
    Exige usuario autenticado y oculta ganancias si es vendedor.
    """
    if not venta.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El carrito de venta no puede estar vacío.")

    for monto in (venta.monto_efectivo, venta.monto_transferencia, venta.monto_tarjeta, venta.monto_garantia):
        if monto is not None and monto < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Los montos de pago no pueden ser negativos.")

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
        return sanitizar_datos_sensibles(resultado, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno procesando la venta.")

@router.get("/recibo/{venta_id}", response_model=VentaDetalleResponse)
def obtener_recibo(
    venta_id: int,
    user: dict = Depends(get_current_user)
):
    """Obtiene los datos de una venta para generar el recibo, exigiendo sesión activa y ocultando márgenes."""
    recibo = crud.get_venta_detalle(venta_id)
    if not recibo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    return sanitizar_datos_sensibles(recibo, user)
