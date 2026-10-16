import os
import sys
import threading
import time
import socket
import webbrowser
import uvicorn

# Asegurar soporte UTF-8 en consola de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def get_local_ip():
    """Detecta la IP local de la computadora en la red Wi-Fi o LAN."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def abrir_navegador(port):
    time.sleep(1.5)
    url = f"http://127.0.0.1:{port}"
    print(f"[*] Abriendo navegador web en: {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"[*] No se pudo abrir automaticamente el navegador: {e}")

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    local_ip = get_local_ip()

    print("=" * 65)
    print("  MI INVENTARIO - SAMUEL NAVARRETE (CELULARES)")
    print("  Sistema Web de Control de Inventario, POS y Reportes")
    print("=" * 65)
    print(f"  > En esta PC:                 http://localhost:{port}")
    if local_ip != "127.0.0.1":
        print(f"  > Desde tu celular (Wi-Fi):   http://{local_ip}:{port}")
    print(f"  > Documentacion de API:       http://localhost:{port}/docs")
    print("=" * 65)
    print("  Presiona CTRL+C para detener el servidor.")
    print("=" * 65)
    
    # Abrir navegador si estamos en entorno interactivo
    if os.environ.get("AUTO_OPEN_BROWSER", "1") == "1" and not os.environ.get("RENDER"):
        threading.Thread(target=abrir_navegador, args=(port,), daemon=True).start()
    
    # Arrancar uvicorn escuchando en 0.0.0.0 para acceso en red y nube
    uvicorn.run("app.main:app", host=host, port=port, reload=False)

