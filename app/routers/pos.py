import logging
from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional, Dict, Any
from app import crud
from app.models import VentaCreate, VentaDetalleResponse, EquipoResponse, AbonoCreditoCreate
from app.security import get_current_user, sanitizar_datos_sensibles, get_current_tenant
from app.dependencies import TenantContext

logger = logging.getLogger("inventario.pos")

router = APIRouter(prefix="/api/pos", tags=["Punto de Venta"])

@router.get("/buscar", response_model=List[EquipoResponse])
def buscar_equipos_disponibles(
    q: Optional[str] = Query(None, description="Búsqueda en tiempo real por IMEI o Modelo"),
    tenant: TenantContext = Depends(get_current_tenant)
):
    """
    Buscador en tiempo real para el POS:
    Retorna únicamente equipos con estado 'Disponible' del tenant en sesión. Oculta costos si no es Dueño.
    """
    equipos = crud.get_equipos(solo_disponibles=True, search=q, tenant_id=tenant.tenant_id)
    return sanitizar_datos_sensibles(equipos, tenant.user)

@router.post("/vender", response_model=VentaDetalleResponse, status_code=status.HTTP_201_CREATED)
def realizar_venta(
    venta: VentaCreate,
    tenant: TenantContext = Depends(get_current_tenant)
):
    """
    Procesa la venta en el POS validando montos no negativos y recalculando totales en BD.
    Inyecta automáticamente el tenant_id y sucursal_id del usuario en sesión.
    Soporta ventas de contado y ventas a crédito ("Nota de Crédito" a 15 o 30 días).
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
            monto_anticipo=getattr(venta, 'monto_anticipo', 0.0) or 0.0,
            tenant_id=tenant.tenant_id,
            sucursal_id=tenant.sucursal_id
        )
        return sanitizar_datos_sensibles(resultado, tenant.user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error interno procesando la venta: %s", repr(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno procesando la venta.")

@router.get("/recibo/{venta_id}", response_model=VentaDetalleResponse)
def obtener_recibo(
    venta_id: int,
    tenant: TenantContext = Depends(get_current_tenant)
):
    """Obtiene los datos de una venta para generar el recibo, exigiendo sesión activa y ocultando márgenes."""
    recibo = crud.get_venta_detalle(venta_id, tenant_id=tenant.tenant_id)
    if not recibo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    return sanitizar_datos_sensibles(recibo, tenant.user)

@router.get("/creditos")
def listar_notas_credito(
    estado: Optional[str] = Query(None, description="Filtro por estado: Pendiente, Vencida, Por Vencer, Liquidada o Todos"),
    tenant: TenantContext = Depends(get_current_tenant)
):
    """
    Lista las notas de crédito otorgadas a clientes (15 y 30 días) con resumen de saldos y vencimientos del tenant en sesión.
    """
    try:
        data = crud.get_notas_credito(estado_filtro=estado, tenant_id=tenant.tenant_id)
        return sanitizar_datos_sensibles(data, tenant.user)
    except Exception as e:
        logger.error("Error al obtener notas de crédito: %s", repr(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al obtener notas de crédito.")

@router.get("/creditos/alertas")
def obtener_alertas_credito(
    tenant: TenantContext = Depends(get_current_tenant)
):
    """
    Devuelve resumen liviano de notas de crédito vencidas y por vencer para alertas visuales en el POS del tenant en sesión.
    """
    try:
        data = crud.get_notas_credito(tenant_id=tenant.tenant_id)
        return {
            "total_vencidas": data.get("total_vencidas", 0),
            "total_por_vencer": data.get("total_por_vencer", 0),
            "total_pendientes": data.get("total_pendientes", 0),
            "monto_total_vencido": data.get("monto_total_vencido", 0.0),
            "monto_total_por_cobrar": data.get("monto_total_por_cobrar", 0.0),
            "alertas": [
                n for n in data.get("notas", [])
                if n.get("estado_calculado") in ("Vencida", "Por Vencer")
            ][:10]
        }
    except Exception as e:
        logger.error("Error al obtener alertas de crédito: %s", repr(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al obtener alertas de crédito.")

@router.post("/creditos/{venta_id}/abono")
def abonar_a_nota_credito(
    venta_id: int,
    abono: AbonoCreditoCreate,
    tenant: TenantContext = Depends(get_current_tenant)
):
    """
    Registra un abono a una nota de crédito existente. Valida pertenencia al tenant.
    """
    try:
        usuario_nombre = tenant.user.get("sub") or tenant.user.get("nombre") or "Cajero"
        resultado = crud.registrar_abono_credito(
            venta_id=venta_id,
            monto=abono.monto,
            metodo_pago=abono.metodo_pago,
            notas=abono.notas,
            usuario=usuario_nombre,
            tenant_id=tenant.tenant_id
        )
        return resultado
    except ValueError as e:
        msg = str(e)
        if "no fue encontrada o no pertenece" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except Exception as e:
        logger.error("Error al registrar abono: %s", repr(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al registrar abono.")

