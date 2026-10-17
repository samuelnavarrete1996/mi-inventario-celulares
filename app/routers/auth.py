"""
app/routers/auth.py - Endpoints de Autenticación, Login por PIN/Contraseña, y Sesiones HttpOnly.
"""

import os
from fastapi import APIRouter, HTTPException, Request, Response, status, Depends
from pydantic import BaseModel, Field
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
    get_current_user,
    COOKIE_NAME
)

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

class LoginRequest(BaseModel):
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
    Protegido con rate limiting contra ataques de fuerza bruta.
    Establece una cookie HttpOnly segura con el JWT firmado.
    """
    client_ip = get_client_ip(request)
    check_login_rate_limit(client_ip)

    conn = get_db_connection()
    cursor = conn.cursor()

    usuario_encontrado = None

    # Caso A: Login con PIN rápido (ideal para mostrador)
    if datos.pin:
        pin_limpio = datos.pin.strip()
        cursor.execute("SELECT * FROM usuarios WHERE activo = 1;")
        todos_usuarios = cursor.fetchall()
        for u in todos_usuarios:
            u_dict = dict(u)
            if verify_secret(pin_limpio, u_dict["pin_hash"], u_dict["salt"]):
                usuario_encontrado = u_dict
                break

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
        
        # Compatibilidad hacia atrás con la contraseña maestra de admin
        admin_master = os.environ.get("ADMIN_DELETE_PASSWORD", "erYHE7yse")
        if not usuario_encontrado and user_limpio == "admin" and pwd_limpio == admin_master:
            cursor.execute("SELECT * FROM usuarios WHERE username = 'admin';",)
            row_admin = cursor.fetchone()
            if row_admin:
                usuario_encontrado = dict(row_admin)

    conn.close()

    if not usuario_encontrado:
        record_failed_login_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales o PIN incorrectos. Acceso denegado."
        )

    # Login exitoso: limpiar intentos fallidos
    reset_login_attempts(client_ip)

    # Generar Token JWT
    token = create_access_token(
        user_id=usuario_encontrado["id"],
        username=usuario_encontrado["username"],
        rol=usuario_encontrado["rol"],
        nombre=usuario_encontrado["nombre"]
    )

    # Establecer Cookie HttpOnly (Invisible para JavaScript para mitigar XSS)
    # max_age = 14 horas
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=14 * 3600,
        httponly=True,
        samesite="lax",
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
        "token": token,
        "user": user_info,
        "mensaje": f"Bienvenido, {usuario_encontrado['nombre']}."
    }

@router.post("/logout")
def logout(response: Response) -> Dict[str, Any]:
    """Cierra la sesión actual eliminando la cookie HttpOnly."""
    response.delete_cookie(key=COOKIE_NAME)
    return {"success": True, "mensaje": "Sesión cerrada exitosamente."}

@router.get("/me", response_model=AuthStateResponse)
def get_auth_state(request: Request) -> Dict[str, Any]:
    """
    Retorna el estado de autenticación actual del usuario.
    Permite al frontend saber si la sesión es de Dueño o Vendedor.
    """
    user = get_current_user_optional(request)
    if user:
        return {"authenticated": True, "user": user}
    return {"authenticated": False, "user": None}
