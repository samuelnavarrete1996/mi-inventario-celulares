"""
app/security.py - Módulo de Autenticación, Hashing Argon2id/PBKDF2, JWT y Control de Acceso por Roles (RBAC).
Implementa sesiones seguras mediante cookies HttpOnly con revocación server-side (jti denylist),
hashing Argon2id (OWASP 2026) con retrocompatibilidad PBKDF2, resistencia a timing attacks,
rate-limiting persistente multi-worker contra fuerza bruta y dependencias de autorización para FastAPI.
"""

import os
import time
import hmac
import hashlib
import secrets
import sqlite3
import tempfile
import ctypes
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

# Separación criptográfica de claves: nunca usar ADMIN_DELETE_PASSWORD en crudo como clave HMAC de JWT
_explicit_jwt_secret = os.environ.get("JWT_SECRET")
if _explicit_jwt_secret:
    JWT_SECRET = (
        hashlib.sha256(_explicit_jwt_secret.encode("utf-8")).hexdigest()
        if len(_explicit_jwt_secret) < 32
        else _explicit_jwt_secret
    )
else:
    _fallback_seed = os.environ.get("ADMIN_DELETE_PASSWORD") or secrets.token_hex(32)
    JWT_SECRET = hmac.new(
        b"SN-POS-JWT-SIGNING-KEY-V2",
        _fallback_seed.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

JWT_ALGORITHM = "HS256"
COOKIE_NAME = "sid"

# Rate Limiting y Denylist de Sesiones Revocadas persistentes en SQLite local (compartido entre workers)
MAX_FAILED_ATTEMPTS_IP = 5
MAX_FAILED_ATTEMPTS_GLOBAL = 15
LOCKOUT_SECONDS = 15 * 60  # 15 minutos
_RATE_LIMIT_DB_PATH = os.path.join(tempfile.gettempdir(), "pos_rate_limit.sqlite3")

def _get_rl_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_RATE_LIMIT_DB_PATH, timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    try:
        conn.execute("PRAGMA busy_timeout=5000;")
    except Exception:
        pass
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            jti TEXT PRIMARY KEY,
            exp INTEGER NOT NULL
        );
        """
    )
    return conn

def get_client_ip(request: Request) -> str:
    """
    Extrae la IP real del cliente de forma segura detrás de Render / Cloudflare.
    Evita IP Spoofing ignorando valores inyectados al inicio de X-Forwarded-For.
    """
    for header in ("true-client-ip", "cf-connecting-ip"):
        val = request.headers.get(header)
        if val:
            return val.strip()

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


# --- Hashing Criptográfico con Argon2id (OWASP Recommended) + Fallback Retrocompatible PBKDF2 ---

ARGON2_TIME_COST = 2
ARGON2_MEMORY_COST_KIB = 19456  # 19 MiB según recomendación OWASP
ARGON2_PARALLELISM = 1
ARGON2_HASH_LEN = 32
PBKDF2_ITERATIONS = 100000

_argon2_cffi_low_level = None
_libargon2_cdll = None

try:
    from argon2 import low_level as _argon2_cffi_low_level  # type: ignore
except ImportError:
    for _lib_path in (
        "/usr/lib/x86_64-linux-gnu/libargon2.so.1",
        "libargon2.so.1",
        "libargon2.so",
    ):
        try:
            _lib = ctypes.CDLL(_lib_path)
            _lib.argon2id_hash_raw.argtypes = [
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_char_p,
                ctypes.c_size_t,
                ctypes.c_char_p,
                ctypes.c_size_t,
                ctypes.c_char_p,
                ctypes.c_size_t,
            ]
            _lib.argon2id_hash_raw.restype = ctypes.c_int
            _libargon2_cdll = _lib
            break
        except Exception:
            continue


def _compute_argon2id_hex(secret_bytes: bytes, salt_bytes: bytes) -> Optional[str]:
    """Calcula el digest Argon2id en hexadecimal usando argon2-cffi o libargon2 nativa."""
    if _argon2_cffi_low_level is not None:
        try:
            raw = _argon2_cffi_low_level.hash_secret_raw(
                secret=secret_bytes,
                salt=salt_bytes,
                time_cost=ARGON2_TIME_COST,
                memory_cost=ARGON2_MEMORY_COST_KIB,
                parallelism=ARGON2_PARALLELISM,
                hash_len=ARGON2_HASH_LEN,
                type=_argon2_cffi_low_level.Type.ID,
            )
            return f"argon2id${raw.hex()}"
        except Exception:
            pass

    if _libargon2_cdll is not None:
        try:
            out_buf = ctypes.create_string_buffer(ARGON2_HASH_LEN)
            rc = _libargon2_cdll.argon2id_hash_raw(
                ARGON2_TIME_COST,
                ARGON2_MEMORY_COST_KIB,
                ARGON2_PARALLELISM,
                secret_bytes,
                len(secret_bytes),
                salt_bytes,
                len(salt_bytes),
                out_buf,
                ARGON2_HASH_LEN,
            )
            if rc == 0:
                return f"argon2id${out_buf.raw.hex()}"
        except Exception:
            pass

    return None


def _compute_pbkdf2_hex(secret_bytes: bytes, salt_bytes: bytes, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Calcula PBKDF2-HMAC-SHA256 para retrocompatibilidad o fallback."""
    derived = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=secret_bytes,
        salt=salt_bytes,
        iterations=iterations,
    )
    return derived.hex()


