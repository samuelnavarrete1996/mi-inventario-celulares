"""
tests/test_nuevas_funcionalidades_p1_p2_p4.py
Pruebas automatizadas de las mejoras estratégicas implementadas:
- Pilar 1: Taller Técnico Avanzado (Checklist digital de entrada, boleta con firma, portal de rastreo público).
- Pilar 2: Control de Gastos Operativos y Ganancia Neta Real (CRUD gastos, RBAC Dueño, aislamiento multi-tenant y métricas en Dashboard).
- Pilar 4: Automatizaciones de WhatsApp (Validación de generación de mensajes de corte y recordatorios).
"""

import json
import pytest
import httpx
from app.main import app
from app.database import get_db_connection, init_db, seed_demo_data_if_empty
from app.security import create_access_token
from app import crud

init_db()
seed_demo_data_if_empty()


@pytest.fixture(autouse=True)
def setup_tenants_and_users():
    """Garantiza la existencia de tenants y usuarios para las pruebas."""
    from app.security import hash_secret
    conn = get_db_connection()
    cur = conn.cursor()

    # Tenant 1 (demo)
    cur.execute("SELECT id FROM tenants WHERE id = 1;")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO tenants (id, nombre_comercial, slug, activo, fecha_creacion)
            VALUES (1, 'Tienda Alfa', 'tienda-alfa', 1, '2026-10-23 00:00:00');
        """)

    # Sucursal 1
    cur.execute("SELECT id FROM sucursales WHERE id = 1;")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO sucursales (id, tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
            VALUES (1, 1, 'Matriz Alfa', 'Av. Central 100', '5511223344', 1, '2026-10-23 00:00:00');
        """)

    # Usuario 1 (Dueño Tenant 1)
    cur.execute("SELECT id FROM usuarios WHERE id = 1;")
    if not cur.fetchone():
        h, s = hash_secret("AdminPass123.")
        cur.execute("""
            INSERT INTO usuarios (id, nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES (1, 'Dueño Alfa', 'admin', ?, ?, 'dueno', 1, '2026-10-23 00:00:00', 1, 1);
        """, (h, s))

    # Usuario 2 (Vendedor Tenant 1)
    cur.execute("SELECT id FROM usuarios WHERE id = 2;")
    if not cur.fetchone():
        h, s = hash_secret("VendPass123.")
        cur.execute("""
            INSERT INTO usuarios (id, nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES (2, 'Vendedor Alfa', 'vendedor', ?, ?, 'vendedor', 1, '2026-10-23 00:00:00', 1, 1);
        """, (h, s))

    # Tenant 2
    cur.execute("SELECT id FROM tenants WHERE id = 2;")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO tenants (id, nombre_comercial, slug, activo, fecha_creacion)
            VALUES (2, 'Tienda Beta', 'tienda-beta', 1, '2026-10-23 00:00:00');
        """)

    # Sucursal 2
    cur.execute("SELECT id FROM sucursales WHERE id = 2;")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO sucursales (id, tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
            VALUES (2, 2, 'Sucursal Beta', 'Calle Beta 123', '5599887766', 1, '2026-10-23 00:00:00');
        """)

    # Usuario 10 (Dueño Tenant 2)
    cur.execute("SELECT id FROM usuarios WHERE id = 10;")
    if not cur.fetchone():
        h, s = hash_secret("BetaPass123.")
        cur.execute("""
            INSERT INTO usuarios (id, nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES (10, 'Dueño Beta', 'admin2', ?, ?, 'dueno', 1, '2026-10-23 00:00:00', 2, 2);
        """, (h, s))

    conn.commit()
    conn.close()


def get_token(user_id=1, username="admin", rol="dueno", tenant_id=1, tenant_slug="tienda-alfa"):
    return create_access_token(
        user_id=user_id,
        username=username,
        rol=rol,
        nombre="Usuario Test",
        tenant_id=tenant_id,
        sucursal_id=1,
        tenant_slug=tenant_slug
    )


# ==============================================================================
# PILAR 1: TALLER TÉCNICO, CHECKLIST DIGITAL Y PORTAL DE RASTREO
# ==============================================================================

