-- ==============================================================================
-- MIGRACIÓN 001: ARQUITECTURA MULTI-TENANT SAAS PARA SQLITE (LOCAL / TURSO)
-- Proyecto: Mi Inventario Celulares - Samuel Navarrete
-- ==============================================================================

-- 1. Tablas Maestras
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
CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);

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
CREATE INDEX IF NOT EXISTS idx_sucursales_tenant ON sucursales(tenant_id);

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
CREATE INDEX IF NOT EXISTS idx_config_tienda_tenant ON configuracion_tienda(tenant_id);

-- 2. Índices y Columnas Multi-Tenant (si las columnas ya existen en SQLite, ALTER TABLE ADD COLUMN se omite)
CREATE INDEX IF NOT EXISTS idx_equipos_tenant_sucursal ON equipos(tenant_id, sucursal_id);
CREATE INDEX IF NOT EXISTS idx_ventas_tenant_sucursal ON ventas(tenant_id, sucursal_id);
CREATE INDEX IF NOT EXISTS idx_reparaciones_tenant_sucursal ON reparaciones(tenant_id, sucursal_id);
CREATE INDEX IF NOT EXISTS idx_accesorios_tenant_sucursal ON accesorios(tenant_id, sucursal_id);
CREATE INDEX IF NOT EXISTS idx_cortes_caja_tenant_sucursal ON cortes_caja(tenant_id, sucursal_id);
CREATE INDEX IF NOT EXISTS idx_clientes_tenant ON clientes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_tenant ON usuarios(tenant_id);

-- Vista de compatibilidad caja_cortes
CREATE VIEW IF NOT EXISTS caja_cortes AS SELECT * FROM cortes_caja;

-- 3. Siembra de Tenant Demo si no existe
INSERT OR IGNORE INTO tenants (id, nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
VALUES (1, 'Demostración Celulares', 'demo-celulares', 'contacto@democelulares.com', '5512345678', 'pro', 1, datetime('now', 'localtime'));

INSERT OR IGNORE INTO sucursales (id, tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
VALUES (1, 1, 'Sucursal Matriz Centro', 'Av. Principal #100, Col. Centro', '5512345678', 1, datetime('now', 'localtime'));

INSERT OR IGNORE INTO configuracion_tienda (id, tenant_id, logo_url, encabezado_ticket, pie_ticket_garantia, whatsapp_notificaciones, fecha_actualizacion)
VALUES (1, 1, '/static/img/logo.png', 'Demostración Celulares | Compra y Venta Móvil', 'Garantía de 30 días válida con este comprobante.', '525512345678', datetime('now', 'localtime'));

-- 4. Backfill de registros huérfanos a tenant_id = 1
UPDATE equipos SET tenant_id = 1, sucursal_id = 1 WHERE tenant_id IS NULL;
UPDATE ventas SET tenant_id = 1, sucursal_id = 1 WHERE tenant_id IS NULL;
UPDATE reparaciones SET tenant_id = 1, sucursal_id = 1 WHERE tenant_id IS NULL;
UPDATE accesorios SET tenant_id = 1, sucursal_id = 1 WHERE tenant_id IS NULL;
UPDATE cortes_caja SET tenant_id = 1, sucursal_id = 1 WHERE tenant_id IS NULL;
UPDATE clientes SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE usuarios SET tenant_id = 1 WHERE tenant_id IS NULL;