def hash_secret(secret: str, salt_hex: Optional[str] = None) -> Tuple[str, str]:
    """
    Genera un hash criptográfico seguro Argon2id (con sal aleatoria única de 128 bits).
    Si Argon2id no está disponible en el sistema operativo, utiliza PBKDF2-HMAC-SHA256.
    """
    if salt_hex is None:
        salt_bytes = secrets.token_bytes(16)
        salt_hex = salt_bytes.hex()
    else:
        salt_bytes = bytes.fromhex(salt_hex)

    secret_bytes = secret.encode("utf-8")
    argon2_hash = _compute_argon2id_hex(secret_bytes, salt_bytes)
    if argon2_hash is not None:
        return argon2_hash, salt_hex

    return _compute_pbkdf2_hex(secret_bytes, salt_bytes), salt_hex


def verify_secret(secret: str, hash_hex: str, salt_hex: str) -> bool:
    """
    Verifica un secreto en tiempo constante usando hmac.compare_digest.
    Soporta transparentemente hashes Argon2id ('argon2id$...') y hashes heredados PBKDF2.
    """
    try:
        salt_bytes = bytes.fromhex(salt_hex)
        secret_bytes = secret.encode("utf-8")

        if hash_hex.startswith("argon2id$"):
            candidate = _compute_argon2id_hex(secret_bytes, salt_bytes)
            if candidate is None:
                return False
            return hmac.compare_digest(candidate.encode("ascii"), hash_hex.encode("ascii"))
        else:
            candidate_pbkdf2 = _compute_pbkdf2_hex(secret_bytes, salt_bytes)
            return hmac.compare_digest(candidate_pbkdf2.encode("ascii"), hash_hex.encode("ascii"))
    except Exception:
        return False


# Hash y salt precalculados para mitigación de ataques de temporización (Timing Attacks) cuando un usuario no existe
_DUMMY_HASH, _DUMMY_SALT = hash_secret("dummy_anti_timing_secret_argon_2026")

def verify_dummy_secret(secret: str) -> bool:
    """Ejecuta el algoritmo de hashing completo contra un hash señuelo para igualar tiempos de respuesta."""
    return verify_secret(secret, _DUMMY_HASH, _DUMMY_SALT)


# --- Manejo de Tokens JWT y Revocación de Sesiones (jti) ---

def revoke_token_jti(jti: str, exp: int) -> None:
    """Registra el identificador único (jti) de un token en la lista negra hasta su expiración."""
    if not jti:
        return
    now = int(time.time())
    conn = _get_rl_conn()
    try:
        with conn:
            conn.execute("DELETE FROM revoked_tokens WHERE exp <= ?;", (now,))
            conn.execute(
                "INSERT OR REPLACE INTO revoked_tokens (jti, exp) VALUES (?, ?);",
                (jti, int(exp)),
            )
    finally:
        conn.close()


def is_token_jti_revoked(jti: Optional[str]) -> bool:
    """Verifica si el jti del token ha sido revocado explícitamente mediante logout."""
    if not jti:
        return False
    conn = _get_rl_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM revoked_tokens WHERE jti = ? LIMIT 1;", (jti,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def create_access_token(
    user_id: int,
    username: str,
    rol: str,
    nombre: str,
    tenant_id: Optional[int] = None,
    sucursal_id: Optional[int] = None,
    tenant_slug: Optional[str] = None,
    ttl_hours: int = 14
) -> str:
    """Crea un token JWT firmado con expiración e identificador único (jti) y contexto multi-tenant."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "username": username,
        "rol": rol,
        "nombre": nombre,
        "tenant_id": tenant_id,
        "sucursal_id": sucursal_id,
        "tenant_slug": tenant_slug,
        "exp": now + (ttl_hours * 3600),
        "iat": now,
        "jti": secrets.token_hex(12),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decodifica y valida la firma, expiración y estado de no-revocación de un token JWT."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "rol", "exp", "iat"]},
        )
        jti = payload.get("jti")
        if jti and is_token_jti_revoked(jti):
            return None
        return payload
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
    "ganancia_celulares",
    "ganancia_accesorios",
    "celulares_ganancias_mes",
    "accesorios_ganancias_mes",
    "celulares_capital_inventario",
    "accesorios_capital_inventario",
    "capital_inventario_total",
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
        "id": int(payload.get("user_id") or payload["sub"]),
        "user_id": int(payload.get("user_id") or payload["sub"]),
        "username": payload.get("username"),
        "rol": payload.get("rol"),
        "nombre": payload.get("nombre"),
        "tenant_id": payload.get("tenant_id"),
        "sucursal_id": payload.get("sucursal_id"),
        "tenant_slug": payload.get("tenant_slug"),
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


def get_current_tenant(user: dict = Depends(get_current_user)):
    """Re-exporta la dependencia get_current_tenant para inyección de aislamiento multi-tenant."""
    from app.dependencies import get_current_tenant as _get_current_tenant
    return _get_current_tenant(user)

