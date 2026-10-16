from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any

class EquipoCreate(BaseModel):
    modelo: str = Field(..., min_length=1, description="Modelo del teléfono, ej. iPhone 13")
    capacidad_gb: int = Field(..., gt=0, description="Capacidad en Gigabytes, ej. 128")
    color: str = Field(..., min_length=1, description="Color del teléfono, ej. Negro Medianoche")
    imei: str = Field(..., min_length=10, max_length=20, description="IMEI único del dispositivo")
    grado: str = Field(..., description="Grado estético y funcional: A, B o C")
    costo_compra: float = Field(..., gt=0, description="Costo al que se adquirió el equipo")
    precio_venta: float = Field(..., gt=0, description="Precio sugerido de venta al público")

    @field_validator('grado')
    def validate_grado(cls, v):
        v = v.strip().upper()
        if v not in ('A', 'B', 'C'):
            raise ValueError("El grado debe ser 'A' (Excelente), 'B' (Regular) o 'C' (Maltratado)")
        return v

    @field_validator('imei')
    def validate_imei(cls, v):
        v = v.strip().replace(" ", "").replace("-", "")
        if not v.isalnum():
            raise ValueError("El IMEI solo debe contener números o caracteres alfanuméricos válidos")
        return v

class EquipoUpdate(BaseModel):
    modelo: Optional[str] = None
    capacidad_gb: Optional[int] = None
    color: Optional[str] = None
    grado: Optional[str] = None
    costo_compra: Optional[float] = None
    precio_venta: Optional[float] = None
    estado: Optional[str] = None

class EquipoResponse(BaseModel):
    id: int
    modelo: str
    capacidad_gb: int
    color: str
    imei: str
    grado: str
    costo_compra: float
    precio_venta: float
    estado: str
    fecha_registro: str
    margen_proyectado: Optional[float] = None
    porcentaje_margen: Optional[float] = None

class ClienteCreate(BaseModel):
    nombre: str = Field(..., min_length=2, description="Nombre completo del cliente")
    telefono: str = Field(..., min_length=7, description="Teléfono de contacto")

class ClienteResponse(BaseModel):
    id: int
    nombre: str
    telefono: str
    fecha_registro: str

class ItemCarrito(BaseModel):
    equipo_id: int = Field(..., description="ID del equipo a vender")
    precio_final: float = Field(..., ge=0, description="Precio acordado para este equipo")

class VentaCreate(BaseModel):
    cliente_nombre: str = Field(..., min_length=2, description="Nombre del comprador")
    cliente_telefono: str = Field(..., min_length=7, description="Teléfono del comprador")
    metodo_pago: str = Field("Efectivo", description="Método de pago: Efectivo, Transferencia, Combinado, Equipo Garantía")
    monto_efectivo: float = Field(0.0, ge=0, description="Monto cubierto en efectivo")
    monto_transferencia: float = Field(0.0, ge=0, description="Monto cubierto por transferencia bancaria")
    monto_tarjeta: float = Field(0.0, ge=0, description="Monto cubierto con tarjeta (si aplica historial)")
    monto_garantia: float = Field(0.0, ge=0, description="Monto cubierto por equipo en garantía")
    notas: Optional[str] = None
    
    # Soporte para carrito de múltiples equipos
    items: Optional[List[ItemCarrito]] = None
    
    # Retrocompatibilidad con venta de un solo equipo
    equipo_id: Optional[int] = None
    precio_final: Optional[float] = None

    @model_validator(mode='after')
    def validate_items_and_payment(self):
        if not self.items and self.equipo_id is not None and self.precio_final is not None:
            self.items = [ItemCarrito(equipo_id=self.equipo_id, precio_final=self.precio_final)]

        if not self.items or len(self.items) == 0:
            raise ValueError("El carrito debe contener al menos un teléfono celular.")

        total_venta = round(sum(item.precio_final for item in self.items), 2)

        mp = self.metodo_pago.strip()
        # Normalizar nombres de métodos
        if mp.lower() in ("equipo garantia", "equipo garantía", "garantia", "garantía"):
            mp = "Equipo Garantía"
            self.metodo_pago = mp

        if mp == "Efectivo":
            if (self.monto_efectivo + self.monto_transferencia + self.monto_garantia) == 0:
                self.monto_efectivo = total_venta
        elif mp == "Transferencia":
            if (self.monto_efectivo + self.monto_transferencia + self.monto_garantia) == 0:
                self.monto_transferencia = total_venta
        elif mp == "Equipo Garantía":
            if (self.monto_efectivo + self.monto_transferencia + self.monto_garantia) == 0:
                self.monto_garantia = total_venta
        elif mp == "Combinado":
            total_pagos = round(self.monto_efectivo + self.monto_transferencia + self.monto_tarjeta + self.monto_garantia, 2)
            if abs(total_pagos - total_venta) > 0.05:
                raise ValueError(
                    f"En pago combinado, la suma de montos (${total_pagos:,.2f}) debe coincidir con el total de la venta (${total_venta:,.2f})."
                )

        return self

