import sqlite3
import os
import tempfile
from datetime import datetime

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


TURSO_URL = os.environ.get("TURSO_DATABASE_URL") or os.environ.get("TURSO_URL") or os.environ.get("DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN") or os.environ.get("TURSO_TOKEN") or os.environ.get("DATABASE_AUTH_TOKEN")

def is_turso_enabled() -> bool:
    """Retorna True si las credenciales de Turso Cloud están configuradas."""
    return bool(TURSO_URL and TURSO_TOKEN and ("turso.io" in TURSO_URL or "libsql:" in TURSO_URL))

def _resolve_sqlite_path() -> str:
    """Resuelve la ruta de SQLite verificando soporte de bloqueo de archivos (compatible con contenedores y montajes FUSE)."""
    explicit = os.environ.get("DATABASE_PATH")
    if explicit:
        return explicit
    if is_turso_enabled():
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

def get_db_connection():
    """Retorna una conexión a Turso Cloud si está configurada, o a SQLite local con WAL y busy_timeout para evitar condiciones de carrera."""
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

def init_db():
    """Crea las tablas, índices y migraciones si no existen."""
    conn = get_db_connection()
    cursor = conn.cursor()

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

    # Migración de constraint en equipos si la tabla fue creada antes con solo Disponible/Vendido
    try:
        cursor.execute("UPDATE equipos SET estado = 'En Garantia' WHERE id = -9999;")
    except (sqlite3.IntegrityError, Exception):
        # Migrar tabla equipos para permitir 'En Garantia' y 'Baja por Garantia'
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS equipos_new (
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
        cursor.execute("INSERT INTO equipos_new SELECT * FROM equipos;")
        cursor.execute("DROP TABLE equipos;")
        cursor.execute("ALTER TABLE equipos_new RENAME TO equipos;")
        cursor.execute("PRAGMA foreign_keys = ON;")

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

    # Migración de venta_items si existe con esquema antiguo (equipo_id NOT NULL)
    cursor.execute("PRAGMA table_info(venta_items);")
    items_rows = cursor.fetchall()
    items_cols = [row["name"] for row in items_rows]
    equipo_id_row = next((r for r in items_rows if r["name"] == "equipo_id"), None)
    equipo_id_notnull = equipo_id_row["notnull"] if equipo_id_row else 0

    if "tipo_item" not in items_cols or equipo_id_notnull == 1:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS venta_items_migrated (
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
        cursor.execute("""
        INSERT INTO venta_items_migrated (id, venta_id, equipo_id, precio_final, costo_compra, margen_ganancia, tipo_item, cantidad)
        SELECT id, venta_id, equipo_id, precio_final, costo_compra, margen_ganancia, 'equipo', 1 FROM venta_items;
        """)
        cursor.execute("DROP TABLE venta_items;")
        cursor.execute("ALTER TABLE venta_items_migrated RENAME TO venta_items;")
        cursor.execute("PRAGMA foreign_keys = ON;")

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
        solucion TEXT NOT NULL DEFAULT 'Reemplazo' CHECK(solucion IN ('Reemplazo', 'Reingreso a Inventario', 'Reembolso')),
        equipo_reemplazo_id INTEGER,
        monto_cubierto REAL NOT NULL DEFAULT 0,
        notas TEXT,
        FOREIGN KEY (venta_id) REFERENCES ventas (id) ON DELETE RESTRICT,
        FOREIGN KEY (equipo_id) REFERENCES equipos (id) ON DELETE RESTRICT,
        FOREIGN KEY (cliente_id) REFERENCES clientes (id) ON DELETE RESTRICT,
        FOREIGN KEY (equipo_reemplazo_id) REFERENCES equipos (id) ON DELETE SET NULL
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

    # 8. Tabla Reparaciones y Servicio Técnico (Taller)
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

    # 9. Tabla Usuarios (Autenticación y Control de Acceso por Roles RBAC)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        pin_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        rol TEXT NOT NULL CHECK(rol IN ('dueno', 'vendedor')),
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accesorios_categoria ON accesorios(categoria);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cortes_fecha ON cortes_caja(fecha_corte);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reparaciones_folio ON reparaciones(folio);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reparaciones_estado ON reparaciones(estado);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reparaciones_telefono ON reparaciones(cliente_telefono);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username);")

    conn.commit()
    conn.close()

def seed_demo_data_if_empty():
    """
    Inserta datos de demostración solo si la base de datos está vacía y se solicita explícitamente vía
    SEED_DEMO_DATA=1 o durante la ejecución de pruebas automatizadas.
    Garantiza siempre la inicialización segura de usuarios de acceso.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Inicialización o sincronización de usuarios
    from app.security import hash_secret
    admin_pwd = os.environ.get("ADMIN_DELETE_PASSWORD", "erYHE7yse")
    admin_hash, admin_salt = hash_secret(admin_pwd)
    vendedor_pwd = os.environ.get("VENDEDOR_PASSWORD", "piso6bodega606.")
    vendedor_hash, vendedor_salt = hash_secret(vendedor_pwd)

    cursor.execute("SELECT COUNT(*) as count FROM usuarios;")
    user_count = cursor.fetchone()["count"]

    if user_count == 0:
        usuarios_init = [
            ("Samuel Navarrete (Dueño)", "admin", admin_hash, admin_salt, "dueno", 1, now),
            ("Vendedor Mostrador", "vendedor", vendedor_hash, vendedor_salt, "vendedor", 1, now)
        ]
        cursor.executemany("""
        INSERT INTO usuarios (nombre, username, pin_hash, salt, rol, activo, fecha_creacion)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, usuarios_init)
        conn.commit()
    else:
        # Solo sincronizar si se proporcionó una variable de entorno explícita para evitar sobreescritura accidental
        if "ADMIN_DELETE_PASSWORD" in os.environ:
            cursor.execute("UPDATE usuarios SET pin_hash = ?, salt = ? WHERE username = 'admin';", (admin_hash, admin_salt))
        if "VENDEDOR_PASSWORD" in os.environ:
            cursor.execute("UPDATE usuarios SET pin_hash = ?, salt = ? WHERE username = 'vendedor';", (vendedor_hash, vendedor_salt))
        conn.commit()

    # 2. Siembra de datos demo (solo en tests o con bandera explícita SEED_DEMO_DATA=1)
    debe_sembrar = os.environ.get("SEED_DEMO_DATA") == "1" or bool(os.environ.get("PYTEST_CURRENT_TEST"))

    if not debe_sembrar:
        conn.close()
        return

    cursor.execute("SELECT COUNT(*) as count FROM equipos;")
    count = cursor.fetchone()["count"]

    if count == 0:
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
        INSERT INTO equipos (modelo, capacidad_gb, color, imei, grado, costo_compra, precio_venta, estado, fecha_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, demo_equipos)

        demo_clientes = [
            ("Carlos Mendoza López", "5512345678", now),
            ("María Fernández Ruiz", "5598765432", now)
        ]
        cursor.executemany("""
        INSERT INTO clientes (nombre, telefono, fecha_registro)
        VALUES (?, ?, ?);
        """, demo_clientes)

        # Equipos vendidos para inicializar historial
        cursor.execute("""
        INSERT INTO equipos (modelo, capacidad_gb, color, imei, grado, costo_compra, precio_venta, estado, fecha_registro)
        VALUES ('iPhone 12', 128, 'Negro', '356789123456788', 'A', 6500.0, 9200.0, 'Vendido', ?);
        """, (now,))
        eq_id_1 = cursor.lastrowid

        cursor.execute("""
        INSERT INTO ventas (equipo_id, cliente_id, precio_final, margen_ganancia, fecha_venta, metodo_pago, monto_efectivo, monto_transferencia, monto_garantia)
        VALUES (?, 1, 9200.0, 2700.0, ?, 'Efectivo', 9200.0, 0, 0);
        """, (eq_id_1, now))
        v_id_1 = cursor.lastrowid

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
        INSERT INTO accesorios (nombre, categoria, costo_compra, precio_venta, stock, es_servicio, fecha_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, demo_acc)
        conn.commit()

    # Sembrar reparaciones demo si la tabla está vacía y se está en modo siembra
    cursor.execute("SELECT COUNT(*) as count FROM reparaciones;")
    if cursor.fetchone()["count"] == 0:
        demo_rep = [
            ("REP-0001", "Roberto Gómez", "5511223344", "iPhone 11", "Negro", "356789123000111", "1234", "Pantalla estrellada y touch no responde", "Cambio de display OLED completo", "Detalles leves en esquinas", 450.0, 950.0, 300.0, 650.0, "En Revision", now, now, None, "Samuel N.", "Pieza en inventario"),
            ("REP-0002", "Ana Patricia Solís", "5599887766", "Samsung Galaxy A52", "Azul", "358888000999222", "Patrón en L", "No carga, puerto flojo", "Cambio de centro de carga flex", "Buen estado general", 120.0, 380.0, 200.0, 180.0, "Listo para Entrega", now, now, None, "Samuel N.", "Probado con carga rápida OK"),
        ]
        cursor.executemany("""
        INSERT INTO reparaciones (folio, cliente_nombre, cliente_telefono, dispositivo_modelo, color, imei_serie, codigo_patron, falla_reportada, diagnostico_tecnico, condicion_recepcion, costo_refaccion, precio_servicio, anticipo, saldo_pendiente, estado, fecha_ingreso, fecha_prometida, fecha_entrega, tecnico_responsable, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, demo_rep)
        conn.commit()

    conn.close()
