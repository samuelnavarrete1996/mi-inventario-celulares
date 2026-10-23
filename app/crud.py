import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from app.database import get_db_connection
from app.models import EquipoCreate, EquipoUpdate, ItemCarrito, GarantiaCreate

COLUMNAS_PERMITIDAS_EQUIPO = {
    "modelo", "capacidad_gb", "color", "grado",
    "costo_compra", "precio_venta", "estado"
}

def _begin_immediate(cursor) -> None:
    """Inicia una transacción con bloqueo de escritura inmediato en SQLite para prevenir condiciones de carrera (TOCTOU)."""
    try:
        cursor.execute("BEGIN IMMEDIATE;")
    except Exception:
        cursor.execute("BEGIN TRANSACTION;")

def _get_default_tenant_and_sucursal() -> Tuple[int, int]:
    """Obtiene tenant y sucursal por defecto para fallback seguro en tests o llamadas sin contexto explícito."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM tenants WHERE slug = 'demo-celulares' LIMIT 1;")
        r_t = c.fetchone()
        t_id = (r_t["id"] if isinstance(r_t, dict) or hasattr(r_t, '__getitem__') else r_t[0]) if r_t else 1
        c.execute("SELECT id FROM sucursales WHERE tenant_id = ? AND (es_matriz IS TRUE OR es_matriz = TRUE) LIMIT 1;", (t_id,))
        r_s = c.fetchone()
        s_id = (r_s["id"] if isinstance(r_s, dict) or hasattr(r_s, '__getitem__') else r_s[0]) if r_s else 1
        conn.close()
        return int(t_id), int(s_id)
    except Exception:
        return 1, 1

def format_equipo_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convierte un row de equipo a dict y añade cálculos de margen proyectado y días en almacén."""
    d = dict(row)
    costo = d.get("costo_compra", 0.0)
    precio = d.get("precio_venta", 0.0)
    margen = round(precio - costo, 2)
    porcentaje = round((margen / costo * 100), 1) if costo > 0 else 0.0
    d["margen_proyectado"] = margen
    d["porcentaje_margen"] = porcentaje

    # Cálculo de antigüedad en inventario (Aging Stock)
    fecha_reg_str = d.get("fecha_registro")
    dias = 0
    if fecha_reg_str:
        try:
            dt_reg = datetime.strptime(fecha_reg_str[:10], "%Y-%m-%d")
            dias = max(0, (datetime.now() - dt_reg).days)
        except Exception:
            dias = 0
    d["dias_en_stock"] = dias
    if dias < 15:
        d["estado_antiguedad"] = "Fresco"
    elif dias <= 30:
        d["estado_antiguedad"] = "Normal"
    elif dias <= 45:
        d["estado_antiguedad"] = "Lento"
    else:
        d["estado_antiguedad"] = "Remate"

    return d

