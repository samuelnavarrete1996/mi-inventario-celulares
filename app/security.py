"""
app/security.py - Módulo de Autenticación, Hashing, JWT y Control de Acceso por Roles (RBAC).
Implementa sesiones seguras mediante cookies HttpOnly, rate-limiting persistente multi-worker
contra fuerza bruta y dependencias de autorización para FastAPI.
"""

import os
import time
import hmac
import hashlib
import secrets
import sqlite3
import tempfile
from typing import Optional, Dict, Any, Tuple
import jwt
from fastapi import Request, HTTPException, status, Depends

def _load_dotenv_if_present() -> None:
    """Carga variables desde .env local antes de inicializar secretos."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_dotenv_if_present()

# Clave secreta para firma de JWT (mínimo 32 bytes para HS256 según RFC 7518)
_raw_secret = os.environ.get("JWT_SECRET") or os.environ.get("ADMIN_DELETE_PASSWORD")
if not _raw_secret:
    # Si no se definió JWT_SECRET ni ADMIN_DELETE_PASSWORD, genera una clave efímera segura por instancia
    _raw_secret = secrets.token_hex(32)

JWT_SECRET = hashlib.sha256(_raw_secret.encode("utf-8")).hexdigest() if len(_raw_secret) < 32 else _raw_secret
JWT_ALGORITHM = "HS256"
COOKIE_NAME = "sid"

# Rate Limiting persistente en SQLite local (compartido entre múltiples workers de Uvicorn)
MAX_FAILED_ATTEMPTS_IP = 5
MAX_FAILED_ATTEMPTS_GLOBAL = 15
LOCKOUT_SECONDS = 15 * 60  # 15 minutos
_RATE_LIMIT_DB_PATH = os.path.join(tempfile.gettempdir(), "pos_rate_limit.sqlite3")

def _get_rl_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_RATE_LIMIT_DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            ts REAL NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_ts ON login_attempts(ip, ts);")
    return conn

def get_client_ip(request: Request) -> str:
    """
    Extrae la IP real del cliente de forma segura detrás de Render / Cloudflare.
    Evita IP Spoofing ignorando valores inyectados al inicio de X-Forwarded-For.
    """
    # 1. Encabezados verificados por el edge de Cloudflare/Render
    for header in ("true-client-ip", "cf-connecting-ip"):
        val = request.headers.get(header)
        if val:
            return val.strip()

    # 2. En X-Forwarded-For, el último IP fue añadido por el proxy reverso confiable de Render
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        if ips:
            return ips[-1]

    return request.client.host if request.client else "127.0.0.1"

def check_login_rate_limit(ip: str) -> None:
    """Verifica bloqueo por IP y límite global anti-spoofing en ventana deslizante."""
    now = time.time()
    cutoff = now - LOCKOUT_SECONDS
    conn = _get_rl_conn()
    try:
        with conn:
            conn.execute("DELETE FROM login_attempts WHERE ts < ?;", (cutoff,))
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), MIN(ts) FROM login_attempts WHERE ip = ?;", (ip,))
            row_ip = cur.fetchone()
            ip_count = row_ip[0] if row_ip else 0
            oldest_ip_ts = row_ip[1] if row_ip else None

            if ip_count >= MAX_FAILED_ATTEMPTS_IP and oldest_ip_ts:
                tiempo_restante = int(LOCKOUT_SECONDS - (now - oldest_ip_ts))
                minutos = max(1, tiempo_restante // 60)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Demasiados intentos fallidos desde esta conexión. Bloqueado por {minutos} min."
                )

            cur.execute("SELECT COUNT(*), MIN(ts) FROM login_attempts;")
            row_global = cur.fetchone()
            global_count = row_global[0] if row_global else 0
            oldest_global_ts = row_global[1] if row_global else None

            if global_count >= MAX_FAILED_ATTEMPTS_GLOBAL and oldest_global_ts:
                tiempo_restante = int(LOCKOUT_SECONDS - (now - oldest_global_ts))
                minutos = max(1, tiempo_restante // 60)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Sistema protegido por actividad inusual. Intenta de nuevo en {minutos} min."
                )
    finally:
        conn.close()

def record_failed_login_attempt(ip: str) -> None:
    """Registra un fallo de autenticación de forma persistente entre workers."""
    conn = _get_rl_conn()
    try:
        with conn:
            conn.execute("INSERT INTO login_attempts (ip, ts) VALUES (?, ?);", (ip, time.time()))
    finally:
        conn.close()

def reset_login_attempts(ip: str) -> None:
    """Limpia los intentos fallidos de la IP al iniciar sesión con éxito."""
    conn = _get_rl_conn()
    try:
        with conn:
            conn.execute("DELETE FROM login_attempts WHERE ip = ?;", (ip,))
    finally:
        conn.close()

def reset_all_rate_limits() -> None:
    """Limpia todos los intentos fallidos (usado en tests y mantenimiento)."""
    conn = _get_rl_conn()
    try:
        with conn:
            conn.execute("DELETE FROM login_attempts;")
    finally:
        conn.close()


# --- Hashing seguro de Contraseñas y PINs con PBKDF2-HMAC-SHA256 ---

def hash_secret(secret: str, salt_hex: Optional[str] = None) -> Tuple[str, str]:
    """Genera un hash criptográfico seguro PBKDF2 con sal aleatoria única."""
    if salt_hex is None:
        salt_bytes = secrets.token_bytes(16)
        salt_hex = salt_bytes.hex()
    else:
        salt_bytes = bytes.fromhex(salt_hex)

    derived = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=secret.encode("utf-8"),
        salt=salt_bytes,
        iterations=100000
    )
    return derived.hex(), salt_hex

def verify_secret(secret: str, hash_hex: str, salt_hex: str) -> bool:
    """Verifica un secreto en tiempo constante para mitigar ataques de timing."""
    try:
        new_hash, _ = hash_secret(secret, salt_hex)
        return hmac.compare_digest(new_hash, hash_hex)
    except Exception:
        return False


# --- Manejo de Tokens JWT ---

def create_access_token(user_id: int, username: str, rol: str, nombre: str, ttl_hours: int = 14) -> str:
    """Crea un token JWT firmado con expiración e identificador único (jti)."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "username": username,
        "rol": rol,
        "nombre": nombre,
        "exp": now + (ttl_hours * 3600),
        "iat": now,
        "jti": secrets.token_hex(8)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    """Decodifica y valida la firma y expiración de un token JWT."""
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "rol", "exp", "iat"]}
        )
    except (jwt.PyJWTError, Exception):
        return None


