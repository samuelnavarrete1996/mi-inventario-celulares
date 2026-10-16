import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.database import get_db_connection
from app.models import EquipoCreate, EquipoUpdate, ItemCarrito, GarantiaCreate

def format_equipo_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convierte un row de equipo a dict y añade cálculos de margen proyectado."""
    d = dict(row)
    costo = d.get("costo_compra", 0.0)
    precio = d.get("precio_venta", 0.0)
    margen = round(precio - costo, 2)
    porcentaje = round((margen / costo * 100), 1) if costo > 0 else 0.0
    d["margen_proyectado"] = margen
    d["porcentaje_margen"] = porcentaje
    return d

def get_equipos(solo_disponibles: bool = True, search: Optional[str] = None, grado: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene equipos con filtros opcionales."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM equipos WHERE 1=1"
    params = []

    if solo_disponibles:
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

def get_equipo_by_id(equipo_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM equipos WHERE id = ?", (equipo_id,))
    row = cursor.fetchone()
    conn.close()
    return format_equipo_dict(row) if row else None

def get_equipo_by_imei(imei: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM equipos WHERE imei = ?", (imei.strip(),))
    row = cursor.fetchone()
    conn.close()
    return format_equipo_dict(row) if row else None

def create_equipo(data: EquipoCreate) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM equipos WHERE imei = ?", (data.imei.strip(),))
    if cursor.fetchone():
        conn.close()
        raise ValueError(f"Ya existe un equipo registrado con el IMEI {data.imei}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO equipos (modelo, capacidad_gb, color, imei, grado, costo_compra, precio_venta, estado, fecha_registro)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'Disponible', ?)
    """, (
        data.modelo.strip(),
        data.capacidad_gb,
        data.color.strip(),
        data.imei.strip(),
        data.grado.upper(),
        round(data.costo_compra, 2),
        round(data.precio_venta, 2),
        now
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return get_equipo_by_id(new_id)

def update_equipo(equipo_id: int, data: EquipoUpdate) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()

    current = get_equipo_by_id(equipo_id)
    if not current:
        conn.close()
        return None

    fields = []
    values = []
    for field, val in data.model_dump(exclude_unset=True).items():
        if val is not None:
            fields.append(f"{field} = ?")
            values.append(val)

    if not fields:
        conn.close()
        return current

    values.append(equipo_id)
    sql = f"UPDATE equipos SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(sql, values)
    conn.commit()
    conn.close()

    return get_equipo_by_id(equipo_id)

def delete_equipo(equipo_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM venta_items WHERE equipo_id = ?", (equipo_id,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("No se puede eliminar un equipo que ya cuenta con un registro de venta histórico.")

    cursor.execute("DELETE FROM equipos WHERE id = ?", (equipo_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

# --- CLIENTES ---

def get_or_create_cliente(nombre: str, telefono: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()

    clean_tel = telefono.strip()
    cursor.execute("SELECT id FROM clientes WHERE telefono = ?", (clean_tel,))
    row = cursor.fetchone()

    if row:
        cliente_id = row["id"]
        cursor.execute("UPDATE clientes SET nombre = ? WHERE id = ?", (nombre.strip(), cliente_id))
        conn.commit()
        conn.close()
        return cliente_id
    else:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        INSERT INTO clientes (nombre, telefono, fecha_registro)
        VALUES (?, ?, ?)
        """, (nombre.strip(), clean_tel, now))
        conn.commit()
        cliente_id = cursor.lastrowid
        conn.close()
        return cliente_id

def get_cliente_by_phone(telefono: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
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
    notas: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registra una venta con múltiples equipos y métodos de pago:
    Efectivo, Transferencia, Combinado o Equipo Garantía.
    """
    if not items or len(items) == 0:
        raise ValueError("El carrito de compras no contiene equipos.")

    item_ids = [it.equipo_id for it in items]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("El carrito contiene equipos duplicados. Cada teléfono debe registrarse una sola vez.")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN TRANSACTION;")

        # 1. Validar disponibilidad
        equipos_db = {}
        for item in items:
            cursor.execute("SELECT * FROM equipos WHERE id = ?", (item.equipo_id,))
            eq = cursor.fetchone()
            if not eq:
                raise ValueError(f"El equipo con ID {item.equipo_id} no existe.")
            if eq["estado"] != "Disponible":
                raise ValueError(f"El equipo '{eq['modelo']}' (IMEI: {eq['imei']}) ya no está disponible (Estado actual: {eq['estado']}).")
            equipos_db[item.equipo_id] = eq

        # 2. Cliente
        clean_tel = cliente_telefono.strip()
        cursor.execute("SELECT id FROM clientes WHERE telefono = ?", (clean_tel,))
        cliente_row = cursor.fetchone()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if cliente_row:
            cliente_id = cliente_row["id"]
            cursor.execute("UPDATE clientes SET nombre = ? WHERE id = ?", (cliente_nombre.strip(), cliente_id))
        else:
            cursor.execute("""
            INSERT INTO clientes (nombre, telefono, fecha_registro)
            VALUES (?, ?, ?)
            """, (cliente_nombre.strip(), clean_tel, now))
            cliente_id = cursor.lastrowid

        # 3. Totales y Márgenes
        total_precio_final = 0.0
        total_margen_ganancia = 0.0
        detalles_items = []

        for item in items:
            eq = equipos_db[item.equipo_id]
            costo = float(eq["costo_compra"])
            precio_item = round(float(item.precio_final), 2)
            margen_item = round(precio_item - costo, 2)

            total_precio_final += precio_item
            total_margen_ganancia += margen_item

            detalles_items.append({
                "equipo_id": item.equipo_id,
                "precio_final": precio_item,
                "costo_compra": costo,
                "margen_ganancia": margen_item
            })

        total_precio_final = round(total_precio_final, 2)
        total_margen_ganancia = round(total_margen_ganancia, 2)

        # 4. Validar método de pago (Efectivo, Transferencia, Combinado, Equipo Garantía)
        metodo = metodo_pago.strip()
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

        # 5. Insertar Cabecera de Venta
        primer_equipo_id = items[0].equipo_id
        cursor.execute("""
        INSERT INTO ventas (
            equipo_id, cliente_id, precio_final, margen_ganancia, fecha_venta,
            metodo_pago, monto_efectivo, monto_transferencia, monto_tarjeta, monto_garantia, notas
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            primer_equipo_id, cliente_id, total_precio_final, total_margen_ganancia, now,
            metodo, m_efectivo, m_transf, m_tarjeta, m_garantia, notas
        ))
        venta_id = cursor.lastrowid

        # 6. Insertar items y actualizar estado
        for det in detalles_items:
            cursor.execute("""
            INSERT INTO venta_items (venta_id, equipo_id, precio_final, costo_compra, margen_ganancia)
            VALUES (?, ?, ?, ?, ?)
            """, (venta_id, det["equipo_id"], det["precio_final"], det["costo_compra"], det["margen_ganancia"]))

            cursor.execute("UPDATE equipos SET estado = 'Vendido' WHERE id = ?", (det["equipo_id"],))

        conn.commit()
        return get_venta_detalle(venta_id, conn)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_venta_detalle(venta_id: int, conn_ext: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    conn = conn_ext if conn_ext else get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
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
        c.nombre as cliente_nombre,
        c.telefono as cliente_telefono
    FROM ventas v
    JOIN clientes c ON v.cliente_id = c.id
    WHERE v.id = ?
    """, (venta_id,))
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
        vi.precio_final,
        vi.costo_compra,
        vi.margen_ganancia,
        e.modelo,
        e.capacidad_gb,
        e.color,
        e.imei,
        e.grado
    FROM venta_items vi
    JOIN equipos e ON vi.equipo_id = e.id
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

    modelos_nombres = [f"{it['modelo']} ({it['capacidad_gb']}GB)" for it in items]
    venta_dict["resumen_modelos"] = ", ".join(modelos_nombres) if modelos_nombres else "Sin equipos"

    if items:
        p = items[0]
        venta_dict["modelo"] = p["modelo"]
        venta_dict["capacidad_gb"] = p["capacidad_gb"]
        venta_dict["color"] = p["color"]
        venta_dict["imei"] = p["imei"]
        venta_dict["grado"] = p["grado"]
        venta_dict["costo_compra"] = p["costo_compra"]

    if not conn_ext:
        conn.close()

    return venta_dict

def get_historial_ventas(limit: int = 200, fecha_inicio: Optional[str] = None, fecha_fin: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
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
        c.nombre as cliente_nombre,
        c.telefono as cliente_telefono
    FROM ventas v
    JOIN clientes c ON v.cliente_id = c.id
    WHERE 1=1
    """
    params = []

    if fecha_inicio:
        query += " AND date(v.fecha_venta) >= date(?)"
        params.append(fecha_inicio)

    if fecha_fin:
        query += " AND date(v.fecha_venta) <= date(?)"
        params.append(fecha_fin)

    query += " ORDER BY v.id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    ventas_rows = cursor.fetchall()

    resultado = []
    for vr in ventas_rows:
        v_dict = dict(vr)
        v_id = v_dict["id"]

        cursor.execute("""
        SELECT 
            vi.id,
            vi.venta_id,
            vi.equipo_id,
            vi.precio_final,
            vi.costo_compra,
            vi.margen_ganancia,
            e.modelo,
            e.capacidad_gb,
            e.color,
            e.imei,
            e.grado
        FROM venta_items vi
        JOIN equipos e ON vi.equipo_id = e.id
        WHERE vi.venta_id = ?
        """, (v_id,))
        items = [dict(r) for r in cursor.fetchall()]

        v_dict["items"] = items
        v_dict["total_equipos"] = len(items)
        modelos_nombres = [f"{it['modelo']}" for it in items]
        v_dict["resumen_modelos"] = ", ".join(modelos_nombres) if modelos_nombres else "Equipo"

        if items:
            v_dict["modelo"] = items[0]["modelo"]
            v_dict["capacidad_gb"] = items[0]["capacidad_gb"]
            v_dict["color"] = items[0]["color"]
            v_dict["imei"] = items[0]["imei"]
            v_dict["grado"] = items[0]["grado"]
            v_dict["costo_compra"] = items[0]["costo_compra"]

        resultado.append(v_dict)

    conn.close()
    return resultado

# --- MÓDULO DE DEVOLUCIÓN Y GESTIÓN DE GARANTÍAS ---

DIAS_GARANTIA_POR_GRADO = {
    "A": 90,
    "B": 30,
    "C": 15
}

def buscar_equipo_para_garantia(imei: str) -> Dict[str, Any]:
    """Busca un equipo vendido por IMEI para verificar si está dentro de su periodo de garantía."""
    conn = get_db_connection()
    cursor = conn.cursor()

    clean_imei = imei.strip()
    cursor.execute("SELECT * FROM equipos WHERE imei = ?", (clean_imei,))
    equipo = cursor.fetchone()

    if not equipo:
        conn.close()
        raise ValueError(f"No existe ningún equipo registrado con el IMEI '{clean_imei}'.")

    eq_dict = dict(equipo)
    eq_id = eq_dict["id"]

    # Buscar la venta más reciente donde se vendió este equipo
    cursor.execute("""
    SELECT 
        v.id as venta_id,
        v.fecha_venta,
        v.cliente_id,
        vi.precio_final,
        c.nombre as cliente_nombre,
        c.telefono as cliente_telefono
    FROM venta_items vi
    JOIN ventas v ON vi.venta_id = v.id
    JOIN clientes c ON v.cliente_id = c.id
    WHERE vi.equipo_id = ?
    ORDER BY v.id DESC LIMIT 1
    """, (eq_id,))
    venta = cursor.fetchone()

    if not venta:
        # Si fue vendido en formato anterior directo
        cursor.execute("""
        SELECT 
            v.id as venta_id,
            v.fecha_venta,
            v.cliente_id,
            v.precio_final,
            c.nombre as cliente_nombre,
            c.telefono as cliente_telefono
        FROM ventas v
        JOIN clientes c ON v.cliente_id = c.id
        WHERE v.equipo_id = ?
        ORDER BY v.id DESC LIMIT 1
        """, (eq_id,))
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

def procesar_devolucion_garantia(data: GarantiaCreate) -> Dict[str, Any]:
    """Registra formalmente el regreso de un equipo por garantía y actualiza su estado."""
    info = buscar_equipo_para_garantia(data.imei)
    eq = info["equipo"]
    venta = info["venta"]

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN TRANSACTION;")

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

        # 2. Actualizar estado del equipo devuelto
        # Puede quedar 'En Garantia' (para revisión), 'Disponible' (reingresado a inventario) o 'Baja por Garantia'
        cursor.execute("UPDATE equipos SET estado = ? WHERE id = ?", (data.estado_equipo_recibido, eq["id"]))

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

def get_historial_garantias(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
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
    ORDER BY g.id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(r) for r in rows]

# --- REPORTES Y DASHBOARD ---

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

def get_dashboard_metrics() -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()

    ahora = datetime.now()
    mes_actual_str = ahora.strftime("%Y-%m")
    nombre_mes = f"{MESES_ES[ahora.month - 1]} {ahora.year}"

    # 1. Ventas y ganancias del mes actual
    cursor.execute("""
    SELECT 
        COALESCE(SUM(v.margen_ganancia), 0) as total_ganancias,
        COALESCE(SUM(v.precio_final), 0) as total_ventas
    FROM ventas v
    WHERE strftime('%Y-%m', v.fecha_venta) = ?
    """, (mes_actual_str,))
    stats_mes = cursor.fetchone()

    cursor.execute("""
    SELECT COUNT(vi.id) as total_equipos
    FROM venta_items vi
    JOIN ventas v ON vi.venta_id = v.id
    WHERE strftime('%Y-%m', v.fecha_venta) = ?
    """, (mes_actual_str,))
    eq_vendidos = cursor.fetchone()["total_equipos"]

    total_ganancias = round(stats_mes["total_ganancias"], 2)
    total_ventas = round(stats_mes["total_ventas"], 2)
    margen_promedio = round((total_ganancias / total_ventas * 100), 1) if total_ventas > 0 else 0.0

    # 2. Métricas de inventario activo y equipos en garantía
    cursor.execute("""
    SELECT 
        COUNT(id) as disponibles,
        COALESCE(SUM(costo_compra), 0) as capital_invertido,
        COALESCE(SUM(precio_venta), 0) as valor_venta
    FROM equipos
    WHERE estado = 'Disponible'
    """)
    stats_inv = cursor.fetchone()

    cursor.execute("SELECT COUNT(id) as en_garantia FROM equipos WHERE estado = 'En Garantia'")
    equipos_en_garantia = cursor.fetchone()["en_garantia"]

    # 3. Ventas de los últimos 30 días para gráfico
    cursor.execute("""
    SELECT 
        date(v.fecha_venta) as dia,
        COUNT(vi.id) as unidades,
        COALESCE(SUM(v.margen_ganancia), 0) as ganancias,
        COALESCE(SUM(v.precio_final), 0) as ventas
    FROM ventas v
    LEFT JOIN venta_items vi ON v.id = vi.venta_id
    WHERE date(v.fecha_venta) >= date('now', '-30 days', 'localtime')
    GROUP BY date(v.fecha_venta)
    ORDER BY dia ASC
    """)
    ventas_dias = [dict(r) for r in cursor.fetchall()]

    # 4. Distribución por Grados
    cursor.execute("""
    SELECT grado, COUNT(id) as total
    FROM equipos
    WHERE estado = 'Disponible'
    GROUP BY grado
    """)
    grados_inv = {r["grado"]: r["total"] for r in cursor.fetchall()}

    # 5. Desglose de ingresos por método de pago en el mes actual
    cursor.execute("""
    SELECT 
        COALESCE(SUM(monto_efectivo), 0) as total_efectivo,
        COALESCE(SUM(monto_transferencia), 0) as total_transferencia,
        COALESCE(SUM(monto_garantia), 0) as total_garantia
    FROM ventas
    WHERE strftime('%Y-%m', fecha_venta) = ?
    """, (mes_actual_str,))
    p_row = cursor.fetchone()

    desglose_pagos = {
        "Efectivo": round(p_row["total_efectivo"], 2),
        "Transferencia": round(p_row["total_transferencia"], 2),
        "Equipo Garantía": round(p_row["total_garantia"], 2)
    }

    conn.close()

    return {
        "total_ganancias_mes": total_ganancias,
        "total_ventas_mes": total_ventas,
        "equipos_vendidos_mes": eq_vendidos,
        "margen_promedio_mes": margen_promedio,
        "equipos_disponibles": stats_inv["disponibles"],
        "equipos_en_garantia": equipos_en_garantia,
        "capital_inventario": round(stats_inv["capital_invertido"], 2),
        "valor_venta_inventario": round(stats_inv["valor_venta"], 2),
        "mes_actual_nombre": nombre_mes,
        "ventas_por_dia": ventas_dias,
        "distribucion_grados": grados_inv,
        "desglose_metodos_pago": desglose_pagos
    }
