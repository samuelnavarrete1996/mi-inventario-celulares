import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import init_db, seed_demo_data_if_empty
from app.routers import inventario, pos, clientes, reportes, garantias, accesorios, caja, backup, reparaciones, catalogo

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Mi Inventario - Celulares Samuel Navarrete",
    description="Sistema web para control de inventario, punto de venta (POS) y reportes de telefonía móvil.",
    version="2.0.0"
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar Base de Datos en el arranque
@app.on_event("startup")
def on_startup():
    init_db()
    seed_demo_data_if_empty()

# Registro de routers de API
app.include_router(inventario.router)
app.include_router(pos.router)
app.include_router(clientes.router)
app.include_router(reportes.router)
app.include_router(garantias.router)
app.include_router(accesorios.router)
app.include_router(caja.router)
app.include_router(backup.router)
app.include_router(reparaciones.router)
app.include_router(catalogo.router)

# Archivos estáticos y Single Page Application (SPA)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Montar directorio estático
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    """Sirve la interfaz gráfica principal con headers anti-caché para actualizaciones inmediatas."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(
        index_path,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    )

@app.get("/manifest.json")
def serve_manifest():
    """Sirve el manifest de PWA."""
    return FileResponse(
        os.path.join(STATIC_DIR, "manifest.json"),
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )

@app.get("/service-worker.js")
def serve_service_worker():
    """Sirve el Service Worker para capacidad offline."""
    return FileResponse(
        os.path.join(STATIC_DIR, "service-worker.js"),
        media_type="application/javascript",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "app": "Mi Inventario Samuel Navarrete", "version": "2.0.0"}