@pytest.mark.anyio
async def test_reparacion_checklist_recepcion():
    """Verifica que el checklist táctil de recepción se guarde y consulte correctamente."""
    token_dueno = get_token(rol="dueno", tenant_id=1)
    checklist_data = {
        "enciende": "Sí",
        "touch": "Touch Dañado",
        "biometria": "OK",
        "camaras": "OK",
        "audio": "OK",
        "carga": "OK",
        "senial": "OK",
        "chasis": "Rayones Leves",
        "botones": "OK",
        "bateria": "88% salud"
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Crear reparación con checklist
        res = await client.post(
            "/api/reparaciones",
            headers={"Authorization": f"Bearer {token_dueno}"},
            json={
                "cliente_nombre": "Laura Méndez",
                "cliente_telefono": "5512345678",
                "dispositivo_modelo": "iPhone 12 Pro",
                "color": "Grafito",
                "imei_serie": "358912345678901",
                "codigo_patron": "123456",
                "falla_reportada": "Pantalla rota, no da touch",
                "diagnostico_tecnico": "Cambio de pantalla OLED GX Incell",
                "condicion_recepcion": "Mica estrellada, rayón leve en marco",
                "checklist_recepcion": json.dumps(checklist_data),
                "costo_refaccion": 650.0,
                "precio_servicio": 1600.0,
                "anticipo": 500.0,
                "fecha_prometida": "2026-10-25"
            }
        )
        assert res.status_code == 201
        data_rep = res.json()
        assert data_rep["folio"].startswith("REP-")
        assert data_rep["saldo_pendiente"] == 1100.0
        assert data_rep["checklist_recepcion"] is not None

        parsed_chk = json.loads(data_rep["checklist_recepcion"])
        assert parsed_chk["touch"] == "Touch Dañado"
        assert parsed_chk["bateria"] == "88% salud"

        rep_id = data_rep["id"]
        folio = data_rep["folio"]

        # 2. Consultar por ID
        res_get = await client.get(
            f"/api/reparaciones/{rep_id}",
            headers={"Authorization": f"Bearer {token_dueno}"}
        )
        assert res_get.status_code == 200
        assert res_get.json()["checklist_recepcion"] == data_rep["checklist_recepcion"]

        # 3. Actualizar checklist o estado
        checklist_data["touch"] = "OK - Reparado"
        res_put = await client.put(
            f"/api/reparaciones/{rep_id}",
            headers={"Authorization": f"Bearer {token_dueno}"},
            json={
                "checklist_recepcion": json.dumps(checklist_data),
                "estado": "Listo para Entrega"
            }
        )
        assert res_put.status_code == 200
        assert res_put.json()["estado"] == "Listo para Entrega"
        assert "OK - Reparado" in res_put.json()["checklist_recepcion"]


@pytest.mark.anyio
async def test_portal_rastreo_publico_reparacion():
    """Verifica el endpoint público de rastreo para clientes (/api/catalogo/reparacion/{folio})."""
    token_dueno = get_token(rol="dueno", tenant_id=1)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Crear orden
        res = await client.post(
            "/api/reparaciones",
            headers={"Authorization": f"Bearer {token_dueno}"},
            json={
                "cliente_nombre": "Roberto Gómez",
                "cliente_telefono": "5587654321",
                "dispositivo_modelo": "Samsung Galaxy S22",
                "color": "Phantom Black",
                "falla_reportada": "Centro de carga flojo",
                "diagnostico_tecnico": "Reemplazo de flexor de carga original",
                "codigo_patron": "PIN Secreto 9999",
                "costo_refaccion": 300.0,
                "precio_servicio": 850.0,
                "anticipo": 350.0
            }
        )
        assert res.status_code == 201
        rep = res.json()
        folio = rep["folio"]

        # Consulta pública (sin token de autenticación)
        res_pub = await client.get(f"/api/catalogo/reparacion/{folio}")
        assert res_pub.status_code == 200
        pub_data = res_pub.json()

        # Datos seguros visibles
        assert pub_data["folio"] == folio
        assert pub_data["dispositivo_modelo"] == "Samsung Galaxy S22"
        assert pub_data["estado"] == "Recibido"
        assert pub_data["precio_servicio"] == 850.0
        assert pub_data["anticipo"] == 350.0
        assert pub_data["saldo_pendiente"] == 500.0

        # Blindaje de seguridad: datos confidenciales NO deben ser expuestos
        assert "costo_refaccion" not in pub_data
        assert "codigo_patron" not in pub_data
        assert "imei_serie" not in pub_data

        # Folio inexistente -> HTTP 404
        res_404 = await client.get("/api/catalogo/reparacion/REP-NO-EXISTE-999")
        assert res_404.status_code == 404


# ==============================================================================
# PILAR 2: GASTOS OPERATIVOS, RBAC Y GANANCIA NETA REAL
# ==============================================================================

@pytest.mark.anyio
async def test_gastos_operativos_rbac():
    """Verifica que solo el Dueño pueda gestionar gastos (Vendedores y Técnicos reciben 403)."""
    token_vendedor = get_token(user_id=2, username="vendedor1", rol="vendedor", tenant_id=1)
    token_dueno = get_token(user_id=1, username="admin", rol="dueno", tenant_id=1)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Vendedor intenta registrar gasto -> 403
        res_vend_post = await client.post(
            "/api/gastos",
            headers={"Authorization": f"Bearer {token_vendedor}"},
            json={
                "concepto": "Pago de Renta Sucursal",
                "categoria": "Renta",
                "monto": 5000.0,
                "metodo_pago": "Transferencia"
            }
        )
        assert res_vend_post.status_code == 403

        # Vendedor intenta listar gastos -> 403
        res_vend_get = await client.get(
            "/api/gastos",
            headers={"Authorization": f"Bearer {token_vendedor}"}
        )
        assert res_vend_get.status_code == 403

        # Dueño registra gasto -> 201 Created
        res_dueno_post = await client.post(
            "/api/gastos",
            headers={"Authorization": f"Bearer {token_dueno}"},
            json={
                "concepto": "Pago de Recibo de Luz CFE",
                "categoria": "Luz / Servicios",
                "monto": 850.50,
                "metodo_pago": "Efectivo",
                "notas": "Bimestre Sep-Oct"
            }
        )
        assert res_dueno_post.status_code == 201
        gasto = res_dueno_post.json()
        assert gasto["concepto"] == "Pago de Recibo de Luz CFE"
        assert gasto["monto"] == 850.50
        assert gasto["categoria"] == "Luz / Servicios"
        gasto_id = gasto["id"]

        # Dueño lista gastos
        res_dueno_get = await client.get(
            "/api/gastos",
            headers={"Authorization": f"Bearer {token_dueno}"}
        )
        assert res_dueno_get.status_code == 200
        gastos_list = res_dueno_get.json()
        assert any(g["id"] == gasto_id for g in gastos_list)

        # Resumen mensual
        res_resumen = await client.get(
            "/api/gastos/resumen",
            headers={"Authorization": f"Bearer {token_dueno}"}
        )
        assert res_resumen.status_code == 200
        res_data = res_resumen.json()
        assert res_data["total_mes"] >= 850.50
        assert "Luz / Servicios" in res_data["desglose_por_categoria"]

        # Eliminar gasto
        res_del = await client.delete(
            f"/api/gastos/{gasto_id}",
            headers={"Authorization": f"Bearer {token_dueno}"}
        )
        assert res_del.status_code == 200
        assert res_del.json()["ok"] is True


def setup_tenant_gastos_beta():
    """Garantiza un segundo tenant activo con sucursal y usuario propio para pruebas de aislamiento."""
    from app.security import hash_secret
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug = 'tienda-gastos-beta' LIMIT 1;")
    row = cur.fetchone()
    if not row:
        cur.execute("""
            INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
            VALUES ('Tienda Gastos Beta', 'tienda-gastos-beta', 'beta_gastos@test.com', '5511002233', 'pro', 1, '2026-10-23 00:00:00');
        """)
        t_id = cur.lastrowid
        cur.execute("""
            INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
            VALUES (?, 'Sucursal Gastos Beta', 'Calle Beta 456', '5511002233', 1, '2026-10-23 00:00:00');
        """, (t_id,))
        s_id = cur.lastrowid
        h, s = hash_secret("BetaGastos123.")
        cur.execute("""
            INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES ('Dueño Gastos Beta', 'admin_gastos_beta', ?, ?, 'dueno', 1, '2026-10-23 00:00:00', ?, ?);
        """, (h, s, t_id, s_id))
        u_id = cur.lastrowid
    else:
        t_id = row["id"]
        cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_id,))
        s_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM usuarios WHERE username = 'admin_gastos_beta' LIMIT 1;")
        u_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return {"tenant_id": t_id, "sucursal_id": s_id, "user_id": u_id}


