import math
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

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
    tenant_id: Optional[int] = Field(None, description="ID del tenant (SaaS Multi-tenant)")
    sucursal_id: Optional[int] = Field(None, description="ID de la sucursal (SaaS Multi-tenant)")

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
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None

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
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None
    precio_venta: float
    estado: str
    fecha_registro: str
    margen_proyectado: Optional[float] = None
    porcentaje_margen: Optional[float] = None
    dias_en_stock: Optional[int] = 0
    estado_antiguedad: Optional[str] = "Fresco"
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None

class ClienteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(..., min_length=2, max_length=150, description="Nombre completo del cliente")
    telefono: str = Field(..., min_length=7, max_length=30, description="Teléfono de contacto")
    tenant_id: Optional[int] = Field(None, description="ID del tenant (SaaS Multi-tenant)")

class ClienteResponse(BaseModel):
    id: int
    nombre: str
    telefono: str
    fecha_registro: str
    tenant_id: Optional[int] = None

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
    tenant_id: Optional[int] = Field(None, description="ID del tenant (SaaS Multi-tenant)")
    sucursal_id: Optional[int] = Field(None, description="ID de la sucursal (SaaS Multi-tenant)")

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
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None

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
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None

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

    # Nota de Crédito (15 o 30 días)
    es_credito: bool = False
    plazo_dias: Optional[int] = Field(None, description="Plazo de crédito: 15 o 30 días")
    fecha_vencimiento: Optional[str] = Field(None, max_length=20, description="Fecha de vencimiento (YYYY-MM-DD)")
    monto_anticipo: float = Field(0.0, ge=0, description="Monto del anticipo inicial")
    
    # Soporte Multi-Tenant
    tenant_id: Optional[int] = Field(None, description="ID del tenant (SaaS Multi-tenant)")
    sucursal_id: Optional[int] = Field(None, description="ID de la sucursal (SaaS Multi-tenant)")

    # Retrocompatibilidad con venta de un solo equipo
    equipo_id: Optional[int] = None
    precio_final: Optional[float] = None

    @field_validator('monto_efectivo', 'monto_transferencia', 'monto_tarjeta', 'monto_garantia', 'precio_final', 'monto_anticipo')
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
        elif mp.lower() in ("nota de credito", "nota de crédito", "credito", "crédito") or self.es_credito:
            mp = "Nota de Crédito"
            self.metodo_pago = mp
            self.es_credito = True
            if self.plazo_dias is not None and self.plazo_dias not in (15, 30):
                raise ValueError("El plazo de crédito debe ser de 15 o 30 días.")
            if not self.plazo_dias:
                self.plazo_dias = 15
            if not self.fecha_vencimiento:
                self.fecha_vencimiento = (datetime.now() + timedelta(days=self.plazo_dias)).strftime("%Y-%m-%d")
            if self.monto_anticipo > total_venta:
                raise ValueError("El anticipo no puede ser mayor al total de la venta.")

        if mp == "Efectivo":
            if (self.monto_efectivo + self.monto_transferencia + self.monto_garantia) == 0:
                self.monto_efectivo = total_venta
        elif mp == "Transferencia":
            if (self.monto_efectivo + self.monto_transferencia + self.monto_garantia) == 0:
                self.monto_transferencia = total_venta
        elif mp == "Equipo Garantía":
            if (self.monto_efectivo + self.monto_transferencia + self.monto_garantia) == 0:
                self.monto_garantia = total_venta
        elif mp == "Nota de Crédito":
            self.monto_efectivo = self.monto_anticipo
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
    cliente_id: Optional[int] = None
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
    
    # Nota de Crédito (15 y 30 días)
    es_credito: bool = False
    plazo_dias: int = 0
    fecha_vencimiento: Optional[str] = None
    monto_credito: float = 0.0
    monto_anticipo: float = 0.0
    saldo_pendiente: float = 0.0
    estado_credito: Optional[str] = None
    abonos: List[Dict[str, Any]] = []

    # Retrocompatibilidad
    equipo_id: Optional[int] = None
    modelo: Optional[str] = None
    capacidad_gb: Optional[int] = None
    color: Optional[str] = None
    imei: Optional[str] = None
    grado: Optional[str] = None
    costo_compra: Optional[float] = None

    # Taller / Reparaciones
    folio: Optional[str] = None
    reparacion_id: Optional[int] = None
    diagnostico_tecnico: Optional[str] = None

class AbonoCreditoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monto: float = Field(..., gt=0, description="Monto del abono")
    metodo_pago: str = Field("Efectivo", max_length=50, description="Efectivo o Transferencia")
    notas: Optional[str] = Field(None, max_length=300)

    @field_validator('monto')
    def validate_monto_abono(cls, v):
        return _check_finite_float(v, "monto")

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
        if v not in ('Reemplazo', 'Reingreso a Inventario', 'Reembolso', 'Nota de Crédito', 'Reparación'):
            raise ValueError("solucion debe ser 'Reemplazo', 'Reingreso a Inventario', 'Reembolso', 'Nota de Crédito' o 'Reparación'")
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

class RestablecerEquipoGarantiaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nuevo_grado: Optional[str] = Field(None, max_length=5, description="Nuevo grado estético del equipo (A, B o C)")
    nuevo_precio_venta: Optional[float] = Field(None, ge=0, description="Nuevo precio de venta")
    costo_adicional: Optional[float] = Field(0.0, ge=0, description="Costo adicional de reparación o refacciones")
    notas: Optional[str] = Field(None, max_length=500, description="Observaciones técnicas o de reparación")

    @field_validator('nuevo_grado')
    def validate_grado(cls, v):
        if v is not None and v.strip() and v.strip().upper() not in ('A', 'B', 'C'):
            raise ValueError("El grado debe ser A, B o C")
        return v.strip().upper() if v and v.strip() else None

    @field_validator('nuevo_precio_venta', 'costo_adicional')
    def validate_precios_finitos(cls, v, info):
        return _check_finite_float(v, info.field_name)

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
    tenant_id: Optional[int] = Field(None, description="ID del tenant (SaaS Multi-tenant)")
    sucursal_id: Optional[int] = Field(None, description="ID de la sucursal (SaaS Multi-tenant)")

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
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None
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
    checklist_recepcion: Optional[str] = Field(None, description="Checklist JSON o resumen de inspección digital inicial")
    costo_refaccion: float = Field(0.0, ge=0)
    precio_servicio: float = Field(..., ge=0, description="Precio total a cobrar al cliente")
    anticipo: float = Field(0.0, ge=0, description="Monto dejado a cuenta")
    tecnico_responsable: Optional[str] = Field("Samuel N.", max_length=100)
    notas: Optional[str] = Field(None, max_length=500)
    fecha_prometida: Optional[str] = Field(None, max_length=40)
    tenant_id: Optional[int] = Field(None, description="ID del tenant (SaaS Multi-tenant)")
    sucursal_id: Optional[int] = Field(None, description="ID de la sucursal (SaaS Multi-tenant)")

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
    checklist_recepcion: Optional[str] = None
    costo_refaccion: Optional[float] = Field(None, ge=0)
    precio_servicio: Optional[float] = Field(None, ge=0)
    anticipo: Optional[float] = Field(None, ge=0)
    saldo_pendiente: Optional[float] = Field(None, ge=0)
    estado: Optional[str] = None
    tecnico_responsable: Optional[str] = Field(None, max_length=100)
    notas: Optional[str] = Field(None, max_length=500)
    fecha_prometida: Optional[str] = Field(None, max_length=40)
    fecha_entrega: Optional[str] = Field(None, max_length=40)
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None

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
    checklist_recepcion: Optional[str] = None
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
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None

# --- MODELOS DE GASTOS OPERATIVOS ---

CATEGORIAS_GASTO_VALIDAS = (
    'Renta', 'Luz / Servicios', 'Sueldos', 'Publicidad',
    'Refacciones', 'Comida / Viáticos', 'Mantenimiento',
    'Herramientas', 'General', 'Otro'
)

class GastoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concepto: str = Field(..., min_length=2, max_length=200, description="Concepto o descripción del gasto")
    categoria: str = Field("General", max_length=60, description="Categoría del gasto")
    monto: float = Field(..., gt=0, description="Monto del gasto")
    fecha: Optional[str] = Field(None, max_length=40, description="Fecha del gasto (YYYY-MM-DD o YYYY-MM-DD HH:MM:SS)")
    metodo_pago: str = Field("Efectivo", max_length=50, description="Método de pago (Efectivo, Transferencia, Tarjeta)")
    comprobante_url: Optional[str] = Field(None, max_length=500, description="URL o referencia de comprobante")
    notas: Optional[str] = Field(None, max_length=500, description="Notas complementarias")
    tenant_id: Optional[int] = Field(None, description="ID del tenant")
    sucursal_id: Optional[int] = Field(None, description="ID de la sucursal")

    @field_validator('monto')
    def validate_monto_gasto(cls, v):
        return _check_finite_float(v, "monto del gasto")

    @field_validator('categoria')
    def validate_categoria_gasto(cls, v):
        if not v or not v.strip():
            return "General"
        return v.strip()[:60]

class GastoResponse(BaseModel):
    id: int
    concepto: str
    categoria: str
    monto: float
    fecha: str
    metodo_pago: str
    comprobante_url: Optional[str] = None
    usuario: str
    notas: Optional[str] = None
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None


# ==============================================================================
# MODELOS MULTI-TENANT SAAS (Tenants, Sucursales, Configuración Tienda)
# ==============================================================================

class TenantBase(BaseModel):
    nombre_comercial: str = Field(..., min_length=2, max_length=150, description="Nombre comercial del negocio / tienda")
    slug: str = Field(..., min_length=2, max_length=60, description="Identificador único para URL/subdominio (slug alfanumérico)")
    email_contacto: Optional[str] = Field(None, max_length=120, description="Correo electrónico de contacto")
    telefono: Optional[str] = Field(None, max_length=30, description="Teléfono de contacto")
    plan: str = Field("basico", max_length=50, description="Plan de suscripción: gratis, basico, pro, enterprise")
    activo: bool = Field(True, description="Estado de la cuenta/tenant")

    @field_validator('slug')
    def validate_slug(cls, v):
        v = v.strip().lower().replace(" ", "-")
        if not all(c.isalnum() or c in ('-', '_') for c in v):
            raise ValueError("El slug solo debe contener letras, números, guiones y guiones bajos.")
        return v

class TenantCreate(TenantBase):
    model_config = ConfigDict(extra="forbid")

class TenantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre_comercial: Optional[str] = Field(None, min_length=2, max_length=150)
    email_contacto: Optional[str] = Field(None, max_length=120)
    telefono: Optional[str] = Field(None, max_length=30)
    plan: Optional[str] = Field(None, max_length=50)
    activo: Optional[bool] = None

class TenantResponse(TenantBase):
    id: int
    fecha_creacion: str


class SucursalBase(BaseModel):
    tenant_id: int = Field(..., description="ID del tenant al que pertenece la sucursal")
    nombre_sucursal: str = Field(..., min_length=2, max_length=100, description="Nombre de la sucursal o punto de venta")
    direccion: Optional[str] = Field(None, max_length=255, description="Dirección física de la sucursal")
    telefono: Optional[str] = Field(None, max_length=30, description="Teléfono de la sucursal")
    es_matriz: bool = Field(False, description="Indica si es la sucursal principal o matriz")

class SucursalCreate(SucursalBase):
    model_config = ConfigDict(extra="forbid")

class SucursalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre_sucursal: Optional[str] = Field(None, min_length=2, max_length=100)
    direccion: Optional[str] = Field(None, max_length=255)
    telefono: Optional[str] = Field(None, max_length=30)
    es_matriz: Optional[bool] = None

class SucursalResponse(SucursalBase):
    id: int
    fecha_registro: Optional[str] = None


