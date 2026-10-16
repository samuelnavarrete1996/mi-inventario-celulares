import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import init_db, seed_demo_data_if_empty
from app.routers import inventario, pos, clientes, reportes, garantias

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Mi Inventario - Celulares Samuel Navarrete",
    description="Sistema web para control de inventario, punto de venta (POS) y reportes de telefonía móvil.",
    version="1.0.0"
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

# Archivos estáticos y Single Page Application (SPA)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Montar directorio estático
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    """Sirve la interfaz gráfica principal."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_path)

@app.get("/health")
def health_check():
    return {"status": "ok", "app": "Mi Inventario Samuel Navarrete", "version": "1.0.0"}
