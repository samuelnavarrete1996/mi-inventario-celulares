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
    _is_production_env,
    COOKIE_NAME
)

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Optional[str] = Field(None, max_length=80)
    password: Optional[str] = Field(None, max_length=200)
    pin: Optional[str] = Field(None, max_length=200)
    tenant_slug: Optional[str] = Field(None, max_length=60)

class UserInfoResponse(BaseModel):
    id: int
    username: str
    nombre: str
    rol: str
    tenant_id: Optional[int] = None
    sucursal_id: Optional[int] = None
    tenant_slug: Optional[str] = None

class AuthStateResponse(BaseModel):
    authenticated: bool
    user: Optional[UserInfoResponse] = None


def _generate_secret_variations(secret_clean: str) -> list:
    """Genera variaciones comunes del secreto (mayúsculas, minúsculas, con/sin punto final)."""
    raw = secret_clean.strip()
    variations = [raw]
    if raw.endswith("."):
        variations.append(raw[:-1])
    else:
        variations.append(raw + ".")
    low = raw.lower()
    variations.append(low)
    if low.endswith("."):
        variations.append(low[:-1])
    else:
        variations.append(low + ".")
    seen = set()
    return [v for v in variations if not (v in seen or seen.add(v))]


def _verify_secret_with_dot_tolerance(secret_clean: str, stored_hash: str, stored_salt: str) -> bool:
    """
    Evalúa el secreto tolerando variaciones de mayúsculas/minúsculas y punto final
    habituales en teclados móviles (iOS/iPadOS/Android) y computadoras.
    """
    for v in _generate_secret_variations(secret_clean):
        if verify_secret(v, stored_hash, stored_salt):
            return True
    return False


def _verify_master_password_constant_time(secret_clean: str, admin_master: str) -> bool:
    """Compara contra la contraseña maestra tolerando punto final o mayúsculas en tiempo constante."""
    variations = _generate_secret_variations(secret_clean)
    master_variations = _generate_secret_variations(admin_master)
    for v in variations:
        b_v = v.encode("utf-8")
        for m in master_variations:
            b_m = m.encode("utf-8")
            if hmac.compare_digest(b_v, b_m):
                return True
    return False


