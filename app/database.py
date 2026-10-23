import sqlite3
import os
import re
import tempfile
from datetime import datetime

# Validador de identificadores SQL para evitar inyección en DDL dinámico
_SQL_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

def _validate_sql_identifier(ident: str) -> str:
    """Valida que un identificador SQL (tabla, columna o índice) sea seguro contra inyección SQL."""
    if not ident or not _SQL_IDENT_RE.match(ident):
        raise ValueError(f"Identificador SQL inválido: '{ident}'")
    return ident

# Cargar variables de entorno desde .env si existe
_env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_file):
    try:
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'").strip('"'))
    except Exception:
        pass


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

def is_postgres_enabled() -> bool:
    """Retorna True si DATABASE_URL está configurada para PostgreSQL / Supabase."""
    raw = os.environ.get("DATABASE_URL", "").strip()
    return bool(raw and (
        raw.startswith("postgresql://") or
        raw.startswith("postgres://") or
        raw.startswith("postgresql+psycopg2://")
    ))

TURSO_URL = os.environ.get("TURSO_DATABASE_URL") or os.environ.get("TURSO_URL") or (DATABASE_URL if not is_postgres_enabled() else "")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN") or os.environ.get("TURSO_TOKEN") or os.environ.get("DATABASE_AUTH_TOKEN")

def is_turso_enabled() -> bool:
    """Retorna True si las credenciales de Turso Cloud están configuradas y no es Postgres."""
    if is_postgres_enabled():
        return False
    return bool(TURSO_URL and TURSO_TOKEN and ("turso.io" in TURSO_URL or "libsql:" in TURSO_URL))

def verificar_guarda_anti_destruccion(operacion: str = "") -> None:
    """
    Guarda de Seguridad Anti-Destrucción:
    Prohíbe estrictamente cualquier operación destructiva de base de datos
    (DROP TABLE, TRUNCATE, DELETE masivo o reseteo de esquemas) si ENVIRONMENT == 'production'
    o si is_postgres_enabled() es True (Supabase / Render / Postgres en producción).
    """
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("ENV") or "").strip().lower()
    es_produccion = env in ("production", "prod") or bool(os.environ.get("RENDER"))
    if es_produccion or is_postgres_enabled():
        raise RuntimeError(
            f"GUARDA DE SEGURIDAD ANTI-DESTRUCCIÓN: La operación '{operacion}' está estrictamente "
            f"bloqueada para proteger la integridad de datos en producción y bases de datos activas."
        )

def _resolve_sqlite_path() -> str:
    """Resuelve la ruta de SQLite verificando soporte de bloqueo de archivos (compatible con contenedores y montajes FUSE)."""
    explicit = os.environ.get("DATABASE_PATH")
    if explicit:
        return explicit
    if is_turso_enabled() or is_postgres_enabled():
        return os.path.join(tempfile.gettempdir(), "inventario.db")

    default_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inventario.db")
    try:
        conn = sqlite3.connect(default_path, timeout=5.0)
        conn.execute("CREATE TABLE IF NOT EXISTS _health_lock_check (id INTEGER PRIMARY KEY);")
        conn.commit()
        conn.close()
        return default_path
    except Exception:
        try:
            if os.path.exists(default_path) and os.path.getsize(default_path) == 0:
                os.remove(default_path)
        except Exception:
            pass
        return os.path.join(tempfile.gettempdir(), "inventario.db")


DATABASE_FILE = _resolve_sqlite_path()

