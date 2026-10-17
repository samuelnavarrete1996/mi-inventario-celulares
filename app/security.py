"""
app/security.py - Módulo de Autenticación, Hashing, JWT y Control de Acceso por Roles (RBAC).
Implementa sesiones seguras mediante cookies HttpOnly, rate-limiting contra fuerza bruta,
y dependencias de autorización para FastAPI.
"""

import os
import time
import hmac
import hashlib
import secrets
from typing import Optional, Dict, List, Tuple
import jwt
from fastapi import Request, HTTPException, status, Depends

# Clave secreta para firma de JWT (mínimo 32 bytes para HS256 según RFC 7518)
_raw_secret = os.environ.get("JWT_SECRET") or os.environ.get("ADMIN_DELETE_PASSWORD") or "inventario-samuel-secret-key-2026-auth-prod"
JWT_SECRET = hashlib.sha256(_raw_secret.encode("utf-8")).hexdigest() if len(_raw_secret) < 32 else _raw_secret
JWT_ALGORITHM = "HS256"
COOKIE_NAME = "sid"

# Rate Limiting en memoria para protección contra ataques de fuerza bruta
# Estructura: { ip: [timestamp_fallo, ...] }
_FAILED_LOGIN_ATTEMPTS: Dict[str, List[float]] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutos

def get_client_ip(request: Request) -> str:
    """Extrae la IP real del cliente considerando encabezados de proxy (como Render o Cloudflare)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

def check_login_rate_limit(ip: str):
    """Verifica si la IP está temporalmente bloqueada por exceso de intentos fallidos."""
    now = time.time()
    attempts = _FAILED_LOGIN_ATTEMPTS.get(ip, [])
    # Filtrar solo los intentos dentro de la ventana de bloqueo
    valid_attempts = [t for t in attempts if now - t < LOCKOUT_SECONDS]
    _FAILED_LOGIN_ATTEMPTS[ip] = valid_attempts

    if len(valid_attempts) >= MAX_FAILED_ATTEMPTS:
        tiempo_restante = int(LOCKOUT_SECONDS - (now - valid_attempts[0]))
        minutos = max(1, tiempo_restante // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Acceso bloqueado temporalmente por {minutos} minutos."
        )

def record_failed_login_attempt(ip: str):
    """Registra un fallo de autenticación para la IP dada."""
    now = time.time()
    if ip not in _FAILED_LOGIN_ATTEMPTS:
        _FAILED_LOGIN_ATTEMPTS[ip] = []
    _FAILED_LOGIN_ATTEMPTS[ip].append(now)

def reset_login_attempts(ip: str):
    """Limpia los intentos fallidos al iniciar sesión con éxito."""
    if ip in _FAILED_LOGIN_ATTEMPTS:
        del _FAILED_LOGIN_ATTEMPTS[ip]


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
    """Crea un token JWT firmado con expiración."""
    exp = int(time.time()) + (ttl_hours * 3600)
    payload = {
        "sub": str(user_id),
        "username": username,
        "rol": rol,
        "nombre": nombre,
        "exp": exp,
        "iat": int(time.time())
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    """Decodifica y valida la firma y expiración de un token JWT."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None


# --- Dependencias de Seguridad para FastAPI ---

def get_current_user_optional(request: Request) -> Optional[dict]:
    """
    Obtiene el usuario autenticado a partir de la cookie HttpOnly o el encabezado Authorization.
    Si no hay sesión válida, retorna None sin lanzar excepción.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        # Intentar desde encabezado Bearer (soporte para llamadas API externas)
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
