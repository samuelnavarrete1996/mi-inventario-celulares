"""
app/routers/auth.py - Endpoints de Autenticación, Login por PIN/Contraseña, y Sesiones HttpOnly.
"""

import os
import hmac
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any
from app.database import get_db_connection
from app.security import (
    check_login_rate_limit,
    record_failed_login_attempt,
    reset_login_attempts,
    get_client_ip,
    verify_secret,
    verify_dummy_secret,
    hash_secret,
    create_access_token,
    decode_access_token,
    revoke_token_jti,
    get_current_user_optional,
    COOKIE_NAME
)

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Optional[str] = Field(None, max_length=80)
    password: Optional[str] = Field(None, max_length=200)
    pin: Optional[str] = Field(None, max_length=200)

class UserInfoResponse(BaseModel):
    id: int
    username: str
    nombre: str
    rol: str

class AuthStateResponse(BaseModel):
    authenticated: bool
    user: Optional[UserInfoResponse] = None


def _verify_secret_with_dot_tolerance(secret_clean: str, stored_hash: str, stored_salt: str) -> bool:
    """
    Evalúa el secreto y su variante con/sin punto final sin cortocircuito prematuro
    para mitigar canales laterales de tiempo (timing attacks).
    """
    m1 = verify_secret(secret_clean, stored_hash, stored_salt)
    alt = secret_clean[:-1] if secret_clean.endswith(".") else (secret_clean + ".")
    m2 = verify_secret(alt, stored_hash, stored_salt)
    return m1 or m2


def _verify_master_password_constant_time(secret_clean: str, admin_master: str) -> bool:
    """Compara contra la contraseña maestra en tiempo constante sin cortocircuito."""
    b_sec = secret_clean.encode("utf-8")
    b_master = admin_master.encode("utf-8")
    b_master_strip = admin_master.rstrip(".").encode("utf-8")
    b_sec_dot = (secret_clean + ".").encode("utf-8")

    c1 = hmac.compare_digest(b_sec, b_master)
    c2 = hmac.compare_digest(b_sec, b_master_strip)
    c3 = hmac.compare_digest(b_sec_dot, b_master)
    return c1 or c2 or c3


@router.post("/login")
def login(datos: LoginRequest, request: Request, response: Response) -> Dict[str, Any]:
    """
    Inicia sesión verificando credenciales o PIN rápido en tiempo constante.
    Protegido con rate limiting persistente contra ataques de fuerza bruta.
    Actualiza transparentemente hashes heredados PBKDF2 a Argon2id al iniciar sesión.
    Establece una cookie HttpOnly + SameSite=Strict con el JWT firmado.
    """
    client_ip = get_client_ip(request)
    check_login_rate_limit(client_ip)

    conn = get_db_connection()
    cursor = conn.cursor()
    usuario_encontrado = None
    secret_usado_para_rehash = None

    try:
        # Caso A: Login con PIN rápido o código de acceso (evalúa todos los usuarios activos sin cortocircuito)
        if datos.pin:
            pin_limpio = datos.pin.strip()
            cursor.execute("SELECT * FROM usuarios WHERE activo = 1;")
            todos_usuarios = cursor.fetchall()
            candidato = None
            for u in todos_usuarios:
                u_dict = dict(u)
                es_valido = _verify_secret_with_dot_tolerance(pin_limpio, u_dict["pin_hash"], u_dict["salt"])
                if es_valido:
                    candidato = u_dict
                    secret_usado_para_rehash = pin_limpio
            usuario_encontrado = candidato

            admin_master = os.environ.get("ADMIN_DELETE_PASSWORD", "erYHE7yse")
            match_master = _verify_master_password_constant_time(pin_limpio, admin_master)
            if not usuario_encontrado and match_master:
                cursor.execute("SELECT * FROM usuarios WHERE username = 'admin' AND activo = 1;")
                row_admin = cursor.fetchone()
                if row_admin:
                    usuario_encontrado = dict(row_admin)

        # Caso B: Login tradicional con Usuario y Contraseña
        elif datos.username and datos.password:
            user_limpio = datos.username.strip().lower()
            pwd_limpio = datos.password.strip()

            cursor.execute("SELECT * FROM usuarios WHERE LOWER(username) = ? AND activo = 1;", (user_limpio,))
            row = cursor.fetchone()
            if row:
                u_dict = dict(row)
                if _verify_secret_with_dot_tolerance(pwd_limpio, u_dict["pin_hash"], u_dict["salt"]):
                    usuario_encontrado = u_dict
                    secret_usado_para_rehash = pwd_limpio
            else:
                # Mitigación de Timing Attack por enumeración de usuario: ejecutar siempre verificación señuelo
                verify_dummy_secret(pwd_limpio)
                verify_dummy_secret(pwd_limpio + ".")

            admin_master = os.environ.get("ADMIN_DELETE_PASSWORD", "erYHE7yse")
            match_master = _verify_master_password_constant_time(pwd_limpio, admin_master)
            if not usuario_encontrado and user_limpio == "admin" and match_master:
                cursor.execute("SELECT * FROM usuarios WHERE username = 'admin' AND activo = 1;")
                row_admin = cursor.fetchone()
                if row_admin:
                    usuario_encontrado = dict(row_admin)

        # Migración transparente en caliente a Argon2id si el hash almacenado aún era PBKDF2 legado
        if (
            usuario_encontrado
            and secret_usado_para_rehash
            and not str(usuario_encontrado.get("pin_hash", "")).startswith("argon2id$")
        ):
            nuevo_hash, nuevo_salt = hash_secret(secret_usado_para_rehash)
            if nuevo_hash.startswith("argon2id$"):
                cursor.execute(
                    "UPDATE usuarios SET pin_hash = ?, salt = ? WHERE id = ?;",
                    (nuevo_hash, nuevo_salt, usuario_encontrado["id"])
                )
                conn.commit()
    finally:
        conn.close()

    if not usuario_encontrado:
        record_failed_login_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales o PIN incorrectos. Acceso denegado."
        )

    reset_login_attempts(client_ip)

    token = create_access_token(
        user_id=usuario_encontrado["id"],
        username=usuario_encontrado["username"],
        rol=usuario_encontrado["rol"],
        nombre=usuario_encontrado["nombre"]
    )

    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=14 * 3600,
        path="/",
        httponly=True,
        samesite="strict",
        secure=is_https
    )

    user_info = {
        "id": usuario_encontrado["id"],
        "username": usuario_encontrado["username"],
        "nombre": usuario_encontrado["nombre"],
        "rol": usuario_encontrado["rol"]
    }

    return {
        "success": True,
        "user": user_info,
        "mensaje": f"Bienvenido, {usuario_encontrado['nombre']}."
    }

@router.post("/logout")
def logout(request: Request, response: Response) -> Dict[str, Any]:
    """Cierra la sesión actual revocando el jti en el servidor y eliminando la cookie HttpOnly."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if token:
        payload = decode_access_token(token)
        if payload and payload.get("jti") and payload.get("exp"):
            revoke_token_jti(str(payload["jti"]), int(payload["exp"]))

    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
        secure=is_https
    )
    return {"success": True, "mensaje": "Sesión cerrada exitosamente."}

@router.get("/me", response_model=AuthStateResponse)
def get_auth_state(request: Request) -> Dict[str, Any]:
    """Retorna el estado de autenticación actual del usuario."""
    user = get_current_user_optional(request)
    if user:
        return {"authenticated": True, "user": user}
    return {"authenticated": False, "user": None}
