import math
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, List, Dict, Any

def _check_finite_float(val: Optional[float], field_label: str) -> Optional[float]:
    if val is not None and (math.isnan(val) or math.isinf(val)):
        raise ValueError(f"El valor de {field_label} debe ser un número finito válido.")
    return val

class EquipoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: str = Field(..., min_length=1, max_length=150, description="Modelo del teléfono, ej. iPhone 13")
    capacidad_gb: int = Field(..., gt=0, le=4096, description="Capacidad en Gigabytes, ej. 128")
    color: str = Field(..., min_length=1, max_length=80, description="Color del teléfono, ej. Negro Medianoche")
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

    @field_validator('costo_compra', 'precio_venta')
    def validate_precios_finitos(cls, v):
        return _check_finite_float(v, "precio/costo")

class EquipoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: Optional[str] = Field(None, min_length=1, max_length=150)
    capacidad_gb: Optional[int] = Field(None, gt=0, le=4096)
    color: Optional[str] = Field(None, min_length=1, max_length=80)
    grado: Optional[str] = None
    costo_compra: Optional[float] = Field(None, gt=0)
    precio_venta: Optional[float] = Field(None, gt=0)
    estado: Optional[str] = None

    @field_validator('grado')
    def validate_grado_update(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if v not in ('A', 'B', 'C'):
            raise ValueError("El grado debe ser 'A', 'B' o 'C'")
        return v

    @field_validator('estado')
    def validate_estado_update(cls, v):
        if v is None:
            return v
        v = v.strip()
        if v not in ('Disponible', 'Vendido', 'En Garantia', 'Baja por Garantia'):
            raise ValueError("Estado de equipo no válido")
        return v

    @field_validator('costo_compra', 'precio_venta')
    def validate_precios_update(cls, v):
        return _check_finite_float(v, "precio/costo")

class EquipoResponse(BaseModel):
    id: int
    modelo: str
    capacidad_gb: int
    color: str
    imei: str
    grado: str
    costo_compra: Optional[float] = None
    precio_venta: float
    estado: str
    fecha_registro: str
    margen_proyectado: Optional[float] = None
    porcentaje_margen: Optional[float] = None
    dias_en_stock: Optional[int] = 0
    estado_antiguedad: Optional[str] = "Fresco"

class ClienteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(..., min_length=2, max_length=150, description="Nombre completo del cliente")
    telefono: str = Field(..., min_length=7, max_length=30, description="Teléfono de contacto")

class ClienteResponse(BaseModel):
    id: int
    nombre: str
    telefono: str
    fecha_registro: str

# --- MODELOS DE ACCESORIOS Y SERVICIOS ---

class AccesorioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(..., min_length=1, max_length=150, description="Nombre del accesorio o servicio")
    categoria: str = Field("Accesorio", max_length=80, description="Funda, Mica, Cargador, Cable, Audio, Reparación, Servicio, Accesorio, Otro")
    codigo_barras: Optional[str] = Field(None, max_length=64, description="Código de barras o SKU del producto")
    costo_compra: float = Field(0.0, ge=0, description="Costo unitario de compra")
    precio_venta: float = Field(..., ge=0, description="Precio de venta unitario")
    precio_mayoreo: Optional[float] = Field(0.0, ge=0, description="Precio de mayoreo (1+ pzas)")
    precio_20_pzs: Optional[float] = Field(0.0, ge=0, description="Precio para más de 20 piezas")
    precio_caja: Optional[float] = Field(0.0, ge=0, description="Precio por caja cerrada")
    imagen_url: Optional[str] = Field(None, max_length=500, description="URL o ruta de la fotografía del producto")
    color: Optional[str] = Field(None, max_length=50, description="Color o variante del accesorio")
    stock: int = Field(0, ge=0, le=1000000, description="Cantidad en stock")
    es_servicio: bool = Field(False, description="True si es servicio/mano de obra")

    @field_validator('costo_compra', 'precio_venta', 'precio_mayoreo', 'precio_20_pzs', 'precio_caja')
    def validate_montos_accesorio(cls, v):
        return _check_finite_float(v, "precio de accesorio")

class AccesorioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    categoria: Optional[str] = Field(None, min_length=1, max_length=80)
    codigo_barras: Optional[str] = Field(None, max_length=64)
    costo_compra: Optional[float] = Field(None, ge=0)
    precio_venta: Optional[float] = Field(None, ge=0)
    precio_mayoreo: Optional[float] = Field(None, ge=0)
    precio_20_pzs: Optional[float] = Field(None, ge=0)
    precio_caja: Optional[float] = Field(None, ge=0)
    imagen_url: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, max_length=50)
    stock: Optional[int] = Field(None, ge=0, le=1000000)
    es_servicio: Optional[bool] = None

    @field_validator('costo_compra', 'precio_venta', 'precio_mayoreo', 'precio_20_pzs', 'precio_caja')
    def validate_montos_accesorio_update(cls, v):
        return _check_finite_float(v, "precio de accesorio")

