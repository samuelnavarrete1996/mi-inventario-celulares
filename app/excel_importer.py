import io
import re
import csv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from typing import List, Dict, Any, Tuple, Optional
from app import crud
from app.models import EquipoCreate

def clean_imei_val(val: Any) -> str:
    """Convierte de forma segura cualquier formato de IMEI (incluso notación científica de Excel) a string exacto."""
    if val is None:
        return ""
    if isinstance(val, float):
        # Evitar notación científica ej. 3.56789123456781e+14 -> 356789123456781
        val_str = f"{val:.0f}"
    else:
        val_str = str(val).strip()

    # Si viene con notación científica en texto ej: '3.56789E+14'
    if 'e+' in val_str.lower():
        try:
            val_str = f"{float(val_str):.0f}"
        except Exception:
            pass

    return val_str.replace(" ", "").replace("-", "").replace(".0", "")

def extraer_capacidad_de_modelo(modelo: str) -> int:
    """Intenta deducir la capacidad en GB si no está en una columna separada."""
    match = re.search(r'(\d+)\s*(?:gb|g\b|tb)', modelo.lower())
    if match:
        num = int(match.group(1))
        if num == 1: # 1 TB
            return 1024
        return num
    return 128

def normalizar_grado(grado_val: Any) -> str:
    g = str(grado_val or '').strip().upper()
    if g.startswith('A') or 'EXCELENTE' in g:
        return 'A'
    elif g.startswith('B') or 'REGULAR' in g or 'BUENO' in g:
        return 'B'
    elif g.startswith('C') or 'MALTRATADO' in g or 'DETALLES' in g:
        return 'C'
    return 'A' # Por defecto Grado A

def mapear_fila_a_equipo(row_dict: Dict[str, Any], fila_num: int) -> Tuple[Optional[EquipoCreate], Optional[str]]:
    """Convierte un diccionario de fila de Excel a un objeto EquipoCreate validado."""
    # Normalizar llaves
    norm = {}
    for k, v in row_dict.items():
        if k is not None:
            clean_k = str(k).strip().lower().replace(" ", "").replace("_", "").replace("-", "")
            norm[clean_k] = v

    # Buscar Modelo
    modelo = norm.get('modelo') or norm.get('nombre') or norm.get('equipo') or norm.get('telefono') or norm.get('dispositivo')
    if not modelo or not str(modelo).strip():
        return None, f"Fila {fila_num}: Falta el 'Modelo' del teléfono."

    modelo_str = str(modelo).strip()

    # Buscar Color
    color = norm.get('color') or norm.get('tono') or 'Negro'
    color_str = str(color).strip()

    # Buscar IMEI
    imei_raw = norm.get('imei') or norm.get('serie') or norm.get('serial') or norm.get('numeroserie') or norm.get('sn')
    imei_str = clean_imei_val(imei_raw)
    if not imei_str or len(imei_str) < 8:
        return None, f"Fila {fila_num}: IMEI inválido o ausente ({imei_raw})."

    # Buscar Grado
    grado_raw = norm.get('grado') or norm.get('condicion') or norm.get('calidad') or norm.get('estado')
    grado_str = normalizar_grado(grado_raw)

    # Buscar Costo
    costo_raw = norm.get('costo') or norm.get('costocompra') or norm.get('preciocompra') or norm.get('compra')
    try:
        costo_float = float(str(costo_raw).replace("$", "").replace(",", "").strip())
        if costo_float <= 0:
            raise ValueError()
    except Exception:
        return None, f"Fila {fila_num}: Costo de compra inválido ({costo_raw}). Debe ser un número mayor a 0."

    # Buscar Capacidad (opcional, si falta se deduce de modelo o 128)
    cap_raw = norm.get('capacidad') or norm.get('capacidadgb') or norm.get('gb') or norm.get('almacenamiento')
    if cap_raw:
        try:
            cap_int = int(re.sub(r'[^\d]', '', str(cap_raw)))
            if cap_int == 1:
                cap_int = 1024
        except Exception:
            cap_int = extraer_capacidad_de_modelo(modelo_str)
    else:
        cap_int = extraer_capacidad_de_modelo(modelo_str)

    # Buscar Precio Venta (opcional, si falta se sugiere costo + 30% de margen)
    precio_raw = norm.get('precioventa') or norm.get('precio') or norm.get('venta') or norm.get('pvp')
    if precio_raw:
        try:
            precio_float = float(str(precio_raw).replace("$", "").replace(",", "").strip())
        except Exception:
            precio_float = round(costo_float * 1.30, 2)
    else:
        precio_float = round(costo_float * 1.30, 2)

    try:
        equipo = EquipoCreate(
            modelo=modelo_str,
            capacidad_gb=cap_int,
            color=color_str,
            imei=imei_str,
            grado=grado_str,
            costo_compra=costo_float,
            precio_venta=precio_float
        )
        return equipo, None
    except Exception as e:
        return None, f"Fila {fila_num}: Error de validación: {str(e)}"

