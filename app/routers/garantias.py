from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List, Optional, Dict, Any
from app import crud
from app.models import GarantiaCreate, GarantiaResponse
from app.security import get_current_user, sanitizar_datos_sensibles

router = APIRouter(prefix="/api/garantias", tags=["Garantías"])

@router.get("/verificar-imei")
def verificar_imei_garantia(
    imei: str = Query(..., min_length=4, max_length=30, description="IMEI del equipo vendido a consultar para garantía"),
    user: dict = Depends(get_current_user)
):
    """
    Verifica los datos de venta de un equipo y calcula si está dentro de su plazo de garantía:
    - Grado A: 90 días
    - Grado B: 30 días
    - Grado C: 15 días
    (Requiere sesión activa y oculta costos confidenciales a vendedores).
    """
    try:
        info = crud.buscar_equipo_para_garantia(imei)
        return sanitizar_datos_sensibles(info, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al verificar la garantía del equipo."
        )

@router.post("/devolucion", response_model=GarantiaResponse, status_code=status.HTTP_201_CREATED)
def procesar_devolucion_garantia(
    garantia: GarantiaCreate,
    user: dict = Depends(get_current_user)
):
    """
    Procesa el regreso de un equipo por garantía:
    - Registra la devolución con el motivo y falla.
    - Actualiza el estado del equipo defectuoso (En Garantía, Reingresado a Inventario o Baja por Daño).
    - Permite enlazarlo al reemplazo correspondiente.
    (Requiere sesión activa).
    """
    try:
        resultado = crud.procesar_devolucion_garantia(garantia)
        return sanitizar_datos_sensibles(resultado, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno procesando la devolución por garantía."
        )

@router.get("", response_model=List[Dict[str, Any]])
def listar_historial_garantias(
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user)
):
    """Obtiene el historial de todas las devoluciones y reclamos de garantía procesados (requiere sesión activa)."""
    historial = crud.get_historial_garantias(limit=limit)
    return sanitizar_datos_sensibles(historial, user)

@router.get("/historial-imei/{imei}")
def obtener_historial_completo_imei(
    imei: str,
    user: dict = Depends(get_current_user)
):
    """
    Trazabilidad 360° por IMEI:
    Línea de tiempo cronológica completa de la vida del equipo
    (Ingreso, ventas, reclamos de garantía, reemplazos entregados).
    (Requiere sesión activa y sanitiza costos de compra para vendedores).
    """
    try:
        historial = crud.obtener_historial_imei(imei)
        return sanitizar_datos_sensibles(historial, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al consultar el historial del IMEI."
        )