class AccesorioResponse(BaseModel):
    id: int
    nombre: str
    categoria: str
    codigo_barras: Optional[str] = None
    costo_compra: Optional[float] = None
    precio_venta: float
    precio_mayoreo: Optional[float] = 0.0
    precio_20_pzs: Optional[float] = 0.0
    precio_caja: Optional[float] = 0.0
    imagen_url: Optional[str] = None
    color: Optional[str] = None
    stock: int
    es_servicio: int
    fecha_registro: str
    margen_unitario: Optional[float] = None

class AccesorioAjusteStockRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nuevo_stock: int = Field(..., ge=0, le=1000000, description="Nuevo stock físico")
    tipo_movimiento: str = Field("AJUSTE", description="ENTRADA, VENTA, MERMA, AJUSTE, MUESTRA, COMPRA, AJUSTE_AUDITORIA, MUESTRA_USO_TIENDA, DEVOLUCION_PROVEEDOR")
    motivo: Optional[str] = Field(None, max_length=200, description="Motivo del ajuste")
    notas: Optional[str] = Field(None, max_length=300, description="Notas complementarias")

    @field_validator('tipo_movimiento')
    def validate_tipo(cls, v):
        v_clean = v.strip().upper()
        permitidos = (
            'ENTRADA', 'VENTA', 'MERMA', 'AJUSTE', 'MUESTRA',
            'COMPRA', 'AJUSTE_AUDITORIA', 'MUESTRA_USO_TIENDA',
            'DEVOLUCION_PROVEEDOR', 'CARGA_MASIVA'
        )
        if v_clean not in permitidos:
            raise ValueError(f"El tipo de movimiento debe ser uno de: {', '.join(permitidos)}")
        return v_clean

    @model_validator(mode='after')
    def validate_motivo(self):
        if not self.motivo:
            self.motivo = self.notas or "Ajuste manual de inventario"
        return self

class AccesorioStockItemMasivo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int = Field(..., gt=0)
    stock: Optional[int] = Field(None, ge=0, le=1000000)
    nuevo_stock: Optional[int] = Field(None, ge=0, le=1000000)

    @model_validator(mode='after')
    def validate_stock_alias(self):
        if self.stock is None and self.nuevo_stock is not None:
            self.stock = self.nuevo_stock
        elif self.stock is None:
            self.stock = 0
        return self

class AccesorioActualizacionMasivaRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: List[AccesorioStockItemMasivo]
    motivo: Optional[str] = Field("Carga masiva de stock", max_length=200)

class MovimientoStockResponse(BaseModel):
    id: int
    accesorio_id: int
    accesorio_nombre: Optional[str] = None
    accesorio_categoria: Optional[str] = None
    tipo_movimiento: str
    cantidad: int
    stock_anterior: int
    stock_nuevo: int
    motivo: str
    usuario: str
    fecha: str

# --- MODELOS DE CARRITO Y VENTAS ---

