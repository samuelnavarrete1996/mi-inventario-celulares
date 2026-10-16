import sys
import os

# Asegurar soporte UTF-8 en consola
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.database import init_db
from app.excel_importer import procesar_archivo_excel_o_csv, guardar_equipos_importados

def main():
    init_db()

    # Si se pasa como argumento o buscar archivo por defecto
    if len(sys.argv) > 1:
        ruta_archivo = sys.argv[1]
    else:
        # Buscar archivos comunes en la carpeta
        candidatos = ["inventario.xlsx", "celulares.xlsx", "equipos.xlsx", "inventario.csv"]
        ruta_archivo = None
        for c in candidatos:
            if os.path.exists(c):
                ruta_archivo = c
                break

        if not ruta_archivo:
            print("Uso: python importar_excel.py <ruta_del_archivo.xlsx o .csv>")
            print("Ejemplo: python importar_excel.py inventario.xlsx")
            return

    if not os.path.exists(ruta_archivo):
        print(f"[ERROR] El archivo '{ruta_archivo}' no existe.")
        return

    print("=" * 65)
    print(f"[*] Procesando archivo: {ruta_archivo}")
    print("=" * 65)

    with open(ruta_archivo, "rb") as fh:
        contenido = fh.read()

    try:
        resultado = procesar_archivo_excel_o_csv(contenido, os.path.basename(ruta_archivo))
    except Exception as e:
        print(f"[ERROR] Fallo al leer el archivo: {e}")
        return

    validos = resultado["validos"]
    errores = resultado["errores"]

    print(f"-> Total de filas analizadas: {resultado['total_filas']}")
    print(f"-> Teléfonos listos para importar: {len(validos)}")

    if errores:
        print(f"\n[!] Advertencias / Errores encontrados ({len(errores)}):")
        for err in errores:
            print(f"    • {err}")

    if not validos:
        print("\n[!] No se encontraron registros válidos para importar.")
        return

    guardados = guardar_equipos_importados(validos)
    print("\n" + "=" * 65)
    print(f"[OK] ¡Se importaron exitosamente {len(guardados)} teléfonos al inventario!")
    print("=" * 65)
    for g in guardados:
        print(f"  + {g['modelo']} ({g['capacidad_gb']}GB) | Color: {g['color']} | IMEI: {g['imei']} | Grado: {g['grado']} | Costo: ${g['costo_compra']:,.2f} | Venta: ${g['precio_venta']:,.2f}")

if __name__ == "__main__":
    main()