def get_db_connection(tenant_id: Optional[int] = None):
    """
    Retorna:
    1. Conexión pooled a PostgreSQL si DATABASE_URL empieza con postgresql / postgres.
       Si se proporciona tenant_id, configura la variable de sesión 'app.current_tenant_id'
       para activar automáticamente las políticas de Row Level Security (RLS).
    2. Conexión a Turso Cloud si está configurada.
    3. Conexión local a SQLite ('inventario.db') con WAL y busy_timeout como fallback.
    """
    if is_postgres_enabled():
        from app.postgres_client import get_postgres_connection
        conn = get_postgres_connection()
        if tenant_id is not None:
            try:
                conn.execute("SELECT set_config('app.current_tenant_id', %s, false);", (str(tenant_id),))
            except Exception:
                pass
        return conn

    if is_turso_enabled():
        from app.turso_client import TursoConnection
        return TursoConnection(TURSO_URL, TURSO_TOKEN)

    conn = sqlite3.connect(DATABASE_FILE, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass
    return conn

def _init_postgres_db(conn, cursor):
    """
    Crea automáticamente todas las tablas maestras y transaccionales para PostgreSQL
    (compatible con Supabase, Render y AWS RDS).
    Garantiza que todas las tablas y columnas existan antes de ejecutar cualquier consulta.
    """
    stmts = [
        # Extensiones recomendadas
        'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";',
        'CREATE EXTENSION IF NOT EXISTS "pgcrypto";',

        # 1. Tablas Maestras Multi-Tenant
        """CREATE TABLE IF NOT EXISTS tenants (
            id SERIAL PRIMARY KEY,
            nombre_comercial VARCHAR(150) NOT NULL,
            slug VARCHAR(60) UNIQUE NOT NULL,
            email_contacto VARCHAR(120),
            telefono VARCHAR(30),
            plan VARCHAR(50) NOT NULL DEFAULT 'basico',
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            fecha_creacion TEXT NOT NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);",
        "CREATE INDEX IF NOT EXISTS idx_tenants_activo ON tenants(activo);",

        """CREATE TABLE IF NOT EXISTS sucursales (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            nombre_sucursal VARCHAR(100) NOT NULL,
            direccion VARCHAR(255),
            telefono VARCHAR(30),
            es_matriz BOOLEAN NOT NULL DEFAULT TRUE,
            fecha_registro TEXT NOT NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_sucursales_tenant ON sucursales(tenant_id);",

        """CREATE TABLE IF NOT EXISTS configuracion_tienda (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
            logo_url VARCHAR(500),
            encabezado_ticket VARCHAR(300),
            pie_ticket_garantia VARCHAR(500),
            whatsapp_notificaciones VARCHAR(30),
            fecha_actualizacion TEXT NOT NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_config_tienda_tenant ON configuracion_tienda(tenant_id);",

        # 2. Clientes
        """CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(150) NOT NULL,
            telefono VARCHAR(30) NOT NULL,
            fecha_registro TEXT NOT NULL,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE
        );""",
        "CREATE INDEX IF NOT EXISTS idx_clientes_tenant ON clientes(tenant_id);",

        # 3. Equipos
        """CREATE TABLE IF NOT EXISTS equipos (
            id SERIAL PRIMARY KEY,
            modelo VARCHAR(150) NOT NULL,
            capacidad_gb INTEGER NOT NULL,
            color VARCHAR(60) NOT NULL,
            imei VARCHAR(40) UNIQUE NOT NULL,
            grado VARCHAR(10) NOT NULL,
            costo_compra DOUBLE PRECISION NOT NULL,
            precio_venta DOUBLE PRECISION NOT NULL,
            estado VARCHAR(40) NOT NULL DEFAULT 'Disponible',
            fecha_registro TEXT NOT NULL,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
            sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_equipos_tenant_sucursal ON equipos(tenant_id, sucursal_id);",

        # 4. Ventas
        """CREATE TABLE IF NOT EXISTS ventas (
            id SERIAL PRIMARY KEY,
            equipo_id INTEGER,
            cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
            precio_final DOUBLE PRECISION NOT NULL,
            margen_ganancia DOUBLE PRECISION NOT NULL,
            fecha_venta TEXT NOT NULL,
            metodo_pago VARCHAR(50) NOT NULL DEFAULT 'Efectivo',
            monto_efectivo DOUBLE PRECISION NOT NULL DEFAULT 0,
            monto_transferencia DOUBLE PRECISION NOT NULL DEFAULT 0,
            monto_tarjeta DOUBLE PRECISION NOT NULL DEFAULT 0,
            monto_garantia DOUBLE PRECISION NOT NULL DEFAULT 0,
            notas TEXT,
            es_credito INTEGER NOT NULL DEFAULT 0,
            plazo_dias INTEGER NOT NULL DEFAULT 0,
            fecha_vencimiento TEXT,
            monto_credito DOUBLE PRECISION NOT NULL DEFAULT 0,
            monto_anticipo DOUBLE PRECISION NOT NULL DEFAULT 0,
            saldo_pendiente DOUBLE PRECISION NOT NULL DEFAULT 0,
            estado_credito VARCHAR(40),
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
            sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_ventas_tenant_sucursal ON ventas(tenant_id, sucursal_id);",

        # 5. Abonos Ventas Crédito
        """CREATE TABLE IF NOT EXISTS abonos_ventas_credito (
            id SERIAL PRIMARY KEY,
            venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
            monto DOUBLE PRECISION NOT NULL,
            fecha TEXT NOT NULL,
            metodo_pago VARCHAR(50) NOT NULL DEFAULT 'Efectivo',
            notas TEXT,
            usuario VARCHAR(100),
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE
        );""",
        "CREATE INDEX IF NOT EXISTS idx_abonos_venta_id ON abonos_ventas_credito(venta_id);",

        # 6. Venta Items
        """CREATE TABLE IF NOT EXISTS venta_items (
            id SERIAL PRIMARY KEY,
            venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
            equipo_id INTEGER REFERENCES equipos(id) ON DELETE SET NULL,
            accesorio_id INTEGER,
            tipo_item VARCHAR(40) NOT NULL DEFAULT 'equipo',
            nombre_item VARCHAR(150),
            cantidad INTEGER NOT NULL DEFAULT 1,
            precio_final DOUBLE PRECISION NOT NULL,
            costo_compra DOUBLE PRECISION NOT NULL,
            margen_ganancia DOUBLE PRECISION NOT NULL,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE
        );""",
        "CREATE INDEX IF NOT EXISTS idx_venta_items_venta ON venta_items(venta_id);",

        # 7. Garantías
        """CREATE TABLE IF NOT EXISTS garantias (
            id SERIAL PRIMARY KEY,
            venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE RESTRICT,
            equipo_id INTEGER NOT NULL REFERENCES equipos(id) ON DELETE RESTRICT,
            cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
            fecha_devolucion TEXT NOT NULL,
            motivo TEXT NOT NULL,
            falla_descripcion TEXT,
            estado_equipo_recibido VARCHAR(40) NOT NULL DEFAULT 'En Garantia',
            solucion VARCHAR(40) NOT NULL DEFAULT 'Reemplazo',
            equipo_reemplazo_id INTEGER REFERENCES equipos(id) ON DELETE SET NULL,
            monto_cubierto DOUBLE PRECISION NOT NULL DEFAULT 0,
            notas TEXT,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
            sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_garantias_tenant ON garantias(tenant_id);",

        # 8. Accesorios
        """CREATE TABLE IF NOT EXISTS accesorios (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(150) NOT NULL,
            categoria VARCHAR(60) NOT NULL DEFAULT 'Accesorio',
            codigo_barras VARCHAR(60),
            costo_compra DOUBLE PRECISION NOT NULL DEFAULT 0,
            precio_venta DOUBLE PRECISION NOT NULL DEFAULT 0,
            precio_mayoreo DOUBLE PRECISION NOT NULL DEFAULT 0,
            precio_20_pzs DOUBLE PRECISION NOT NULL DEFAULT 0,
            precio_caja DOUBLE PRECISION NOT NULL DEFAULT 0,
            imagen_url VARCHAR(500),
            color VARCHAR(60),
            stock INTEGER NOT NULL DEFAULT 0,
            es_servicio INTEGER NOT NULL DEFAULT 0,
            fecha_registro TEXT NOT NULL,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
            sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_accesorios_tenant_sucursal ON accesorios(tenant_id, sucursal_id);",

        # 9. Cortes de Caja
        """CREATE TABLE IF NOT EXISTS cortes_caja (
            id SERIAL PRIMARY KEY,
            fecha_corte TEXT,
            fecha_inicio_periodo TEXT,
            total_ventas DOUBLE PRECISION NOT NULL DEFAULT 0,
            total_efectivo DOUBLE PRECISION NOT NULL DEFAULT 0,
            total_transferencia DOUBLE PRECISION NOT NULL DEFAULT 0,
            total_garantia DOUBLE PRECISION NOT NULL DEFAULT 0,
            efectivo_declarado DOUBLE PRECISION NOT NULL DEFAULT 0,
            diferencia DOUBLE PRECISION NOT NULL DEFAULT 0,
            cantidad_ventas INTEGER NOT NULL DEFAULT 0,
            notas TEXT,
            fecha_registro TEXT,
            fecha_hora TEXT,
            monto_efectivo DOUBLE PRECISION DEFAULT 0,
            monto_transferencia DOUBLE PRECISION DEFAULT 0,
            monto_tarjeta DOUBLE PRECISION DEFAULT 0,
            efectivo_esperado DOUBLE PRECISION DEFAULT 0,
            efectivo_real DOUBLE PRECISION DEFAULT 0,
            usuario VARCHAR(100) DEFAULT 'Admin',
            equipos_vendidos INTEGER NOT NULL DEFAULT 0,
            accesorios_vendidos INTEGER NOT NULL DEFAULT 0,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
            sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_cortes_caja_tenant_sucursal ON cortes_caja(tenant_id, sucursal_id);",

        # 10. Vista caja_cortes
        "CREATE OR REPLACE VIEW caja_cortes AS SELECT * FROM cortes_caja;",

        # 11. Reparaciones
        """CREATE TABLE IF NOT EXISTS reparaciones (
            id SERIAL PRIMARY KEY,
            folio VARCHAR(40) UNIQUE NOT NULL,
            cliente_nombre VARCHAR(150) NOT NULL,
            cliente_telefono VARCHAR(40) NOT NULL,
            dispositivo_modelo VARCHAR(150) NOT NULL,
            color VARCHAR(60),
            imei_serie VARCHAR(60),
            codigo_patron VARCHAR(100),
            falla_reportada TEXT NOT NULL,
            diagnostico_tecnico TEXT,
            condicion_recepcion TEXT,
            checklist_recepcion TEXT,
            costo_refaccion DOUBLE PRECISION NOT NULL DEFAULT 0,
            precio_servicio DOUBLE PRECISION NOT NULL DEFAULT 0,
            anticipo DOUBLE PRECISION NOT NULL DEFAULT 0,
            saldo_pendiente DOUBLE PRECISION NOT NULL DEFAULT 0,
            estado VARCHAR(40) NOT NULL DEFAULT 'Recibido',
            tecnico_responsable VARCHAR(100) DEFAULT 'Samuel N.',
            notas TEXT,
            fecha_ingreso TEXT NOT NULL,
            fecha_prometida TEXT,
            fecha_entrega TEXT,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
            sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_reparaciones_tenant_sucursal ON reparaciones(tenant_id, sucursal_id);",

        # 12. Usuarios
        """CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(150) NOT NULL,
            username VARCHAR(60) UNIQUE NOT NULL,
            pin_hash VARCHAR(255) NOT NULL,
            salt VARCHAR(100) NOT NULL,
            rol VARCHAR(40) NOT NULL DEFAULT 'vendedor',
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            fecha_creacion TEXT NOT NULL,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
            sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_usuarios_tenant_sucursal ON usuarios(tenant_id, sucursal_id);",

        # 13. Historiales
        """CREATE TABLE IF NOT EXISTS garantias_historial (
            id SERIAL PRIMARY KEY,
            garantia_id INTEGER REFERENCES garantias(id) ON DELETE CASCADE,
            estado_anterior VARCHAR(50),
            estado_nuevo VARCHAR(50),
            fecha_cambio TEXT NOT NULL,
            usuario VARCHAR(100),
            observaciones TEXT,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE
        );""",

        """CREATE TABLE IF NOT EXISTS historial_ventas_cambios (
            id SERIAL PRIMARY KEY,
            venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
            campo_modificado VARCHAR(100) NOT NULL,
            valor_anterior TEXT,
            valor_nuevo TEXT,
            usuario VARCHAR(100) NOT NULL,
            fecha_modificacion TEXT NOT NULL,
            motivo TEXT,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE
        );""",

        # 14. Movimientos Stock Accesorios
        """CREATE TABLE IF NOT EXISTS movimientos_stock_accesorios (
            id SERIAL PRIMARY KEY,
            accesorio_id INTEGER NOT NULL REFERENCES accesorios(id) ON DELETE CASCADE,
            tipo_movimiento VARCHAR(40) NOT NULL,
            cantidad INTEGER NOT NULL,
            stock_anterior INTEGER NOT NULL,
            stock_nuevo INTEGER NOT NULL,
            motivo TEXT,
            usuario VARCHAR(100),
            fecha TEXT NOT NULL,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE
        );""",
        "CREATE INDEX IF NOT EXISTS idx_mov_stock_tenant ON movimientos_stock_accesorios(tenant_id);",

        # 15. Gastos Operativos de Sucursal
        """CREATE TABLE IF NOT EXISTS gastos (
            id SERIAL PRIMARY KEY,
            concepto VARCHAR(200) NOT NULL,
            categoria VARCHAR(60) NOT NULL DEFAULT 'General',
            monto DOUBLE PRECISION NOT NULL,
            fecha TEXT NOT NULL,
            metodo_pago VARCHAR(50) NOT NULL DEFAULT 'Efectivo',
            comprobante_url VARCHAR(500),
            usuario VARCHAR(100) NOT NULL DEFAULT 'Admin',
            notas TEXT,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
            sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL
        );""",
        "CREATE INDEX IF NOT EXISTS idx_gastos_tenant_sucursal ON gastos(tenant_id, sucursal_id);",
        "CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);"
    ]

    def _safe_exec(sql_cmd: str, params: Optional[Any] = None) -> bool:
        try:
            if params is not None:
                cursor.execute(sql_cmd, params)
            else:
                cursor.execute(sql_cmd)
            conn.commit()
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False

    for stmt in stmts:
        _safe_exec(stmt)

    # Añadir columnas tenant_id / sucursal_id si no existen en caso de tablas existentes
    column_checks = [
        ("equipos", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("equipos", "sucursal_id", "INTEGER REFERENCES sucursales(id) ON DELETE SET NULL"),
        ("ventas", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("ventas", "sucursal_id", "INTEGER REFERENCES sucursales(id) ON DELETE SET NULL"),
        ("reparaciones", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("reparaciones", "sucursal_id", "INTEGER REFERENCES sucursales(id) ON DELETE SET NULL"),
        ("reparaciones", "checklist_recepcion", "TEXT"),
        ("gastos", "metodo_pago", "VARCHAR(50) DEFAULT 'Efectivo'"),
        ("gastos", "comprobante_url", "VARCHAR(500)"),
        ("gastos", "usuario", "VARCHAR(100) DEFAULT 'Admin'"),
        ("gastos", "notas", "TEXT"),
        ("gastos", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("gastos", "sucursal_id", "INTEGER REFERENCES sucursales(id) ON DELETE SET NULL"),
        ("accesorios", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("accesorios", "sucursal_id", "INTEGER REFERENCES sucursales(id) ON DELETE SET NULL"),
        ("accesorios", "imagen_url", "VARCHAR(500)"),
        ("accesorios", "precio_20_pzs", "DOUBLE PRECISION DEFAULT 0"),
        ("accesorios", "precio_caja", "DOUBLE PRECISION DEFAULT 0"),
        ("accesorios", "color", "VARCHAR(60)"),
        ("cortes_caja", "fecha_corte", "TEXT"),
        ("cortes_caja", "fecha_inicio_periodo", "TEXT"),
        ("cortes_caja", "total_ventas", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "total_efectivo", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "total_transferencia", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "total_garantia", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "efectivo_declarado", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "diferencia", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "cantidad_ventas", "INTEGER DEFAULT 0"),
        ("cortes_caja", "fecha_registro", "TEXT"),
        ("cortes_caja", "fecha_hora", "TEXT"),
        ("cortes_caja", "monto_efectivo", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "monto_transferencia", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "monto_tarjeta", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "efectivo_esperado", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "efectivo_real", "DOUBLE PRECISION DEFAULT 0"),
        ("cortes_caja", "usuario", "VARCHAR(100) DEFAULT 'Admin'"),
        ("cortes_caja", "equipos_vendidos", "INTEGER DEFAULT 0"),
        ("cortes_caja", "accesorios_vendidos", "INTEGER DEFAULT 0"),
        ("cortes_caja", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("cortes_caja", "sucursal_id", "INTEGER REFERENCES sucursales(id) ON DELETE SET NULL"),
        ("clientes", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("usuarios", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("usuarios", "sucursal_id", "INTEGER REFERENCES sucursales(id) ON DELETE SET NULL"),
        ("movimientos_stock_accesorios", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("garantias_historial", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("garantias_historial", "equipo_id", "INTEGER REFERENCES equipos(id) ON DELETE CASCADE"),
        ("historial_ventas_cambios", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("venta_items", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
        ("abonos_ventas_credito", "tenant_id", "INTEGER REFERENCES tenants(id) ON DELETE CASCADE"),
    ]
    for tbl, col, col_def in column_checks:
        try:
            _validate_sql_identifier(tbl)
            _validate_sql_identifier(col)
            _safe_exec(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {col_def};")
        except Exception:
            pass

    # Migrar columnas booleanas con operadores enteros a INTEGER para compatibilidad total
    for tbl, col, def_val in [("accesorios", "es_servicio", 0), ("ventas", "es_credito", 0)]:
        try:
            _validate_sql_identifier(tbl)
            _validate_sql_identifier(col)
            cursor.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s;
            """, (tbl, col))
            row_col = cursor.fetchone()
            if row_col and row_col["data_type"] == "boolean":
                cursor.execute(f"""
                    ALTER TABLE {tbl} ALTER COLUMN {col} DROP DEFAULT;
                    ALTER TABLE {tbl} ALTER COLUMN {col} TYPE INTEGER USING (CASE WHEN {col} = true THEN 1 WHEN {col} = false THEN 0 ELSE {col}::text::integer END);
                    ALTER TABLE {tbl} ALTER COLUMN {col} SET DEFAULT {def_val};
                """)
                conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

    # Índices únicos multi-tenant en PostgreSQL
    _safe_exec("CREATE UNIQUE INDEX IF NOT EXISTS uq_equipos_tenant_imei ON equipos(tenant_id, imei);")
    _safe_exec("CREATE UNIQUE INDEX IF NOT EXISTS uq_reparaciones_tenant_folio ON reparaciones(tenant_id, folio);")

    # Funciones auxiliares de compatibilidad SQLite -> PostgreSQL
    _safe_exec("""
        CREATE OR REPLACE FUNCTION date(val text) RETURNS text IMMUTABLE LANGUAGE sql AS $$
            SELECT SUBSTR(val, 1, 10);
        $$;
    """)
    _safe_exec("""
        CREATE OR REPLACE FUNCTION date(val timestamp) RETURNS text IMMUTABLE LANGUAGE sql AS $$
            SELECT TO_CHAR(val, 'YYYY-MM-DD');
        $$;
    """)
    _safe_exec("""
        CREATE OR REPLACE FUNCTION date(val timestamp with time zone) RETURNS text IMMUTABLE LANGUAGE sql AS $$
            SELECT TO_CHAR(val, 'YYYY-MM-DD');
        $$;
    """)

    # Activar y forzar Row Level Security (RLS) en todas las tablas operativas
    rls_tablas = [
        'sucursales', 'configuracion_tienda', 'usuarios', 'equipos', 'accesorios',
        'clientes', 'ventas', 'venta_items', 'abonos_ventas_credito',
        'movimientos_stock_accesorios', 'reparaciones', 'garantias', 'cortes_caja',
        'garantias_historial', 'historial_ventas_cambios', 'gastos'
    ]
    for tbl in rls_tablas:
        try:
            _validate_sql_identifier(tbl)
            cursor.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'tenant_id'
                LIMIT 1;
            """, (tbl,))
            if cursor.fetchone():
                cursor.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
                cursor.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
                cursor.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {tbl};")
                cursor.execute(f"""
                    CREATE POLICY tenant_isolation_policy ON {tbl}
                    FOR ALL
                    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER)
                    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER);
                """)
                conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass


def init_db():
    """Crea las tablas, índices y migraciones si no existen."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Si estamos en PostgreSQL (Supabase / Render), ejecutar esquema nativo de PostgreSQL
    if is_postgres_enabled():
        try:
            cursor.execute("SELECT pg_advisory_lock(948271645);")
            _init_postgres_db(conn, cursor)
            conn.commit()
            # Verificar si ya existían tenants antes de inicializar demo
            cursor.execute("SELECT COUNT(*) as count FROM tenants;")
            row_chk = cursor.fetchone()
            tenants_existian = (((row_chk["count"] if isinstance(row_chk, dict) or hasattr(row_chk, '__getitem__') else row_chk[0]) or 0) > 0)
        finally:
            try:
                cursor.execute("SELECT pg_advisory_unlock(948271645);")
                conn.commit()
            except Exception:
                pass
            conn.close()
        init_demo_tenant_if_empty()
        seed_demo_data_if_empty(forzar_si_recien_creado=(not tenants_existian))
        return

    # ==========================================================================
    # 0. TABLAS MAESTRAS MULTI-TENANT SAAS (Tenants, Sucursales, Configuración)
    # ==========================================================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_comercial TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        email_contacto TEXT,
        telefono TEXT,
        plan TEXT NOT NULL DEFAULT 'basico',
        activo INTEGER NOT NULL DEFAULT 1,
        fecha_creacion TEXT NOT NULL
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sucursales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        nombre_sucursal TEXT NOT NULL,
        direccion TEXT,
        telefono TEXT,
        es_matriz INTEGER NOT NULL DEFAULT 1,
        fecha_registro TEXT NOT NULL,
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sucursales_tenant ON sucursales(tenant_id);")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracion_tienda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL UNIQUE,
        logo_url TEXT,
        encabezado_ticket TEXT,
        pie_ticket_garantia TEXT,
        whatsapp_notificaciones TEXT,
        fecha_actualizacion TEXT NOT NULL,
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_config_tienda_tenant ON configuracion_tienda(tenant_id);")

    # 1. Tabla Equipos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS equipos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        modelo TEXT NOT NULL,
        capacidad_gb INTEGER NOT NULL,
        color TEXT NOT NULL,
        imei TEXT UNIQUE NOT NULL,
        grado TEXT NOT NULL CHECK(grado IN ('A', 'B', 'C')),
        costo_compra REAL NOT NULL,
        precio_venta REAL NOT NULL,
        estado TEXT NOT NULL DEFAULT 'Disponible' CHECK(estado IN ('Disponible', 'Vendido', 'En Garantia', 'Baja por Garantia')),
        fecha_registro TEXT NOT NULL
    );
    """)

    # 2. Tabla Clientes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        telefono TEXT NOT NULL,
        fecha_registro TEXT NOT NULL
    );
    """)

    # 3. Tabla Ventas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipo_id INTEGER,
        cliente_id INTEGER NOT NULL,
        precio_final REAL NOT NULL,
        margen_ganancia REAL NOT NULL,
        fecha_venta TEXT NOT NULL,
        metodo_pago TEXT NOT NULL DEFAULT 'Efectivo',
        monto_efectivo REAL NOT NULL DEFAULT 0,
        monto_transferencia REAL NOT NULL DEFAULT 0,
        monto_tarjeta REAL NOT NULL DEFAULT 0,
        monto_garantia REAL NOT NULL DEFAULT 0,
        notas TEXT,
        FOREIGN KEY (cliente_id) REFERENCES clientes (id) ON DELETE RESTRICT
    );
    """)

    cursor.execute("PRAGMA table_info(ventas);")
    existing_cols = [row["name"] for row in cursor.fetchall()]

    if "metodo_pago" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN metodo_pago TEXT NOT NULL DEFAULT 'Efectivo';")
    if "monto_efectivo" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN monto_efectivo REAL NOT NULL DEFAULT 0;")
    if "monto_transferencia" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN monto_transferencia REAL NOT NULL DEFAULT 0;")
    if "monto_tarjeta" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN monto_tarjeta REAL NOT NULL DEFAULT 0;")
    if "monto_garantia" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN monto_garantia REAL NOT NULL DEFAULT 0;")
    if "notas" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN notas TEXT;")
    if "es_credito" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN es_credito INTEGER NOT NULL DEFAULT 0;")
    if "plazo_dias" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN plazo_dias INTEGER NOT NULL DEFAULT 0;")
    if "fecha_vencimiento" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN fecha_vencimiento TEXT;")
    if "monto_credito" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN monto_credito REAL NOT NULL DEFAULT 0;")
    if "monto_anticipo" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN monto_anticipo REAL NOT NULL DEFAULT 0;")
    if "saldo_pendiente" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN saldo_pendiente REAL NOT NULL DEFAULT 0;")
    if "estado_credito" not in existing_cols:
        cursor.execute("ALTER TABLE ventas ADD COLUMN estado_credito TEXT;")

    # Tabla de Abonos de Ventas a Crédito (Notas de Crédito a 15 y 30 días)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS abonos_ventas_credito (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venta_id INTEGER NOT NULL,
        monto REAL NOT NULL,
        fecha TEXT NOT NULL,
        metodo_pago TEXT NOT NULL DEFAULT 'Efectivo',
        notas TEXT,
        usuario TEXT,
        FOREIGN KEY (venta_id) REFERENCES ventas (id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_credito ON ventas(es_credito, estado_credito, fecha_vencimiento);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_abonos_venta_id ON abonos_ventas_credito(venta_id);")

    # 4. Tabla Detalle de Venta (Venta Items)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS venta_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venta_id INTEGER NOT NULL,
        equipo_id INTEGER,
        accesorio_id INTEGER,
        tipo_item TEXT NOT NULL DEFAULT 'equipo',
        nombre_item TEXT,
        cantidad INTEGER NOT NULL DEFAULT 1,
        precio_final REAL NOT NULL,
        costo_compra REAL NOT NULL,
        margen_ganancia REAL NOT NULL,
        FOREIGN KEY (venta_id) REFERENCES ventas (id) ON DELETE CASCADE,
        FOREIGN KEY (equipo_id) REFERENCES equipos (id) ON DELETE SET NULL
    );
    """)

    # 5. Tabla Devoluciones por Garantía
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS garantias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venta_id INTEGER NOT NULL,
        equipo_id INTEGER NOT NULL,
        cliente_id INTEGER NOT NULL,
        fecha_devolucion TEXT NOT NULL,
        motivo TEXT NOT NULL,
        falla_descripcion TEXT,
        estado_equipo_recibido TEXT NOT NULL DEFAULT 'En Garantia' CHECK(estado_equipo_recibido IN ('En Garantia', 'Disponible', 'Baja por Garantia')),
        solucion TEXT NOT NULL DEFAULT 'Reemplazo' CHECK(solucion IN ('Reemplazo', 'Reingreso a Inventario', 'Reembolso', 'Nota de Crédito', 'Reparación')),
        equipo_reemplazo_id INTEGER,
        monto_cubierto REAL NOT NULL DEFAULT 0,
        notas TEXT,
        FOREIGN KEY (venta_id) REFERENCES ventas (id) ON DELETE RESTRICT,
        FOREIGN KEY (equipo_id) REFERENCES equipos (id) ON DELETE RESTRICT,
        FOREIGN KEY (cliente_id) REFERENCES clientes (id) ON DELETE RESTRICT,
        FOREIGN KEY (equipo_reemplazo_id) REFERENCES equipos (id) ON DELETE SET NULL
    );
    """)

    # 5.1 Tabla Historial de Estados de Garantía y Trazabilidad (SQLite)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS garantias_historial (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        garantia_id INTEGER,
        equipo_id INTEGER,
        estado_anterior TEXT,
        estado_nuevo TEXT,
        fecha_cambio TEXT NOT NULL,
        usuario TEXT,
        observaciones TEXT,
        tenant_id INTEGER,
        FOREIGN KEY (garantia_id) REFERENCES garantias(id) ON DELETE CASCADE,
        FOREIGN KEY (equipo_id) REFERENCES equipos(id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
    );
    """)

    # 6. Tabla Accesorios y Servicios / Reparaciones (Sin IMEI)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accesorios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        categoria TEXT NOT NULL DEFAULT 'Accesorio',
        codigo_barras TEXT,
        costo_compra REAL NOT NULL DEFAULT 0,
        precio_venta REAL NOT NULL DEFAULT 0,
        stock INTEGER NOT NULL DEFAULT 0,
        es_servicio INTEGER NOT NULL DEFAULT 0,
        fecha_registro TEXT NOT NULL
    );
    """)

    cursor.execute("PRAGMA table_info(accesorios);")
    acc_cols = [row["name"] for row in cursor.fetchall()]
    if "precio_mayoreo" not in acc_cols:
        try:
            cursor.execute("ALTER TABLE accesorios ADD COLUMN precio_mayoreo REAL NOT NULL DEFAULT 0;")
        except Exception:
            pass
    if "precio_20_pzs" not in acc_cols:
        try:
            cursor.execute("ALTER TABLE accesorios ADD COLUMN precio_20_pzs REAL NOT NULL DEFAULT 0;")
        except Exception:
            pass
    if "precio_caja" not in acc_cols:
        try:
            cursor.execute("ALTER TABLE accesorios ADD COLUMN precio_caja REAL NOT NULL DEFAULT 0;")
        except Exception:
            pass
    if "imagen_url" not in acc_cols:
        try:
            cursor.execute("ALTER TABLE accesorios ADD COLUMN imagen_url TEXT;")
        except Exception:
            pass
    if "color" not in acc_cols:
        try:
            cursor.execute("ALTER TABLE accesorios ADD COLUMN color TEXT;")
        except Exception:
            pass

    # 6b. Tabla Kardex y Auditoría de Movimientos de Stock de Accesorios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movimientos_stock_accesorios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        accesorio_id INTEGER NOT NULL,
        tipo_movimiento TEXT NOT NULL CHECK(tipo_movimiento IN ('ENTRADA', 'VENTA', 'MERMA', 'AJUSTE', 'MUESTRA')),
        cantidad INTEGER NOT NULL,
        stock_anterior INTEGER NOT NULL,
        stock_nuevo INTEGER NOT NULL,
        motivo TEXT NOT NULL,
        usuario TEXT NOT NULL DEFAULT 'Sistema',
        fecha TEXT NOT NULL,
        FOREIGN KEY (accesorio_id) REFERENCES accesorios (id) ON DELETE CASCADE
    );
    """)
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mov_stock_acc_id ON movimientos_stock_accesorios(accesorio_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mov_stock_fecha ON movimientos_stock_accesorios(fecha);")
    except Exception:
        pass

    # 7. Tabla Cortes de Caja Diarios (Arqueo / Reporte Z)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cortes_caja (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha_corte TEXT NOT NULL,
        fecha_inicio_periodo TEXT,
        total_ventas REAL NOT NULL DEFAULT 0,
        total_efectivo REAL NOT NULL DEFAULT 0,
        total_transferencia REAL NOT NULL DEFAULT 0,
        total_garantia REAL NOT NULL DEFAULT 0,
        efectivo_declarado REAL NOT NULL DEFAULT 0,
        diferencia REAL NOT NULL DEFAULT 0,
        cantidad_ventas INTEGER NOT NULL DEFAULT 0,
        notas TEXT,
        fecha_registro TEXT NOT NULL
    );
    """)

    cursor.execute("PRAGMA table_info(cortes_caja);")
    corte_cols = [row["name"] for row in cursor.fetchall()]
    for c_col, c_def in [
        ("fecha_hora", "TEXT"),
        ("monto_efectivo", "REAL DEFAULT 0"),
        ("monto_transferencia", "REAL DEFAULT 0"),
        ("monto_tarjeta", "REAL DEFAULT 0"),
        ("efectivo_esperado", "REAL DEFAULT 0"),
        ("efectivo_real", "REAL DEFAULT 0"),
        ("usuario", "TEXT DEFAULT 'Admin'"),
        ("equipos_vendidos", "INTEGER DEFAULT 0"),
        ("accesorios_vendidos", "INTEGER DEFAULT 0"),
    ]:
        if c_col not in corte_cols:
            try:
                cursor.execute(f"ALTER TABLE cortes_caja ADD COLUMN {c_col} {c_def};")
            except Exception:
                pass
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reparaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folio TEXT UNIQUE NOT NULL,
        cliente_nombre TEXT NOT NULL,
        cliente_telefono TEXT NOT NULL,
        dispositivo_modelo TEXT NOT NULL,
        color TEXT,
        imei_serie TEXT,
        codigo_patron TEXT,
        falla_reportada TEXT NOT NULL,
        diagnostico_tecnico TEXT,
        condicion_recepcion TEXT,
        checklist_recepcion TEXT,
        costo_refaccion REAL NOT NULL DEFAULT 0,
        precio_servicio REAL NOT NULL DEFAULT 0,
        anticipo REAL NOT NULL DEFAULT 0,
        saldo_pendiente REAL NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'Recibido' CHECK(estado IN ('Recibido', 'En Revision', 'Esperando Refaccion', 'Listo para Entrega', 'Entregado', 'Cancelado')),
        fecha_ingreso TEXT NOT NULL,
        fecha_prometida TEXT,
        fecha_entrega TEXT,
        tecnico_responsable TEXT,
        notas TEXT
    );
    """)

    cursor.execute("PRAGMA table_info(reparaciones);")
    rep_cols = [row["name"] for row in cursor.fetchall()]
    if "checklist_recepcion" not in rep_cols:
        try:
            cursor.execute("ALTER TABLE reparaciones ADD COLUMN checklist_recepcion TEXT;")
        except Exception:
            pass

    # 8b. Tabla Gastos Operativos de Sucursal
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        concepto TEXT NOT NULL,
        categoria TEXT NOT NULL DEFAULT 'General',
        monto REAL NOT NULL,
        fecha TEXT NOT NULL,
        metodo_pago TEXT NOT NULL DEFAULT 'Efectivo',
        comprobante_url TEXT,
        usuario TEXT NOT NULL DEFAULT 'Admin',
        notas TEXT,
        tenant_id INTEGER,
        sucursal_id INTEGER,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
        FOREIGN KEY (sucursal_id) REFERENCES sucursales(id) ON DELETE SET NULL
    );
    """)
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gastos_cat ON gastos(categoria);")
    except Exception:
        pass

    cursor.execute("PRAGMA table_info(gastos);")
    gas_cols = [row["name"] for row in cursor.fetchall()]
    for col_n, col_def in [
        ("metodo_pago", "TEXT NOT NULL DEFAULT 'Efectivo'"),
        ("comprobante_url", "TEXT"),
        ("usuario", "TEXT NOT NULL DEFAULT 'Admin'"),
        ("notas", "TEXT"),
        ("tenant_id", "INTEGER"),
        ("sucursal_id", "INTEGER"),
    ]:
        if col_n not in gas_cols:
            try:
                cursor.execute(f"ALTER TABLE gastos ADD COLUMN {col_n} {col_def};")
            except Exception:
                pass

    # 9. Tabla Usuarios (Autenticación y Control de Acceso por Roles RBAC)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        pin_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        rol TEXT NOT NULL CHECK(rol IN ('dueno', 'vendedor', 'tecnico')),
        activo INTEGER NOT NULL DEFAULT 1,
        fecha_creacion TEXT NOT NULL
    );
    """)

    # Índices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_equipos_imei ON equipos(imei);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_equipos_estado ON equipos(estado);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_telefono ON clientes(telefono);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha_venta);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_venta_items_venta ON venta_items(venta_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_venta_items_equipo ON venta_items(equipo_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_venta_items_accesorio ON venta_items(accesorio_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_garantias_equipo ON garantias(equipo_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_garantias_venta ON garantias(venta_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_garantias_fecha ON garantias(fecha_devolucion);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_garantias_hist_equipo ON garantias_historial(equipo_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_garantias_hist_tenant ON garantias_historial(tenant_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accesorios_categoria ON accesorios(categoria);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cortes_fecha ON cortes_caja(fecha_corte);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reparaciones_folio ON reparaciones(folio);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reparaciones_estado ON reparaciones(estado);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reparaciones_telefono ON reparaciones(cliente_telefono);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username);")

    # ==========================================================================
    # MIGRACIÓN DE COLUMNAS MULTI-TENANT (tenant_id, sucursal_id)
    # ==========================================================================
    tablas_multitenant = [
        ("equipos", True),
        ("ventas", True),
        ("reparaciones", True),
        ("accesorios", True),
        ("cortes_caja", True),
        ("clientes", False),
        ("usuarios", True),
        ("garantias", True),
        ("garantias_historial", False),
        ("gastos", True),
    ]

    for tabla, tiene_sucursal in tablas_multitenant:
        try:
            _validate_sql_identifier(tabla)
            cursor.execute(f"PRAGMA table_info({tabla});")
            cols = [row["name"] for row in cursor.fetchall()]
            if cols:
                if "tenant_id" not in cols:
                    cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;")
                if tiene_sucursal and "sucursal_id" not in cols:
                    cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL;")
                
                # Crear índices de búsqueda multi-tenant
                if tiene_sucursal:
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{tabla}_tenant_sucursal ON {tabla}(tenant_id, sucursal_id);")
                else:
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{tabla}_tenant ON {tabla}(tenant_id);")
        except Exception:
            pass

    # Índices únicos multi-tenant compuestos
    try:
        cursor.execute("PRAGMA table_info(garantias_historial);")
        gh_cols = [row["name"] for row in cursor.fetchall()]
        if gh_cols and "equipo_id" not in gh_cols:
            cursor.execute("ALTER TABLE garantias_historial ADD COLUMN equipo_id INTEGER REFERENCES equipos(id) ON DELETE CASCADE;")
    except Exception:
        pass

    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_equipos_tenant_imei ON equipos(tenant_id, imei);")
    except Exception:
        pass
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_reparaciones_tenant_folio ON reparaciones(tenant_id, folio);")
    except Exception:
        pass

    # Crear vista de compatibilidad caja_cortes
    try:
        cursor.execute("CREATE VIEW IF NOT EXISTS caja_cortes AS SELECT * FROM cortes_caja;")
    except Exception:
        pass

    conn.commit()
    conn.close()

    # Verificar si existían tenants antes de inicializar demo para blindaje anti-overwrite
    conn_chk = get_db_connection()
    c_chk = conn_chk.cursor()
    c_chk.execute("SELECT COUNT(*) as count FROM tenants;")
    r_chk = c_chk.fetchone()
    tenants_existian = (((r_chk["count"] if isinstance(r_chk, dict) or hasattr(r_chk, '__getitem__') else r_chk[0]) or 0) > 0)
    conn_chk.close()

    # Inicializar el tenant de prueba y asignar registros existentes (Backfill)
    init_demo_tenant_if_empty()
    seed_demo_data_if_empty(forzar_si_recien_creado=(not tenants_existian))


def init_demo_tenant_if_empty():
    """
    Inicializa la arquitectura Multi-Tenant SaaS únicamente si la base de datos está completamente vacía (0 tenants).
    BLINDAJE ESTRICTO ANTI-OVERWRITE:
    Si la tabla 'tenants' tiene al menos 1 registro (COUNT(*) > 0), retorna inmediatamente
    sin realizar ningún INSERT, UPDATE ni alteración de registros existentes.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Blindaje Estricto Anti-Overwrite: si ya existe al menos 1 tenant, salir inmediatamente
        cursor.execute("SELECT COUNT(*) as count FROM tenants;")
        row_count = cursor.fetchone()
        count = (row_count["count"] if isinstance(row_count, dict) or hasattr(row_count, '__getitem__') else row_count[0]) if row_count else 0
        if count > 0:
            return

        # 1. Crear Tenant de Demostración inicial
        cursor.execute("""
        INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            "Demostración Celulares",
            "demo-celulares",
            "contacto@democelulares.com",
            "5512345678",
            "pro",
            True,
            now
        ))
        tenant_id = cursor.lastrowid
        if not tenant_id:
            cursor.execute("SELECT id FROM tenants WHERE slug = 'demo-celulares';")
            tenant_id = cursor.fetchone()["id"]

        # 2. Crear Sucursal Matriz
        cursor.execute("""
        INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (
            tenant_id,
            "Sucursal Matriz Centro",
            "Av. Principal #100, Col. Centro",
            "5512345678",
            True,
            now
        ))
        sucursal_id = cursor.lastrowid
        if not sucursal_id:
            cursor.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (tenant_id,))
            sucursal_id = cursor.fetchone()["id"]

        # 3. Crear Configuración de Tienda
        cursor.execute("""
        INSERT INTO configuracion_tienda (tenant_id, logo_url, encabezado_ticket, pie_ticket_garantia, whatsapp_notificaciones, fecha_actualizacion)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (
            tenant_id,
            "/static/img/logo.png",
            "Demostración Celulares | Compra y Venta Móvil",
            "Garantía de 30 días válida únicamente con este comprobante original.",
            "525512345678",
            now
        ))

        # 4. Crear Usuarios iniciales para este tenant inicial (admin y vendedor)
        from app.security import hash_secret
        admin_pwd = os.environ.get("ADMIN_DELETE_PASSWORD", "samuelykim.")
        admin_hash, admin_salt = hash_secret(admin_pwd)
        vendedor_pwd = os.environ.get("VENDEDOR_PASSWORD", "piso6bodega606.")
        vendedor_hash, vendedor_salt = hash_secret(vendedor_pwd)

        cursor.execute("SELECT id FROM usuarios WHERE username = 'admin' LIMIT 1;")
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES (?, ?, ?, ?, 'dueno', ?, ?, ?, ?);
            """, ("Samuel Navarrete (Dueño)", "admin", admin_hash, admin_salt, True, now, tenant_id, sucursal_id))

        cursor.execute("SELECT id FROM usuarios WHERE username = 'vendedor' LIMIT 1;")
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion, tenant_id, sucursal_id)
            VALUES (?, ?, ?, ?, 'vendedor', ?, ?, ?, ?);
            """, ("Vendedor Mostrador", "vendedor", vendedor_hash, vendedor_salt, True, now, tenant_id, sucursal_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def seed_demo_data_if_empty(forzar_si_recien_creado: bool = False):
    """
    Inserta datos de demostración solo si la base de datos está completamente vacía (0 tenants)
    y se solicita explícitamente vía SEED_DEMO_DATA=1 o durante la ejecución de pruebas automatizadas.
    BLINDAJE ESTRICTO ANTI-OVERWRITE:
    Si la tabla 'tenants' tiene al menos 1 registro (COUNT(*) > 0) y no se trata de una inicialización
    desde cero recién creada, retorna inmediatamente sin realizar ningún INSERT, UPDATE ni alteración de registros existentes.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Blindaje Estricto Anti-Overwrite: si ya existían tenants, salir inmediatamente
        cursor.execute("SELECT COUNT(*) as count FROM tenants;")
        row_count = cursor.fetchone()
        count = (row_count["count"] if isinstance(row_count, dict) or hasattr(row_count, '__getitem__') else row_count[0]) if row_count else 0
        if count > 0 and not forzar_si_recien_creado:
            return

        # Si no se solicitó siembra, salir
        debe_sembrar = os.environ.get("SEED_DEMO_DATA") == "1" or bool(os.environ.get("PYTEST_CURRENT_TEST"))
        if not debe_sembrar:
            return

        cursor.execute("SELECT id FROM tenants ORDER BY id ASC LIMIT 1;")
        t_row = cursor.fetchone()
        t_id = (t_row["id"] if isinstance(t_row, dict) or hasattr(t_row, '__getitem__') else t_row[0]) if t_row else 1

        cursor.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_id,))
        s_row = cursor.fetchone()
        s_id = (s_row["id"] if isinstance(s_row, dict) or hasattr(s_row, '__getitem__') else s_row[0]) if s_row else 1

        cursor.execute("SELECT COUNT(*) as count FROM equipos;")
        count_eq = cursor.fetchone()["count"]

        if count_eq == 0:
            demo_equipos = [
                ("iPhone 14 Pro Max", 256, "Morado Oscuro", "356789123456781", "A", 14500.0, 18900.0, "Disponible", now),
                ("iPhone 13", 128, "Azul Medianoche", "356789123456782", "A", 8200.0, 11500.0, "Disponible", now),
                ("Samsung Galaxy S23 Ultra", 512, "Negro Fantasma", "356789123456783", "A", 13000.0, 17500.0, "Disponible", now),
                ("Samsung Galaxy A54 5G", 128, "Lima", "356789123456784", "B", 4100.0, 5800.0, "Disponible", now),
                ("Xiaomi Redmi Note 13 Pro+", 256, "Blanco Luz", "356789123456785", "B", 4900.0, 6900.0, "Disponible", now),
                ("iPhone 11", 64, "Rojo Product", "356789123456786", "C", 3800.0, 5200.0, "Disponible", now),
                ("Google Pixel 7 Pro", 128, "Hazel", "356789123456787", "A", 7500.0, 10200.0, "Disponible", now),
            ]

            cursor.executemany("""
            INSERT INTO equipos (modelo, capacidad_gb, color, imei, grado, costo_compra, precio_venta, estado, fecha_registro, tenant_id, sucursal_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, [(*item, t_id, s_id) for item in demo_equipos])

            demo_clientes = [
                ("Carlos Mendoza López", "5512345678", now),
                ("María Fernández Ruiz", "5598765432", now)
            ]
            cursor.executemany("""
            INSERT INTO clientes (nombre, telefono, fecha_registro, tenant_id)
            VALUES (?, ?, ?, ?);
            """, [(*item, t_id) for item in demo_clientes])

            # Equipos vendidos para inicializar historial
            cursor.execute("""
            INSERT INTO equipos (modelo, capacidad_gb, color, imei, grado, costo_compra, precio_venta, estado, fecha_registro, tenant_id, sucursal_id)
            VALUES ('iPhone 12', 128, 'Negro', '356789123456788', 'A', 6500.0, 9200.0, 'Vendido', ?, ?, ?);
            """, (now, t_id, s_id))
            eq_id_1 = cursor.lastrowid
            if not eq_id_1:
                cursor.execute("SELECT id FROM equipos WHERE imei = '356789123456788';")
                eq_id_1 = cursor.fetchone()["id"]

            cursor.execute("""
            INSERT INTO ventas (equipo_id, cliente_id, precio_final, margen_ganancia, fecha_venta, metodo_pago, monto_efectivo, monto_transferencia, monto_garantia, tenant_id, sucursal_id)
            VALUES (?, 1, 9200.0, 2700.0, ?, 'Efectivo', 9200.0, 0, 0, ?, ?);
            """, (eq_id_1, now, t_id, s_id))
            v_id_1 = cursor.lastrowid
            if not v_id_1:
                cursor.execute("SELECT id FROM ventas WHERE equipo_id = ? LIMIT 1;", (eq_id_1,))
                v_id_1 = cursor.fetchone()["id"]

            cursor.execute("""
            INSERT INTO venta_items (venta_id, equipo_id, precio_final, costo_compra, margen_ganancia, tipo_item, cantidad)
            VALUES (?, ?, 9200.0, 6500.0, 2700.0, 'equipo', 1);
            """, (v_id_1, eq_id_1))

            conn.commit()

        # Sembrar accesorios demo si la tabla está vacía y se está en modo siembra
        cursor.execute("SELECT COUNT(*) as count FROM accesorios;")
        if cursor.fetchone()["count"] == 0:
            demo_acc = [
                ("Funda Uso Rudo Silicona (Varios)", "Funda", 45.0, 150.0, 30, 0, now),
                ("Mica de Cristal Templado 9D", "Mica", 20.0, 100.0, 50, 0, now),
                ("Cargador Rápido 20W Carga Rápida", "Cargador", 85.0, 250.0, 20, 0, now),
                ("Cable USB-C a Lightning 1m", "Cable", 35.0, 120.0, 25, 0, now),
                ("Cable USB-C a USB-C 60W 1m", "Cable", 35.0, 120.0, 25, 0, now),
                ("Servicio Cambio de Pantalla", "Reparación", 400.0, 850.0, 999, 1, now),
                ("Servicio Cambio de Batería Original", "Reparación", 300.0, 650.0, 999, 1, now),
            ]
            cursor.executemany("""
            INSERT INTO accesorios (nombre, categoria, costo_compra, precio_venta, stock, es_servicio, fecha_registro, tenant_id, sucursal_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, [(*item, t_id, s_id) for item in demo_acc])
            conn.commit()

        # Sembrar reparaciones demo si la tabla está vacía y se está en modo siembra
        cursor.execute("SELECT COUNT(*) as count FROM reparaciones;")
        if cursor.fetchone()["count"] == 0:
            demo_rep = [
                ("REP-0001", "Roberto Gómez", "5511223344", "iPhone 11", "Negro", "356789123000111", "1234", "Pantalla estrellada y touch no responde", "Cambio de display OLED completo", "Detalles leves en esquinas", 450.0, 950.0, 300.0, 650.0, "En Revision", now, now, None, "Samuel N.", "Pieza en inventario"),
                ("REP-0002", "Ana Patricia Solís", "5599887766", "Samsung Galaxy A52", "Azul", "358888000999222", "Patrón en L", "No carga, puerto flojo", "Cambio de centro de carga flex", "Buen estado general", 120.0, 380.0, 200.0, 180.0, "Listo para Entrega", now, now, None, "Samuel N.", "Probado con carga rápida OK"),
            ]
            cursor.executemany("""
            INSERT INTO reparaciones (folio, cliente_nombre, cliente_telefono, dispositivo_modelo, color, imei_serie, codigo_patron, falla_reportada, diagnostico_tecnico, condicion_recepcion, costo_refaccion, precio_servicio, anticipo, saldo_pendiente, estado, fecha_ingreso, fecha_prometida, fecha_entrega, tecnico_responsable, notas, tenant_id, sucursal_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, [(*item, t_id, s_id) for item in demo_rep])
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