class ItemCarrito(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo_item: str = Field("equipo", description="'equipo' o 'accesorio'")
    equipo_id: Optional[int] = Field(None, gt=0, description="ID del equipo celular (si aplica)")
    accesorio_id: Optional[int] = Field(None, gt=0, description="ID del accesorio/servicio (si aplica)")
    nombre_item: Optional[str] = Field(None, max_length=200, description="Nombre o descripción para el recibo")
    cantidad: int = Field(1, ge=1, le=10000, description="Cantidad")
    precio_final: float = Field(..., ge=0, description="Precio acordado para esta línea")

    @field_validator('precio_final')
    def validate_precio_final(cls, v):
        return _check_finite_float(v, "precio_final")

class VentaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cliente_nombre: str = Field(..., min_length=2, max_length=150, description="Nombre del comprador")
    cliente_telefono: str = Field(..., min_length=7, max_length=30, description="Teléfono del comprador")
    metodo_pago: str = Field("Efectivo", description="Método de pago: Efectivo, Transferencia, Combinado, Equipo Garantía")
    monto_efectivo: float = Field(0.0, ge=0, description="Monto cubierto en efectivo")
    monto_transferencia: float = Field(0.0, ge=0, description="Monto cubierto por transferencia bancaria")
    monto_tarjeta: float = Field(0.0, ge=0, description="Monto cubierto con tarjeta (si aplica historial)")
    monto_garantia: float = Field(0.0, ge=0, description="Monto cubierto por equipo en garantía")
    notas: Optional[str] = Field(None, max_length=500)
    
    # Soporte para carrito de múltiples items
    items: Optional[List[ItemCarrito]] = None
    
    # Retrocompatibilidad con venta de un solo equipo
    equipo_id: Optional[int] = None
    precio_final: Optional[float] = None

    @field_validator('monto_efectivo', 'monto_transferencia', 'monto_tarjeta', 'monto_garantia', 'precio_final')
    def validate_montos_venta(cls, v):
        return _check_finite_float(v, "monto de pago")

    @model_validator(mode='after')
    def validate_items_and_payment(self):
        if not self.items and self.equipo_id is not None and self.precio_final is not None:
            self.items = [ItemCarrito(equipo_id=self.equipo_id, precio_final=self.precio_final, tipo_item='equipo')]

        if not self.items or len(self.items) == 0:
            raise ValueError("El carrito debe contener al menos un artículo o servicio.")

        total_venta = round(sum(item.precio_final for item in self.items), 2)

        mp = self.metodo_pago.strip()
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
    equipo_id: Optional[int] = None
    accesorio_id: Optional[int] = None
    tipo_item: str = "equipo"
    nombre_item: Optional[str] = None
    cantidad: int = 1
    precio_final: float
    costo_compra: Optional[float] = None
    margen_ganancia: Optional[float] = None
    modelo: Optional[str] = None
    capacidad_gb: Optional[int] = None
    color: Optional[str] = None
    imei: Optional[str] = None
    grado: Optional[str] = None

class VentaDetalleResponse(BaseModel):
    id: int
    cliente_id: int
    precio_final: float
    margen_ganancia: Optional[float] = None
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
    total_accesorios: int = 0
    ganancia_celulares: Optional[float] = None
    ganancia_accesorios: Optional[float] = None
    venta_celulares: float = 0.0
    venta_accesorios: float = 0.0
    tipo_venta: str = "celulares"
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
    model_config = ConfigDict(extra="forbid")
    imei: str = Field(..., min_length=8, max_length=25, description="IMEI del equipo a regresar por garantía")
    motivo: str = Field(..., min_length=2, max_length=200, description="Motivo de la devolución por garantía")
    falla_descripcion: Optional[str] = Field(None, max_length=500)
    estado_equipo_recibido: str = Field("En Garantia", description="En Garantia, Disponible o Baja por Garantia")
    solucion: str = Field("Reemplazo", description="Reemplazo por otro equipo, Reingreso a Inventario o Reembolso")
    equipo_reemplazo_id: Optional[int] = Field(None, gt=0)
    monto_cubierto: Optional[float] = Field(None, ge=0)
    notas: Optional[str] = Field(None, max_length=500)

    @field_validator('estado_equipo_recibido')
    def validate_estado_recibido(cls, v):
        if v not in ('En Garantia', 'Disponible', 'Baja por Garantia'):
            raise ValueError("estado_equipo_recibido debe ser 'En Garantia', 'Disponible' o 'Baja por Garantia'")
        return v

    @field_validator('solucion')
    def validate_solucion(cls, v):
        if v not in ('Reemplazo', 'Reingreso a Inventario', 'Reembolso'):
            raise ValueError("solucion debe ser 'Reemplazo', 'Reingreso a Inventario' o 'Reembolso'")
        return v

    @field_validator('monto_cubierto')
    def validate_monto_cubierto(cls, v):
        return _check_finite_float(v, "monto_cubierto")

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

# --- MODELOS DE CORTE DE CAJA ---

class CorteCajaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    efectivo_declarado: float = Field(..., ge=0, description="Efectivo físico contado en caja")
    notas: Optional[str] = Field(None, max_length=500)

    @field_validator('efectivo_declarado')
    def validate_efectivo(cls, v):
        return _check_finite_float(v, "efectivo_declarado")

class CorteCajaResponse(BaseModel):
    id: Optional[int] = None
    fecha_corte: str
    fecha_inicio_periodo: Optional[str] = None
    total_ventas: float
    total_efectivo: float
    total_transferencia: float
    total_garantia: float
    efectivo_declarado: float
    diferencia: float
    cantidad_ventas: int
    notas: Optional[str] = None
    fecha_registro: Optional[str] = None

# --- MODELOS DE HISTORIAL DE IMEI (TRAZABILIDAD 360°) ---

class HistorialImeiEvento(BaseModel):
    tipo: str  # 'INGRESO', 'VENTA', 'GARANTIA_RECLAMO', 'REEMPLAZO'
    fecha: str
    titulo: str
    descripcion: str
    detalles: Dict[str, Any] = {}

class HistorialImeiResponse(BaseModel):
    imei: str
    modelo: Optional[str] = None
    color: Optional[str] = None
    capacidad_gb: Optional[int] = None
    grado: Optional[str] = None
    estado_actual: str
    eventos: List[HistorialImeiEvento] = []


# --- MODELOS DE REPARACIONES Y TALLER TÉCNICO ---

ESTADOS_REPARACION_VALIDOS = (
    'Recibido', 'En Revision', 'Esperando Refaccion',
    'Listo para Entrega', 'Entregado', 'Cancelado'
)

class ReparacionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cliente_nombre: str = Field(..., min_length=2, max_length=150, description="Nombre del cliente")
    cliente_telefono: str = Field(..., min_length=7, max_length=30, description="Teléfono de contacto para avisos por WhatsApp")
    dispositivo_modelo: str = Field(..., min_length=1, max_length=150, description="Ej. iPhone 13, Galaxy A54")
    color: Optional[str] = Field("", max_length=60)
    imei_serie: Optional[str] = Field("", max_length=40)
    codigo_patron: Optional[str] = Field(None, max_length=100, description="PIN, contraseña o patrón para probar el equipo")
    falla_reportada: str = Field(..., min_length=2, max_length=500, description="Problema que reporta el cliente")
    diagnostico_tecnico: Optional[str] = Field(None, max_length=500)
    condicion_recepcion: Optional[str] = Field(None, max_length=500, description="Detalles estéticos con los que ingresa")
    costo_refaccion: float = Field(0.0, ge=0)
    precio_servicio: float = Field(..., ge=0, description="Precio total a cobrar al cliente")
    anticipo: float = Field(0.0, ge=0, description="Monto dejado a cuenta")
    tecnico_responsable: Optional[str] = Field("Samuel N.", max_length=100)
    notas: Optional[str] = Field(None, max_length=500)
    fecha_prometida: Optional[str] = Field(None, max_length=40)

    @field_validator('costo_refaccion', 'precio_servicio', 'anticipo')
    def validate_montos_reparacion(cls, v):
        return _check_finite_float(v, "monto de reparación")

class ReparacionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cliente_nombre: Optional[str] = Field(None, min_length=2, max_length=150)
    cliente_telefono: Optional[str] = Field(None, min_length=7, max_length=30)
    dispositivo_modelo: Optional[str] = Field(None, min_length=1, max_length=150)
    color: Optional[str] = Field(None, max_length=60)
    imei_serie: Optional[str] = Field(None, max_length=40)
    codigo_patron: Optional[str] = Field(None, max_length=100)
    falla_reportada: Optional[str] = Field(None, min_length=2, max_length=500)
    diagnostico_tecnico: Optional[str] = Field(None, max_length=500)
    condicion_recepcion: Optional[str] = Field(None, max_length=500)
    costo_refaccion: Optional[float] = Field(None, ge=0)
    precio_servicio: Optional[float] = Field(None, ge=0)
    anticipo: Optional[float] = Field(None, ge=0)
    saldo_pendiente: Optional[float] = Field(None, ge=0)
    estado: Optional[str] = None
    tecnico_responsable: Optional[str] = Field(None, max_length=100)
    notas: Optional[str] = Field(None, max_length=500)
    fecha_prometida: Optional[str] = Field(None, max_length=40)
    fecha_entrega: Optional[str] = Field(None, max_length=40)

    @field_validator('estado')
    def validate_estado_rep(cls, v):
        if v is not None and v not in ESTADOS_REPARACION_VALIDOS:
            raise ValueError(f"Estado inválido. Permitidos: {', '.join(ESTADOS_REPARACION_VALIDOS)}")
        return v

    @field_validator('costo_refaccion', 'precio_servicio', 'anticipo', 'saldo_pendiente')
    def validate_montos_rep_update(cls, v):
        return _check_finite_float(v, "monto de reparación")

class ReparacionAbono(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monto_abono: float = Field(..., gt=0, description="Monto del abono en efectivo o transferencia")
    metodo_pago: str = Field("Efectivo", max_length=50, description="Efectivo o Transferencia")
    notas: Optional[str] = Field(None, max_length=300)

    @field_validator('monto_abono')
    def validate_monto_abono(cls, v):
        return _check_finite_float(v, "monto_abono")

class ReparacionResponse(BaseModel):
    id: int
    folio: str
    cliente_nombre: str
    cliente_telefono: str
    dispositivo_modelo: str
    color: Optional[str] = None
    imei_serie: Optional[str] = None
    codigo_patron: Optional[str] = None
    falla_reportada: str
    diagnostico_tecnico: Optional[str] = None
    condicion_recepcion: Optional[str] = None
    costo_refaccion: Optional[float] = None
    precio_servicio: float
    anticipo: float
    saldo_pendiente: float
    estado: str
    fecha_ingreso: str
    fecha_prometida: Optional[str] = None
    fecha_entrega: Optional[str] = None
    tecnico_responsable: Optional[str] = None
    notas: Optional[str] = None
    margen_ganancia: Optional[float] = None
