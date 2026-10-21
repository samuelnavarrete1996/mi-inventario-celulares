"""
test_multitenant_seguridad.py - Suite de pruebas automatizadas de seguridad y aislamiento Multi-Tenant estricto.
Verifica:
1. Autenticación y Token JWT con claims: user_id, username, rol, tenant_id, sucursal_id, tenant_slug.
2. Bloqueo HTTP 403 Forbidden para usuarios de tenants suspendidos o inactivos (activo = 0 / False).
3. Aislamiento de Equipos: Tenant B no puede listar, consultar por ID, modificar ni eliminar equipos de Tenant A (HTTP 404).
4. Aislamiento de Accesorios y Kardex: Tenant B no puede ver ni modificar inventario de Tenant A (HTTP 404).
5. Aislamiento de Órdenes de Reparación (Taller): Tenant B no puede ver, editar, cambiar estado ni abonar a reparaciones de Tenant A (HTTP 404).
6. Aislamiento de Punto de Venta (POS): Tenant B no puede consultar recibos, notas de crédito ni abonar a créditos de Tenant A (HTTP 404).
7. Prevención de Client Spoofing: Inyección automática de tenant_id y sucursal_id de la sesión autenticada, ignorando parámetros enviados en el body.
8. Aislamiento de Cortes de Caja y Dashboard de Reportes: Totales de ventas, ganancias y efectivo aislados exclusivamente por tienda.
"""

import os
import time
import pytest
import httpx
from app.main import app
from app.database import get_db_connection, init_db, seed_demo_data_if_empty
from app.security import hash_secret, reset_all_rate_limits

init_db()
seed_demo_data_if_empty()

@pytest.fixture(autouse=True)
def clean_rate_limits():
    reset_all_rate_limits()
    yield
    reset_all_rate_limits()