class VentaItemResponse(BaseModel):
    id: int
    venta_id: int
    equipo_id: int
    precio_final: float
    costo_compra: float
    margen_ganancia: float
    modelo: str
    capacidad_gb: int
    color: str
    imei: str
    grado: str

class VentaDetalleResponse(BaseModel):
    id: int
    cliente_id: int
    precio_final: float
    margen_ganancia: float
    fecha_venta: str
    metodo_pago: str
    monto_efectivo: float
    monto_transferencia: float
    monto_tarjeta: float = 0.0
    monto_garantia: float = 0.0
    notas: Optional[str] = None
    cliente_nombre: str
    cliente_telefono: str
    items: List[VentaItemResponse] = []
    total_equipos: int = 1
    resumen_modelos: str = ""
    
    # Retrocompatibilidad
    equipo_id: Optional[int] = None
    modelo: Optional[str] = None
    capacidad_gb: Optional[int] = None
    color: Optional[str] = None
    imei: Optional[str] = None
    grado: Optional[str] = None
    costo_compra: Optional[float] = None

# --- MODELOS DE GARANTÍA ---

class GarantiaCreate(BaseModel):
    imei: str = Field(..., description="IMEI del equipo a regresar por garantía")
    motivo: str = Field(..., min_length=2, description="Motivo de la devolución por garantía")
    falla_descripcion: Optional[str] = None
    estado_equipo_recibido: str = Field("En Garantia", description="En Garantia, Disponible o Baja por Garantia")
    solucion: str = Field("Reemplazo", description="Reemplazo por otro equipo, Reingreso a Inventario o Reembolso")
    equipo_reemplazo_id: Optional[int] = None
    monto_cubierto: Optional[float] = None
    notas: Optional[str] = None

class GarantiaResponse(BaseModel):
    id: int
    venta_id: int
    equipo_id: int
    cliente_id: int
    fecha_devolucion: str
    motivo: str
    falla_descripcion: Optional[str] = None
    estado_equipo_recibido: str
    solucion: str
    equipo_reemplazo_id: Optional[int] = None
    monto_cubierto: float
    notas: Optional[str] = None
    # Datos adicionales
    modelo: str
    imei: str
    grado: str
    color: str
    cliente_nombre: str
    cliente_telefono: str
    fecha_venta_original: str
    dias_garantia_permitidos: int
    dias_transcurridos: int
    dentro_de_garantia: bool

class DashboardMetrics(BaseModel):
    total_ganancias_mes: float
    total_ventas_mes: float
    equipos_vendidos_mes: int
    equipos_disponibles: int
    equipos_en_garantia: int = 0
    capital_inventario: float
    valor_venta_inventario: float
    margen_promedio_mes: float
    mes_actual_nombre: str
    ventas_por_dia: List[Dict[str, Any]] = []
    distribucion_grados: Dict[str, int] = {}
    desglose_metodos_pago: Dict[str, float] = {}
