from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional, Dict, Any
from app import crud
from app.models import GarantiaCreate, GarantiaResponse

router = APIRouter(prefix="/api/garantias", tags=["Garantías"])

@router.get("/verificar-imei")
def verificar_imei_garantia(
    imei: str = Query(..., description="IMEI del equipo vendido a consultar para garantía")
):
    """
    Verifica los datos de venta de un equipo y calcula si está dentro de su plazo de garantía:
    - Grado A: 90 días
    - Grado B: 30 días
    - Grado C: 15 días
    """
    try:
        info = crud.buscar_equipo_para_garantia(imei)
        return info
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al verificar garantía: {str(e)}")

@router.post("/devolucion", response_model=GarantiaResponse, status_code=status.HTTP_201_CREATED)
def procesar_devolucion_garantia(garantia: GarantiaCreate):
    """
    Procesa el regreso de un equipo por garantía:
    - Registra la devolución con el motivo y falla.
    - Actualiza el estado del equipo defectuoso (En Garantía, Reingresado a Inventario o Baja por Daño).
    - Permite enlazarlo al reemplazo correspondiente.
    """
    try:
        resultado = crud.procesar_devolucion_garantia(garantia)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error procesando garantía: {str(e)}")

@router.get("", response_model=List[Dict[str, Any]])
def listar_historial_garantias(limit: int = 100):
    """Obtiene el historial de todas las devoluciones y reclamos de garantía procesados."""
    return crud.get_historial_garantias(limit=limit)

@router.get("/historial-imei/{imei}")
def obtener_historial_completo_imei(imei: str):
    """
    Trazabilidad 360° por IMEI:
    Línea de tiempo cronológica completa de la vida del equipo
    (Ingreso, ventas, reclamos de garantía, reemplazos entregados).
    """
    try:
        return crud.obtener_historial_imei(imei)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