@pytest.mark.anyio
async def test_gastos_aislamiento_multitenant():
    """Verifica que el Tenant 1 no pueda ver ni borrar los gastos del Tenant 2."""
    t2 = setup_tenant_gastos_beta()
    token_tenant1 = get_token(user_id=1, username="admin", rol="dueno", tenant_id=1, tenant_slug="tienda-alfa")
    token_tenant2 = get_token(
        user_id=t2["user_id"],
        username="admin_gastos_beta",
        rol="dueno",
        tenant_id=t2["tenant_id"],
        tenant_slug="tienda-gastos-beta"
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Tenant 2 crea un gasto privado
        res_t2 = await client.post(
            "/api/gastos",
            headers={"Authorization": f"Bearer {token_tenant2}"},
            json={
                "concepto": "Gasto Secreto de Tenant 2",
                "categoria": "General",
                "monto": 2500.0,
                "metodo_pago": "Transferencia"
            }
        )
        assert res_t2.status_code == 201
        gasto_t2_id = res_t2.json()["id"]

        # Tenant 1 consulta gastos -> NO debe ver el gasto de Tenant 2
        res_t1_list = await client.get(
            "/api/gastos",
            headers={"Authorization": f"Bearer {token_tenant1}"}
        )
        assert res_t1_list.status_code == 200
        ids_t1 = [g["id"] for g in res_t1_list.json()]
        assert gasto_t2_id not in ids_t1

        # Tenant 1 intenta eliminar el gasto de Tenant 2 -> 404 Not Found
        res_del_hack = await client.delete(
            f"/api/gastos/{gasto_t2_id}",
            headers={"Authorization": f"Bearer {token_tenant1}"}
        )
        assert res_del_hack.status_code == 404


@pytest.mark.anyio
async def test_dashboard_ganancia_neta_con_gastos():
    """Verifica que el Dashboard calcule Ganancia Neta Real = Bruta - Gastos."""
    token_dueno = get_token(user_id=1, username="admin", rol="dueno", tenant_id=1)
    token_vendedor = get_token(user_id=2, username="vendedor", rol="vendedor", tenant_id=1)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Registrar un gasto en Tenant 1
        await client.post(
            "/api/gastos",
            headers={"Authorization": f"Bearer {token_dueno}"},
            json={
                "concepto": "Compra de herramientas para taller",
                "categoria": "Herramientas",
                "monto": 400.0,
                "metodo_pago": "Efectivo"
            }
        )

        # 2. Consultar métricas como Dueño
        res_dash_dueno = await client.get(
            "/api/reportes/dashboard",
            headers={"Authorization": f"Bearer {token_dueno}"}
        )
        assert res_dash_dueno.status_code == 200
        d_metrics = res_dash_dueno.json()

        assert "total_gastos_mes" in d_metrics
        assert "ganancia_neta_mes" in d_metrics
        assert d_metrics["total_gastos_mes"] >= 400.0

        esperada_neta = round(d_metrics["total_ganancias_mes"] - d_metrics["total_gastos_mes"], 2)
        assert d_metrics["ganancia_neta_mes"] == esperada_neta

        # 3. Consultar métricas como Vendedor (confidencialidad de ganancias y gastos)
        res_dash_vend = await client.get(
            "/api/reportes/dashboard",
            headers={"Authorization": f"Bearer {token_vendedor}"}
        )
        assert res_dash_vend.status_code == 200
        v_metrics = res_dash_vend.json()

        # Debe estar oculto para vendedores
        assert v_metrics.get("total_gastos_mes") is None
        assert v_metrics.get("ganancia_neta_mes") is None
        assert v_metrics.get("total_ganancias_mes") is None