# --- Dependencias de Seguridad y Sanitización RBAC para FastAPI ---

CAMPOS_FINANCIEROS_SENSIBLES = {
    "costo_compra",
    "margen_proyectado",
    "porcentaje_margen",
    "margen_ganancia",
    "margen_unitario",
    "costo_refaccion",
    "costo_pieza",
    "utilidad_neta",
    "utilidad_reparacion",
    "costo_reemplazo",
}

def sanitizar_datos_sensibles(data: Any, user: Optional[dict]) -> Any:
    """
    Limpia recursivamente cualquier campo de costo o margen en diccionarios o listas
    si el usuario autenticado no tiene el rol 'dueno'.
    """
    if is_user_dueno(user):
        return data

    if isinstance(data, list):
        return [sanitizar_datos_sensibles(item, user) for item in data]

    if isinstance(data, dict):
        limpio = {}
        for k, v in data.items():
            if k in CAMPOS_FINANCIEROS_SENSIBLES:
                limpio[k] = None
            elif isinstance(v, (dict, list)):
                limpio[k] = sanitizar_datos_sensibles(v, user)
            else:
                limpio[k] = v
        return limpio

    return data

def get_current_user_optional(request: Request) -> Optional[dict]:
    """
    Obtiene el usuario autenticado a partir de la cookie HttpOnly o el encabezado Authorization.
    Si no hay sesión válida, retorna None sin lanzar excepción.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    return {
        "id": int(payload["sub"]),
        "username": payload.get("username"),
        "rol": payload.get("rol"),
        "nombre": payload.get("nombre")
    }

def get_current_user(request: Request) -> dict:
    """Exige que exista un usuario autenticado. Lanza 401 si no lo hay."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no iniciada o token expirado. Por favor ingresa tus credenciales."
        )
    return user

def require_role(*allowed_roles: str):
    """
    Fábrica de dependencias que valida que el usuario actual tenga uno de los roles permitidos.
    Lanza 403 si el rol no coincide.
    """
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user.get("rol") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado: Se requieren permisos de Dueño para esta acción."
            )
        return user
    return dependency

def is_user_dueno(user: Optional[dict]) -> bool:
    """Verifica si el diccionario de usuario corresponde al rol de dueño."""
    return bool(user and user.get("rol") == "dueno")
