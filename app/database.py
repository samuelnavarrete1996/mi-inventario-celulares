import sqlite3
import os
from datetime import datetime

DATABASE_FILE = os.environ.get("DATABASE_PATH") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inventario.db")

def get_db_connection():
    """Retorna una conexión a SQLite configurada con Row factory y claves foráneas activas."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
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
    except sqlite3.IntegrityError:
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
        equipo_id INTEGER NOT NULL,
        precio_final REAL NOT NULL,
        costo_compra REAL NOT NULL,
        margen_ganancia REAL NOT NULL,
        FOREIGN KEY (venta_id) REFERENCES ventas (id) ON DELETE CASCADE,
        FOREIGN KEY (equipo_id) REFERENCES equipos (id) ON DELETE RESTRICT
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

    # Índices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_equipos_imei ON equipos(imei);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_equipos_estado ON equipos(estado);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_telefono ON clientes(telefono);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha_venta);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_venta_items_venta ON venta_items(venta_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_venta_items_equipo ON venta_items(equipo_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_garantias_equipo ON garantias(equipo_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_garantias_venta ON garantias(venta_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_garantias_fecha ON garantias(fecha_devolucion);")

    conn.commit()
    conn.close()

def seed_demo_data_if_empty():
    """Inserta datos de demostración si la base de datos está vacía."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM equipos;")
    count = cursor.fetchone()["count"]

    if count == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        INSERT INTO venta_items (venta_id, equipo_id, precio_final, costo_compra, margen_ganancia)
        VALUES (?, ?, 9200.0, 6500.0, 2700.0);
        """, (v_id_1, eq_id_1))

        conn.commit()

    conn.close()
