import os
import pytest
from app import database, models
from app.postgres_client import _convert_sql_for_postgres, PostgresRow

@pytest.fixture(autouse=True)
def setup_db():
    database.init_db()

def test_multitenant_tablas_y_demo_tenant():
    """Verifica que las tablas maestras multi-tenant existan y que el tenant de prueba esté creado."""
    conn = database.get_db_connection()
    cur = conn.cursor()

    # 1. Verificar existencia de tablas maestras
    cur.execute("SELECT id, nombre_comercial, slug, plan, activo FROM tenants WHERE slug = 'demo-celulares';")
    tenant = cur.fetchone()
    assert tenant is not None, "El tenant 'demo-celulares' no fue creado"
    assert tenant["nombre_comercial"] == "Demostración Celulares"
    assert tenant["plan"] == "pro"
    assert tenant["activo"] in (1, True)

    tenant_id = tenant["id"]

    # 2. Verificar sucursal matriz
    cur.execute("SELECT id, nombre_sucursal, es_matriz FROM sucursales WHERE tenant_id = ? AND es_matriz = 1;", (tenant_id,))
    sucursal = cur.fetchone()
    assert sucursal is not None, "La sucursal matriz no fue creada"
    assert "Matriz" in sucursal["nombre_sucursal"]

    # 3. Verificar configuración de tienda
    cur.execute("SELECT id, encabezado_ticket, pie_ticket_garantia FROM configuracion_tienda WHERE tenant_id = ?;", (tenant_id,))
    config = cur.fetchone()
    assert config is not None, "La configuración de tienda no fue creada"
    assert config["encabezado_ticket"] is not None

    # 4. Verificar columnas tenant_id y sucursal_id en tablas transaccionales
    tablas_verificar = ['equipos', 'ventas', 'reparaciones', 'accesorios', 'cortes_caja']
    for t in tablas_verificar:
        cur.execute(f"PRAGMA table_info({t});")
        cols = [r["name"] for r in cur.fetchall()]
        assert "tenant_id" in cols, f"Columna tenant_id ausente en tabla {t}"
        assert "sucursal_id" in cols, f"Columna sucursal_id ausente en tabla {t}"

    conn.close()

def test_pydantic_modelos_multitenant():
    """Verifica la validación estricta de los modelos Pydantic de Tenants, Sucursales y Configuración."""
    # Tenant Create
    t = models.TenantCreate(
        nombre_comercial="Tienda Móvil Express",
        slug="tienda-movil-express",
        email_contacto="express@tienda.com",
        telefono="5512345678",
        plan="pro"
    )
    assert t.slug == "tienda-movil-express"
    assert t.activo is True

    # Slug con espacios se normaliza con guiones
    t2 = models.TenantCreate(
        nombre_comercial="Tienda Centro",
        slug="Tienda Centro CDMX",
        plan="basico"
    )
    assert t2.slug == "tienda-centro-cdmx"

    # Sucursal Create
    s = models.SucursalCreate(
        tenant_id=1,
        nombre_sucursal="Sucursal Plaza Satélite",
        direccion="Circuito Centro Comercial 2251",
        telefono="5555555555",
        es_matriz=False
    )
    assert s.tenant_id == 1
    assert s.es_matriz is False

    # Configuración Tienda Create
    cfg = models.ConfiguracionTiendaCreate(
        tenant_id=1,
        encabezado_ticket="Celulares & Más | Calidad Garantizada",
        pie_ticket_garantia="30 días de garantía en placa base.",
        whatsapp_notificaciones="525512345678"
    )
    assert cfg.tenant_id == 1
    assert "Garantizada" in cfg.encabezado_ticket

def test_postgres_sql_converter_placeholders_y_tipos():
    """Verifica que el traductor SQL convierta '?' a '%s', autoincrement a serial y fechas sqlite a postgres."""
    sql_sqlite = "SELECT * FROM ventas WHERE id = ? AND notas != '¿Pregunta?' AND total > ?"
    sql_pg = _convert_sql_for_postgres(sql_sqlite)
    assert "id = %s" in sql_pg
    assert "total > %s" in sql_pg
    assert "'¿Pregunta?'" in sql_pg, "No debe alterar los signos de interrogación dentro de literales"

    sql_create = "CREATE TABLE test (id INTEGER PRIMARY KEY AUTOINCREMENT, modelo TEXT NOT NULL);"
    sql_create_pg = _convert_sql_for_postgres(sql_create)
    assert "id SERIAL PRIMARY KEY" in sql_create_pg

    sql_fechas = "SELECT * FROM ventas v WHERE date(v.fecha_venta) >= date('now', 'localtime') AND date(v.fecha_venta) >= date('now', '-30 days', 'localtime')"
    sql_fechas_pg = _convert_sql_for_postgres(sql_fechas)
    assert "CURRENT_DATE" in sql_fechas_pg
    assert "(CURRENT_DATE - INTERVAL '30 days')" in sql_fechas_pg

def test_postgres_row_interface():
    """Verifica que PostgresRow emule exactamente a sqlite3.Row / dict."""
    row = PostgresRow(cols=["id", "nombre_comercial", "activo"], values=[101, "Celulares Alfa", True])
    # Acceso por índice
    assert row[0] == 101
    assert row[1] == "Celulares Alfa"
    # Acceso por nombre
    assert row["id"] == 101
    assert row["nombre_comercial"] == "Celulares Alfa"
    # Acceso case-insensitive
    assert row["NOMBRE_COMERCIAL"] == "Celulares Alfa"
    # Conversión a dict nativo
    d = dict(row)
    assert d == {"id": 101, "nombre_comercial": "Celulares Alfa", "activo": True}
    assert row.get("inexistente", 999) == 999

def test_postgres_detection():
    """Verifica que is_postgres_enabled detecte correctamente DATABASE_URL."""
    orig = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/testdb"
        assert database.is_postgres_enabled() is True

        os.environ["DATABASE_URL"] = "postgres://supabase_admin:secret@aws-0.supabase.com:5432/postgres"
        assert database.is_postgres_enabled() is True

        os.environ["DATABASE_URL"] = ""
        assert database.is_postgres_enabled() is False
    finally:
        if orig is not None:
            os.environ["DATABASE_URL"] = orig
        elif "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