def setup_tenants_and_users():
    """Crea los tenants y usuarios de prueba si no existen."""
    conn = get_db_connection()
    cur = conn.cursor()
    now = "2026-10-21 12:00:00"

    try:
        # 1. Tenant Alfa (Activo)
        cur.execute("SELECT id FROM tenants WHERE slug = 'tienda-alfa' LIMIT 1;")
        row_a = cur.fetchone()
        if not row_a:
            cur.execute("""
                INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
                VALUES ('Celulares Alfa', 'tienda-alfa', 'alfa@test.com', '5511111111', 'pro', 1, ?);
            """, (now,))
            t_alfa_id = cur.lastrowid
            cur.execute("""
                INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
                VALUES (?, 'Alfa Matriz', 'Av Alfa 100', '5511111111', 1, ?);
            """, (t_alfa_id, now))
            s_alfa_id = cur.lastrowid
        else:
            t_alfa_id = row_a["id"]
            cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_alfa_id,))
            s_alfa_id = cur.fetchone()["id"]

        # 2. Tenant Beta (Activo)
        cur.execute("SELECT id FROM tenants WHERE slug = 'tienda-beta' LIMIT 1;")
        row_b = cur.fetchone()
        if not row_b:
            cur.execute("""
                INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
                VALUES ('Reparaciones Beta', 'tienda-beta', 'beta@test.com', '5522222222', 'starter', 1, ?);
            """, (now,))
            t_beta_id = cur.lastrowid
            cur.execute("""
                INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
                VALUES (?, 'Beta Sucursal 1', 'Calle Beta 200', '5522222222', 1, ?);
            """, (t_beta_id, now))
            s_beta_id = cur.lastrowid
        else:
            t_beta_id = row_b["id"]
            cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_beta_id,))
            s_beta_id = cur.fetchone()["id"]

        # 3. Tenant Suspendido (Inactivo)
        cur.execute("SELECT id FROM tenants WHERE slug = 'tienda-suspendida' LIMIT 1;")
        row_s = cur.fetchone()
        if not row_s:
            cur.execute("""
                INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
                VALUES ('Tienda Suspendida', 'tienda-suspendida', 'suspendida@test.com', '5533333333', 'basic', 0, ?);
            """, (now,))
            t_susp_id = cur.lastrowid
            cur.execute("""
                INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
                VALUES (?, 'Matriz Suspendida', 'Calle Nula 0', '5533333333', 1, ?);
            """, (t_susp_id, now))
            s_susp_id = cur.lastrowid
        else:
            t_susp_id = row_s["id"]
            cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_susp_id,))
            s_row = cur.fetchone()
            s_susp_id = s_row["id"] if s_row else 1

        # Crear Usuarios de prueba
        h_a, s_a = hash_secret("AlfaPass123.")
        h_b, s_b = hash_secret("BetaPass123.")
        h_s, s_s = hash_secret("SuspPass123.")

        cur.execute("SELECT id FROM usuarios WHERE username = 'dueno_alfa' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
                VALUES ('Dueño Alfa', 'dueno_alfa', ?, ?, 'dueno', 1, ?, ?, ?);
            """, (h_a, s_a, now, t_alfa_id, s_alfa_id))

        cur.execute("SELECT id FROM usuarios WHERE username = 'dueno_beta' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
                VALUES ('Dueño Beta', 'dueno_beta', ?, ?, 'dueno', 1, ?, ?, ?);
            """, (h_b, s_b, now, t_beta_id, s_beta_id))

        cur.execute("SELECT id FROM usuarios WHERE username = 'dueno_suspendido' LIMIT 1;")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
                VALUES ('Dueño Suspendido', 'dueno_suspendido', ?, ?, 'dueno', 1, ?, ?, ?);
            """, (h_s, s_s, now, t_susp_id, s_susp_id))

        conn.commit()
    finally:
        conn.close()

    return {
        "t_alfa_id": t_alfa_id,
        "s_alfa_id": s_alfa_id,
        "t_beta_id": t_beta_id,
        "s_beta_id": s_beta_id,
        "t_susp_id": t_susp_id,
    }


# ==============================================================================
# TEST 1: AUTENTICACIÓN JWT Y TENANT INACTIVO
# ==============================================================================

@pytest.mark.anyio
async def test_login_jwt_claims_y_bloqueo_tenant_inactivo():
    ids = setup_tenants_and_users()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login exitoso Dueño Alfa
        res_a = await client.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        assert res_a.status_code == 200, res_a.text
        data_a = res_a.json()
        assert data_a["user"]["tenant_id"] == ids["t_alfa_id"]
        assert data_a["user"]["tenant_slug"] == "tienda-alfa"
        assert data_a["user"]["rol"] == "dueno"
        assert "access_token" in data_a

        # 2. Login exitoso Dueño Beta
        res_b = await client.post("/api/auth/login", json={"username": "dueno_beta", "password": "BetaPass123."})
        assert res_b.status_code == 200
        data_b = res_b.json()
        assert data_b["user"]["tenant_id"] == ids["t_beta_id"]
        assert data_b["user"]["tenant_slug"] == "tienda-beta"

        # 3. Login de Tenant Suspendido / Inactivo -> HTTP 403 Forbidden
        res_s = await client.post("/api/auth/login", json={"username": "dueno_suspendido", "password": "SuspPass123."})
        assert res_s.status_code == 403
        assert "suspendida o inactiva" in res_s.text.lower() or "inactiva" in res_s.text.lower()


# ==============================================================================
# TEST 2: AISLAMIENTO DE EQUIPOS (INVENTARIO)
# ==============================================================================

@pytest.mark.anyio
async def test_aislamiento_equipos_entre_tenants():
    setup_tenants_and_users()
    suffix = str(int(time.time() * 1000))[-6:]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_a:
        await client_a.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})

        # Tenant A registra un teléfono
        imei_a = f"351111000{suffix}"
        res_eq_a = await client_a.post("/api/equipos", json={
            "modelo": "iPhone 15 Pro Alfa",
            "capacidad_gb": 128,
            "color": "Titanio Natural",
            "imei": imei_a,
            "costo_compra": 14000.0,
            "precio_venta": 18500.0,
            "grado": "A"
        })
        assert res_eq_a.status_code == 201
        eq_a_id = res_eq_a.json()["id"]

        # Tenant A puede consultarlo
        get_res_a = await client_a.get(f"/api/equipos/{eq_a_id}")
        assert get_res_a.status_code == 200
        assert get_res_a.json()["imei"] == imei_a

        # Ahora Tenant B inicia sesión
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_b:
            await client_b.post("/api/auth/login", json={"username": "dueno_beta", "password": "BetaPass123."})

            # Tenant B lista equipos: el equipo de Alfa NO debe aparecer
            list_b = await client_b.get("/api/equipos")
            assert list_b.status_code == 200
            imeis_en_b = [e["imei"] for e in list_b.json()]
            assert imei_a not in imeis_en_b

            # Tenant B intenta leer por ID el equipo de Tenant A -> HTTP 404
            get_b = await client_b.get(f"/api/equipos/{eq_a_id}")
            assert get_b.status_code == 404

            # Tenant B intenta modificar el precio del equipo de Tenant A -> HTTP 404
            put_b = await client_b.put(f"/api/equipos/{eq_a_id}", json={
                "precio_venta": 1000.0
            })
            assert put_b.status_code == 404

            # Tenant B intenta borrar el equipo de Tenant A -> HTTP 404
            del_b = await client_b.delete(f"/api/equipos/{eq_a_id}")
            assert del_b.status_code == 404

        # Confirmar que para Tenant A el equipo sigue intacto y con su precio original
        check_a = await client_a.get(f"/api/equipos/{eq_a_id}")
        assert check_a.status_code == 200
        assert check_a.json()["precio_venta"] == 18500.0


# ==============================================================================
# TEST 3: AISLAMIENTO DE ACCESORIOS Y AUDITORÍA KARDEX
# ==============================================================================

@pytest.mark.anyio
async def test_aislamiento_accesorios_y_kardex_entre_tenants():
    setup_tenants_and_users()
    suffix = str(int(time.time() * 1000))[-6:]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_a:
        await client_a.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})

        # Tenant A crea un accesorio
        res_acc = await client_a.post("/api/accesorios", json={
            "nombre": f"Funda Silicona Alfa {suffix}",
            "categoria": "Fundas",
            "costo_compra": 50.0,
            "precio_venta": 250.0,
            "stock": 20,
            "es_servicio": False
        })
        assert res_acc.status_code == 201
        acc_a_id = res_acc.json()["id"]

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_b:
            await client_b.post("/api/auth/login", json={"username": "dueno_beta", "password": "BetaPass123."})

            # Tenant B no debe ver el accesorio en su lista
            list_acc_b = await client_b.get("/api/accesorios")
            assert list_acc_b.status_code == 200
            nombres_b = [a["nombre"] for a in list_acc_b.json()]
            assert f"Funda Silicona Alfa {suffix}" not in nombres_b

            # Tenant B no puede consultarlo por ID -> HTTP 404
            assert (await client_b.get(f"/api/accesorios/{acc_a_id}")).status_code == 404

            # Tenant B no puede editarlo -> HTTP 404
            assert (await client_b.put(f"/api/accesorios/{acc_a_id}", json={"stock": 999})).status_code == 404

            # Tenant B no puede ajustar su stock -> HTTP 404
            assert (await client_b.post(f"/api/accesorios/{acc_a_id}/ajuste-stock", json={
                "nuevo_stock": 0,
                "tipo_movimiento": "MERMA",
                "motivo": "Intento ataque cross-tenant"
            })).status_code == 404

            # Tenant B no puede eliminarlo -> HTTP 404
            assert (await client_b.delete(f"/api/accesorios/{acc_a_id}")).status_code == 404


# ==============================================================================
# TEST 4: AISLAMIENTO DE TALLER / REPARACIONES
# ==============================================================================

@pytest.mark.anyio
async def test_aislamiento_reparaciones_entre_tenants():
    setup_tenants_and_users()
    suffix = str(int(time.time() * 1000))[-6:]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_a:
        await client_a.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})

        # Tenant A registra una orden de reparación
        res_rep = await client_a.post("/api/reparaciones", json={
            "cliente_nombre": f"Cliente Alfa {suffix}",
            "cliente_telefono": f"5512{suffix}",
            "dispositivo_modelo": "Galaxy A54 Alfa",
            "imei_serie": f"998877{suffix}",
            "falla_reportada": "Centro de carga dañado",
            "precio_servicio": 800.0,
            "anticipo": 200.0
        })
        assert res_rep.status_code == 201
        rep_a_id = res_rep.json()["id"]

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_b:
            await client_b.post("/api/auth/login", json={"username": "dueno_beta", "password": "BetaPass123."})

            # Tenant B no la ve en su lista
            list_rep_b = await client_b.get("/api/reparaciones")
            assert list_rep_b.status_code == 200
            ids_rep_b = [r["id"] for r in list_rep_b.json()]
            assert rep_a_id not in ids_rep_b

            # Tenant B no puede consultar por ID -> HTTP 404
            assert (await client_b.get(f"/api/reparaciones/{rep_a_id}")).status_code == 404

            # Tenant B no puede cambiarle el estado -> HTTP 404
            assert (await client_b.patch(f"/api/reparaciones/{rep_a_id}/estado?nuevo_estado=Entregado")).status_code == 404

            # Tenant B no puede abonar dinero a la orden de Alfa -> HTTP 404
            assert (await client_b.post(f"/api/reparaciones/{rep_a_id}/abono", json={"monto_abono": 600.0})).status_code == 404

            # Tenant B no puede borrarla -> HTTP 404
            assert (await client_b.delete(f"/api/reparaciones/{rep_a_id}")).status_code == 404


# ==============================================================================
# TEST 5: PREVENCIÓN DE CLIENT SPOOFING & AISLAMIENTO DE VENTAS Y CRÉDITOS
# ==============================================================================

@pytest.mark.anyio
async def test_prevencion_spoofing_y_aislamiento_ventas_pos():
    ids = setup_tenants_and_users()
    suffix = str(int(time.time() * 1000))[-6:]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_a:
        await client_a.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})

        # 1. Anti-Spoofing: Tenant A envía en el body un tenant_id manipulado (ej. 99999 o el de Beta)
        imei = f"3588776655{suffix}"
        res_spoof = await client_a.post("/api/equipos", json={
            "modelo": "Equipo Anti Spoofing",
            "capacidad_gb": 64,
            "color": "Azul",
            "imei": imei,
            "grado": "A",
            "costo_compra": 2000.0,
            "precio_venta": 3500.0,
            "tenant_id": 99999,  # Intento de spoofing
            "sucursal_id": 99999
        })
        assert res_spoof.status_code == 201
        eq_id = res_spoof.json()["id"]

        # Validar directamente en base de datos que el tenant_id asignado es el de Alfa, NO 99999
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT tenant_id FROM equipos WHERE id = ?;", (eq_id,))
        saved_row = c.fetchone()
        conn.close()
        assert saved_row["tenant_id"] == ids["t_alfa_id"]
        assert saved_row["tenant_id"] != 99999

        # 2. Venta a Crédito en Tenant A
        res_venta = await client_a.post("/api/pos/vender", json={
            "items": [{"equipo_id": eq_id, "precio_final": 3500.0}],
            "cliente_nombre": f"Comprador Alfa {suffix}",
            "cliente_telefono": f"5588{suffix}",
            "metodo_pago": "Nota de Crédito",
            "es_credito": True,
            "plazo_dias": 15,
            "monto_anticipo": 500.0,
            "notas": "Venta prueba aislamiento"
        })
        assert res_venta.status_code == 201
        venta_a_id = res_venta.json()["id"]

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_b:
            await client_b.post("/api/auth/login", json={"username": "dueno_beta", "password": "BetaPass123."})

            # Tenant B intenta ver el recibo de venta de Tenant A -> HTTP 404
            rec_b = await client_b.get(f"/api/pos/recibo/{venta_a_id}")
            assert rec_b.status_code == 404

            # Tenant B intenta abonar al crédito de Tenant A -> HTTP 404
            abono_b = await client_b.post(f"/api/pos/creditos/{venta_a_id}/abono", json={
                "monto": 3000.0,
                "metodo_pago": "Efectivo"
            })
            assert abono_b.status_code == 404

            # Tenant B lista notas de crédito -> NO debe aparecer la venta de Alfa
            cred_b = await client_b.get("/api/pos/creditos")
            assert cred_b.status_code == 200
            notas_b_ids = [n["id"] for n in cred_b.json().get("notas", [])]
            assert venta_a_id not in notas_b_ids


# ==============================================================================
# TEST 6: AISLAMIENTO ESTRICTO DE CORTES DE CAJA Y DASHBOARD FINANCIERO
# ==============================================================================

@pytest.mark.anyio
async def test_aislamiento_corte_caja_y_reportes_dashboard():
    setup_tenants_and_users()
    suffix = str(int(time.time() * 1000))[-6:]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_a:
        await client_a.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        # Resetear turno actual de Alfa
        res_reset_a = await client_a.post("/api/caja/corte", json={"efectivo_declarado": 0.0, "notas": "Cierre turno previo"})
        assert res_reset_a.status_code == 201
        time.sleep(1.05)

        # Tenant A crea y vende accesorio de $5,000 en Efectivo
        acc_a = (await client_a.post("/api/accesorios", json={
            "nombre": f"Item Alfa $5000 {suffix}",
            "categoria": "Fundas",
            "costo_compra": 2000.0,
            "precio_venta": 5000.0,
            "stock": 10,
            "es_servicio": False
        })).json()

        v_a = await client_a.post("/api/pos/vender", json={
            "items": [{"accesorio_id": acc_a["id"], "cantidad": 1, "precio_final": 5000.0}],
            "cliente_nombre": "Cliente Alfa Efectivo",
            "cliente_telefono": f"5501{suffix}",
            "metodo_pago": "Efectivo",
            "monto_efectivo": 5000.0
        })
        assert v_a.status_code == 201

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_b:
        await client_b.post("/api/auth/login", json={"username": "dueno_beta", "password": "BetaPass123."})
        # Resetear turno actual de Beta
        res_reset_b = await client_b.post("/api/caja/corte", json={"efectivo_declarado": 0.0, "notas": "Cierre turno previo"})
        assert res_reset_b.status_code == 201
        time.sleep(1.05)

        # Tenant B crea y vende accesorio de $1,200 en Efectivo
        acc_b = (await client_b.post("/api/accesorios", json={
            "nombre": f"Item Beta $1200 {suffix}",
            "categoria": "Cables",
            "costo_compra": 300.0,
            "precio_venta": 1200.0,
            "stock": 10,
            "es_servicio": False
        })).json()

        v_b = await client_b.post("/api/pos/vender", json={
            "items": [{"accesorio_id": acc_b["id"], "cantidad": 1, "precio_final": 1200.0}],
            "cliente_nombre": "Cliente Beta Efectivo",
            "cliente_telefono": f"5502{suffix}",
            "metodo_pago": "Efectivo",
            "monto_efectivo": 1200.0
        })
        assert v_b.status_code == 201

        # 1. Verificar Resumen de Corte de Caja de Tenant B: debe tener exactamente $1,200 (NO $6,200)
        corte_b = (await client_b.get("/api/caja/resumen-actual")).json()
        assert corte_b["total_efectivo"] == 1200.0
        assert corte_b["total_ventas"] == 1200.0

    # 2. Verificar Resumen de Corte de Caja de Tenant A: debe tener exactamente $5,000 (NO $6,200)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_a:
        await client_a.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})
        corte_a = (await client_a.get("/api/caja/resumen-actual")).json()
        assert corte_a["total_efectivo"] == 5000.0
        assert corte_a["total_ventas"] == 5000.0

        # Dashboard de Tenant A
        dash_a = (await client_a.get("/api/reportes/dashboard")).json()
        assert dash_a["total_ventas_mes"] >= 5000.0


# ==============================================================================
# TEST 7: AISLAMIENTO DE CLIENTES Y GARANTÍAS
# ==============================================================================

@pytest.mark.anyio
async def test_aislamiento_clientes_y_garantias():
    setup_tenants_and_users()
    suffix = str(int(time.time() * 1000))[-6:]
    tel_alfa = f"5599{suffix}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_a:
        await client_a.post("/api/auth/login", json={"username": "dueno_alfa", "password": "AlfaPass123."})

        # Tenant A vende para registrar el cliente en su tenant
        acc_a = (await client_a.post("/api/accesorios", json={
            "nombre": f"Audífonos Alfa {suffix}",
            "categoria": "Audio",
            "costo_compra": 50.0,
            "precio_venta": 150.0,
            "stock": 5,
            "es_servicio": False
        })).json()

        await client_a.post("/api/pos/vender", json={
            "items": [{"accesorio_id": acc_a["id"], "cantidad": 1, "precio_final": 150.0}],
            "cliente_nombre": f"Cliente Exclusivo Alfa {suffix}",
            "cliente_telefono": tel_alfa,
            "metodo_pago": "Efectivo",
            "monto_efectivo": 150.0
        })

        # Tenant A encuentra el cliente
        c_a = await client_a.get(f"/api/clientes/buscar-telefono?telefono={tel_alfa}")
        assert c_a.status_code == 200
        assert c_a.json() is not None
        assert c_a.json()["telefono"] == tel_alfa

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client_b:
        await client_b.post("/api/auth/login", json={"username": "dueno_beta", "password": "BetaPass123."})

        # Tenant B busca el mismo teléfono y NO debe encontrarlo (aislado por tenant_id)
        c_b = await client_b.get(f"/api/clientes/buscar-telefono?telefono={tel_alfa}")
        assert c_b.status_code == 200
        assert c_b.json() is None

        # Tenant B lista clientes: no debe aparecer el cliente de Alfa
        lista_b = (await client_b.get("/api/clientes")).json()
        telefonos_b = [cl["telefono"] for cl in lista_b]
        assert tel_alfa not in telefonos_b