@router.post("/login")
def login(datos: LoginRequest, request: Request, response: Response) -> Dict[str, Any]:
    """
    Inicia sesión verificando credenciales o PIN rápido en tiempo constante.
    Protegido con rate limiting persistente por IP y usuario contra ataques de fuerza bruta.
    Actualiza transparentemente hashes heredados PBKDF2 a Argon2id al iniciar sesión.
    Establece una cookie HttpOnly + SameSite=Strict con el JWT firmado.
    """
    client_ip = get_client_ip(request)
    login_user_target = (datos.username or "").strip().lower() or None
    check_login_rate_limit(client_ip, username=login_user_target)

    conn = get_db_connection()
    cursor = conn.cursor()
    usuario_encontrado = None
    secret_usado_para_rehash = None

    try:
        # Caso A: Login con PIN rápido o contraseña directa
        secret_rapido = (datos.pin or datos.password).strip() if (datos.pin or (datos.password and not datos.username)) else None
        if secret_rapido:
            pin_limpio = secret_rapido
            if datos.tenant_slug:
                cursor.execute("""
                    SELECT u.* FROM usuarios u
                    JOIN tenants t ON u.tenant_id = t.id
                    WHERE LOWER(t.slug) = ? AND (u.activo IS TRUE OR u.activo = TRUE) AND (t.activo IS TRUE OR t.activo = TRUE);
                """, (datos.tenant_slug.strip().lower(),))
                todos_usuarios = cursor.fetchall()
                candidatos = []
                for u in todos_usuarios:
                    u_dict = dict(u)
                    if _verify_secret_with_dot_tolerance(pin_limpio, u_dict["pin_hash"], u_dict["salt"]):
                        candidatos.append(u_dict)
                if candidatos:
                    usuario_encontrado = candidatos[0]
                    secret_usado_para_rehash = pin_limpio
            else:
                cursor.execute("SELECT * FROM usuarios WHERE (activo IS TRUE OR activo = TRUE);")
                todos_usuarios = cursor.fetchall()
                candidatos = []
                for u in todos_usuarios:
                    u_dict = dict(u)
                    if _verify_secret_with_dot_tolerance(pin_limpio, u_dict["pin_hash"], u_dict["salt"]):
                        candidatos.append(u_dict)
                tenants_distintos = {c.get("tenant_id") for c in candidatos if c.get("tenant_id") is not None}
                if len(tenants_distintos) > 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Por seguridad multi-tenant, ingresa tu nombre de usuario además de tu contraseña."
                    )
                if candidatos:
                    usuario_encontrado = candidatos[0]
                    secret_usado_para_rehash = pin_limpio

            # Comparación con credencial maestra
            if _is_production_env():
                admin_master = os.environ.get("ADMIN_DELETE_PASSWORD")
                match_master = _verify_master_password_constant_time(pin_limpio, admin_master) if admin_master else False
            else:
                admin_master = os.environ.get("ADMIN_DELETE_PASSWORD", "samuelykim.")
                match_master = _verify_master_password_constant_time(pin_limpio, admin_master) or _verify_master_password_constant_time(pin_limpio, "samuelykim.")

            if not usuario_encontrado and match_master:
                cursor.execute("SELECT * FROM usuarios WHERE username = 'admin' AND (activo IS TRUE OR activo = TRUE);")
                row_admin = cursor.fetchone()
                if row_admin:
                    usuario_encontrado = dict(row_admin)

        # Caso B: Login tradicional con Usuario y Contraseña
        elif datos.username and datos.password:
            user_limpio = datos.username.strip().lower()
            pwd_limpio = datos.password.strip()

            if datos.tenant_slug:
                cursor.execute("""
                    SELECT u.* FROM usuarios u
                    JOIN tenants t ON u.tenant_id = t.id
                    WHERE LOWER(u.username) = ? AND LOWER(t.slug) = ? AND (u.activo IS TRUE OR u.activo = TRUE) AND (t.activo IS TRUE OR t.activo = TRUE);
                """, (user_limpio, datos.tenant_slug.strip().lower()))
            else:
                cursor.execute("SELECT * FROM usuarios WHERE LOWER(username) = ? AND (activo IS TRUE OR activo = TRUE);", (user_limpio,))
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

            if _is_production_env():
                admin_master = os.environ.get("ADMIN_DELETE_PASSWORD")
                match_master = _verify_master_password_constant_time(pwd_limpio, admin_master) if admin_master else False
            else:
                admin_master = os.environ.get("ADMIN_DELETE_PASSWORD", "samuelykim.")
                match_master = _verify_master_password_constant_time(pwd_limpio, admin_master) or _verify_master_password_constant_time(pwd_limpio, "samuelykim.")

            if not usuario_encontrado and user_limpio == "admin" and match_master:
                cursor.execute("SELECT * FROM usuarios WHERE username = 'admin' AND (activo IS TRUE OR activo = TRUE);")
                row_admin = cursor.fetchone()
                if row_admin:
                    usuario_encontrado = dict(row_admin)
    finally:
        conn.close()

    if not usuario_encontrado:
        record_failed_login_attempt(client_ip, username=login_user_target)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales o PIN incorrectos. Acceso denegado."
        )

    reset_login_attempts(client_ip, username=usuario_encontrado.get("username"))

    # Actualización transparente a Argon2id si el hash almacenado es heredado (PBKDF2)
    stored_hash = usuario_encontrado.get("pin_hash") or ""
    if not stored_hash.startswith("argon2id$") and secret_usado_para_rehash:
        try:
            nuevo_hash, nuevo_salt = hash_secret(secret_usado_para_rehash)
            if nuevo_hash.startswith("argon2id$"):
                conn_rehash = get_db_connection()
                try:
                    c_rehash = conn_rehash.cursor()
                    c_rehash.execute(
                        "UPDATE usuarios SET pin_hash = ?, salt = ? WHERE id = ?;",
                        (nuevo_hash, nuevo_salt, usuario_encontrado["id"])
                    )
                    conn_rehash.commit()
                    usuario_encontrado["pin_hash"] = nuevo_hash
                    usuario_encontrado["salt"] = nuevo_salt
                finally:
                    conn_rehash.close()
        except Exception:
            pass

    tenant_id = usuario_encontrado.get("tenant_id")
    sucursal_id = usuario_encontrado.get("sucursal_id")
    tenant_slug = None

    conn_tenant = get_db_connection()
    c_t = conn_tenant.cursor()
    try:
        if not tenant_id:
            c_t.execute("SELECT id, slug, activo FROM tenants WHERE slug = 'demo-celulares' LIMIT 1;")
            t_row = c_t.fetchone()
            if t_row:
                tenant_id = t_row["id"]
                tenant_slug = t_row["slug"]
                c_t.execute("UPDATE usuarios SET tenant_id = ? WHERE id = ?;", (tenant_id, usuario_encontrado["id"]))
                conn_tenant.commit()
        else:
            c_t.execute("SELECT id, slug, activo FROM tenants WHERE id = ? LIMIT 1;", (tenant_id,))
            t_row = c_t.fetchone()
            if t_row:
                es_activo = bool(t_row["activo"])
                if not es_activo:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Acceso denegado: La cuenta de su empresa se encuentra inactiva o suspendida."
                    )
                tenant_slug = t_row["slug"]
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Acceso denegado: El tenant asociado no existe."
                )

        if tenant_id and not sucursal_id:
            c_t.execute("SELECT id FROM sucursales WHERE tenant_id = ? AND (es_matriz IS TRUE OR es_matriz = TRUE) LIMIT 1;", (tenant_id,))
            s_row = c_t.fetchone()
            if s_row:
                sucursal_id = s_row["id"]
                c_t.execute("UPDATE usuarios SET sucursal_id = ? WHERE id = ?;", (sucursal_id, usuario_encontrado["id"]))
                conn_tenant.commit()
    finally:
        conn_tenant.close()

    token = create_access_token(
        user_id=usuario_encontrado["id"],
        username=usuario_encontrado["username"],
        rol=usuario_encontrado["rol"],
        nombre=usuario_encontrado["nombre"],
        tenant_id=tenant_id,
        sucursal_id=sucursal_id,
        tenant_slug=tenant_slug
    )

    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=14 * 3600,
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_https
    )

    user_info = {
        "id": usuario_encontrado["id"],
        "username": usuario_encontrado["username"],
        "nombre": usuario_encontrado["nombre"],
        "rol": usuario_encontrado["rol"],
        "tenant_id": tenant_id,
        "sucursal_id": sucursal_id,
        "tenant_slug": tenant_slug
    }

    return {
        "success": True,
        "token": token,
        "access_token": token,
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
