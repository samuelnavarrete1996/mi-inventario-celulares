"""
app/routers/auth.py - Endpoints de Autenticación, Login por PIN/Contraseña, y Sesiones HttpOnly.
"""

import os
import hmac
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from app.database import get_db_connection
from app.security import (
    check_login_rate_limit,
    record_failed_login_attempt,
    reset_login_attempts,
    get_client_ip,
    verify_secret,
    create_access_token,
    get_current_user_optional,
    COOKIE_NAME
)

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Optional[str] = None
    password: Optional[str] = None
    pin: Optional[str] = None

class UserInfoResponse(BaseModel):
    id: int
    username: str
    nombre: str
    rol: str

class AuthStateResponse(BaseModel):
    authenticated: bool
    user: Optional[UserInfoResponse] = None

@router.post("/login")
def login(datos: LoginRequest, request: Request, response: Response) -> Dict[str, Any]:
    """
    Inicia sesión verificando credenciales o PIN rápido.
    Protegido con rate limiting persistente contra ataques de fuerza bruta.
    Establece una cookie HttpOnly + SameSite=Strict con el JWT firmado.
    """
    client_ip = get_client_ip(request)
    check_login_rate_limit(client_ip)

    conn = get_db_connection()
    cursor = conn.cursor()
    usuario_encontrado = None

    try:
        # Caso A: Login con PIN rápido (evalúa todos los activos sin cortocircuito para evitar timing side-channel)
        if datos.pin:
            pin_limpio = datos.pin.strip()
            cursor.execute("SELECT * FROM usuarios WHERE activo = 1;")
            todos_usuarios = cursor.fetchall()
            candidato = None
            for u in todos_usuarios:
                u_dict = dict(u)
                if verify_secret(pin_limpio, u_dict["pin_hash"], u_dict["salt"]):
                    candidato = u_dict
            usuario_encontrado = candidato

        # Caso B: Login tradicional con Usuario y Contraseña
        elif datos.username and datos.password:
            user_limpio = datos.username.strip().lower()
            pwd_limpio = datos.password.strip()

            cursor.execute("SELECT * FROM usuarios WHERE LOWER(username) = ? AND activo = 1;", (user_limpio,))
            row = cursor.fetchone()
            if row:
                u_dict = dict(row)
                if verify_secret(pwd_limpio, u_dict["pin_hash"], u_dict["salt"]):
                    usuario_encontrado = u_dict

            # Fallback seguro SOLO si ADMIN_DELETE_PASSWORD está explícitamente definido en variables de entorno
            admin_master = os.environ.get("ADMIN_DELETE_PASSWORD")
            if (
                not usuario_encontrado
                and admin_master
                and user_limpio == "admin"
                and hmac.compare_digest(pwd_limpio.encode("utf-8"), admin_master.encode("utf-8"))
            ):
                cursor.execute("SELECT * FROM usuarios WHERE username = 'admin' AND activo = 1;")
                row_admin = cursor.fetchone()
                if row_admin:
                    usuario_encontrado = dict(row_admin)
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
    """Cierra la sesión actual eliminando la cookie HttpOnly con los mismos atributos de creación."""
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
