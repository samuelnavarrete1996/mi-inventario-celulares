import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
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

    try:
        _begin_immediate(cursor)
        cursor.execute("SELECT id FROM equipos WHERE imei = ?", (data.imei.strip(),))
        if cursor.fetchone():
            conn.rollback()
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
    except Exception:
        conn.rollback()
        raise
    finally:
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
        if val is not None and field in COLUMNAS_PERMITIDAS_EQUIPO:
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
    Registra una venta con múltiples equipos o accesorios/servicios y métodos de pago:
    Efectivo, Transferencia, Combinado o Equipo Garantía.
    Protegido con transacción inmediata y actualización atómica Compare-And-Swap contra condiciones de carrera.
    """
    if not items or len(items) == 0:
        raise ValueError("El carrito de compras no contiene artículos.")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _begin_immediate(cursor)

        # 1. Validar equipos y accesorios
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

                cursor.execute("SELECT * FROM equipos WHERE id = ?", (item.equipo_id,))
                eq = cursor.fetchone()
                if not eq:
                    raise ValueError(f"El equipo con ID {item.equipo_id} no existe.")
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
                cursor.execute("SELECT * FROM accesorios WHERE id = ?", (item.accesorio_id,))
                acc = cursor.fetchone()
                if not acc:
                    raise ValueError(f"El accesorio/servicio con ID {item.accesorio_id} no existe.")
                
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

                detalles_items.append({
                    "tipo_item": "servicio" if acc["es_servicio"] else "accesorio",
                    "equipo_id": None,
                    "accesorio_id": item.accesorio_id,
                    "nombre_item": acc["nombre"],
                    "cantidad": cant,
                    "precio_final": precio_item,
                    "costo_compra": costo_total,
                    "margen_ganancia": margen_item,
                    "es_servicio": bool(acc["es_servicio"])
                })
            else:
                raise ValueError("Cada línea del carrito debe especificar un equipo o un accesorio.")

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

        total_precio_final = round(total_precio_final, 2)
        total_margen_ganancia = round(total_margen_ganancia, 2)

        # 3. Validar método de pago
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

        # 4. Insertar Cabecera de Venta
        primer_equipo_id = equipos_ids_usados[0] if equipos_ids_usados else None
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

        # 5. Insertar items y actualizar estado/stock de forma atómica (Compare-And-Swap)
        for det in detalles_items:
            if det["equipo_id"]:
                cursor.execute(
                    "UPDATE equipos SET estado = 'Vendido' WHERE id = ? AND estado = 'Disponible'",
                    (det["equipo_id"],)
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"El equipo '{det['nombre_item']}' ya fue vendido en una operación simultánea.")
            elif det["accesorio_id"] and not det.get("es_servicio", False):
                cursor.execute(
                    "UPDATE accesorios SET stock = stock - ? WHERE id = ? AND stock >= ?",
                    (det["cantidad"], det["accesorio_id"], det["cantidad"])
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"Stock insuficiente para '{det['nombre_item']}' debido a una venta simultánea.")

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
    """Registra formalmente el regreso de un equipo por garantía y actualiza su estado de forma atómica."""
    info = buscar_equipo_para_garantia(data.imei)
    eq = info["equipo"]
    venta = info["venta"]

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        _begin_immediate(cursor)

        if data.equipo_reemplazo_id is not None:
            cursor.execute("SELECT id FROM equipos WHERE id = ?", (data.equipo_reemplazo_id,))
            if not cursor.fetchone():
                raise ValueError(f"El equipo de reemplazo con ID {data.equipo_reemplazo_id} no existe.")

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
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM accesorios WHERE 1=1"
    params = []

    if categoria and categoria != "Todos":
        cat_clean = categoria.rstrip('s').rstrip('es')
        query += " AND (categoria = ? OR categoria LIKE ?)"
        params.extend([categoria, f"{cat_clean}%"])

    if solo_con_stock:
        query += " AND (stock > 0 OR es_servicio = 1)"

    if search:
        s = f"%{search.strip()}%"
        query += " AND (nombre LIKE ? OR categoria LIKE ? OR codigo_barras LIKE ?)"
        params.extend([s, s, s])

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [format_accesorio_dict(r) for r in rows]

def get_accesorio_by_id(acc_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
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
    imagen_url: Optional[str] = None
) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO accesorios (nombre, categoria, codigo_barras, costo_compra, precio_venta, precio_mayoreo, precio_20_pzs, precio_caja, imagen_url, stock, es_servicio, fecha_registro)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        stock if not es_servicio else 999,
        1 if es_servicio else 0,
        now
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return get_accesorio_by_id(new_id)

COLUMNAS_PERMITIDAS_ACCESORIO = (
    "nombre", "categoria", "codigo_barras", "costo_compra", "precio_venta",
    "precio_mayoreo", "precio_20_pzs", "precio_caja", "imagen_url", "stock", "es_servicio"
)

def update_accesorio(acc_id: int, datos: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    current = get_accesorio_by_id(acc_id)
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
        cursor.execute(f"UPDATE accesorios SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    conn.close()
    return get_accesorio_by_id(acc_id)

def delete_accesorio(acc_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM accesorios WHERE id = ?", (acc_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

# ==============================================================================
# CORTES DE CAJA DIARIOS (ARQUEO / REPORTE Z)
# ==============================================================================

def obtener_resumen_corte_actual(conn_ext: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Calcula el balance acumulado de ventas desde el último corte de caja registrado (o del día de hoy)."""
    conn = conn_ext if conn_ext else get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT fecha_corte FROM cortes_caja ORDER BY id DESC LIMIT 1")
    ultimo_corte = cursor.fetchone()

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    if ultimo_corte and ultimo_corte["fecha_corte"]:
        fecha_inicio = ultimo_corte["fecha_corte"]
    else:
        # Inicio del día actual a las 00:00:00
        fecha_inicio = now.strftime("%Y-%m-%d 00:00:00")

    cursor.execute("""
    SELECT 
        COUNT(id) as total_operaciones,
        COALESCE(SUM(precio_final), 0) as total_ventas,
        COALESCE(SUM(monto_efectivo), 0) as total_efectivo,
        COALESCE(SUM(monto_transferencia), 0) as total_transferencia,
        COALESCE(SUM(monto_garantia), 0) as total_garantia
    FROM ventas
    WHERE fecha_venta >= ? AND fecha_venta <= ?
    """, (fecha_inicio, now_str))
    r = cursor.fetchone()

    cursor.execute("""
    SELECT v.id, v.fecha_venta, v.precio_final, v.metodo_pago, v.monto_efectivo, v.monto_transferencia, v.monto_garantia, c.nombre as cliente_nombre
    FROM ventas v
    JOIN clientes c ON v.cliente_id = c.id
    WHERE v.fecha_venta >= ? AND v.fecha_venta <= ?
    ORDER BY v.id DESC
    """, (fecha_inicio, now_str))
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

