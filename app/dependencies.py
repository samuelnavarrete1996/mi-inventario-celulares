"""
app/dependencies.py - Dependencias de Inyección de Dependencias para FastAPI.
Aislamiento estricto de datos Multi-Tenant y validación de estado de cuenta.
"""

from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from app.security import get_current_user
from app.database import get_db_connection

class TenantContext:
    """Contenedor seguro e inmutable del contexto multi-tenant de la sesión actual."""
    def __init__(
        self,
        tenant_id: int,
        sucursal_id: Optional[int],
        tenant_slug: str,
        nombre_comercial: str,
        plan: str,
        user: dict
    ):
        self.tenant_id = tenant_id
        self.sucursal_id = sucursal_id
        self.tenant_slug = tenant_slug
        self.nombre_comercial = nombre_comercial
        self.plan = plan
        self.user = user

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "sucursal_id": self.sucursal_id,
            "tenant_slug": self.tenant_slug,
            "nombre_comercial": self.nombre_comercial,
            "plan": self.plan,
            "user": self.user,
        }

    def __repr__(self) -> str:
        return f"<TenantContext(tenant_id={self.tenant_id}, sucursal_id={self.sucursal_id}, slug='{self.tenant_slug}')>"


def get_current_tenant(user: dict = Depends(get_current_user)) -> TenantContext:
    """
    Dependencia de seguridad FastAPI para resolver el tenant activo:
    1. Extrae 'tenant_id' del usuario/token JWT autenticado.
    2. Valida la existencia del tenant en la base de datos.
    3. Verifica que la cuenta esté activa (activo = True / 1). Si está inactivo, rechaza con HTTP 403 Forbidden.
    4. Resuelve la 'sucursal_id' activa.
    5. Retorna el objeto TenantContext listo para inyectar en queries.
    """
    tenant_id = user.get("tenant_id")
    user_id = user.get("id") or user.get("user_id")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Si el token no tenía tenant_id, buscar en el registro del usuario en BD
        if not tenant_id and user_id:
            cursor.execute("SELECT tenant_id, sucursal_id FROM usuarios WHERE id = ?;", (user_id,))
            u_row = cursor.fetchone()
            if u_row:
                tenant_id = u_row["tenant_id"]

        if not tenant_id:
            # Si aún no tiene tenant asignado, verificar si existe el demo tenant
            cursor.execute("SELECT id, slug, activo, nombre_comercial, plan FROM tenants WHERE slug = 'demo-celulares' LIMIT 1;")
            demo_t = cursor.fetchone()
            if demo_t:
                tenant_id = demo_t["id"]
                if user_id:
                    cursor.execute("UPDATE usuarios SET tenant_id = ? WHERE id = ?;", (tenant_id, user_id))
                    conn.commit()
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Acceso denegado: El usuario no tiene una empresa (tenant) asignada."
                )

        cursor.execute("SELECT id, nombre_comercial, slug, plan, activo FROM tenants WHERE id = ? LIMIT 1;", (tenant_id,))
        t_row = cursor.fetchone()
        if not t_row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado: El tenant asociado a esta sesión no existe."
            )

        # Validación estricta de cuenta activa
        es_activo = bool(t_row["activo"])
        if not es_activo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado: La cuenta de esta empresa se encuentra suspendida o inactiva."
            )

        # Resolución de sucursal_id
        sucursal_id = user.get("sucursal_id")
        if not sucursal_id:
            cursor.execute("SELECT id FROM sucursales WHERE tenant_id = ? AND es_matriz = 1 LIMIT 1;", (tenant_id,))
            s_row = cursor.fetchone()
            if s_row:
                sucursal_id = s_row["id"]
            else:
                cursor.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (tenant_id,))
                s_row2 = cursor.fetchone()
                sucursal_id = s_row2["id"] if s_row2 else 1

        return TenantContext(
            tenant_id=int(tenant_id),
            sucursal_id=int(sucursal_id) if sucursal_id is not None else None,
            tenant_slug=str(t_row["slug"]),
            nombre_comercial=str(t_row["nombre_comercial"]),
            plan=str(t_row["plan"]),
            user=user
        )
    finally:
        conn.close()