class ConfiguracionTiendaBase(BaseModel):
    tenant_id: int = Field(..., description="ID del tenant asociado a esta configuración")
    logo_url: Optional[str] = Field(None, max_length=500, description="URL pública del logotipo")
    encabezado_ticket: Optional[str] = Field(None, max_length=300, description="Texto personalizado en cabecera de tickets")
    pie_ticket_garantia: Optional[str] = Field(None, max_length=500, description="Texto de políticas y garantía al pie del ticket")
    whatsapp_notificaciones: Optional[str] = Field(None, max_length=30, description="Número de WhatsApp para notificaciones del negocio")

class ConfiguracionTiendaCreate(ConfiguracionTiendaBase):
    model_config = ConfigDict(extra="forbid")

class ConfiguracionTiendaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    logo_url: Optional[str] = Field(None, max_length=500)
    encabezado_ticket: Optional[str] = Field(None, max_length=300)
    pie_ticket_garantia: Optional[str] = Field(None, max_length=500)
    whatsapp_notificaciones: Optional[str] = Field(None, max_length=30)

class ConfiguracionTiendaResponse(ConfiguracionTiendaBase):
    id: int
    fecha_actualizacion: Optional[str] = None


class ConfiguracionGeneralUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre_comercial: Optional[str] = Field(None, min_length=1, max_length=150, description="Nombre del negocio")
    telefono: Optional[str] = Field(None, max_length=30, description="Teléfono de contacto general")
    whatsapp_notificaciones: Optional[str] = Field(None, max_length=30, description="WhatsApp para notificaciones de tickets")
    direccion: Optional[str] = Field(None, max_length=250, description="Dirección física del establecimiento")
    encabezado_ticket: Optional[str] = Field(None, max_length=300, description="Encabezado impreso en tickets térmicos")
    pie_ticket_garantia: Optional[str] = Field(None, max_length=500, description="Póliza de garantía impresa al pie")


class ConfiguracionGeneralResponse(BaseModel):
    tenant_id: int
    nombre_comercial: str
    slug: str
    email_contacto: Optional[str] = None
    telefono: Optional[str] = None
    whatsapp_notificaciones: Optional[str] = None
    direccion: Optional[str] = None
    nombre_sucursal: Optional[str] = None
    logo_url: Optional[str] = None
    encabezado_ticket: Optional[str] = None
    pie_ticket_garantia: Optional[str] = None
    fecha_actualizacion: Optional[str] = None


# ==============================================================================
# MODELOS DE USUARIO Y LOGIN MULTI-TENANT
# ==============================================================================

class UsuarioBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=150)
    username: str = Field(..., min_length=2, max_length=80)
    rol: str = Field("vendedor", description="Rol de acceso: dueno, vendedor, tecnico")
    activo: bool = Field(True, description="Estado del usuario")
    tenant_id: Optional[int] = Field(None, description="ID del tenant al que pertenece")
    sucursal_id: Optional[int] = Field(None, description="ID de la sucursal asignada")

class UsuarioCreate(UsuarioBase):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(..., min_length=4, max_length=120)

class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    username: str
    rol: str
    activo: bool = True
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None
    tenant_slug: Optional[str] = None


class EmpleadoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(..., min_length=2, max_length=150, description="Nombre completo del empleado")
    username: str = Field(..., min_length=3, max_length=60, description="Nombre de usuario único para inicio de sesión")
    password: str = Field(..., min_length=4, max_length=120, description="Contraseña de acceso")
    rol: str = Field(..., description="Rol del empleado: vendedor o tecnico")

    @field_validator('rol')
    def validate_rol(cls, v):
        v = v.strip().lower()
        if v not in ('vendedor', 'tecnico'):
            raise ValueError("El rol debe ser 'vendedor' o 'tecnico'")
        return v

    @field_validator('username')
    def validate_username(cls, v):
        v = v.strip().lower()
        if len(v) < 3:
            raise ValueError("El nombre de usuario debe tener al menos 3 caracteres")
        if not v.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValueError("El nombre de usuario solo puede contener letras, números, puntos, guiones y guiones bajos")
        return v

class EmpleadoEstadoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activo: bool = Field(..., description="Estado del empleado: True (activo) o False (suspendido/inactivo)")

class EmpleadoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    username: str
    rol: str
    activo: bool = True
    fecha_creacion: Optional[str] = None
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None