def guardar_corte_caja(efectivo_declarado: float, notas: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        _begin_immediate(cursor)
        resumen = obtener_resumen_corte_actual(conn_ext=conn)
        total_efectivo_sistema = resumen["total_efectivo"]
        efectivo_declarado = round(float(efectivo_declarado), 2)
        diferencia = round(efectivo_declarado - total_efectivo_sistema, 2)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO cortes_caja (
            fecha_corte, fecha_inicio_periodo, total_ventas, total_efectivo, total_transferencia,
            total_garantia, efectivo_declarado, diferencia, cantidad_ventas, notas, fecha_registro
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            now_str
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
    return resumen

def get_cortes_caja(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cortes_caja ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# ==============================================================================
# HISTORIAL UNIVERSAL POR IMEI (TRAZABILIDAD 360°)
# ==============================================================================

def obtener_historial_imei(imei: str) -> Dict[str, Any]:
    clean_imei = imei.strip().replace(" ", "").replace("-", "")
    conn = get_db_connection()
    cursor = conn.cursor()

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
    "equipos", "clientes", "ventas", "venta_items",
    "garantias", "accesorios", "cortes_caja", "reparaciones"
)

def exportar_todo_json() -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    resultado = {
        "version": "2.0",
        "app": "Mi Inventario Samuel Navarrete",
        "fecha_exportacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "datos": {}
    }
    for t in TABLAS_PERMITIDAS_EXPORTACION:
        try:
            cursor.execute(f"SELECT * FROM {t}")
            resultado["datos"][t] = [dict(r) for r in cursor.fetchall()]
        except Exception:
            resultado["datos"][t] = []
    conn.close()
    return resultado


# ==============================================================================
# MÓDULO DE REPARACIONES Y TALLER TÉCNICO
# ==============================================================================

def generar_siguiente_folio_reparacion(cursor) -> str:
    cursor.execute("SELECT COALESCE(MAX(id), 0) as max_id FROM reparaciones")
    row = cursor.fetchone()
    next_id = (int(row["max_id"]) + 1) if row else 1
    return f"REP-{next_id:04d}"

def get_reparaciones(estado: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM reparaciones WHERE 1=1"
    params = []

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

def get_reparacion_by_id(rep_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reparaciones WHERE id = ?", (rep_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    res = dict(row)
    res["margen_ganancia"] = round(res["precio_servicio"] - res["costo_refaccion"], 2)
    return res

def create_reparacion(datos: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        _begin_immediate(cursor)
        folio = generar_siguiente_folio_reparacion(cursor)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        precio = float(datos.get("precio_servicio", 0))
        anticipo = float(datos.get("anticipo", 0))
        saldo = round(max(0.0, precio - anticipo), 2)

        cursor.execute("""
        INSERT INTO reparaciones (
            folio, cliente_nombre, cliente_telefono, dispositivo_modelo, color,
            imei_serie, codigo_patron, falla_reportada, diagnostico_tecnico,
            condicion_recepcion, costo_refaccion, precio_servicio, anticipo,
            saldo_pendiente, estado, fecha_ingreso, fecha_prometida,
            tecnico_responsable, notas
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Recibido', ?, ?, ?, ?)
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
            float(datos.get("costo_refaccion", 0)),
            precio,
            anticipo,
            saldo,
            now_str,
            datos.get("fecha_prometida") or None,
            datos.get("tecnico_responsable", "Samuel N."),
            datos.get("notas", "").strip() if datos.get("notas") else None
        ))
        conn.commit()
        new_id = cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_reparacion_by_id(new_id)

COLUMNAS_PERMITIDAS_REPARACION = {
    "cliente_nombre", "cliente_telefono", "dispositivo_modelo", "color",
    "imei_serie", "codigo_patron", "falla_reportada", "diagnostico_tecnico",
    "condicion_recepcion", "costo_refaccion", "precio_servicio", "anticipo",
    "saldo_pendiente", "estado", "fecha_ingreso", "fecha_prometida",
    "fecha_entrega", "tecnico_responsable", "notas"
}

def update_reparacion(rep_id: int, datos: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reparaciones WHERE id = ?", (rep_id,))
    existing = cursor.fetchone()
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
        cursor.execute(f"UPDATE reparaciones SET {', '.join(campos)} WHERE id = ?", valores)
        conn.commit()

    conn.close()
    return get_reparacion_by_id(rep_id)

def cambiar_estado_reparacion(rep_id: int, nuevo_estado: str) -> Optional[Dict[str, Any]]:
    estados_validos = ('Recibido', 'En Revision', 'Esperando Refaccion', 'Listo para Entrega', 'Entregado', 'Cancelado')
    if nuevo_estado not in estados_validos:
        raise ValueError(f"Estado inválido: {nuevo_estado}. Válidos: {', '.join(estados_validos)}")
    
    update_data = {"estado": nuevo_estado}
    if nuevo_estado == "Entregado":
        update_data["fecha_entrega"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        update_data["saldo_pendiente"] = 0.0

    return update_reparacion(rep_id, update_data)

def abonar_reparacion(rep_id: int, monto_abono: float) -> Optional[Dict[str, Any]]:
    if monto_abono <= 0:
        raise ValueError("El monto del abono debe ser mayor a cero.")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        _begin_immediate(cursor)
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

    return get_reparacion_by_id(rep_id)

def delete_reparacion(rep_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reparaciones WHERE id = ?", (rep_id,))
    conn.commit()
    filas = cursor.rowcount
    conn.close()
    return filas > 0
