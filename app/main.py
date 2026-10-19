import os
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from app.database import init_db, seed_demo_data_if_empty
from app.routers import inventario, pos, clientes, reportes, garantias, accesorios, caja, backup, reparaciones, catalogo, auth

logger = logging.getLogger("inventario.security")

# Ocultar documentación interactiva en producción salvo que se habilite explícitamente
_enable_docs = os.environ.get("ENABLE_API_DOCS", "1") == "1" and not os.environ.get("RENDER")

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Mi Inventario - Celulares Samuel Navarrete",
    description="Sistema web para control de inventario, punto de venta (POS) y reportes de telefonía móvil.",
    version="2.1.0",
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
    openapi_url="/openapi.json" if _enable_docs else None,
)

# Manejador global de excepciones no controladas para evitar fuga de stack traces en producción
@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Excepción no controlada en %s %s: %s", request.method, request.url.path, repr(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Error interno del servidor. La operación no pudo completarse."}
    )

# Configuración Segura de CORS (Permite localhost, red local Wi-Fi y subdominios de Render)
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS")
if allowed_origins_env:
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
else:
    allowed_origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$|^https://[a-zA-Z0-9-]+\.onrender\.com$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Middleware de Seguridad y Anti-Caché (OWASP Recommended)
@app.middleware("http")
async def security_and_cache_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Cabeceras de Seguridad HTTP para mitigar Clickjacking, MIME sniffing, XSS y ataques de protocolo
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' data: blob:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https:; "
        "font-src 'self' https: data:; "
        "img-src 'self' data: https: blob:; "
        "worker-src 'self' blob:; "
        "connect-src 'self' https: blob:; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Anti-caché para archivos estáticos, API y Single Page Application
    path = request.url.path
    if path.endswith((".html", ".js", ".css", ".json")) or path == "/" or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
    return response

# Inicializar Base de Datos en el arranque
@app.on_event("startup")
def on_startup():
    init_db()

# Registro de routers de API
app.include_router(auth.router)
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
    return {"status": "ok", "app": "Mi Inventario Samuel Navarrete", "version": "2.1.0"}