def procesar_archivo_excel_o_csv(contenido_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Lee un archivo Excel (.xlsx) o CSV en memoria y retorna los registros válidos y errores."""
    filename_lower = filename.lower()
    filas_dict = []

    if filename_lower.endswith('.csv'):
        # Intentar decodificar como utf-8 o latin-1
        texto = None
        for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
            try:
                texto = contenido_bytes.decode(enc)
                break
            except Exception:
                continue

        if not texto:
            raise ValueError("No se pudo leer la codificación del archivo CSV.")

        reader = csv.DictReader(io.StringIO(texto))
        for row in reader:
            filas_dict.append(row)

    elif filename_lower.endswith(('.xlsx', '.xlsm')):
        wb = openpyxl.load_workbook(io.BytesIO(contenido_bytes), data_only=True)
        sheet = wb.active

        headers = []
        for col_idx in range(1, sheet.max_column + 1):
            val = sheet.cell(row=1, column=col_idx).value
            headers.append(str(val).strip() if val is not None else f"col_{col_idx}")

        for row_idx in range(2, sheet.max_row + 1):
            row_data = {}
            has_data = False
            for col_idx, h in enumerate(headers, start=1):
                val = sheet.cell(row=row_idx, column=col_idx).value
                if val is not None and str(val).strip() != "":
                    has_data = True
                row_data[h] = val
            if has_data:
                filas_dict.append(row_data)
    else:
        raise ValueError("Formato no compatible. Por favor sube un archivo Excel (.xlsx) o CSV (.csv).")

    if not filas_dict:
        raise ValueError("El archivo está vacío o no contiene filas de datos debajo del encabezado.")

    equipos_validos: List[EquipoCreate] = []
    errores: List[str] = []
    imeis_vistos = set()

    for idx, r in enumerate(filas_dict, start=2):
        eq, err = mapear_fila_a_equipo(r, idx)
        if err:
            errores.append(err)
            continue

        # Verificar si el IMEI está repetido dentro del mismo archivo
        if eq.imei in imeis_vistos:
            errores.append(f"Fila {idx}: El IMEI {eq.imei} está duplicado dentro de este mismo archivo.")
            continue

        # Verificar si ya existe en la base de datos
        existente = crud.get_equipo_by_imei(eq.imei)
        if existente:
            errores.append(f"Fila {idx}: El IMEI {eq.imei} ya existe registrado en el inventario ({existente['modelo']}).")
            continue

        imeis_vistos.add(eq.imei)
        equipos_validos.append(eq)

    return {
        "total_filas": len(filas_dict),
        "validos": equipos_validos,
        "errores": errores
    }

def guardar_equipos_importados(equipos: List[EquipoCreate]) -> List[Dict[str, Any]]:
    """Inserta en lote los equipos validados."""
    guardados = []
    for eq in equipos:
        nuevo = crud.create_equipo(eq)
        guardados.append(nuevo)
    return guardados

def generar_plantilla_excel_bytes() -> bytes:
    """Genera un archivo Excel (.xlsx) profesional con estilos y datos de ejemplo para descargar."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventario Celulares"

    # Encabezados
    headers = ["modelo", "capacidad_gb", "color", "imei", "grado", "costo_compra", "precio_venta"]
    ws.append(headers)

    # Filas de ejemplo
    ejemplos = [
        ["iPhone 14", 128, "Negro Medianoche", "356789123456790", "A", 9500.0, 13000.0],
        ["Samsung Galaxy S23", 256, "Verde", "356789123456791", "A", 9000.0, 12500.0],
        ["Xiaomi Redmi Note 12", 128, "Azul", "356789123456792", "B", 2800.0, 3900.0],
        ["iPhone 11", 64, "Blanco", "356789123456793", "C", 3500.0, 4800.0],
    ]

    for row in ejemplos:
        ws.append(row)

    # Estilos
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid") # Azul
    alignment_center = Alignment(horizontal="center", vertical="center")

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = alignment_center

    # Ajustar ancho de columnas
    anchos = [26, 16, 20, 22, 12, 16, 16]
    for col_idx, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = ancho

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def generar_plantilla_celulares_csv() -> bytes:
    """Genera un archivo CSV profesional optimizado al 100% para Google Sheets y Excel (UTF-8 con BOM)."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\r\n')
    
    headers = ["modelo", "capacidad_gb", "color", "imei", "grado", "costo_compra", "precio_venta"]
    writer.writerow(headers)
    
    ejemplos = [
        ["iPhone 14", 128, "Negro Medianoche", "356789123456790", "A", 9500.0, 13000.0],
        ["Samsung Galaxy S23", 256, "Verde", "356789123456791", "A", 9000.0, 12500.0],
        ["Xiaomi Redmi Note 12", 128, "Azul", "356789123456792", "B", 2800.0, 3900.0],
        ["iPhone 11", 64, "Blanco", "356789123456793", "C", 3500.0, 4800.0],
    ]
    for row in ejemplos:
        writer.writerow(row)
        
    return output.getvalue().encode('utf-8-sig')


def generar_plantilla_stock_accesorios_excel() -> bytes:
    """Genera un archivo Excel (.xlsx) con la lista completa de accesorios para carga masiva de stock."""
    from app import crud
    accesorios = crud.get_accesorios()
    # Excluir servicios intangibles
    accesorios_fisicos = [a for a in accesorios if not a.get("es_servicio")]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Carga Stock Accesorios"

    # Encabezados
    headers = ["ID", "Nombre del Accesorio", "Color", "Categoría", "Stock Actual", "NUEVO STOCK", "Precio Mayoreo ($)"]
    ws.append(headers)

    for a in accesorios_fisicos:
        ws.append([
            a["id"],
            a["nombre"],
            a.get("color") or "",
            a["categoria"],
            int(a.get("stock", 0) or 0),
            int(a.get("stock", 0) or 0), # Prellenado con stock actual para fácil edición
            float(a.get("precio_mayoreo") or a.get("precio_venta") or 0.0)
        ])

    # Estilos de encabezado
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid") # Verde Teal
    nuevo_stock_fill = PatternFill(start_color="15803D", end_color="15803D", fill_type="solid") # Verde Esmeralda Destacado
    alignment_center = Alignment(horizontal="center", vertical="center")

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = nuevo_stock_fill if col_idx == 6 else header_fill
        cell.alignment = alignment_center

    # Resaltar la columna NUEVO STOCK en las filas de datos con fondo suave
    editable_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    for r in range(2, len(accesorios_fisicos) + 2):
        cell_stock = ws.cell(row=r, column=6)
        cell_stock.fill = editable_fill
        cell_stock.alignment = alignment_center
        cell_stock.font = Font(name="Calibri", size=11, bold=True)

    # Anchos de columna
    anchos = [8, 44, 18, 22, 14, 18, 20]
    for col_idx, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = ancho

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def generar_plantilla_stock_accesorios_csv() -> bytes:
    """Genera un archivo CSV profesional optimizado al 100% para Google Sheets con el catálogo completo de accesorios y colores."""
    from app import crud
    accesorios = crud.get_accesorios()
    accesorios_fisicos = [a for a in accesorios if not a.get("es_servicio")]

    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\r\n')

    # Encabezados compatibles con Google Sheets
    headers = ["ID", "Nombre del Accesorio", "Color", "Categoría", "Stock Actual", "NUEVO STOCK", "Precio Mayoreo ($)"]
    writer.writerow(headers)

    for a in accesorios_fisicos:
        writer.writerow([
            a["id"],
            a["nombre"],
            a.get("color") or "",
            a["categoria"],
            int(a.get("stock", 0) or 0),
            int(a.get("stock", 0) or 0),
            float(a.get("precio_mayoreo") or a.get("precio_venta") or 0.0)
        ])

    return output.getvalue().encode('utf-8-sig')


def importar_stock_accesorios_excel(contenido_bytes: bytes, filename: str = "", usuario: str = "Admin") -> Dict[str, Any]:
    """Procesa el archivo de stock de accesorios (compatible con Google Sheets .csv y Excel .xlsx) y actualiza masivamente registrando Kardex."""
    from app import crud

    items_to_update = []
    errores = []

    filename_lower = filename.lower()
    is_csv = filename_lower.endswith('.csv')
    if not is_csv and not contenido_bytes.startswith(b'PK'):
        is_csv = True

    if is_csv:
        texto = None
        for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
            try:
                texto = contenido_bytes.decode(enc)
                break
            except Exception:
                continue

        if not texto:
            raise ValueError("No se pudo leer la codificación del archivo CSV de Google Sheets.")

        reader = csv.reader(io.StringIO(texto))
        filas = list(reader)
        if not filas:
            raise ValueError("El archivo está vacío.")

        headers = [str(c).strip().lower().replace(" ", "").replace("_", "") for c in filas[0]]
        id_col = None
        stock_col = None

        for idx, h in enumerate(headers):
            if h in ("id", "codigo", "clave"):
                id_col = idx
            elif h in ("nuevostock", "stock", "stockfisico", "piezas", "cantidad"):
                stock_col = idx

        if id_col is None or stock_col is None:
            raise ValueError("El archivo de Google Sheets/CSV debe contener al menos las columnas 'ID' y 'NUEVO STOCK'.")

        for row_idx, row in enumerate(filas[1:], start=2):
            if not row or len(row) <= max(id_col, stock_col) or not str(row[id_col]).strip():
                continue
            try:
                acc_id = int(float(str(row[id_col]).strip()))
                val_stock = str(row[stock_col]).strip()
                if val_stock == "":
                    continue
                nuevo_stock = max(0, int(float(val_stock)))
                items_to_update.append({"id": acc_id, "stock": nuevo_stock})
            except Exception as e:
                errores.append(f"Fila {row_idx}: {str(e)}")
    else:
        wb = openpyxl.load_workbook(io.BytesIO(contenido_bytes), data_only=True)
        ws = wb.active

        headers = [cell.value for cell in ws[1] if cell.value is not None]
        norm_headers = [str(h).strip().lower().replace(" ", "").replace("_", "") for h in headers]

        id_col = None
        stock_col = None

        for idx, h in enumerate(norm_headers):
            if h in ("id", "codigo", "clave"):
                id_col = idx
            elif h in ("nuevostock", "stock", "stockfisico", "piezas", "cantidad"):
                stock_col = idx

        if id_col is None or stock_col is None:
            raise ValueError("El archivo Excel debe contener al menos las columnas 'ID' y 'NUEVO STOCK'.")

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or row[id_col] is None:
                continue
            try:
                acc_id = int(row[id_col])
                val_stock = row[stock_col]
                if val_stock is None or str(val_stock).strip() == "":
                    continue
                nuevo_stock = max(0, int(float(str(val_stock).strip())))
                items_to_update.append({"id": acc_id, "stock": nuevo_stock})
            except Exception as e:
                errores.append(f"Fila {row_idx}: {str(e)}")

    if not items_to_update:
        raise ValueError("No se encontraron filas con datos válidos de ID y stock para procesar.")

    res = crud.actualizar_stock_masivo(
        items=items_to_update,
        motivo_general="Importación masiva desde Google Sheets / Excel",
        usuario=usuario
    )
    res["errores_filas"] = errores
    return res