def get_equipos(
    solo_disponibles: bool = True,
    search: Optional[str] = None,
    grado: Optional[str] = None,
    estado: Optional[str] = None,
    tenant_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Obtiene equipos con filtros opcionales y aislamiento multi-tenant estricto."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    query = "SELECT * FROM equipos WHERE 1=1"
    params = []

    if tenant_id is not None:
        query += " AND tenant_id = ?"
        params.append(tenant_id)

    if estado:
        if estado.strip().lower() != 'todos':
            query += " AND estado = ?"
            params.append(estado.strip())
    elif solo_disponibles:
        query += " AND estado = 'Disponible'"

    if grado:
        query += " AND grado = ?"
        params.append(grado.upper())

    if search:
        search_param = f"%{search.strip()}%"
        query += " AND (modelo LIKE ? OR imei LIKE ? OR color LIKE ?)"
        params.extend([search_param, search_param, search_param])

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [format_equipo_dict(r) for r in rows]

def get_equipo_by_id(equipo_id: int, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Obtiene un equipo por su ID validando obligatoriamente el tenant_id si se proporciona."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    if tenant_id is not None:
        cursor.execute("SELECT * FROM equipos WHERE id = ? AND tenant_id = ?", (equipo_id, tenant_id))
    else:
        cursor.execute("SELECT * FROM equipos WHERE id = ?", (equipo_id,))
    row = cursor.fetchone()
    conn.close()
    return format_equipo_dict(row) if row else None

def get_equipo_by_imei(imei: str, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Busca un equipo por IMEI dentro del tenant actual."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    if tenant_id is not None:
        cursor.execute("SELECT * FROM equipos WHERE imei = ? AND tenant_id = ?", (imei.strip(), tenant_id))
    else:
        cursor.execute("SELECT * FROM equipos WHERE imei = ?", (imei.strip(),))
    row = cursor.fetchone()
    conn.close()
    return format_equipo_dict(row) if row else None

def create_equipo(
    data: EquipoCreate,
    tenant_id: Optional[int] = None,
    sucursal_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Registra un nuevo teléfono inyectando automáticamente el tenant_id y sucursal_id
    del usuario en sesión para prevenir manipulación por parte del cliente.
    """
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    if tenant_id is None:
        def_t, def_s = _get_default_tenant_and_sucursal()
        final_tenant_id = getattr(data, 'tenant_id', None) or def_t
        final_sucursal_id = getattr(data, 'sucursal_id', None) or def_s
    else:
        final_tenant_id = tenant_id
        final_sucursal_id = sucursal_id or getattr(data, 'sucursal_id', None)

    try:
        _begin_immediate(cursor)
        cursor.execute(
            "SELECT id FROM equipos WHERE imei = ? AND tenant_id = ?",
            (data.imei.strip(), final_tenant_id)
        )
        if cursor.fetchone():
            conn.rollback()
            raise ValueError(f"Ya existe un equipo registrado con el IMEI {data.imei} en este negocio.")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        INSERT INTO equipos (
            modelo, capacidad_gb, color, imei, grado, costo_compra,
            precio_venta, estado, fecha_registro, tenant_id, sucursal_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Disponible', ?, ?, ?)
        """, (
            data.modelo.strip(),
            data.capacidad_gb,
            data.color.strip(),
            data.imei.strip(),
            data.grado.upper(),
            round(data.costo_compra, 2),
            round(data.precio_venta, 2),
            now,
            final_tenant_id,
            final_sucursal_id
        ))
        conn.commit()
        new_id = cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return get_equipo_by_id(new_id, tenant_id=final_tenant_id)

def update_equipo(
    equipo_id: int,
    data: EquipoUpdate,
    tenant_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Actualiza datos de un equipo validando que pertenezca al tenant del usuario en sesión."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    current = get_equipo_by_id(equipo_id, tenant_id=tenant_id)
    if not current:
        conn.close()
        return None

    fields = []
    values = []
    for field, val in data.model_dump(exclude_unset=True).items():
        if val is not None and field in COLUMNAS_PERMITIDAS_EQUIPO:
            fields.append(f"{field} = ?")
            values.append(val)

    if not fields:
        conn.close()
        return current

    values.append(equipo_id)
    if tenant_id is not None:
        values.append(tenant_id)
        sql = f"UPDATE equipos SET {', '.join(fields)} WHERE id = ? AND tenant_id = ?"
    else:
        sql = f"UPDATE equipos SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(sql, values)
    conn.commit()
    conn.close()

    return get_equipo_by_id(equipo_id, tenant_id=tenant_id)

def delete_equipo(equipo_id: int, tenant_id: Optional[int] = None) -> bool:
    """Elimina un equipo si aún no ha sido vendido y pertenece al tenant en sesión."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    current = get_equipo_by_id(equipo_id, tenant_id=tenant_id)
    if not current:
        conn.close()
        return False

    cursor.execute("SELECT id FROM venta_items WHERE equipo_id = ?", (equipo_id,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("No se puede eliminar un equipo que ya cuenta con un registro de venta histórico.")

    if tenant_id is not None:
        cursor.execute("DELETE FROM equipos WHERE id = ? AND tenant_id = ?", (equipo_id, tenant_id))
    else:
        cursor.execute("DELETE FROM equipos WHERE id = ?", (equipo_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# --- CLIENTES ---

def get_or_create_cliente(nombre: str, telefono: str, tenant_id: Optional[int] = None, cursor: Optional[Any] = None) -> int:
    """Busca o registra un cliente dentro del tenant especificado."""
    close_conn = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        close_conn = True
    else:
        conn = None

    clean_tel = telefono.strip()
    if tenant_id is not None:
        cursor.execute("SELECT id FROM clientes WHERE telefono = ? AND tenant_id = ?", (clean_tel, tenant_id))
    else:
        cursor.execute("SELECT id FROM clientes WHERE telefono = ?", (clean_tel,))
    row = cursor.fetchone()

    if row:
        cliente_id = row["id"]
        cursor.execute("UPDATE clientes SET nombre = ? WHERE id = ?", (nombre.strip(), cliente_id))
        if close_conn and conn:
            conn.commit()
            conn.close()
        return cliente_id
    else:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if tenant_id is not None:
            cursor.execute("""
            INSERT INTO clientes (nombre, telefono, fecha_registro, tenant_id)
            VALUES (?, ?, ?, ?)
            """, (nombre.strip(), clean_tel, now, tenant_id))
        else:
            cursor.execute("""
            INSERT INTO clientes (nombre, telefono, fecha_registro)
            VALUES (?, ?, ?)
            """, (nombre.strip(), clean_tel, now))
        cliente_id = cursor.lastrowid
        if close_conn and conn:
            conn.commit()
            conn.close()
        return cliente_id

def get_cliente_by_phone(telefono: str, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Obtiene un cliente por teléfono dentro del tenant especificado."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    if tenant_id is not None:
        cursor.execute("SELECT * FROM clientes WHERE telefono = ? AND tenant_id = ?", (telefono.strip(), tenant_id))
    else:
        cursor.execute("SELECT * FROM clientes WHERE telefono = ?", (telefono.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# --- VENTAS Y FORMAS DE PAGO (EFECTIVO, TRANSFERENCIA, COMBINADO, EQUIPO GARANTÍA) ---

def registrar_venta_carrito(
    items: List[ItemCarrito],
    cliente_nombre: str,
    cliente_telefono: str,
    metodo_pago: str = "Efectivo",
    monto_efectivo: float = 0.0,
    monto_transferencia: float = 0.0,
    monto_tarjeta: float = 0.0,
    monto_garantia: float = 0.0,
    notas: Optional[str] = None,
    es_credito: bool = False,
    plazo_dias: Optional[int] = None,
    fecha_vencimiento: Optional[str] = None,
    monto_anticipo: float = 0.0,
    tenant_id: Optional[int] = None,
    sucursal_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Registra una venta con múltiples equipos o accesorios/servicios y métodos de pago:
    Efectivo, Transferencia, Combinado o Equipo Garantía.
    Inyecta automáticamente tenant_id y sucursal_id y valida propiedad multi-tenant estricta.
    """
    if not items or len(items) == 0:
        raise ValueError("El carrito de compras no contiene artículos.")

    if tenant_id is None:
        def_t, def_s = _get_default_tenant_and_sucursal()
        final_tenant_id = def_t
        final_sucursal_id = def_s
    else:
        final_tenant_id = tenant_id
        final_sucursal_id = sucursal_id

    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    try:
        _begin_immediate(cursor)

        # 1. Validar equipos y accesorios pertenecientes al tenant
        detalles_items = []
        total_precio_final = 0.0
        total_margen_ganancia = 0.0
        equipos_ids_usados = []

        for item in items:
            t_item = getattr(item, "tipo_item", "equipo") or "equipo"
            if item.equipo_id:
                if item.equipo_id in equipos_ids_usados:
                    raise ValueError(f"El equipo con ID {item.equipo_id} está duplicado en el carrito.")
                equipos_ids_usados.append(item.equipo_id)

                cursor.execute(
                    "SELECT * FROM equipos WHERE id = ? AND tenant_id = ?",
                    (item.equipo_id, final_tenant_id)
                )
                eq = cursor.fetchone()
                if not eq:
                    raise ValueError(f"El equipo con ID {item.equipo_id} no existe o no pertenece a este negocio.")
                if eq["estado"] != "Disponible":
                    raise ValueError(f"El equipo '{eq['modelo']}' (IMEI: {eq['imei']}) ya no está disponible (Estado actual: {eq['estado']}).")

                costo = float(eq["costo_compra"])
                precio_item = round(float(item.precio_final), 2)
                margen_item = round(precio_item - costo, 2)

                total_precio_final += precio_item
                total_margen_ganancia += margen_item

                detalles_items.append({
                    "tipo_item": "equipo",
                    "equipo_id": item.equipo_id,
                    "accesorio_id": None,
                    "nombre_item": f"{eq['modelo']} ({eq['imei']})",
                    "cantidad": 1,
                    "precio_final": precio_item,
                    "costo_compra": costo,
                    "margen_ganancia": margen_item
                })

            elif item.accesorio_id:
                cursor.execute(
                    "SELECT * FROM accesorios WHERE id = ? AND tenant_id = ?",
                    (item.accesorio_id, final_tenant_id)
                )
                acc = cursor.fetchone()
                if not acc:
                    raise ValueError(f"El accesorio/servicio con ID {item.accesorio_id} no existe o no pertenece a este negocio.")
                
                cant = getattr(item, "cantidad", 1) or 1
                if cant <= 0:
                    raise ValueError("La cantidad debe ser al menos 1.")
                if not acc["es_servicio"] and acc["stock"] < cant:
                    raise ValueError(f"Stock insuficiente para '{acc['nombre']}'. Disponible: {acc['stock']}, Solicitado: {cant}")

                costo_total = round(float(acc["costo_compra"]) * cant, 2)
                precio_item = round(float(item.precio_final), 2)
                margen_item = round(precio_item - costo_total, 2)

                total_precio_final += precio_item
                total_margen_ganancia += margen_item

                acc_color = acc["color"] if "color" in acc.keys() and acc["color"] else None
                nombre_con_color = f"{acc['nombre']} ({acc_color})" if (acc_color and f"({acc_color})" not in acc["nombre"]) else acc["nombre"]
                nombre_final = getattr(item, "nombre_item", None) or nombre_con_color

                detalles_items.append({
                    "tipo_item": "servicio" if acc["es_servicio"] else "accesorio",
                    "equipo_id": None,
                    "accesorio_id": item.accesorio_id,
                    "nombre_item": nombre_final,
                    "cantidad": cant,
                    "precio_final": precio_item,
                    "costo_compra": costo_total,
                    "margen_ganancia": margen_item,
                    "es_servicio": bool(acc["es_servicio"])
                })
            else:
                raise ValueError("Cada línea del carrito debe especificar un equipo o un accesorio.")

        # 2. Cliente scoped al tenant
        cliente_id = get_or_create_cliente(cliente_nombre, cliente_telefono, tenant_id=final_tenant_id, cursor=cursor)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        total_precio_final = round(total_precio_final, 2)
        total_margen_ganancia = round(total_margen_ganancia, 2)

        # 3. Validar método de pago
        metodo = metodo_pago.strip()
        es_cred = bool(es_credito or metodo.lower() in ("nota de credito", "nota de crédito", "credito", "crédito"))

        if es_cred:
            metodo = "Nota de Crédito"
            plazo = plazo_dias if (plazo_dias in (15, 30)) else 15
            if not fecha_vencimiento:
                f_venc = (datetime.now() + timedelta(days=plazo)).strftime("%Y-%m-%d")
            else:
                f_venc = fecha_vencimiento.strip()
            anticipo = round(float(monto_anticipo or 0.0), 2)
            saldo = max(0.0, round(total_precio_final - anticipo, 2))
            estado_cred = "Liquidada" if saldo <= 0 else "Pendiente"
            m_efectivo = anticipo
            m_transf = 0.0
            m_tarjeta = 0.0
            m_garantia = 0.0
        else:
            plazo = 0
            f_venc = None
            anticipo = 0.0
            saldo = 0.0
            estado_cred = None
            if metodo.lower() in ("equipo garantia", "equipo garantía", "garantia", "garantía"):
                metodo = "Equipo Garantía"
            elif metodo.lower() in ("transferencia", "transf"):
                metodo = "Transferencia"
            elif metodo.lower() in ("combinado", "combinar"):
                metodo = "Combinado"
            else:
                metodo = "Efectivo"

            m_efectivo = round(float(monto_efectivo), 2)
            m_transf = round(float(monto_transferencia), 2)
            m_tarjeta = round(float(monto_tarjeta), 2)
            m_garantia = round(float(monto_garantia), 2)

            if metodo == "Efectivo" and (m_efectivo + m_transf + m_garantia) == 0:
                m_efectivo = total_precio_final
            elif metodo == "Transferencia" and (m_efectivo + m_transf + m_garantia) == 0:
                m_transf = total_precio_final
            elif metodo == "Equipo Garantía" and (m_efectivo + m_transf + m_garantia) == 0:
                m_garantia = total_precio_final
            elif metodo == "Combinado":
                suma_pagos = round(m_efectivo + m_transf + m_tarjeta + m_garantia, 2)
                if abs(suma_pagos - total_precio_final) > 0.05:
                    raise ValueError(f"En pago combinado, la suma de montos (${suma_pagos:,.2f}) debe coincidir con el total (${total_precio_final:,.2f}).")

        # 4. Insertar Cabecera de Venta con tenant_id y sucursal_id
        primer_equipo_id = equipos_ids_usados[0] if equipos_ids_usados else None
        cursor.execute("""
        INSERT INTO ventas (
            equipo_id, cliente_id, precio_final, margen_ganancia, fecha_venta,
            metodo_pago, monto_efectivo, monto_transferencia, monto_tarjeta, monto_garantia, notas,
            es_credito, plazo_dias, fecha_vencimiento, monto_credito, monto_anticipo, saldo_pendiente, estado_credito,
            tenant_id, sucursal_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            primer_equipo_id, cliente_id, total_precio_final, total_margen_ganancia, now,
            metodo, m_efectivo, m_transf, m_tarjeta, m_garantia, notas,
            1 if es_cred else 0,
            plazo if es_cred else 0,
            f_venc if es_cred else None,
            total_precio_final if es_cred else 0.0,
            anticipo if es_cred else 0.0,
            saldo if es_cred else 0.0,
            estado_cred if es_cred else None,
            final_tenant_id,
            final_sucursal_id
        ))
        venta_id = cursor.lastrowid

        if es_cred and anticipo > 0:
            cursor.execute("""
            INSERT INTO abonos_ventas_credito (venta_id, monto, fecha, metodo_pago, notas, usuario)
            VALUES (?, ?, ?, 'Efectivo', 'Anticipo inicial', 'Cajero')
            """, (venta_id, anticipo, now))

        # 5. Insertar items y actualizar estado/stock de forma atómica (Compare-And-Swap)
        for det in detalles_items:
            if det["equipo_id"]:
                cursor.execute(
                    "UPDATE equipos SET estado = 'Vendido' WHERE id = ? AND estado = 'Disponible' AND tenant_id = ?",
                    (det["equipo_id"], final_tenant_id)
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"El equipo '{det['nombre_item']}' ya fue vendido en una operación simultánea.")
            elif det["accesorio_id"] and not det.get("es_servicio", False):
                cursor.execute("SELECT stock FROM accesorios WHERE id = ? AND tenant_id = ?", (det["accesorio_id"], final_tenant_id))
                prev_row = cursor.fetchone()
                prev_stock = prev_row["stock"] if prev_row else 0

                cursor.execute(
                    "UPDATE accesorios SET stock = stock - ? WHERE id = ? AND stock >= ? AND tenant_id = ?",
                    (det["cantidad"], det["accesorio_id"], det["cantidad"], final_tenant_id)
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"Stock insuficiente para '{det['nombre_item']}' debido a una venta simultánea.")

                try:
                    cursor.execute("""
                    INSERT INTO movimientos_stock_accesorios (accesorio_id, tipo_movimiento, cantidad, stock_anterior, stock_nuevo, motivo, usuario, fecha)
                    VALUES (?, 'VENTA', ?, ?, ?, ?, ?, ?);
                    """, (
                        det["accesorio_id"],
                        det["cantidad"],
                        prev_stock,
                        prev_stock - det["cantidad"],
                        f"Venta en POS #{venta_id}",
                        "Venta Mostrador",
                        now
                    ))
                except Exception:
                    pass

            cursor.execute("""
            INSERT INTO venta_items (venta_id, equipo_id, accesorio_id, tipo_item, nombre_item, cantidad, precio_final, costo_compra, margen_ganancia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                venta_id,
                det["equipo_id"],
                det["accesorio_id"],
                det["tipo_item"],
                det["nombre_item"],
                det["cantidad"],
                det["precio_final"],
                det["costo_compra"],
                det["margen_ganancia"]
            ))

        conn.commit()
        return get_venta_detalle(venta_id, conn, tenant_id=final_tenant_id)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_venta_detalle(
    venta_id: int,
    conn_ext: Optional[sqlite3.Connection] = None,
    tenant_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    conn = conn_ext if conn_ext else get_db_connection()
    cursor = conn.cursor()

    query_v = """
    SELECT 
        v.id,
        v.cliente_id,
        v.precio_final,
        v.margen_ganancia,
        v.fecha_venta,
        v.metodo_pago,
        v.monto_efectivo,
        v.monto_transferencia,
        COALESCE(v.monto_tarjeta, 0) as monto_tarjeta,
        COALESCE(v.monto_garantia, 0) as monto_garantia,
        v.notas,
        v.equipo_id,
        COALESCE(v.es_credito, 0) as es_credito,
        COALESCE(v.plazo_dias, 0) as plazo_dias,
        v.fecha_vencimiento,
        COALESCE(v.monto_credito, 0) as monto_credito,
        COALESCE(v.monto_anticipo, 0) as monto_anticipo,
        COALESCE(v.saldo_pendiente, 0) as saldo_pendiente,
        v.estado_credito,
        v.tenant_id,
        v.sucursal_id,
        c.nombre as cliente_nombre,
        c.telefono as cliente_telefono
    FROM ventas v
    JOIN clientes c ON v.cliente_id = c.id
    WHERE v.id = ?
    """
    params_v = [venta_id]
    if tenant_id is not None:
        query_v += " AND v.tenant_id = ?"
        params_v.append(tenant_id)

    cursor.execute(query_v, params_v)
    venta_row = cursor.fetchone()

    if not venta_row:
        if not conn_ext:
            conn.close()
        return None

    venta_dict = dict(venta_row)

    cursor.execute("""
    SELECT 
        vi.id,
        vi.venta_id,
        vi.equipo_id,
        vi.accesorio_id,
        COALESCE(vi.tipo_item, 'equipo') as tipo_item,
        COALESCE(vi.nombre_item, e.modelo, a.nombre, 'Artículo') as nombre_item,
        COALESCE(vi.cantidad, 1) as cantidad,
        vi.precio_final,
        vi.costo_compra,
        vi.margen_ganancia,
        COALESCE(e.modelo, a.nombre, vi.nombre_item, 'Artículo') as modelo,
        e.capacidad_gb,
        e.color,
        e.imei,
        e.grado
    FROM venta_items vi
    LEFT JOIN equipos e ON vi.equipo_id = e.id
    LEFT JOIN accesorios a ON vi.accesorio_id = a.id
    WHERE vi.venta_id = ?
    ORDER BY vi.id ASC
    """, (venta_id,))
    items_rows = cursor.fetchall()
    items = [dict(r) for r in items_rows]

    if len(items) == 0 and venta_dict.get("equipo_id"):
        cursor.execute("SELECT * FROM equipos WHERE id = ?", (venta_dict["equipo_id"],))
        eq = cursor.fetchone()
        if eq:
            items = [{
                "id": 1,
                "venta_id": venta_id,
                "equipo_id": eq["id"],
                "accesorio_id": None,
                "tipo_item": "equipo",
                "nombre_item": eq["modelo"],
                "cantidad": 1,
                "precio_final": venta_dict["precio_final"],
                "costo_compra": eq["costo_compra"],
                "margen_ganancia": venta_dict["margen_ganancia"],
                "modelo": eq["modelo"],
                "capacidad_gb": eq["capacidad_gb"],
                "color": eq["color"],
                "imei": eq["imei"],
                "grado": eq["grado"]
            }]

    venta_dict["items"] = items
    venta_dict["total_equipos"] = len(items)

    modelos_nombres = []
    for it in items:
        nom = it.get("modelo") or it.get("nombre_item") or "Item"
        if it.get("capacidad_gb"):
            nom += f" ({it['capacidad_gb']}GB)"
        if it.get("cantidad", 1) > 1:
            nom += f" x{it['cantidad']}"
        modelos_nombres.append(nom)

    venta_dict["resumen_modelos"] = ", ".join(modelos_nombres) if modelos_nombres else "Sin artículos"

    if items:
        p = items[0]
        venta_dict["modelo"] = p.get("modelo") or p.get("nombre_item")
        venta_dict["capacidad_gb"] = p.get("capacidad_gb")
        venta_dict["color"] = p.get("color")
        venta_dict["imei"] = p.get("imei")
        venta_dict["grado"] = p.get("grado")
        venta_dict["costo_compra"] = p.get("costo_compra")

    cursor.execute("SELECT * FROM abonos_ventas_credito WHERE venta_id = ? ORDER BY id ASC", (venta_id,))
    venta_dict["abonos"] = [dict(a) for a in cursor.fetchall()]

    if not conn_ext:
        conn.close()

    return venta_dict

def get_historial_ventas(
    limit: int = 200,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    tipo: Optional[str] = "todos",
    tenant_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    query = """
    SELECT 
        v.id,
        v.cliente_id,
        v.precio_final,
        v.margen_ganancia,
        v.fecha_venta,
        v.metodo_pago,
        v.monto_efectivo,
        v.monto_transferencia,
        COALESCE(v.monto_tarjeta, 0) as monto_tarjeta,
        COALESCE(v.monto_garantia, 0) as monto_garantia,
        v.notas,
        v.equipo_id,
        COALESCE(v.es_credito, 0) as es_credito,
        COALESCE(v.plazo_dias, 0) as plazo_dias,
        v.fecha_vencimiento,
        COALESCE(v.monto_credito, 0) as monto_credito,
        COALESCE(v.monto_anticipo, 0) as monto_anticipo,
        COALESCE(v.saldo_pendiente, 0) as saldo_pendiente,
        v.estado_credito,
        v.tenant_id,
        v.sucursal_id,
        c.nombre as cliente_nombre,
        c.telefono as cliente_telefono
    FROM ventas v
    JOIN clientes c ON v.cliente_id = c.id
    WHERE 1=1
    """
    params = []

    if tenant_id is not None:
        query += " AND v.tenant_id = ?"
        params.append(tenant_id)

    if fecha_inicio:
        query += " AND date(v.fecha_venta) >= date(?)"
        params.append(fecha_inicio)

    if fecha_fin:
        query += " AND date(v.fecha_venta) <= date(?)"
        params.append(fecha_fin)

    tipo_filtro = (tipo or "todos").lower().strip()
    resultado = []

    # 1. Ventas estándar de mostrador (si no se pide exclusivamente taller/reparaciones)
    if tipo_filtro not in ("reparaciones", "taller"):
        query += " ORDER BY v.id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        ventas_rows = cursor.fetchall()

        for vr in ventas_rows:
            v_dict = dict(vr)
            v_id = v_dict["id"]

            cursor.execute("""
            SELECT 
                vi.id,
                vi.venta_id,
                vi.equipo_id,
                vi.accesorio_id,
                COALESCE(vi.tipo_item, CASE WHEN vi.equipo_id IS NOT NULL THEN 'equipo' ELSE 'accesorio' END) as tipo_item,
                COALESCE(vi.nombre_item, e.modelo, a.nombre, 'Artículo') as nombre_item,
                COALESCE(vi.cantidad, 1) as cantidad,
                vi.precio_final,
                vi.costo_compra,
                vi.margen_ganancia,
                COALESCE(e.modelo, a.nombre, vi.nombre_item, 'Artículo') as modelo,
                e.capacidad_gb,
                e.color,
                e.imei,
                e.grado
            FROM venta_items vi
            LEFT JOIN equipos e ON vi.equipo_id = e.id
            LEFT JOIN accesorios a ON vi.accesorio_id = a.id
            WHERE vi.venta_id = ?
            ORDER BY vi.id ASC
            """, (v_id,))
            items = [dict(r) for r in cursor.fetchall()]

            # Soporte para ventas históricas directas sin venta_items
            if len(items) == 0 and v_dict.get("equipo_id"):
                cursor.execute("SELECT * FROM equipos WHERE id = ?", (v_dict["equipo_id"],))
                eq = cursor.fetchone()
                if eq:
                    items = [{
                        "id": 1,
                        "venta_id": v_id,
                        "equipo_id": eq["id"],
                        "accesorio_id": None,
                        "tipo_item": "equipo",
                        "nombre_item": eq["modelo"],
                        "cantidad": 1,
                        "precio_final": v_dict["precio_final"],
                        "costo_compra": eq["costo_compra"],
                        "margen_ganancia": v_dict["margen_ganancia"],
                        "modelo": eq["modelo"],
                        "capacidad_gb": eq["capacidad_gb"],
                        "color": eq["color"],
                        "imei": eq["imei"],
                        "grado": eq["grado"]
                    }]

            cel_items = [it for it in items if (it.get("tipo_item") == "equipo" or it.get("equipo_id"))]
            acc_items = [it for it in items if not (it.get("tipo_item") == "equipo" or it.get("equipo_id"))]

            total_equipos = len(cel_items)
            total_accesorios = sum(int(it.get("cantidad", 1) or 1) for it in acc_items)

            # Filtro de tipo si se especificó
            if tipo_filtro == "celulares" and total_equipos == 0:
                continue
            if tipo_filtro == "accesorios" and total_accesorios == 0:
                continue

            ganancia_celulares = round(sum(float(it.get("margen_ganancia", 0) or 0) for it in cel_items), 2)
            ganancia_accesorios = round(sum(float(it.get("margen_ganancia", 0) or 0) for it in acc_items), 2)
            venta_celulares = round(sum(float(it.get("precio_final", 0) or 0) for it in cel_items), 2)
            venta_accesorios = round(sum(float(it.get("precio_final", 0) or 0) for it in acc_items), 2)

            if total_equipos > 0 and total_accesorios > 0:
                tipo_venta = "mixta"
            elif total_equipos > 0:
                tipo_venta = "celulares"
            else:
                tipo_venta = "accesorios"

            resumen_partes = []
            if cel_items:
                nombres_cel = [f"{it['modelo']}" for it in cel_items]
                resumen_partes.append(", ".join(nombres_cel))
            if acc_items:
                nombres_acc = [f"{it['nombre_item']} (x{it.get('cantidad', 1)})" for it in acc_items]
                resumen_partes.append(", ".join(nombres_acc))

            v_dict["items"] = items
            v_dict["total_equipos"] = total_equipos
            v_dict["total_accesorios"] = total_accesorios
            v_dict["ganancia_celulares"] = ganancia_celulares
            v_dict["ganancia_accesorios"] = ganancia_accesorios
            v_dict["venta_celulares"] = venta_celulares
            v_dict["venta_accesorios"] = venta_accesorios
            v_dict["tipo_venta"] = tipo_venta
            v_dict["resumen_modelos"] = " + ".join(resumen_partes) if resumen_partes else "Venta"

            if cel_items:
                v_dict["modelo"] = cel_items[0]["modelo"]
                v_dict["capacidad_gb"] = cel_items[0]["capacidad_gb"]
                v_dict["color"] = cel_items[0]["color"]
                v_dict["imei"] = cel_items[0]["imei"]
                v_dict["grado"] = cel_items[0]["grado"]
                v_dict["costo_compra"] = cel_items[0]["costo_compra"]
            elif items:
                v_dict["modelo"] = items[0]["nombre_item"]
                v_dict["costo_compra"] = items[0]["costo_compra"]
                v_dict["imei"] = None
                v_dict["grado"] = None
                v_dict["color"] = None
                v_dict["capacidad_gb"] = None

            resultado.append(v_dict)

    # 2. Órdenes de Reparación de Taller (cuando el filtro sea "todos", "reparaciones" o "taller")
    if tipo_filtro in ("todos", "reparaciones", "taller"):
        q_rep = """
        SELECT 
            r.id,
            r.folio,
            r.cliente_nombre,
            r.cliente_telefono,
            r.dispositivo_modelo,
            r.color,
            r.imei_serie,
            r.falla_reportada,
            r.diagnostico_tecnico,
            r.costo_refaccion,
            r.precio_servicio,
            r.anticipo,
            r.saldo_pendiente,
            r.estado,
            COALESCE(r.fecha_entrega, r.fecha_ingreso) as fecha_operacion,
            r.fecha_ingreso,
            r.fecha_entrega,
            r.tecnico_responsable,
            r.tenant_id,
            r.sucursal_id
        FROM reparaciones r
        WHERE r.estado != 'Cancelado'
        """
        p_rep = []
        if tenant_id is not None:
            q_rep += " AND r.tenant_id = ?"
            p_rep.append(tenant_id)
        if fecha_inicio:
            q_rep += " AND date(COALESCE(r.fecha_entrega, r.fecha_ingreso)) >= date(?)"
            p_rep.append(fecha_inicio)
        if fecha_fin:
            q_rep += " AND date(COALESCE(r.fecha_entrega, r.fecha_ingreso)) <= date(?)"
            p_rep.append(fecha_fin)
        q_rep += " ORDER BY r.id DESC LIMIT ?"
        p_rep.append(limit)

        cursor.execute(q_rep, p_rep)
        rep_rows = cursor.fetchall()
        for rr in rep_rows:
            r = dict(rr)
            costo = float(r.get("costo_refaccion") or 0.0)
            precio = float(r.get("precio_servicio") or 0.0)
            ganancia = round(precio - costo, 2)
            r_id = int(r["id"])
            virtual_venta_id = 900000 + r_id

            rep_item = {
                "id": 1,
                "venta_id": virtual_venta_id,
                "equipo_id": None,
                "accesorio_id": None,
                "tipo_item": "reparacion",
                "nombre_item": f"Reparación: {r.get('dispositivo_modelo', 'Equipo')} ({r.get('falla_reportada', 'Falla')})",
                "cantidad": 1,
                "precio_final": precio,
                "costo_compra": costo,
                "margen_ganancia": ganancia,
                "modelo": r.get("dispositivo_modelo", "Reparación"),
                "capacidad_gb": None,
                "color": r.get("color"),
                "imei": r.get("imei_serie"),
                "grado": None
            }

            diag_txt = f" [{r['diagnostico_tecnico']}]" if r.get("diagnostico_tecnico") else ""
            resumen = f"🔧 {r.get('dispositivo_modelo', 'Equipo')} - {r.get('falla_reportada', 'Servicio')}{diag_txt}"

            rep_dict = {
                "id": virtual_venta_id,
                "cliente_id": None,
                "precio_final": precio,
                "margen_ganancia": ganancia,
                "fecha_venta": str(r.get("fecha_operacion") or r.get("fecha_ingreso") or ""),
                "metodo_pago": "Taller",
                "monto_efectivo": float(r.get("anticipo") or 0.0),
                "monto_transferencia": 0.0,
                "monto_tarjeta": 0.0,
                "monto_garantia": 0.0,
                "notas": f"Folio: {r.get('folio')} | Técnico: {r.get('tecnico_responsable') or 'Samuel N.'}",
                "cliente_nombre": r.get("cliente_nombre") or "Cliente Taller",
                "cliente_telefono": r.get("cliente_telefono") or "",
                "items": [rep_item],
                "total_equipos": 0,
                "total_accesorios": 0,
                "ganancia_celulares": 0.0,
                "ganancia_accesorios": 0.0,
                "venta_celulares": 0.0,
                "venta_accesorios": 0.0,
                "tipo_venta": "reparacion",
                "resumen_modelos": resumen,
                "es_credito": False,
                "plazo_dias": 0,
                "fecha_vencimiento": None,
                "monto_credito": 0.0,
                "monto_anticipo": float(r.get("anticipo") or 0.0),
                "saldo_pendiente": float(r.get("saldo_pendiente") or 0.0),
                "estado_credito": None,
                "abonos": [],
                "equipo_id": None,
                "modelo": r.get("dispositivo_modelo"),
                "capacidad_gb": None,
                "color": r.get("color"),
                "imei": r.get("imei_serie"),
                "grado": None,
                "costo_compra": costo,
                "folio": r.get("folio"),
                "reparacion_id": r_id,
                "diagnostico_tecnico": r.get("diagnostico_tecnico")
            }
            resultado.append(rep_dict)

    # Ordenar unificado por fecha descendente
    resultado.sort(key=lambda x: str(x.get("fecha_venta", "")), reverse=True)
    if len(resultado) > limit:
        resultado = resultado[:limit]

    conn.close()
    return resultado


# ==============================================================================
# NOTAS DE CRÉDITO A CLIENTES (15 Y 30 DÍAS) Y ALERTAS DE VENCIMIENTO
# ==============================================================================

def get_notas_credito(
    estado_filtro: Optional[str] = None,
    tenant_id: Optional[int] = None
) -> Dict[str, Any]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    # Actualización automática de estado Vencida si pasó la fecha límite
    try:
        upd_sql = """
        UPDATE ventas
        SET estado_credito = 'Vencida'
        WHERE es_credito = 1
          AND saldo_pendiente > 0
          AND date('now', 'localtime') > date(fecha_vencimiento)
          AND (estado_credito IS NULL OR estado_credito != 'Vencida')
        """
        upd_params = []
        if tenant_id is not None:
            upd_sql += " AND tenant_id = ?"
            upd_params.append(tenant_id)
        upd_sql += ";"
        cursor.execute(upd_sql, upd_params)
        conn.commit()
    except Exception:
        pass

    query_nc = """
    SELECT 
        v.id,
        v.cliente_id,
        v.precio_final as total_venta,
        v.fecha_venta,
        COALESCE(v.plazo_dias, 15) as plazo_dias,
        v.fecha_vencimiento,
        COALESCE(v.monto_anticipo, 0) as monto_anticipo,
        COALESCE(v.saldo_pendiente, 0) as saldo_pendiente,
        v.estado_credito,
        v.tenant_id,
        v.sucursal_id,
        c.nombre as cliente_nombre,
        c.telefono as cliente_telefono,
        CAST(ROUND(julianday(date(v.fecha_vencimiento)) - julianday(date('now', 'localtime'))) AS INTEGER) as dias_restantes
    FROM ventas v
    JOIN clientes c ON v.cliente_id = c.id
    WHERE v.es_credito = 1
    """
    params_nc = []
    if tenant_id is not None:
        query_nc += " AND v.tenant_id = ?"
        params_nc.append(tenant_id)

    query_nc += """
    ORDER BY 
        CASE 
            WHEN v.saldo_pendiente > 0 AND date('now', 'localtime') > date(v.fecha_vencimiento) THEN 1
            WHEN v.saldo_pendiente > 0 THEN 2
            ELSE 3
        END,
        v.fecha_vencimiento ASC
    """
    cursor.execute(query_nc, params_nc)
    rows = cursor.fetchall()

    notas = []
    total_pendientes = 0
    total_vencidas = 0
    total_por_vencer = 0
    monto_total_por_cobrar = 0.0
    monto_total_vencido = 0.0

    for r in rows:
        d = dict(r)
        v_id = d["id"]
        # Cálculo seguro y consistente de días restantes
        f_venc_raw = d.get("fecha_vencimiento")
        if f_venc_raw:
            try:
                f_venc_date = datetime.strptime(str(f_venc_raw)[:10], "%Y-%m-%d").date()
                dias_rest = (f_venc_date - datetime.now().date()).days
            except Exception:
                dias_rest = d.get("dias_restantes") or 0
        else:
            dias_rest = d.get("dias_restantes") or 0
        d["dias_restantes"] = dias_rest

        saldo = float(d["saldo_pendiente"] or 0)

        if saldo <= 0.01:
            est = "Liquidada"
        elif dias_rest < 0:
            est = "Vencida"
        elif dias_rest <= 3:
            est = "Por Vencer"
        else:
            est = "Vigente"
        d["estado_calculado"] = est

        # Artículos de la venta
        cursor.execute("""
        SELECT COALESCE(nombre_item, 'Artículo') as nombre, cantidad, precio_final
        FROM venta_items WHERE venta_id = ?
        """, (v_id,))
        its = cursor.fetchall()
        d["articulos_resumen"] = ", ".join([f"{it['nombre']} (x{it['cantidad']})" for it in its]) if its else "Artículo"

        # Historial de abonos
        cursor.execute("""
        SELECT id, monto, fecha, metodo_pago, notas, usuario
        FROM abonos_ventas_credito WHERE venta_id = ? ORDER BY id ASC
        """, (v_id,))
        abonos = [dict(a) for a in cursor.fetchall()]
        d["abonos"] = abonos
        d["total_abonado"] = round(sum(float(a["monto"]) for a in abonos), 2)

        if saldo > 0.01:
            total_pendientes += 1
            monto_total_por_cobrar += saldo
            if est == "Vencida":
                total_vencidas += 1
                monto_total_vencido += saldo
            elif est == "Por Vencer":
                total_por_vencer += 1

        if not estado_filtro or estado_filtro.lower() in ("todos", "todas") or est.lower() == estado_filtro.lower():
            notas.append(d)

    conn.close()

    return {
        "total_pendientes": total_pendientes,
        "total_vencidas": total_vencidas,
        "total_por_vencer": total_por_vencer,
        "monto_total_por_cobrar": round(monto_total_por_cobrar, 2),
        "monto_total_vencido": round(monto_total_vencido, 2),
        "notas": notas
    }

def registrar_abono_credito(
    venta_id: int,
    monto: float,
    metodo_pago: str = "Efectivo",
    notas: Optional[str] = None,
    usuario: Optional[str] = None,
    tenant_id: Optional[int] = None
) -> Dict[str, Any]:
    if monto <= 0:
        raise ValueError("El monto del abono debe ser mayor a $0.00.")

    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    try:
        _begin_immediate(cursor)

        if tenant_id is not None:
            cursor.execute("SELECT * FROM ventas WHERE id = ? AND tenant_id = ?", (venta_id, tenant_id))
        else:
            cursor.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,))
        v = cursor.fetchone()
        if not v:
            raise ValueError("La venta no fue encontrada o no pertenece a este negocio.")
        if not v["es_credito"]:
            raise ValueError("Esta venta no corresponde a una Nota de Crédito.")

        saldo_actual = float(v["saldo_pendiente"] or 0)
        if saldo_actual <= 0.01:
            raise ValueError("Esta Nota de Crédito ya se encuentra 100% liquidada.")

        if monto > saldo_actual + 0.05:
            raise ValueError(f"El monto a abonar (${monto:,.2f}) excede el saldo pendiente (${saldo_actual:,.2f}).")

        nuevo_saldo = max(0.0, round(saldo_actual - monto, 2))
        nuevo_estado = "Liquidada" if nuevo_saldo <= 0.01 else ("Vencida" if v["estado_credito"] == "Vencida" else "Pendiente")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO abonos_ventas_credito (venta_id, monto, fecha, metodo_pago, notas, usuario)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (venta_id, monto, now, metodo_pago, notas or "Abono a cuenta", usuario or "Caja"))

        cursor.execute("""
        UPDATE ventas 
        SET saldo_pendiente = ?, estado_credito = ?
        WHERE id = ?;
        """, (nuevo_saldo, nuevo_estado, venta_id))

        conn.commit()

        return {
            "venta_id": venta_id,
            "monto_abonado": monto,
            "saldo_anterior": saldo_actual,
            "nuevo_saldo": nuevo_saldo,
            "estado": nuevo_estado,
            "fecha": now
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# --- MÓDULO DE DEVOLUCIÓN Y GESTIÓN DE GARANTÍAS ---

DIAS_GARANTIA_POR_GRADO = {
    "A": 90,
    "B": 30,
    "C": 15
}

def buscar_equipo_para_garantia(imei: str, tenant_id: Optional[int] = None) -> Dict[str, Any]:
    """Busca un equipo vendido por IMEI para verificar si está dentro de su periodo de garantía y pertenece al tenant."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    clean_imei = imei.strip()
    if tenant_id is not None:
        cursor.execute("SELECT * FROM equipos WHERE imei = ? AND tenant_id = ?", (clean_imei, tenant_id))
    else:
        cursor.execute("SELECT * FROM equipos WHERE imei = ?", (clean_imei,))
    equipo = cursor.fetchone()

    if not equipo:
        conn.close()
        raise ValueError(f"No existe ningún equipo registrado con el IMEI '{clean_imei}'.")

    eq_dict = dict(equipo)
    eq_id = eq_dict["id"]

    # Buscar la venta más reciente donde se vendió este equipo
    q_venta = """
    SELECT 
        v.id as venta_id,
        v.fecha_venta,
        v.cliente_id,
        v.tenant_id,
        vi.precio_final,
        c.nombre as cliente_nombre,
        c.telefono as cliente_telefono
    FROM venta_items vi
    JOIN ventas v ON vi.venta_id = v.id
    JOIN clientes c ON v.cliente_id = c.id
    WHERE vi.equipo_id = ?
    """
    p_venta = [eq_id]
    if tenant_id is not None:
        q_venta += " AND v.tenant_id = ?"
        p_venta.append(tenant_id)
    q_venta += " ORDER BY v.id DESC LIMIT 1"
    cursor.execute(q_venta, p_venta)
    venta = cursor.fetchone()

    if not venta:
        # Si fue vendido en formato anterior directo
        q_legacy = """
        SELECT 
            v.id as venta_id,
            v.fecha_venta,
            v.cliente_id,
            v.tenant_id,
            v.precio_final,
            c.nombre as cliente_nombre,
            c.telefono as cliente_telefono
        FROM ventas v
        JOIN clientes c ON v.cliente_id = c.id
        WHERE v.equipo_id = ?
        """
        p_legacy = [eq_id]
        if tenant_id is not None:
            q_legacy += " AND v.tenant_id = ?"
            p_legacy.append(tenant_id)
        q_legacy += " ORDER BY v.id DESC LIMIT 1"
        cursor.execute(q_legacy, p_legacy)
        venta = cursor.fetchone()

    if not venta:
        conn.close()
        raise ValueError(f"El equipo '{eq_dict['modelo']}' (IMEI: {clean_imei}) no tiene registro de venta (Estado actual: {eq_dict['estado']}).")

    v_dict = dict(venta)

    # Calcular días transcurridos desde la fecha de venta
    fecha_venta_str = v_dict["fecha_venta"].split(" ")[0]
    fecha_venta_dt = datetime.strptime(fecha_venta_str, "%Y-%m-%d")
    hoy_dt = datetime.now()
    dias_transcurridos = max(0, (hoy_dt - fecha_venta_dt).days)

    grado = eq_dict["grado"].upper()
    dias_permitidos = DIAS_GARANTIA_POR_GRADO.get(grado, 30)
    dentro_garantia = dias_transcurridos <= dias_permitidos

    conn.close()

    return {
        "equipo": eq_dict,
        "venta": v_dict,
        "dias_transcurridos": dias_transcurridos,
        "dias_permitidos": dias_permitidos,
        "dentro_garantia": dentro_garantia,
        "estado_actual": eq_dict["estado"]
    }

def procesar_devolucion_garantia(
    data: GarantiaCreate,
    tenant_id: Optional[int] = None,
    sucursal_id: Optional[int] = None
) -> Dict[str, Any]:
    """Registra formalmente el regreso de un equipo por garantía y actualiza su estado de forma atómica."""
    info = buscar_equipo_para_garantia(data.imei, tenant_id=tenant_id)
    eq = info["equipo"]
    venta = info["venta"]

    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    try:
        _begin_immediate(cursor)

        if data.equipo_reemplazo_id is not None:
            if tenant_id is not None:
                cursor.execute("SELECT id FROM equipos WHERE id = ? AND tenant_id = ?", (data.equipo_reemplazo_id, tenant_id))
            else:
                cursor.execute("SELECT id FROM equipos WHERE id = ?", (data.equipo_reemplazo_id,))
            if not cursor.fetchone():
                raise ValueError(f"El equipo de reemplazo con ID {data.equipo_reemplazo_id} no existe o no pertenece a este negocio.")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        monto_cubierto = data.monto_cubierto if data.monto_cubierto is not None else float(venta["precio_final"])

        # 1. Insertar registro en tabla garantias
        cursor.execute("""
        INSERT INTO garantias (
            venta_id, equipo_id, cliente_id, fecha_devolucion, motivo, falla_descripcion,
            estado_equipo_recibido, solucion, equipo_reemplazo_id, monto_cubierto, notas
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            venta["venta_id"], eq["id"], venta["cliente_id"], now, data.motivo.strip(),
            data.falla_descripcion, data.estado_equipo_recibido, data.solucion,
            data.equipo_reemplazo_id, monto_cubierto, data.notas
        ))
        garantia_id = cursor.lastrowid
        if not garantia_id:
            cursor.execute("SELECT id FROM garantias WHERE venta_id = ? AND equipo_id = ? ORDER BY id DESC LIMIT 1;", (venta["venta_id"], eq["id"]))
            r_gid = cursor.fetchone()
            garantia_id = r_gid["id"] if r_gid else None

        # 2. Actualizar estado del equipo devuelto
        if tenant_id is not None:
            cursor.execute("UPDATE equipos SET estado = ? WHERE id = ? AND tenant_id = ?", (data.estado_equipo_recibido, eq["id"], tenant_id))
        else:
            cursor.execute("UPDATE equipos SET estado = ? WHERE id = ?", (data.estado_equipo_recibido, eq["id"]))

        # 3. Registrar en historial de garantías y trazabilidad del equipo
        try:
            cursor.execute("""
            INSERT INTO garantias_historial (
                garantia_id, equipo_id, estado_anterior, estado_nuevo, fecha_cambio, usuario, observaciones, tenant_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                garantia_id, eq["id"], eq.get("estado", "Vendido"), data.estado_equipo_recibido,
                now, "Garantía/Recepción", f"Devolución por garantía: {data.motivo}. Falla: {data.falla_descripcion or 'N/A'}. Solución: {data.solucion}.",
                tenant_id
            ))
        except Exception:
            pass

        conn.commit()

        # Retornar registro completo
        res = {
            "id": garantia_id,
            "venta_id": venta["venta_id"],
            "equipo_id": eq["id"],
            "cliente_id": venta["cliente_id"],
            "fecha_devolucion": now,
            "motivo": data.motivo,
            "falla_descripcion": data.falla_descripcion,
            "estado_equipo_recibido": data.estado_equipo_recibido,
            "solucion": data.solucion,
            "equipo_reemplazo_id": data.equipo_reemplazo_id,
            "monto_cubierto": monto_cubierto,
            "notas": data.notas,
            "modelo": eq["modelo"],
            "imei": eq["imei"],
            "grado": eq["grado"],
            "color": eq["color"],
            "cliente_nombre": venta["cliente_nombre"],
            "cliente_telefono": venta["cliente_telefono"],
            "fecha_venta_original": venta["fecha_venta"],
            "dias_garantia_permitidos": info["dias_permitidos"],
            "dias_transcurridos": info["dias_transcurridos"],
            "dentro_de_garantia": info["dentro_garantia"]
        }
        return res

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_historial_garantias(limit: int = 100, tenant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    query = """
    SELECT 
        g.*,
        e.modelo,
        e.imei,
        e.grado,
        e.color,
        c.nombre as cliente_nombre,
        c.telefono as cliente_telefono,
        v.fecha_venta as fecha_venta_original
    FROM garantias g
    JOIN equipos e ON g.equipo_id = e.id
    JOIN clientes c ON g.cliente_id = c.id
    JOIN ventas v ON g.venta_id = v.id
    WHERE 1=1
    """
    params = []
    if tenant_id is not None:
        query += " AND (v.tenant_id = ? OR e.tenant_id = ?)"
        params.extend([tenant_id, tenant_id])

    query += " ORDER BY g.id DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(r) for r in rows]

def restablecer_equipo_garantia(
    equipo_id: int,
    nuevo_grado: Optional[str] = None,
    nuevo_precio_venta: Optional[float] = None,
    costo_adicional: Optional[float] = 0.0,
    notas: Optional[str] = None,
    usuario: Optional[str] = "Admin",
    tenant_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Restaura un equipo (por ejemplo de 'En Garantia' o 'Baja por Garantia') a 'Disponible',
    actualizando opcionalmente su grado, precio de venta, costo de compra acumulado
    y registrando la auditoría del cambio en garantias_historial.
    """
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        _begin_immediate(cursor)

        # 1. Obtener y validar el equipo
        if tenant_id is not None:
            cursor.execute("SELECT * FROM equipos WHERE id = ? AND tenant_id = ?;", (equipo_id, tenant_id))
        else:
            cursor.execute("SELECT * FROM equipos WHERE id = ?;", (equipo_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"No se encontró el equipo con ID {equipo_id} en el inventario.")

        eq = format_equipo_dict(row)
        estado_anterior = eq["estado"]

        # 2. Preparar campos a actualizar
        updates = ["estado = 'Disponible'"]
        params = []

        grado_final = eq["grado"]
        if nuevo_grado and nuevo_grado.strip():
            grado_final = nuevo_grado.strip().upper()
            updates.append("grado = ?")
            params.append(grado_final)

        precio_final = eq["precio_venta"]
        if nuevo_precio_venta is not None and nuevo_precio_venta > 0:
            precio_final = float(nuevo_precio_venta)
            updates.append("precio_venta = ?")
            params.append(precio_final)

        costo_extra = float(costo_adicional or 0.0)
        costo_acumulado = eq["costo_compra"] + costo_extra
        if costo_extra > 0:
            updates.append("costo_compra = ?")
            params.append(costo_acumulado)

        if tenant_id is not None:
            params.extend([equipo_id, tenant_id])
            cursor.execute(f"UPDATE equipos SET {', '.join(updates)} WHERE id = ? AND tenant_id = ?;", params)
        else:
            params.append(equipo_id)
            cursor.execute(f"UPDATE equipos SET {', '.join(updates)} WHERE id = ?;", params)

        # 3. Vincular a la última garantía si existió
        cursor.execute("SELECT id FROM garantias WHERE equipo_id = ? ORDER BY id DESC LIMIT 1;", (equipo_id,))
        row_g = cursor.fetchone()
        last_garantia_id = row_g["id"] if row_g else None

        obs = f"Puesto funcional y reingresado a inventario disponible. Grado: {grado_final}. Precio venta: ${precio_final:,.2f}."
        if costo_extra > 0:
            obs += f" Costo refacción/reparación: ${costo_extra:,.2f}."
        if notas and notas.strip():
            obs += f" Notas técnicas: {notas.strip()}"

        try:
            cursor.execute("""
            INSERT INTO garantias_historial (
                garantia_id, equipo_id, estado_anterior, estado_nuevo, fecha_cambio, usuario, observaciones, tenant_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                last_garantia_id, equipo_id, estado_anterior, 'Disponible',
                now, usuario or "Admin", obs, tenant_id
            ))
        except Exception:
            pass

        conn.commit()

        # 4. Retornar equipo actualizado
        if tenant_id is not None:
            cursor.execute("SELECT * FROM equipos WHERE id = ? AND tenant_id = ?;", (equipo_id, tenant_id))
        else:
            cursor.execute("SELECT * FROM equipos WHERE id = ?;", (equipo_id,))
        row_updated = cursor.fetchone()
        return format_equipo_dict(row_updated)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# --- REPORTES Y DASHBOARD ---

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

def get_dashboard_metrics(tenant_id: Optional[int] = None) -> Dict[str, Any]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    ahora = datetime.now()
    mes_actual_str = ahora.strftime("%Y-%m")
    nombre_mes = f"{MESES_ES[ahora.month - 1]} {ahora.year}"

    # 1. Métricas de Celulares (Smartphones) en el mes actual
    q_cel_items = """
    SELECT 
        COALESCE(SUM(vi.precio_final), 0) as total_ventas,
        COALESCE(SUM(vi.margen_ganancia), 0) as total_ganancias,
        COALESCE(SUM(vi.cantidad), 0) as total_unidades
    FROM venta_items vi
    JOIN ventas v ON vi.venta_id = v.id
    WHERE strftime('%Y-%m', v.fecha_venta) = ?
      AND (vi.tipo_item = 'equipo' OR vi.equipo_id IS NOT NULL)
    """
    p_cel_items = [mes_actual_str]
    if tenant_id is not None:
        q_cel_items += " AND v.tenant_id = ?"
        p_cel_items.append(tenant_id)
    cursor.execute(q_cel_items, p_cel_items)
    cel_items_row = cursor.fetchone()

    # Ventas históricas directas de celulares sin venta_items
    q_cel_legacy = """
    SELECT 
        COALESCE(SUM(v.precio_final), 0) as total_ventas,
        COALESCE(SUM(v.margen_ganancia), 0) as total_ganancias,
        COUNT(v.id) as total_unidades
    FROM ventas v
    WHERE strftime('%Y-%m', v.fecha_venta) = ?
      AND v.id NOT IN (SELECT DISTINCT venta_id FROM venta_items)
      AND v.equipo_id IS NOT NULL
    """
    p_cel_legacy = [mes_actual_str]
    if tenant_id is not None:
        q_cel_legacy += " AND v.tenant_id = ?"
        p_cel_legacy.append(tenant_id)
    cursor.execute(q_cel_legacy, p_cel_legacy)
    cel_legacy_row = cursor.fetchone()

    cel_ventas = round(float(cel_items_row["total_ventas"]) + float(cel_legacy_row["total_ventas"]), 2)
    cel_ganancias = round(float(cel_items_row["total_ganancias"]) + float(cel_legacy_row["total_ganancias"]), 2)
    cel_unidades = int(cel_items_row["total_unidades"]) + int(cel_legacy_row["total_unidades"])
    cel_margen_pct = round((cel_ganancias / cel_ventas * 100), 1) if cel_ventas > 0 else 0.0

    # 2. Métricas de Accesorios y Servicios en el mes actual
    q_acc_items = """
    SELECT 
        COALESCE(SUM(vi.precio_final), 0) as total_ventas,
        COALESCE(SUM(vi.margen_ganancia), 0) as total_ganancias,
        COALESCE(SUM(vi.cantidad), 0) as total_unidades
    FROM venta_items vi
    JOIN ventas v ON vi.venta_id = v.id
    WHERE strftime('%Y-%m', v.fecha_venta) = ?
      AND (vi.tipo_item != 'equipo' OR vi.accesorio_id IS NOT NULL)
    """
    p_acc_items = [mes_actual_str]
    if tenant_id is not None:
        q_acc_items += " AND v.tenant_id = ?"
        p_acc_items.append(tenant_id)
    cursor.execute(q_acc_items, p_acc_items)
    acc_items_row = cursor.fetchone()

    acc_ventas = round(float(acc_items_row["total_ventas"]), 2)
    acc_ganancias = round(float(acc_items_row["total_ganancias"]), 2)
    acc_unidades = int(acc_items_row["total_unidades"])
    acc_margen_pct = round((acc_ganancias / acc_ventas * 100), 1) if acc_ventas > 0 else 0.0

    # 2.5 Métricas de Taller / Reparaciones en el mes actual
    q_rep_mes = """
    SELECT 
        COALESCE(SUM(precio_servicio), 0) as total_ventas,
        COALESCE(SUM(precio_servicio - costo_refaccion), 0) as total_ganancias,
        COUNT(id) as total_unidades
    FROM reparaciones
    WHERE estado != 'Cancelado'
      AND strftime('%Y-%m', COALESCE(fecha_entrega, fecha_ingreso)) = ?
    """
    p_rep_mes = [mes_actual_str]
    if tenant_id is not None:
        q_rep_mes += " AND tenant_id = ?"
        p_rep_mes.append(tenant_id)
    cursor.execute(q_rep_mes, p_rep_mes)
    rep_mes_row = cursor.fetchone()

    rep_ventas = round(float(rep_mes_row["total_ventas"] or 0), 2)
    rep_ganancias = round(float(rep_mes_row["total_ganancias"] or 0), 2)
    rep_unidades = int(rep_mes_row["total_unidades"] or 0)
    rep_margen_pct = round((rep_ganancias / rep_ventas * 100), 1) if rep_ventas > 0 else 0.0

    # 3. Totales Consolidados del Mes (Celulares + Accesorios + Taller)
    total_ventas = round(cel_ventas + acc_ventas + rep_ventas, 2)
    total_ganancias = round(cel_ganancias + acc_ganancias + rep_ganancias, 2)
    eq_vendidos = cel_unidades
    margen_promedio = round((total_ganancias / total_ventas * 100), 1) if total_ventas > 0 else 0.0

    # 3.5 Gastos Operativos y Ganancia Neta Real del mes actual
    q_gastos_mes = """
    SELECT COALESCE(SUM(monto), 0) as total_gastos
    FROM gastos
    WHERE strftime('%Y-%m', fecha) = ?
    """
    p_gastos_mes = [mes_actual_str]
    if tenant_id is not None:
        q_gastos_mes += " AND tenant_id = ?"
        p_gastos_mes.append(tenant_id)
    try:
        cursor.execute(q_gastos_mes, p_gastos_mes)
        gastos_mes_row = cursor.fetchone()
        total_gastos = round(float(gastos_mes_row["total_gastos"] or 0), 2)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        total_gastos = 0.0
    ganancia_neta_mes = round(total_ganancias - total_gastos, 2)

    # 4. Inventario Activo de Celulares
    q_stats_inv = """
    SELECT 
        COUNT(id) as disponibles,
        COALESCE(SUM(costo_compra), 0) as capital_invertido,
        COALESCE(SUM(precio_venta), 0) as valor_venta
    FROM equipos
    WHERE estado = 'Disponible'
    """
    p_stats_inv = []
    if tenant_id is not None:
        q_stats_inv += " AND tenant_id = ?"
        p_stats_inv.append(tenant_id)
    cursor.execute(q_stats_inv, p_stats_inv)
    stats_inv = cursor.fetchone()

    q_en_garantia = "SELECT COUNT(id) as en_garantia FROM equipos WHERE estado = 'En Garantia'"
    p_en_garantia = []
    if tenant_id is not None:
        q_en_garantia += " AND tenant_id = ?"
        p_en_garantia.append(tenant_id)
    cursor.execute(q_en_garantia, p_en_garantia)
    equipos_en_garantia = cursor.fetchone()["en_garantia"]

    # 5. Inventario Activo de Accesorios
    q_acc_inv = """
    SELECT 
        COALESCE(SUM(stock), 0) as total_piezas,
        COALESCE(SUM(stock * costo_compra), 0) as capital_invertido,
        COALESCE(SUM(stock * precio_venta), 0) as valor_venta
    FROM accesorios
    WHERE es_servicio = 0
    """
    p_acc_inv = []
    if tenant_id is not None:
        q_acc_inv += " AND tenant_id = ?"
        p_acc_inv.append(tenant_id)
    cursor.execute(q_acc_inv, p_acc_inv)
    acc_inv_row = cursor.fetchone()
    acc_stock = int(acc_inv_row["total_piezas"]) if acc_inv_row else 0
    acc_capital = round(float(acc_inv_row["capital_invertido"] or 0), 2)
    acc_valor = round(float(acc_inv_row["valor_venta"] or 0), 2)

    # 6. Ventas de los últimos 30 días para gráfico (desglosado por celulares y accesorios)
    q_ventas_dias = """
    SELECT 
        date(v.fecha_venta) as dia,
        COALESCE(SUM(CASE WHEN vi.tipo_item = 'equipo' OR vi.equipo_id IS NOT NULL THEN vi.precio_final ELSE 0 END), 0) as ventas_celulares,
        COALESCE(SUM(CASE WHEN vi.tipo_item = 'equipo' OR vi.equipo_id IS NOT NULL THEN vi.margen_ganancia ELSE 0 END), 0) as ganancias_celulares,
        COALESCE(SUM(CASE WHEN vi.tipo_item = 'equipo' OR vi.equipo_id IS NOT NULL THEN vi.cantidad ELSE 0 END), 0) as unidades_celulares,
        COALESCE(SUM(CASE WHEN vi.tipo_item != 'equipo' OR vi.accesorio_id IS NOT NULL THEN vi.precio_final ELSE 0 END), 0) as ventas_accesorios,
        COALESCE(SUM(CASE WHEN vi.tipo_item != 'equipo' OR vi.accesorio_id IS NOT NULL THEN vi.margen_ganancia ELSE 0 END), 0) as ganancias_accesorios,
        COALESCE(SUM(CASE WHEN vi.tipo_item != 'equipo' OR vi.accesorio_id IS NOT NULL THEN vi.cantidad ELSE 0 END), 0) as unidades_accesorios,
        COALESCE(SUM(vi.precio_final), 0) as ventas,
        COALESCE(SUM(vi.margen_ganancia), 0) as ganancias,
        COUNT(vi.id) as unidades
    FROM ventas v
    LEFT JOIN venta_items vi ON v.id = vi.venta_id
    WHERE date(v.fecha_venta) >= date('now', '-30 days', 'localtime')
    """
    p_ventas_dias = []
    if tenant_id is not None:
        q_ventas_dias += " AND v.tenant_id = ?"
        p_ventas_dias.append(tenant_id)
    q_ventas_dias += " GROUP BY date(v.fecha_venta) ORDER BY dia ASC"
    cursor.execute(q_ventas_dias, p_ventas_dias)
    ventas_dias = []
    for r in cursor.fetchall():
        d = dict(r)
        if "dia" in d and d["dia"] is not None:
            d["dia"] = str(d["dia"])
        ventas_dias.append(d)

    # 6b. Ventas de Taller de los últimos 30 días para integrar al gráfico
    q_rep_dias = """
    SELECT 
        date(COALESCE(fecha_entrega, fecha_ingreso)) as dia,
        COALESCE(SUM(precio_servicio), 0) as ventas_taller,
        COALESCE(SUM(precio_servicio - costo_refaccion), 0) as ganancias_taller,
        COUNT(id) as unidades_taller
    FROM reparaciones
    WHERE estado != 'Cancelado'
      AND date(COALESCE(fecha_entrega, fecha_ingreso)) >= date('now', '-30 days', 'localtime')
    """
    p_rep_dias = []
    if tenant_id is not None:
        q_rep_dias += " AND tenant_id = ?"
        p_rep_dias.append(tenant_id)
    q_rep_dias += " GROUP BY date(COALESCE(fecha_entrega, fecha_ingreso)) ORDER BY dia ASC"
    cursor.execute(q_rep_dias, p_rep_dias)
    rep_dias_map = {str(r["dia"]): dict(r) for r in cursor.fetchall() if r["dia"]}

    dias_seen = set()
    for d in ventas_dias:
        dia_str = str(d.get("dia", ""))
        dias_seen.add(dia_str)
        if dia_str in rep_dias_map:
            r_data = rep_dias_map[dia_str]
            v_t = round(float(r_data.get("ventas_taller", 0) or 0), 2)
            g_t = round(float(r_data.get("ganancias_taller", 0) or 0), 2)
            u_t = int(r_data.get("unidades_taller", 0) or 0)
            d["ventas_taller"] = v_t
            d["ganancias_taller"] = g_t
            d["unidades_taller"] = u_t
            d["ventas"] = round(float(d.get("ventas", 0) or 0) + v_t, 2)
            d["ganancias"] = round(float(d.get("ganancias", 0) or 0) + g_t, 2)
        else:
            d["ventas_taller"] = 0.0
            d["ganancias_taller"] = 0.0
            d["unidades_taller"] = 0

    for dia_str, r_data in rep_dias_map.items():
        if dia_str not in dias_seen:
            v_t = round(float(r_data.get("ventas_taller", 0) or 0), 2)
            g_t = round(float(r_data.get("ganancias_taller", 0) or 0), 2)
            u_t = int(r_data.get("unidades_taller", 0) or 0)
            ventas_dias.append({
                "dia": dia_str,
                "ventas_celulares": 0.0,
                "ganancias_celulares": 0.0,
                "unidades_celulares": 0,
                "ventas_accesorios": 0.0,
                "ganancias_accesorios": 0.0,
                "unidades_accesorios": 0,
                "ventas_taller": v_t,
                "ganancias_taller": g_t,
                "unidades_taller": u_t,
                "ventas": v_t,
                "ganancias": g_t,
                "unidades": u_t
            })
    ventas_dias.sort(key=lambda x: str(x.get("dia", "")))

    # 7. Distribución por Grados
    q_grados = "SELECT grado, COUNT(id) as total FROM equipos WHERE estado = 'Disponible'"
    p_grados = []
    if tenant_id is not None:
        q_grados += " AND tenant_id = ?"
        p_grados.append(tenant_id)
    q_grados += " GROUP BY grado"
    cursor.execute(q_grados, p_grados)
    grados_inv = {r["grado"]: r["total"] for r in cursor.fetchall()}

    # 8. Desglose de ingresos por método de pago en el mes actual
    q_p_row = """
    SELECT 
        COALESCE(SUM(monto_efectivo), 0) as total_efectivo,
        COALESCE(SUM(monto_transferencia), 0) as total_transferencia,
        COALESCE(SUM(monto_garantia), 0) as total_garantia
    FROM ventas
    WHERE strftime('%Y-%m', fecha_venta) = ?
    """
    p_p_row = [mes_actual_str]
    if tenant_id is not None:
        q_p_row += " AND tenant_id = ?"
        p_p_row.append(tenant_id)
    cursor.execute(q_p_row, p_p_row)
    p_row = cursor.fetchone()

    desglose_pagos = {
        "Efectivo": round(p_row["total_efectivo"], 2),
        "Transferencia": round(p_row["total_transferencia"], 2),
        "Equipo Garantía": round(p_row["total_garantia"], 2)
    }

    # 9. Top Celulares Más Vendidos en el Mes
    q_top_cel = """
    SELECT 
        COALESCE(e.modelo, vi.nombre_item, 'Celular') as nombre,
        COUNT(vi.id) as unidades,
        COALESCE(SUM(vi.precio_final), 0) as recaudado,
        COALESCE(SUM(vi.margen_ganancia), 0) as ganancia
    FROM venta_items vi
    JOIN ventas v ON vi.venta_id = v.id
    LEFT JOIN equipos e ON vi.equipo_id = e.id
    WHERE strftime('%Y-%m', v.fecha_venta) = ?
      AND (vi.tipo_item = 'equipo' OR vi.equipo_id IS NOT NULL)
    """
    p_top_cel = [mes_actual_str]
    if tenant_id is not None:
        q_top_cel += " AND v.tenant_id = ?"
        p_top_cel.append(tenant_id)
    q_top_cel += " GROUP BY 1 ORDER BY unidades DESC, ganancia DESC LIMIT 5"
    cursor.execute(q_top_cel, p_top_cel)
    top_celulares = [
        {
            "nombre": r["nombre"],
            "unidades": int(r["unidades"]),
            "recaudado": round(float(r["recaudado"] or 0), 2),
            "ganancia": round(float(r["ganancia"] or 0), 2)
        }
        for r in cursor.fetchall()
    ]

    # 10. Top Accesorios Más Vendidos en el Mes
    q_top_acc = """
    SELECT 
        COALESCE(a.nombre, vi.nombre_item, 'Accesorio') as nombre,
        COALESCE(SUM(vi.cantidad), 0) as unidades,
        COALESCE(SUM(vi.precio_final), 0) as recaudado,
        COALESCE(SUM(vi.margen_ganancia), 0) as ganancia
    FROM venta_items vi
    JOIN ventas v ON vi.venta_id = v.id
    LEFT JOIN accesorios a ON vi.accesorio_id = a.id
    WHERE strftime('%Y-%m', v.fecha_venta) = ?
      AND (vi.tipo_item != 'equipo' OR vi.accesorio_id IS NOT NULL)
    """
    p_top_acc = [mes_actual_str]
    if tenant_id is not None:
        q_top_acc += " AND v.tenant_id = ?"
        p_top_acc.append(tenant_id)
    q_top_acc += " GROUP BY 1 ORDER BY unidades DESC, ganancia DESC LIMIT 5"
    cursor.execute(q_top_acc, p_top_acc)
    top_accesorios = [
        {
            "nombre": r["nombre"],
            "unidades": int(r["unidades"]),
            "recaudado": round(float(r["recaudado"] or 0), 2),
            "ganancia": round(float(r["ganancia"] or 0), 2)
        }
        for r in cursor.fetchall()
    ]

    conn.close()

    return {
        # Métricas Consolidadas (Retrocompatibilidad)
        "total_ganancias_mes": total_ganancias,
        "total_ventas_mes": total_ventas,
        "equipos_vendidos_mes": eq_vendidos,
        "margen_promedio_mes": margen_promedio,
        "equipos_disponibles": stats_inv["disponibles"],
        "equipos_en_garantia": equipos_en_garantia,
        "capital_inventario": round(stats_inv["capital_invertido"], 2),
        "valor_venta_inventario": round(stats_inv["valor_venta"], 2),
        "capital_inventario_total": round(stats_inv["capital_invertido"] + acc_capital, 2),
        "mes_actual_nombre": nombre_mes,
        "ventas_por_dia": ventas_dias,
        "distribucion_grados": grados_inv,
        "desglose_metodos_pago": desglose_pagos,

        # 📱 SECCIÓN 1: ANALÍTICA Y GANANCIAS DE CELULARES
        "celulares_ventas_mes": cel_ventas,
        "celulares_ganancias_mes": cel_ganancias,
        "celulares_unidades_mes": cel_unidades,
        "celulares_margen_pct": cel_margen_pct,
        "celulares_stock_disponible": stats_inv["disponibles"],
        "celulares_capital_inventario": round(stats_inv["capital_invertido"], 2),
        "celulares_valor_venta_inventario": round(stats_inv["valor_venta"], 2),
        "celulares_top_vendidos": top_celulares,

        # 🎧 SECCIÓN 2: ANALÍTICA Y GANANCIAS DE ACCESORIOS
        "accesorios_ventas_mes": acc_ventas,
        "accesorios_ganancias_mes": acc_ganancias,
        "accesorios_unidades_mes": acc_unidades,
        "accesorios_margen_pct": acc_margen_pct,
        "accesorios_stock_disponible": acc_stock,
        "accesorios_capital_inventario": acc_capital,
        "accesorios_valor_venta_inventario": acc_valor,
        "accesorios_top_vendidos": top_accesorios,

        # 🔧 SECCIÓN 3: ANALÍTICA Y GANANCIAS DE REPARACIONES / TALLER
        "reparaciones_ventas_mes": rep_ventas,
        "reparaciones_ganancias_mes": rep_ganancias,
        "reparaciones_unidades_mes": rep_unidades,
        "reparaciones_margen_pct": rep_margen_pct,

        # 💰 SECCIÓN 4: GASTOS OPERATIVOS Y GANANCIA NETA REAL
        "total_gastos_mes": total_gastos,
        "ganancia_neta_mes": ganancia_neta_mes
    }

# ==============================================================================
# ACCESORIOS Y SERVICIOS (SIN IMEI)
# ==============================================================================

def format_accesorio_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    c = float(d.get("costo_compra", 0.0) or 0.0)
    p = float(d.get("precio_venta", 0.0) or 0.0)
    d["margen_unitario"] = round(p - c, 2)
    d["precio_mayoreo"] = float(d.get("precio_mayoreo") or p)
    d["precio_20_pzs"] = float(d.get("precio_20_pzs") or d.get("precio_mayoreo") or p)
    d["precio_caja"] = float(d.get("precio_caja") or c)
    d["imagen_url"] = d.get("imagen_url")
    return d

def get_accesorios(
    categoria: Optional[str] = None,
    solo_con_stock: bool = False,
    search: Optional[str] = None,
    tenant_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    query = "SELECT * FROM accesorios WHERE 1=1"
    params = []

    if tenant_id is not None:
        query += " AND tenant_id = ?"
        params.append(tenant_id)

    if categoria and categoria != "Todos":
        cat_clean = categoria.rstrip('s').rstrip('es')
        query += " AND (categoria = ? OR categoria LIKE ?)"
        params.extend([categoria, f"{cat_clean}%"])

    if solo_con_stock:
        query += " AND (stock > 0 OR es_servicio = 1)"

    if search:
        s = f"%{search.strip()}%"
        query += " AND (nombre LIKE ? OR categoria LIKE ? OR codigo_barras LIKE ? OR color LIKE ?)"
        params.extend([s, s, s, s])

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [format_accesorio_dict(r) for r in rows]

def get_accesorio_by_id(acc_id: int, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    if tenant_id is not None:
        cursor.execute("SELECT * FROM accesorios WHERE id = ? AND tenant_id = ?", (acc_id, tenant_id))
    else:
        cursor.execute("SELECT * FROM accesorios WHERE id = ?", (acc_id,))
    row = cursor.fetchone()
    conn.close()
    return format_accesorio_dict(row) if row else None

def create_accesorio(
    nombre: str,
    categoria: str,
    costo_compra: float,
    precio_venta: float,
    stock: int,
    es_servicio: bool,
    codigo_barras: Optional[str] = None,
    precio_mayoreo: float = 0.0,
    precio_20_pzs: float = 0.0,
    precio_caja: float = 0.0,
    imagen_url: Optional[str] = None,
    color: Optional[str] = None,
    tenant_id: Optional[int] = None,
    sucursal_id: Optional[int] = None
) -> Dict[str, Any]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    if tenant_id is None:
        def_t, def_s = _get_default_tenant_and_sucursal()
        final_tenant_id = def_t
        final_sucursal_id = def_s
    else:
        final_tenant_id = tenant_id
        final_sucursal_id = sucursal_id

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO accesorios (
        nombre, categoria, codigo_barras, costo_compra, precio_venta,
        precio_mayoreo, precio_20_pzs, precio_caja, imagen_url, color,
        stock, es_servicio, fecha_registro, tenant_id, sucursal_id
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        nombre.strip(),
        categoria.strip(),
        codigo_barras.strip() if codigo_barras else None,
        round(costo_compra, 2),
        round(precio_venta, 2),
        round(precio_mayoreo or precio_venta, 2),
        round(precio_20_pzs or precio_mayoreo or precio_venta, 2),
        round(precio_caja or costo_compra, 2),
        imagen_url.strip() if imagen_url else None,
        color.strip() if color else None,
        stock if not es_servicio else 999,
        1 if es_servicio else 0,
        now,
        final_tenant_id,
        final_sucursal_id
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return get_accesorio_by_id(new_id, tenant_id=final_tenant_id)

COLUMNAS_PERMITIDAS_ACCESORIO = (
    "nombre", "categoria", "codigo_barras", "costo_compra", "precio_venta",
    "precio_mayoreo", "precio_20_pzs", "precio_caja", "imagen_url", "color", "stock", "es_servicio"
)

def update_accesorio(acc_id: int, datos: Dict[str, Any], tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    current = get_accesorio_by_id(acc_id, tenant_id=tenant_id)
    if not current:
        conn.close()
        return None

    fields, values = [], []
    for k in COLUMNAS_PERMITIDAS_ACCESORIO:
        if k in datos and datos[k] is not None:
            fields.append(f"{k} = ?")
            if k in ("costo_compra", "precio_venta", "precio_mayoreo", "precio_20_pzs", "precio_caja"):
                values.append(round(float(datos[k]), 2))
            elif k == "es_servicio":
                values.append(1 if datos[k] else 0)
            elif k in ("codigo_barras", "imagen_url"):
                values.append(datos[k].strip() if datos[k] else None)
            else:
                values.append(datos[k])

    if fields:
        values.append(acc_id)
        if tenant_id is not None:
            values.append(tenant_id)
            cursor.execute(f"UPDATE accesorios SET {', '.join(fields)} WHERE id = ? AND tenant_id = ?", values)
        else:
            cursor.execute(f"UPDATE accesorios SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    conn.close()
    return get_accesorio_by_id(acc_id, tenant_id=tenant_id)

def delete_accesorio(acc_id: int, tenant_id: Optional[int] = None) -> bool:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    current = get_accesorio_by_id(acc_id, tenant_id=tenant_id)
    if not current:
        conn.close()
        return False

    if tenant_id is not None:
        cursor.execute("DELETE FROM accesorios WHERE id = ? AND tenant_id = ?", (acc_id, tenant_id))
    else:
        cursor.execute("DELETE FROM accesorios WHERE id = ?", (acc_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

# --- Kardex, Auditoría de Stock y Reabastecimiento de Accesorios ---

MAPEO_TIPOS_KARDEX_DB = {
    'COMPRA': 'ENTRADA',
    'ENTRADA': 'ENTRADA',
    'VENTA': 'VENTA',
    'MERMA': 'MERMA',
    'AJUSTE': 'AJUSTE',
    'AJUSTE_AUDITORIA': 'AJUSTE',
    'MUESTRA': 'MUESTRA',
    'MUESTRA_USO_TIENDA': 'MUESTRA',
    'DEVOLUCION_PROVEEDOR': 'AJUSTE',
    'CARGA_MASIVA': 'ENTRADA'
}

def registrar_movimiento_stock_accesorio(
    accesorio_id: int,
    tipo_movimiento: str,
    cantidad: int,
    stock_anterior: int,
    stock_nuevo: int,
    motivo: str,
    usuario: str = "Admin",
    cursor: Optional[Any] = None
) -> None:
    """Registra una entrada, salida o ajuste en el Kardex de accesorios para auditoría."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tipo_upper = (tipo_movimiento or "AJUSTE").strip().upper()
    tipo_valido_db = MAPEO_TIPOS_KARDEX_DB.get(tipo_upper, "AJUSTE")

    motivo_final = motivo.strip() if motivo else "Ajuste de inventario"
    if tipo_upper in ('COMPRA', 'AJUSTE_AUDITORIA', 'MUESTRA_USO_TIENDA', 'DEVOLUCION_PROVEEDOR') and tipo_upper not in motivo_final.upper():
        motivo_final = f"[{tipo_upper}] {motivo_final}"

    sql = """
    INSERT INTO movimientos_stock_accesorios (accesorio_id, tipo_movimiento, cantidad, stock_anterior, stock_nuevo, motivo, usuario, fecha)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """
    params = (accesorio_id, tipo_valido_db, cantidad, stock_anterior, stock_nuevo, motivo_final, usuario, now)
    if cursor:
        cursor.execute(sql, params)
    else:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(sql, params)
        conn.commit()
        conn.close()

def ajustar_stock_accesorio(
    acc_id: int,
    nuevo_stock: int,
    tipo_movimiento: str = "AJUSTE",
    motivo: str = "Ajuste manual de stock",
    usuario: str = "Admin",
    tenant_id: Optional[int] = None
) -> Dict[str, Any]:
    """Ajusta el stock de un accesorio registrando el motivo en el Kardex (Auditoría Anti-Mermas)."""
    if nuevo_stock < 0:
        raise ValueError("El stock no puede ser un número negativo.")
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    try:
        _begin_immediate(cursor)
        if tenant_id is not None:
            cursor.execute("SELECT id, stock, nombre FROM accesorios WHERE id = ? AND tenant_id = ?", (acc_id, tenant_id))
        else:
            cursor.execute("SELECT id, stock, nombre FROM accesorios WHERE id = ?", (acc_id,))
        acc = cursor.fetchone()
        if not acc:
            raise ValueError(f"Accesorio con ID {acc_id} no encontrado o no pertenece a este negocio.")
        stock_anterior = int(acc["stock"] or 0)
        diferencia = abs(nuevo_stock - stock_anterior)
        if tenant_id is not None:
            cursor.execute("UPDATE accesorios SET stock = ? WHERE id = ? AND tenant_id = ?", (nuevo_stock, acc_id, tenant_id))
        else:
            cursor.execute("UPDATE accesorios SET stock = ? WHERE id = ?", (nuevo_stock, acc_id))
        registrar_movimiento_stock_accesorio(
            accesorio_id=acc_id,
            tipo_movimiento=tipo_movimiento,
            cantidad=diferencia,
            stock_anterior=stock_anterior,
            stock_nuevo=nuevo_stock,
            motivo=motivo,
            usuario=usuario,
            cursor=cursor
        )
        if tenant_id is not None:
            cursor.execute("SELECT * FROM accesorios WHERE id = ? AND tenant_id = ?", (acc_id, tenant_id))
        else:
            cursor.execute("SELECT * FROM accesorios WHERE id = ?", (acc_id,))
        row = cursor.fetchone()
        conn.commit()
        return format_accesorio_dict(row) if row else None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def actualizar_stock_masivo(
    items: List[Dict[str, Any]],
    motivo_general: str = "Carga masiva de inventario",
    usuario: str = "Admin",
    tenant_id: Optional[int] = None
) -> Dict[str, Any]:
    """Actualiza en masa el stock de múltiples accesorios en una sola transacción atómica."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    total_actualizados = 0
    try:
        _begin_immediate(cursor)
        for it in items:
            acc_id = int(it["id"])
            nuevo_stock = max(0, int(it.get("stock", 0)))
            if tenant_id is not None:
                cursor.execute("SELECT stock FROM accesorios WHERE id = ? AND tenant_id = ?", (acc_id, tenant_id))
            else:
                cursor.execute("SELECT stock FROM accesorios WHERE id = ?", (acc_id,))
            row = cursor.fetchone()
            if row:
                stock_ant = int(row["stock"] or 0)
                if stock_ant != nuevo_stock:
                    dif = abs(nuevo_stock - stock_ant)
                    tipo = "ENTRADA" if nuevo_stock > stock_ant else "AJUSTE"
                    if tenant_id is not None:
                        cursor.execute("UPDATE accesorios SET stock = ? WHERE id = ? AND tenant_id = ?", (nuevo_stock, acc_id, tenant_id))
                    else:
                        cursor.execute("UPDATE accesorios SET stock = ? WHERE id = ?", (nuevo_stock, acc_id))
                    registrar_movimiento_stock_accesorio(
                        accesorio_id=acc_id,
                        tipo_movimiento=tipo,
                        cantidad=dif,
                        stock_anterior=stock_ant,
                        stock_nuevo=nuevo_stock,
                        motivo=motivo_general,
                        usuario=usuario,
                        cursor=cursor
                    )
                    total_actualizados += 1
        conn.commit()
        return {
            "total_actualizados": total_actualizados,
            "mensaje": f"Se actualizaron exitosamente {total_actualizados} accesorios."
        }
    finally:
        conn.close()

def get_historial_kardex_accesorios(
    acc_id: Optional[int] = None,
    tipo: Optional[str] = None,
    limit: int = 150,
    tenant_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Consulta la bitácora de movimientos de accesorios para auditoría."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    query = """
    SELECT 
        m.id,
        m.accesorio_id,
        a.nombre as accesorio_nombre,
        a.categoria as accesorio_categoria,
        m.tipo_movimiento,
        m.cantidad,
        m.stock_anterior,
        m.stock_nuevo,
        m.motivo,
        m.usuario,
        m.fecha
    FROM movimientos_stock_accesorios m
    JOIN accesorios a ON m.accesorio_id = a.id
    WHERE 1=1
    """
    params = []
    if tenant_id is not None:
        query += " AND a.tenant_id = ?"
        params.append(tenant_id)
    if acc_id:
        query += " AND m.accesorio_id = ?"
        params.append(acc_id)
    if tipo and tipo != "Todos":
        query += " AND m.tipo_movimiento = ?"
        params.append(tipo.upper())
    query += " ORDER BY m.id DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def generar_sugerido_reabastecimiento(
    stock_objetivo: int = 10,
    stock_minimo: int = 3,
    tenant_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Analiza accesorios agotados o con stock bajo y genera una lista de compra inteligente
    con cantidades sugeridas para reordenar al proveedor y texto para WhatsApp.
    """
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    query = """
    SELECT id, nombre, categoria, costo_compra, precio_mayoreo, stock, imagen_url
    FROM accesorios
    WHERE es_servicio = 0 AND stock <= ?
    """
    params = [stock_minimo]
    if tenant_id is not None:
        query += " AND tenant_id = ?"
        params.append(tenant_id)
    query += " ORDER BY categoria ASC, stock ASC, nombre ASC;"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    total_piezas_pedir = 0
    inversion_estimada = 0.0

    for r in rows:
        d = dict(r)
        curr_stock = int(d["stock"] or 0)
        sugerido = max(1, stock_objetivo - curr_stock)
        costo = float(d.get("costo_compra", 0.0) or 0.0)
        subtotal = round(sugerido * costo, 2)
        d["cantidad_sugerida"] = sugerido
        d["subtotal_estimado"] = subtotal
        items.append(d)
        total_piezas_pedir += sugerido
        inversion_estimada += subtotal

    inversion_estimada = round(inversion_estimada, 2)

    # Texto formateado para WhatsApp al proveedor
    now_str = datetime.now().strftime("%d/%m/%Y")
    lineas_wa = [
        f"📦 *PEDIDO DE REABASTECIMIENTO - SAMUEL NAVARRETE* ({now_str})",
        f"Total artículos: {len(items)} | Total piezas: {total_piezas_pedir} pzs\n"
    ]
    por_cat: Dict[str, list] = {}
    for it in items:
        cat = it["categoria"]
        if cat not in por_cat:
            por_cat[cat] = []
        por_cat[cat].append(f"• *{it['cantidad_sugerida']} pzs* - {it['nombre']} (Stock actual: {it['stock']})")

    for cat, prods in por_cat.items():
        lineas_wa.append(f"📁 *{cat.upper()}*")
        lineas_wa.extend(prods)
        lineas_wa.append("")

    texto_whatsapp = "\n".join(lineas_wa)

    total_agotados = sum(1 for it in items if int(it.get("stock", 0)) <= 0)

    return {
        "items": items,
        "sugeridos": items,
        "total_items": len(items),
        "total_items_surtir": len(items),
        "total_agotados": total_agotados,
        "total_piezas_sugeridas": total_piezas_pedir,
        "inversion_estimada": inversion_estimada,
        "inversion_estimada_total": inversion_estimada,
        "texto_whatsapp": texto_whatsapp,
        "mensaje_whatsapp": texto_whatsapp
    }


# ==============================================================================
# CORTES DE CAJA DIARIOS (ARQUEO / REPORTE Z)
# ==============================================================================

def obtener_resumen_corte_actual(
    conn_ext: Optional[sqlite3.Connection] = None,
    tenant_id: Optional[int] = None,
    sucursal_id: Optional[int] = None
) -> Dict[str, Any]:
    """Calcula el balance acumulado de ventas desde el último corte de caja del tenant (o del día de hoy)."""
    conn = conn_ext if conn_ext else get_db_connection()
    cursor = conn.cursor()

    q_corte = "SELECT fecha_corte FROM cortes_caja"
    p_corte = []
    if tenant_id is not None:
        q_corte += " WHERE tenant_id = ?"
        p_corte.append(tenant_id)
    q_corte += " ORDER BY id DESC LIMIT 1"
    cursor.execute(q_corte, p_corte)
    ultimo_corte = cursor.fetchone()

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    if ultimo_corte and ultimo_corte["fecha_corte"]:
        fecha_inicio = ultimo_corte["fecha_corte"]
        op_comparacion = ">"
    else:
        fecha_inicio = now.strftime("%Y-%m-%d 00:00:00")
        op_comparacion = ">="

    q_totales = f"""
    SELECT 
        COUNT(id) as total_operaciones,
        COALESCE(SUM(precio_final), 0) as total_ventas,
        COALESCE(SUM(monto_efectivo), 0) as total_efectivo,
        COALESCE(SUM(monto_transferencia), 0) as total_transferencia,
        COALESCE(SUM(monto_garantia), 0) as total_garantia
    FROM ventas
    WHERE fecha_venta {op_comparacion} ? AND fecha_venta <= ?
    """
    p_totales = [fecha_inicio, now_str]
    if tenant_id is not None:
        q_totales += " AND tenant_id = ?"
        p_totales.append(tenant_id)
    cursor.execute(q_totales, p_totales)
    r = cursor.fetchone()

    q_ventas = f"""
    SELECT v.id, v.fecha_venta, v.precio_final, v.metodo_pago, v.monto_efectivo, v.monto_transferencia, v.monto_garantia, c.nombre as cliente_nombre
    FROM ventas v
    JOIN clientes c ON v.cliente_id = c.id
    WHERE v.fecha_venta {op_comparacion} ? AND v.fecha_venta <= ?
    """
    p_ventas = [fecha_inicio, now_str]
    if tenant_id is not None:
        q_ventas += " AND v.tenant_id = ?"
        p_ventas.append(tenant_id)
    q_ventas += " ORDER BY v.id DESC"
    cursor.execute(q_ventas, p_ventas)
    ventas_rows = [dict(v) for v in cursor.fetchall()]

    if not conn_ext:
        conn.close()

    return {
        "fecha_corte": now_str,
        "fecha_inicio_periodo": fecha_inicio,
        "cantidad_ventas": r["total_operaciones"],
        "total_ventas": round(r["total_ventas"], 2),
        "total_efectivo": round(r["total_efectivo"], 2),
        "total_transferencia": round(r["total_transferencia"], 2),
        "total_garantia": round(r["total_garantia"], 2),
        "ventas_periodo": ventas_rows
    }

def guardar_corte_caja(
    efectivo_declarado: float,
    notas: Optional[str] = None,
    tenant_id: Optional[int] = None,
    sucursal_id: Optional[int] = None
) -> Dict[str, Any]:
    if tenant_id is None:
        def_t, def_s = _get_default_tenant_and_sucursal()
        final_tenant_id = def_t
        final_sucursal_id = def_s
    else:
        final_tenant_id = tenant_id
        final_sucursal_id = sucursal_id

    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    try:
        _begin_immediate(cursor)
        resumen = obtener_resumen_corte_actual(
            conn_ext=conn,
            tenant_id=final_tenant_id,
            sucursal_id=final_sucursal_id
        )
        total_efectivo_sistema = resumen["total_efectivo"]
        efectivo_declarado = round(float(efectivo_declarado), 2)
        diferencia = round(efectivo_declarado - total_efectivo_sistema, 2)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO cortes_caja (
            fecha_corte, fecha_inicio_periodo, total_ventas, total_efectivo, total_transferencia,
            total_garantia, efectivo_declarado, diferencia, cantidad_ventas, notas, fecha_registro,
            tenant_id, sucursal_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_str,
            resumen["fecha_inicio_periodo"],
            resumen["total_ventas"],
            total_efectivo_sistema,
            resumen["total_transferencia"],
            resumen["total_garantia"],
            efectivo_declarado,
            diferencia,
            resumen["cantidad_ventas"],
            notas,
            now_str,
            final_tenant_id,
            final_sucursal_id
        ))
        conn.commit()
        new_id = cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    resumen["id"] = new_id
    resumen["efectivo_declarado"] = efectivo_declarado
    resumen["diferencia"] = diferencia
    resumen["notas"] = notas
    resumen["fecha_registro"] = now_str
    resumen["tenant_id"] = final_tenant_id
    resumen["sucursal_id"] = final_sucursal_id
    return resumen

def get_cortes_caja(limit: int = 50, tenant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    if tenant_id is not None:
        cursor.execute("SELECT * FROM cortes_caja WHERE tenant_id = ? ORDER BY id DESC LIMIT ?", (tenant_id, limit))
    else:
        cursor.execute("SELECT * FROM cortes_caja ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# ==============================================================================
# HISTORIAL UNIVERSAL POR IMEI (TRAZABILIDAD 360°)
# ==============================================================================

def obtener_historial_imei(imei: str, tenant_id: Optional[int] = None) -> Dict[str, Any]:
    clean_imei = imei.strip().replace(" ", "").replace("-", "")
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    if tenant_id is not None:
        cursor.execute("SELECT * FROM equipos WHERE imei = ? AND tenant_id = ?", (clean_imei, tenant_id))
    else:
        cursor.execute("SELECT * FROM equipos WHERE imei = ?", (clean_imei,))
    eq = cursor.fetchone()
    if not eq:
        conn.close()
        raise ValueError(f"No se encontró ningún equipo con el IMEI '{imei}' en el sistema.")

    eq_dict = format_equipo_dict(eq)
    eventos = []

    # Evento 1: Ingreso al inventario
    eventos.append({
        "tipo": "INGRESO",
        "fecha": eq["fecha_registro"],
        "titulo": "Ingreso a Almacén",
        "descripcion": f"Registrado en inventario como Grado {eq['grado']} ({eq['color']}).",
        "detalles": {
            "costo_compra": eq["costo_compra"],
            "precio_venta": eq["precio_venta"],
            "grado": eq["grado"]
        }
    })

    # Evento 2: Ventas asociadas a este equipo
    cursor.execute("""
    SELECT 
        v.id as venta_id,
        v.fecha_venta,
        v.metodo_pago,
        v.precio_final as venta_total,
        vi.precio_final as precio_equipo,
        c.nombre as cliente_nombre,
        c.telefono as cliente_telefono
    FROM venta_items vi
    JOIN ventas v ON vi.venta_id = v.id
    JOIN clientes c ON v.cliente_id = c.id
    WHERE vi.equipo_id = ?
    ORDER BY v.id ASC
    """, (eq["id"],))
    ventas = cursor.fetchall()
    for v in ventas:
        eventos.append({
            "tipo": "VENTA",
            "fecha": v["fecha_venta"],
            "titulo": f"Vendido a {v['cliente_nombre']}",
            "descripcion": f"Venta #{v['venta_id']} por ${v['precio_equipo']:,.2f} con método '{v['metodo_pago']}'.",
            "detalles": {
                "venta_id": v["venta_id"],
                "cliente_nombre": v["cliente_nombre"],
                "cliente_telefono": v["cliente_telefono"],
                "precio_cobrado": v["precio_equipo"],
                "metodo_pago": v["metodo_pago"]
            }
        })

    # Evento 3: Garantías registradas para este equipo
    cursor.execute("""
    SELECT 
        g.id as garantia_id,
        g.fecha_devolucion,
        g.motivo,
        g.falla_descripcion,
        g.solucion,
        g.estado_equipo_recibido,
        g.monto_cubierto,
        eq_rep.modelo as reemplazo_modelo,
        eq_rep.imei as reemplazo_imei
    FROM garantias g
    LEFT JOIN equipos eq_rep ON g.equipo_reemplazo_id = eq_rep.id
    WHERE g.equipo_id = ?
    ORDER BY g.id ASC
    """, (eq["id"],))
    garantias = cursor.fetchall()
    for g in garantias:
        desc = f"Devuelto por: {g['motivo']}. Solución: {g['solucion']}."
        if g["reemplazo_imei"]:
            desc += f" (Se entregó {g['reemplazo_modelo']} IMEI {g['reemplazo_imei']})"
        eventos.append({
            "tipo": "GARANTIA_RECLAMO",
            "fecha": g["fecha_devolucion"],
            "titulo": f"Reclamo de Garantía #{g['garantia_id']}",
            "descripcion": desc,
            "detalles": {
                "motivo": g["motivo"],
                "falla": g["falla_descripcion"],
                "solucion": g["solucion"],
                "estado_final": g["estado_equipo_recibido"]
            }
        })

    # Evento 4: ¿Fue entregado como equipo de reemplazo en otra garantía?
    cursor.execute("""
    SELECT g.id, g.fecha_devolucion, eq_orig.modelo as orig_modelo, eq_orig.imei as orig_imei
    FROM garantias g
    JOIN equipos eq_orig ON g.equipo_id = eq_orig.id
    WHERE g.equipo_reemplazo_id = ?
    """, (eq["id"],))
    como_reemplazo = cursor.fetchall()
    for cr in como_reemplazo:
        eventos.append({
            "tipo": "REEMPLAZO",
            "fecha": cr["fecha_devolucion"],
            "titulo": "Entregado como Reemplazo de Garantía",
            "descripcion": f"Entregado al cliente en sustitución del equipo defectuoso {cr['orig_modelo']} (IMEI: {cr['orig_imei']}).",
            "detalles": {
                "garantia_id": cr["id"],
                "imei_defectuoso": cr["orig_imei"]
            }
        })

    # Evento 5: Transiciones de estado y reingreso a funcional (garantias_historial)
    try:
        if tenant_id is not None:
            cursor.execute("""
            SELECT id, garantia_id, estado_anterior, estado_nuevo, fecha_cambio, usuario, observaciones
            FROM garantias_historial
            WHERE equipo_id = ? AND tenant_id = ?
            ORDER BY id ASC;
            """, (eq["id"], tenant_id))
        else:
            cursor.execute("""
            SELECT id, garantia_id, estado_anterior, estado_nuevo, fecha_cambio, usuario, observaciones
            FROM garantias_historial
            WHERE equipo_id = ?
            ORDER BY id ASC;
            """, (eq["id"],))
        hist_filas = cursor.fetchall()
        for gh in hist_filas:
            if gh["estado_nuevo"] == "Disponible":
                eventos.append({
                    "tipo": "RESTAURADO",
                    "fecha": gh["fecha_cambio"],
                    "titulo": "Puesto Funcional / Reingreso a Stock",
                    "descripcion": gh["observaciones"] or "Equipo reacondicionado/reparado y puesto nuevamente como funcional para venta.",
                    "detalles": {
                        "usuario": gh["usuario"] or "Técnico",
                        "estado_anterior": gh["estado_anterior"],
                        "estado_nuevo": gh["estado_nuevo"]
                    }
                })
            elif gh["estado_nuevo"] in ("En Garantia", "Baja por Garantia") and not gh["garantia_id"]:
                eventos.append({
                    "tipo": "GARANTIA_RECLAMO",
                    "fecha": gh["fecha_cambio"],
                    "titulo": f"Cambio de Estado: {gh['estado_nuevo']}",
                    "descripcion": gh["observaciones"] or f"Estado modificado a {gh['estado_nuevo']}.",
                    "detalles": {
                        "usuario": gh["usuario"],
                        "estado_anterior": gh["estado_anterior"],
                        "estado_nuevo": gh["estado_nuevo"]
                    }
                })
    except Exception:
        pass

    # Evento 6: Órdenes de Servicio Técnico en Taller
    try:
        if tenant_id is not None:
            cursor.execute("""
            SELECT id, folio, equipo_modelo, descripcion_falla, costo_estimado, estado, fecha_ingreso, tecnico_asignado
            FROM reparaciones
            WHERE imei_serie = ? AND tenant_id = ?
            ORDER BY id ASC;
            """, (clean_imei, tenant_id))
        else:
            cursor.execute("""
            SELECT id, folio, equipo_modelo, descripcion_falla, costo_estimado, estado, fecha_ingreso, tecnico_asignado
            FROM reparaciones
            WHERE imei_serie = ?
            ORDER BY id ASC;
            """, (clean_imei,))
        reparaciones = cursor.fetchall()
        for rep in reparaciones:
            costo_val = rep["costo_estimado"] or 0
            eventos.append({
                "tipo": "REPARACION_TALLER",
                "fecha": rep["fecha_ingreso"],
                "titulo": f"Taller: Orden #{rep['folio']}",
                "descripcion": f"Falla: {rep['descripcion_falla']}. Estado: {rep['estado']}. Costo: ${costo_val:,.2f}.",
                "detalles": {
                    "folio": rep["folio"],
                    "estado": rep["estado"],
                    "tecnico": rep["tecnico_asignado"] or "No asignado",
                    "costo": costo_val
                }
            })
    except Exception:
        pass

    # Ordenar cronológicamente
    eventos.sort(key=lambda x: x["fecha"])
    conn.close()

    return {
        "imei": eq_dict["imei"],
        "modelo": eq_dict["modelo"],
        "color": eq_dict["color"],
        "capacidad_gb": eq_dict["capacidad_gb"],
        "grado": eq_dict["grado"],
        "estado_actual": eq_dict["estado"],
        "costo_compra": eq_dict["costo_compra"],
        "precio_venta": eq_dict["precio_venta"],
        "margen_proyectado": eq_dict["margen_proyectado"],
        "porcentaje_margen": eq_dict["porcentaje_margen"],
        "dias_en_stock": eq_dict["dias_en_stock"],
        "estado_antiguedad": eq_dict["estado_antiguedad"],
        "eventos": eventos
    }

# ==============================================================================
# RESPALDO Y EXPORTACIÓN COMPLETA
# ==============================================================================

TABLAS_PERMITIDAS_EXPORTACION = (
    "tenants", "sucursales", "configuracion_tienda", "usuarios",
    "clientes", "equipos", "accesorios", "ventas", "venta_items",
    "abonos_ventas_credito", "reparaciones", "garantias", "cortes_caja",
    "historial_ventas_cambios", "garantias_historial"
)

def exportar_todo_json(tenant_id: Optional[int] = None) -> Dict[str, Any]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    resultado = {
        "version": "2.0",
        "app": "Mi Inventario Samuel Navarrete",
        "fecha_exportacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_id": tenant_id,
        "datos": {}
    }

    columnas_usuarios_seguras = "id, nombre, username, rol, activo, fecha_creacion, tenant_id, sucursal_id"

    for t in TABLAS_PERMITIDAS_EXPORTACION:
        try:
            if tenant_id is not None:
                if t == "tenants":
                    cursor.execute("SELECT * FROM tenants WHERE id = ?;", (tenant_id,))
                elif t == "usuarios":
                    cursor.execute(f"SELECT {columnas_usuarios_seguras} FROM usuarios WHERE tenant_id = ?;", (tenant_id,))
                elif t in ("sucursales", "configuracion_tienda", "clientes", "equipos", "accesorios", "ventas", "reparaciones", "cortes_caja"):
                    cursor.execute(f"SELECT * FROM {t} WHERE tenant_id = ?;", (tenant_id,))
                elif t == "venta_items":
                    cursor.execute("SELECT vi.* FROM venta_items vi JOIN ventas v ON vi.venta_id = v.id WHERE v.tenant_id = ?;", (tenant_id,))
                elif t == "abonos_ventas_credito":
                    cursor.execute("SELECT a.* FROM abonos_ventas_credito a JOIN ventas v ON a.venta_id = v.id WHERE v.tenant_id = ?;", (tenant_id,))
                elif t == "garantias":
                    cursor.execute("SELECT g.* FROM garantias g JOIN equipos e ON g.equipo_id = e.id WHERE e.tenant_id = ?;", (tenant_id,))
                elif t == "historial_ventas_cambios":
                    cursor.execute("SELECT h.* FROM historial_ventas_cambios h JOIN ventas v ON h.venta_id = v.id WHERE v.tenant_id = ?;", (tenant_id,))
                elif t == "garantias_historial":
                    cursor.execute("SELECT gh.* FROM garantias_historial gh JOIN garantias g ON gh.garantia_id = g.id JOIN equipos e ON g.equipo_id = e.id WHERE e.tenant_id = ?;", (tenant_id,))
                else:
                    cursor.execute(f"SELECT * FROM {t};")
            else:
                if t == "usuarios":
                    cursor.execute(f"SELECT {columnas_usuarios_seguras} FROM usuarios;")
                else:
                    cursor.execute(f"SELECT * FROM {t};")

            resultado["datos"][t] = [dict(r) for r in cursor.fetchall()]
        except Exception:
            resultado["datos"][t] = []

    conn.close()
    return resultado


# ==============================================================================
# MÓDULO DE REPARACIONES Y TALLER TÉCNICO
# ==============================================================================

def generar_siguiente_folio_reparacion(cursor, tenant_id: Optional[int] = None) -> str:
    cursor.execute("SELECT COALESCE(MAX(id), 0) as max_id FROM reparaciones;")
    row = cursor.fetchone()
    next_id = (int(row["max_id"]) + 1) if row else 1
    if tenant_id and tenant_id > 1:
        return f"REP-T{tenant_id}-{next_id:04d}"
    return f"REP-{next_id:04d}"

def get_reparaciones(
    estado: Optional[str] = None,
    search: Optional[str] = None,
    tenant_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    query = "SELECT * FROM reparaciones WHERE 1=1"
    params = []

    if tenant_id is not None:
        query += " AND tenant_id = ?"
        params.append(tenant_id)

    if estado and estado != "Todos":
        query += " AND estado = ?"
        params.append(estado)

    if search:
        s = f"%{search.strip()}%"
        query += " AND (folio LIKE ? OR cliente_nombre LIKE ? OR cliente_telefono LIKE ? OR dispositivo_modelo LIKE ? OR imei_serie LIKE ?)"
        params.extend([s, s, s, s, s])

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        r["margen_ganancia"] = round(r["precio_servicio"] - r["costo_refaccion"], 2)

    conn.close()
    return rows

def get_reparacion_by_id(rep_id: int, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    if tenant_id is not None:
        cursor.execute("SELECT * FROM reparaciones WHERE id = ? AND tenant_id = ?", (rep_id, tenant_id))
    else:
        cursor.execute("SELECT * FROM reparaciones WHERE id = ?", (rep_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    res = dict(row)
    res["margen_ganancia"] = round(res["precio_servicio"] - res["costo_refaccion"], 2)
    return res

def get_reparacion_publica_by_folio(folio: str) -> Optional[Dict[str, Any]]:
    """Consulta segura y pública del estado de una orden de servicio para clientes (portal web / QR)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.folio, r.dispositivo_modelo, r.color, r.estado, r.falla_reportada,
               r.diagnostico_tecnico, r.fecha_ingreso, r.fecha_prometida, r.fecha_entrega,
               r.precio_servicio, r.anticipo, r.saldo_pendiente, r.checklist_recepcion,
               r.tenant_id,
               COALESCE(t.nombre_comercial, 'Taller Técnico') as nombre_tienda,
               COALESCE(cfg.whatsapp_notificaciones, t.telefono, '') as telefono_tienda
        FROM reparaciones r
        LEFT JOIN tenants t ON r.tenant_id = t.id
        LEFT JOIN configuracion_tienda cfg ON (cfg.tenant_id = r.tenant_id)
        WHERE UPPER(TRIM(r.folio)) = UPPER(TRIM(?))
        ORDER BY cfg.id DESC LIMIT 1;
    """, (folio,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)

def create_reparacion(
    datos: Dict[str, Any],
    tenant_id: Optional[int] = None,
    sucursal_id: Optional[int] = None
) -> Dict[str, Any]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    if tenant_id is None:
        def_t, def_s = _get_default_tenant_and_sucursal()
        final_tenant_id = def_t
        final_sucursal_id = def_s
    else:
        final_tenant_id = tenant_id
        final_sucursal_id = sucursal_id

    try:
        _begin_immediate(cursor)
        folio = generar_siguiente_folio_reparacion(cursor, tenant_id=final_tenant_id)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        precio = float(datos.get("precio_servicio", 0))
        anticipo = float(datos.get("anticipo", 0))
        saldo = round(max(0.0, precio - anticipo), 2)

        cursor.execute("""
        INSERT INTO reparaciones (
            folio, cliente_nombre, cliente_telefono, dispositivo_modelo, color,
            imei_serie, codigo_patron, falla_reportada, diagnostico_tecnico,
            condicion_recepcion, checklist_recepcion, costo_refaccion, precio_servicio, anticipo,
            saldo_pendiente, estado, fecha_ingreso, fecha_prometida,
            tecnico_responsable, notas, tenant_id, sucursal_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Recibido', ?, ?, ?, ?, ?, ?)
        """, (
            folio,
            datos["cliente_nombre"].strip(),
            datos["cliente_telefono"].strip(),
            datos["dispositivo_modelo"].strip(),
            datos.get("color", "").strip() if datos.get("color") else "",
            datos.get("imei_serie", "").strip() if datos.get("imei_serie") else "",
            datos.get("codigo_patron", "").strip() if datos.get("codigo_patron") else None,
            datos["falla_reportada"].strip(),
            datos.get("diagnostico_tecnico", "").strip() if datos.get("diagnostico_tecnico") else None,
            datos.get("condicion_recepcion", "").strip() if datos.get("condicion_recepcion") else None,
            datos.get("checklist_recepcion", "").strip() if datos.get("checklist_recepcion") else None,
            float(datos.get("costo_refaccion", 0)),
            precio,
            anticipo,
            saldo,
            now_str,
            datos.get("fecha_prometida") or None,
            datos.get("tecnico_responsable", "Samuel N."),
            datos.get("notas", "").strip() if datos.get("notas") else None,
            final_tenant_id,
            final_sucursal_id
        ))
        conn.commit()
        new_id = cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_reparacion_by_id(new_id, tenant_id=final_tenant_id)

COLUMNAS_PERMITIDAS_REPARACION = {
    "cliente_nombre", "cliente_telefono", "dispositivo_modelo", "color",
    "imei_serie", "codigo_patron", "falla_reportada", "diagnostico_tecnico",
    "condicion_recepcion", "checklist_recepcion", "costo_refaccion", "precio_servicio", "anticipo",
    "saldo_pendiente", "estado", "fecha_ingreso", "fecha_prometida",
    "fecha_entrega", "tecnico_responsable", "notas"
}

def update_reparacion(
    rep_id: int,
    datos: Dict[str, Any],
    tenant_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    existing = get_reparacion_by_id(rep_id, tenant_id=tenant_id)
    if not existing:
        conn.close()
        return None

    ex_dict = dict(existing)
    precio = float(datos.get("precio_servicio", ex_dict["precio_servicio"]))
    anticipo = float(datos.get("anticipo", ex_dict["anticipo"]))
    saldo = round(max(0.0, precio - anticipo), 2)
    datos["saldo_pendiente"] = saldo

    if datos.get("estado") == "Entregado" and not ex_dict.get("fecha_entrega"):
        datos["fecha_entrega"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    campos = []
    valores = []
    for k, v in datos.items():
        if k in COLUMNAS_PERMITIDAS_REPARACION:
            campos.append(f"{k} = ?")
            valores.append(v)

    if campos:
        valores.append(rep_id)
        if tenant_id is not None:
            valores.append(tenant_id)
            cursor.execute(f"UPDATE reparaciones SET {', '.join(campos)} WHERE id = ? AND tenant_id = ?", valores)
        else:
            cursor.execute(f"UPDATE reparaciones SET {', '.join(campos)} WHERE id = ?", valores)
        conn.commit()

    conn.close()
    return get_reparacion_by_id(rep_id, tenant_id=tenant_id)

def cambiar_estado_reparacion(
    rep_id: int,
    nuevo_estado: str,
    tenant_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    estados_validos = ('Recibido', 'En Revision', 'Esperando Refaccion', 'Listo para Entrega', 'Entregado', 'Cancelado')
    if nuevo_estado not in estados_validos:
        raise ValueError(f"Estado inválido: {nuevo_estado}. Válidos: {', '.join(estados_validos)}")
    
    update_data = {"estado": nuevo_estado}
    if nuevo_estado == "Entregado":
        update_data["fecha_entrega"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        update_data["saldo_pendiente"] = 0.0

    return update_reparacion(rep_id, update_data, tenant_id=tenant_id)

def abonar_reparacion(
    rep_id: int,
    monto_abono: float,
    tenant_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    if monto_abono <= 0:
        raise ValueError("El monto del abono debe ser mayor a cero.")

    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    try:
        _begin_immediate(cursor)
        if tenant_id is not None:
            cursor.execute("SELECT * FROM reparaciones WHERE id = ? AND tenant_id = ?", (rep_id, tenant_id))
        else:
            cursor.execute("SELECT * FROM reparaciones WHERE id = ?", (rep_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return None

        rep = dict(row)
        if rep["estado"] == "Cancelado":
            raise ValueError("No se pueden registrar abonos en una orden cancelada.")

        nuevo_anticipo = round(float(rep["anticipo"]) + float(monto_abono), 2)
        nuevo_saldo = round(max(0.0, float(rep["precio_servicio"]) - nuevo_anticipo), 2)

        if tenant_id is not None:
            cursor.execute(
                "UPDATE reparaciones SET anticipo = ?, saldo_pendiente = ? WHERE id = ? AND tenant_id = ?",
                (nuevo_anticipo, nuevo_saldo, rep_id, tenant_id)
            )
        else:
            cursor.execute(
                "UPDATE reparaciones SET anticipo = ?, saldo_pendiente = ? WHERE id = ?",
                (nuevo_anticipo, nuevo_saldo, rep_id)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return get_reparacion_by_id(rep_id, tenant_id=tenant_id)

def delete_reparacion(rep_id: int, tenant_id: Optional[int] = None) -> bool:
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    existing = get_reparacion_by_id(rep_id, tenant_id=tenant_id)
    if not existing:
        conn.close()
        return False

    if tenant_id is not None:
        cursor.execute("DELETE FROM reparaciones WHERE id = ? AND tenant_id = ?", (rep_id, tenant_id))
    else:
        cursor.execute("DELETE FROM reparaciones WHERE id = ?", (rep_id,))
    conn.commit()
    filas = cursor.rowcount
    conn.close()
    return filas > 0


# ==============================================================================
# CONFIGURACIÓN DE TIENDA Y MARCA BLANCA (WHITE-LABEL)
# ==============================================================================

def get_configuracion_general(tenant_id: int) -> Dict[str, Any]:
    """Obtiene la configuración visual, fiscal y de tickets para el tenant especificado."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM tenants WHERE id = ? LIMIT 1;", (tenant_id,))
        tenant = cursor.fetchone()
        if not tenant:
            raise ValueError(f"El tenant con ID {tenant_id} no existe.")

        cursor.execute("SELECT * FROM sucursales WHERE tenant_id = ? ORDER BY es_matriz DESC, id ASC LIMIT 1;", (tenant_id,))
        sucursal = cursor.fetchone()

        cursor.execute("SELECT * FROM configuracion_tienda WHERE tenant_id = ? LIMIT 1;", (tenant_id,))
        conf = cursor.fetchone()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not conf:
            def_logo = "/static/img/logo.png"
            def_encabezado = f"{tenant['nombre_comercial']} | Compra, Venta y Reparación"
            def_pie = "Garantía de 30 días válida únicamente con este comprobante original. No cubre humedad, golpes ni manipulación indebida."
            def_wsp = tenant["telefono"] or ""

            cursor.execute("""
            INSERT INTO configuracion_tienda (tenant_id, logo_url, encabezado_ticket, pie_ticket_garantia, whatsapp_notificaciones, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (tenant_id, def_logo, def_encabezado, def_pie, def_wsp, now))
            conn.commit()
            conf_dict = {
                "logo_url": def_logo,
                "encabezado_ticket": def_encabezado,
                "pie_ticket_garantia": def_pie,
                "whatsapp_notificaciones": def_wsp,
                "fecha_actualizacion": now,
            }
        else:
            conf_dict = dict(conf)

        return {
            "tenant_id": int(tenant["id"]),
            "nombre_comercial": str(tenant["nombre_comercial"]),
            "slug": str(tenant["slug"]),
            "email_contacto": tenant["email_contacto"],
            "telefono": tenant["telefono"] or conf_dict.get("whatsapp_notificaciones"),
            "whatsapp_notificaciones": conf_dict.get("whatsapp_notificaciones") or tenant["telefono"],
            "direccion": sucursal["direccion"] if sucursal and sucursal["direccion"] else "",
            "nombre_sucursal": sucursal["nombre_sucursal"] if sucursal and sucursal["nombre_sucursal"] else "Matriz",
            "logo_url": conf_dict.get("logo_url") or "/static/img/logo.png",
            "encabezado_ticket": conf_dict.get("encabezado_ticket") or f"{tenant['nombre_comercial']} | Compra, Venta y Reparación",
            "pie_ticket_garantia": conf_dict.get("pie_ticket_garantia") or "Garantía de 30 días válida únicamente con este comprobante original.",
            "fecha_actualizacion": conf_dict.get("fecha_actualizacion") or now,
        }
    finally:
        conn.close()


def update_configuracion_general(tenant_id: int, datos: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza datos del negocio, sucursal matriz y configuración de tickets."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        _begin_immediate(cursor)

        # 1. Actualizar tenants si aplica
        if "nombre_comercial" in datos and datos["nombre_comercial"] is not None:
            cursor.execute("UPDATE tenants SET nombre_comercial = ? WHERE id = ?;", (datos["nombre_comercial"].strip(), tenant_id))

        if "telefono" in datos and datos["telefono"] is not None:
            cursor.execute("UPDATE tenants SET telefono = ? WHERE id = ?;", (datos["telefono"].strip(), tenant_id))

        # 2. Actualizar sucursal matriz
        if "direccion" in datos and datos["direccion"] is not None:
            cursor.execute("SELECT id FROM sucursales WHERE tenant_id = ? ORDER BY es_matriz DESC, id ASC LIMIT 1;", (tenant_id,))
            suc = cursor.fetchone()
            if suc:
                cursor.execute("UPDATE sucursales SET direccion = ? WHERE id = ?;", (datos["direccion"].strip(), suc["id"]))
            else:
                cursor.execute("""
                INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
                VALUES (?, 'Matriz', ?, ?, 1, ?);
                """, (tenant_id, datos["direccion"].strip(), datos.get("telefono", ""), now))

        # 3. Actualizar configuracion_tienda
        cursor.execute("SELECT id FROM configuracion_tienda WHERE tenant_id = ? LIMIT 1;", (tenant_id,))
        conf_row = cursor.fetchone()

        encabezado = datos.get("encabezado_ticket")
        pie = datos.get("pie_ticket_garantia")
        whatsapp = datos.get("whatsapp_notificaciones")

        if not conf_row:
            cursor.execute("""
            INSERT INTO configuracion_tienda (tenant_id, logo_url, encabezado_ticket, pie_ticket_garantia, whatsapp_notificaciones, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (
                tenant_id,
                "/static/img/logo.png",
                encabezado.strip() if encabezado else None,
                pie.strip() if pie else None,
                whatsapp.strip() if whatsapp else None,
                now
            ))
        else:
            updates = ["fecha_actualizacion = ?"]
            vals = [now]
            if encabezado is not None:
                updates.append("encabezado_ticket = ?")
                vals.append(encabezado.strip())
            if pie is not None:
                updates.append("pie_ticket_garantia = ?")
                vals.append(pie.strip())
            if whatsapp is not None:
                updates.append("whatsapp_notificaciones = ?")
                vals.append(whatsapp.strip())

            vals.append(tenant_id)
            cursor.execute(f"UPDATE configuracion_tienda SET {', '.join(updates)} WHERE tenant_id = ?;", vals)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return get_configuracion_general(tenant_id)


def update_logo_tienda(tenant_id: int, logo_url: str) -> str:
    """Actualiza la URL del logotipo de la tienda para el tenant especificado."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        _begin_immediate(cursor)
        cursor.execute("SELECT id FROM configuracion_tienda WHERE tenant_id = ? LIMIT 1;", (tenant_id,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO configuracion_tienda (tenant_id, logo_url, encabezado_ticket, pie_ticket_garantia, whatsapp_notificaciones, fecha_actualizacion)
            VALUES (?, ?, NULL, NULL, NULL, ?);
            """, (tenant_id, logo_url, now))
        else:
            cursor.execute("UPDATE configuracion_tienda SET logo_url = ?, fecha_actualizacion = ? WHERE tenant_id = ?;", (logo_url, now, tenant_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return logo_url


# ==============================================================================
# GESTIÓN DE EMPLEADOS Y CAJEROS MULTI-TENANT
# ==============================================================================

def get_empleados(tenant_id: int) -> List[Dict[str, Any]]:
    """
    Retorna la lista de empleados y usuarios pertenecientes al tenant_id en sesión.
    """
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, nombre, username, rol, activo, fecha_creacion, tenant_id, sucursal_id
            FROM usuarios
            WHERE tenant_id = ?
            ORDER BY id ASC;
        """, (tenant_id,))
        rows = cursor.fetchall()
        empleados = []
        for r in rows:
            d = dict(r)
            d["activo"] = bool(d["activo"])
            empleados.append(d)
        return empleados
    finally:
        conn.close()


def get_empleado_by_id(empleado_id: int, tenant_id: int) -> Optional[Dict[str, Any]]:
    """
    Obtiene un usuario/empleado por ID garantizando aislamiento multi-tenant.
    """
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, nombre, username, rol, activo, fecha_creacion, tenant_id, sucursal_id
            FROM usuarios
            WHERE id = ? AND tenant_id = ?
            LIMIT 1;
        """, (empleado_id, tenant_id))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["activo"] = bool(d["activo"])
        return d
    finally:
        conn.close()


def create_empleado(
    nombre: str,
    username: str,
    password: str,
    rol: str,
    tenant_id: int,
    sucursal_id: Optional[int]
) -> Dict[str, Any]:
    """
    Registra un nuevo empleado con rol 'vendedor' o 'tecnico', validando duplicidad de username,
    hasheando con Argon2id y vinculándolo al tenant y sucursal de la sesión del dueño.
    """
    from app.security import hash_secret

    clean_username = username.strip().lower()
    clean_nombre = nombre.strip()
    clean_rol = rol.strip().lower()

    if clean_rol not in ('vendedor', 'tecnico'):
        raise ValueError("El rol asignado debe ser 'vendedor' o 'tecnico'.")

    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        _begin_immediate(cursor)

        # Validación de username único en el sistema
        cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = ? LIMIT 1;", (clean_username,))
        if cursor.fetchone():
            raise ValueError(f"El nombre de usuario '{clean_username}' ya se encuentra en uso.")

        # Hashing criptográfico Argon2id
        pin_hash, salt = hash_secret(password)

        cursor.execute("""
            INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (clean_nombre, clean_username, pin_hash, salt, clean_rol, True, now, tenant_id, sucursal_id))

        new_id = cursor.lastrowid
        if not new_id:
            cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = ? LIMIT 1;", (clean_username,))
            r = cursor.fetchone()
            new_id = r["id"] if r else None

        conn.commit()

        return {
            "id": new_id,
            "nombre": clean_nombre,
            "username": clean_username,
            "rol": clean_rol,
            "activo": True,
            "fecha_creacion": now,
            "tenant_id": tenant_id,
            "sucursal_id": sucursal_id,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_empleado_estado(empleado_id: int, activo: bool, tenant_id: int) -> Optional[Dict[str, Any]]:
    """
    Activa o desactiva (suspende) un empleado perteneciente al tenant_id sin eliminar su historial.
    """
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    try:
        _begin_immediate(cursor)

        cursor.execute("""
            SELECT id, nombre, username, rol, activo, fecha_creacion, tenant_id, sucursal_id
            FROM usuarios
            WHERE id = ? AND tenant_id = ?
            LIMIT 1;
        """, (empleado_id, tenant_id))
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute("""
            UPDATE usuarios
            SET activo = ?
            WHERE id = ? AND tenant_id = ?;
        """, (bool(activo), empleado_id, tenant_id))

        conn.commit()

        d = dict(row)
        d["activo"] = bool(activo)
        return d
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ==============================================================================
# GASTOS OPERATIVOS Y CONTROL DE GANANCIA NETA REAL
# ==============================================================================

def crear_gasto(
    datos: Dict[str, Any],
    usuario_nombre: str = "Admin",
    tenant_id: Optional[int] = None,
    sucursal_id: Optional[int] = None
) -> Dict[str, Any]:
    """Registra un nuevo gasto operativo con aislamiento multi-tenant."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    if tenant_id is None:
        def_t, def_s = _get_default_tenant_and_sucursal()
        final_tenant_id = def_t
        final_sucursal_id = def_s
    else:
        final_tenant_id = tenant_id
        final_sucursal_id = sucursal_id

    # Validar FKs existentes para evitar IntegrityError en PostgreSQL
    if final_tenant_id:
        try:
            cursor.execute("SELECT id FROM tenants WHERE id = ? LIMIT 1;", (final_tenant_id,))
            if not cursor.fetchone():
                final_tenant_id = None
        except Exception:
            final_tenant_id = None

    if final_sucursal_id:
        try:
            cursor.execute("SELECT id FROM sucursales WHERE id = ? LIMIT 1;", (final_sucursal_id,))
            if not cursor.fetchone():
                final_sucursal_id = None
        except Exception:
            final_sucursal_id = None

    fecha_final = datos.get("fecha") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        _begin_immediate(cursor)
        cursor.execute("""
            INSERT INTO gastos (
                concepto, categoria, monto, fecha, metodo_pago,
                comprobante_url, usuario, notas, tenant_id, sucursal_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datos["concepto"].strip(),
            datos.get("categoria", "General").strip(),
            float(datos["monto"]),
            fecha_final,
            datos.get("metodo_pago", "Efectivo").strip(),
            datos.get("comprobante_url"),
            usuario_nombre,
            datos.get("notas", "").strip() if datos.get("notas") else None,
            final_tenant_id,
            final_sucursal_id
        ))
        conn.commit()
        gasto_id = cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    res = get_gasto_by_id(gasto_id, tenant_id=final_tenant_id)
    if not res:
        res = {
            "id": gasto_id or 1,
            "concepto": datos["concepto"].strip(),
            "categoria": datos.get("categoria", "General").strip(),
            "monto": float(datos["monto"]),
            "fecha": str(fecha_final),
            "metodo_pago": datos.get("metodo_pago", "Efectivo").strip(),
            "comprobante_url": datos.get("comprobante_url"),
            "usuario": usuario_nombre,
            "notas": datos.get("notas", "").strip() if datos.get("notas") else None,
            "tenant_id": final_tenant_id,
            "sucursal_id": final_sucursal_id
        }
    return res


def get_gasto_by_id(gasto_id: int, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Obtiene un gasto por su ID verificando tenant_id."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    if tenant_id is not None:
        cursor.execute("SELECT * FROM gastos WHERE id = ? AND tenant_id = ?", (gasto_id, tenant_id))
    else:
        cursor.execute("SELECT * FROM gastos WHERE id = ?", (gasto_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_gastos(
    tenant_id: Optional[int] = None,
    mes: Optional[str] = None,
    categoria: Optional[str] = None,
    sucursal_id: Optional[int] = None,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """Obtiene la lista de gastos operativos con filtros opcionales por mes y categoría."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    query = "SELECT * FROM gastos WHERE 1=1"
    params: List[Any] = []

    if tenant_id is not None:
        query += " AND tenant_id = ?"
        params.append(tenant_id)

    if sucursal_id is not None:
        query += " AND sucursal_id = ?"
        params.append(sucursal_id)

    if mes:
        query += " AND strftime('%Y-%m', fecha) = ?"
        params.append(mes.strip())

    if categoria and categoria != "Todas" and categoria != "Todos":
        query += " AND categoria = ?"
        params.append(categoria.strip())

    query += " ORDER BY fecha DESC, id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def eliminar_gasto(gasto_id: int, tenant_id: Optional[int] = None) -> bool:
    """Elimina un gasto operativo."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()
    try:
        _begin_immediate(cursor)
        if tenant_id is not None:
            cursor.execute("DELETE FROM gastos WHERE id = ? AND tenant_id = ?", (gasto_id, tenant_id))
        else:
            cursor.execute("DELETE FROM gastos WHERE id = ?", (gasto_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_resumen_gastos(
    tenant_id: Optional[int] = None,
    mes: Optional[str] = None
) -> Dict[str, Any]:
    """Calcula totales y desglose por categoría de gastos para un mes específico."""
    conn = get_db_connection(tenant_id=tenant_id)
    cursor = conn.cursor()

    mes_target = mes or datetime.now().strftime("%Y-%m")

    query = """
        SELECT categoria, COALESCE(SUM(monto), 0) as total, COUNT(id) as cantidad
        FROM gastos
        WHERE strftime('%Y-%m', fecha) = ?
    """
    params = [mes_target]
    if tenant_id is not None:
        query += " AND tenant_id = ?"
        params.append(tenant_id)
    query += " GROUP BY categoria ORDER BY total DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    desglose = {r["categoria"]: round(float(r["total"]), 2) for r in rows}
    total_mes = round(sum(desglose.values()), 2)
    conn.close()

    return {
        "mes": mes_target,
        "total_mes": total_mes,
        "desglose_por_categoria": desglose
    }

