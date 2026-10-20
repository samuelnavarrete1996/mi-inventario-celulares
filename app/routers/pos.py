from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional, Dict, Any
from app import crud
from app.models import VentaCreate, VentaDetalleResponse, EquipoResponse, AbonoCreditoCreate
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
    Soporta ventas de contado y ventas a crédito ("Nota de Crédito" a 15 o 30 días).
    Exige usuario autenticado y oculta ganancias si es vendedor.
    """
    if not venta.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El carrito de venta no puede estar vacío.")

    for monto in (venta.monto_efectivo, venta.monto_transferencia, venta.monto_tarjeta, venta.monto_garantia, venta.monto_anticipo):
        if monto is not None and monto < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Los montos de pago o anticipo no pueden ser negativos.")

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
            notas=venta.notas,
            es_credito=getattr(venta, 'es_credito', False),
            plazo_dias=getattr(venta, 'plazo_dias', None),
            fecha_vencimiento=getattr(venta, 'fecha_vencimiento', None),
            monto_anticipo=getattr(venta, 'monto_anticipo', 0.0) or 0.0
        )
        return sanitizar_datos_sensibles(resultado, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno procesando la venta: {str(e)}")

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

@router.get("/creditos")
def listar_notas_credito(
    estado: Optional[str] = Query(None, description="Filtro por estado: Pendiente, Vencida, Por Vencer, Liquidada o Todos"),
    user: dict = Depends(get_current_user)
):
    """
    Lista las notas de crédito otorgadas a clientes (15 y 30 días) con resumen de saldos y vencimientos.
    """
    try:
        data = crud.get_notas_credito(estado_filtro=estado)
        return sanitizar_datos_sensibles(data, user)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al obtener notas de crédito: {str(e)}")

@router.get("/creditos/alertas")
def obtener_alertas_credito(
    user: dict = Depends(get_current_user)
):
    """
    Devuelve resumen liviano de notas de crédito vencidas y por vencer para alertas visuales en el POS.
    """
    try:
        data = crud.get_notas_credito()
        return {
            "total_vencidas": data.get("total_vencidas", 0),
            "total_por_vencer": data.get("total_por_vencer", 0),
            "total_pendientes": data.get("total_pendientes", 0),
            "monto_total_vencido": data.get("monto_total_vencido", 0.0),
            "monto_total_por_cobrar": data.get("monto_total_por_cobrar", 0.0),
            "alertas": [
                n for n in data.get("notas", [])
                if n.get("estado_calculado") in ("Vencida", "Por Vencer")
            ][:10]  # Primeras 10 alertas más críticas para mostrar en el POS
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al obtener alertas de crédito: {str(e)}")

@router.post("/creditos/{venta_id}/abono")
def abonar_a_nota_credito(
    venta_id: int,
    abono: AbonoCreditoCreate,
    user: dict = Depends(get_current_user)
):
    """
    Registra un abono a una nota de crédito existente.
    """
    try:
        usuario_nombre = user.get("sub") or user.get("nombre") or "Cajero"
        resultado = crud.registrar_abono_credito(
            venta_id=venta_id,
            monto=abono.monto,
            metodo_pago=abono.metodo_pago,
            notas=abono.notas,
            usuario=usuario_nombre
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al registrar abono: {str(e)}")

