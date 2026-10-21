-- ==============================================================================
-- MIGRACIÓN 001: ARQUITECTURA MULTI-TENANT SAAS PARA POSTGRESQL (SUPABASE / RENDER / RDS)
-- Proyecto: Mi Inventario Celulares - Samuel Navarrete
-- Descripción: Creación de tablas maestras de tenants, sucursales y configuración,
--              adición de columnas tenant_id y sucursal_id con FKs e índices,
--              y siembra del tenant de prueba 'Demostración Celulares'.
-- ==============================================================================

BEGIN;

-- 1. EXTENSIONES RECOMENDADAS PARA SUPABASE / POSTGRESQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- 2. TABLAS MAESTRAS SAAS MULTI-TENANT
-- ==============================================================================

-- 2.1 Tabla de Tenants (Empresas / Negocios suscriptores)
CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    nombre_comercial VARCHAR(150) NOT NULL,
    slug VARCHAR(60) UNIQUE NOT NULL,
    email_contacto VARCHAR(120),
    telefono VARCHAR(30),
    plan VARCHAR(50) NOT NULL DEFAULT 'basico',
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
CREATE INDEX IF NOT EXISTS idx_tenants_activo ON tenants(activo);

-- 2.2 Tabla de Sucursales (Puntos de Venta / Tiendas por Tenant)
CREATE TABLE IF NOT EXISTS sucursales (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    nombre_sucursal VARCHAR(100) NOT NULL,
    direccion VARCHAR(255),
    telefono VARCHAR(30),
    es_matriz BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sucursales_tenant ON sucursales(tenant_id);

-- 2.3 Tabla de Configuración de Tienda por Tenant
CREATE TABLE IF NOT EXISTS configuracion_tienda (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
    logo_url VARCHAR(500),
    encabezado_ticket VARCHAR(300),
    pie_ticket_garantia VARCHAR(500),
    whatsapp_notificaciones VARCHAR(30),
    fecha_actualizacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_config_tienda_tenant ON configuracion_tienda(tenant_id);

-- ==============================================================================
-- 3. ADICIÓN DE COLUMNAS MULTI-TENANT EN TABLAS TRANSACCIONALES
-- ==============================================================================

-- 3.1 Tabla Equipos
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'equipos' AND column_name = 'tenant_id') THEN
        ALTER TABLE equipos ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'equipos' AND column_name = 'sucursal_id') THEN
        ALTER TABLE equipos ADD COLUMN sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_equipos_tenant_sucursal ON equipos(tenant_id, sucursal_id);

-- 3.2 Tabla Ventas
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ventas' AND column_name = 'tenant_id') THEN
        ALTER TABLE ventas ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ventas' AND column_name = 'sucursal_id') THEN
        ALTER TABLE ventas ADD COLUMN sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_ventas_tenant_sucursal ON ventas(tenant_id, sucursal_id);

-- 3.3 Tabla Reparaciones
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'reparaciones' AND column_name = 'tenant_id') THEN
        ALTER TABLE reparaciones ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'reparaciones' AND column_name = 'sucursal_id') THEN
        ALTER TABLE reparaciones ADD COLUMN sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_reparaciones_tenant_sucursal ON reparaciones(tenant_id, sucursal_id);

-- 3.4 Tabla Accesorios
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'accesorios' AND column_name = 'tenant_id') THEN
        ALTER TABLE accesorios ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'accesorios' AND column_name = 'sucursal_id') THEN
        ALTER TABLE accesorios ADD COLUMN sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_accesorios_tenant_sucursal ON accesorios(tenant_id, sucursal_id);

-- 3.5 Tabla Cortes de Caja (y compatibilidad caja_cortes)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'cortes_caja') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cortes_caja' AND column_name = 'tenant_id') THEN
            ALTER TABLE cortes_caja ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cortes_caja' AND column_name = 'sucursal_id') THEN
            ALTER TABLE cortes_caja ADD COLUMN sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE SET NULL;
        END IF;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_cortes_caja_tenant_sucursal ON cortes_caja(tenant_id, sucursal_id);

-- Vista de compatibilidad para consultas bajo el alias 'caja_cortes'
CREATE OR REPLACE VIEW caja_cortes AS SELECT * FROM cortes_caja;

-- 3.6 Tabla Clientes
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'clientes' AND column_name = 'tenant_id') THEN
        ALTER TABLE clientes ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_clientes_tenant ON clientes(tenant_id);

-- 3.7 Tabla Usuarios
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'usuarios' AND column_name = 'tenant_id') THEN
        ALTER TABLE usuarios ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_usuarios_tenant ON usuarios(tenant_id);

-- ==============================================================================
-- 4. INICIALIZACIÓN DE TENANT POR DEFECTO Y BACKFILL DE DATOS EXISTENTES
-- ==============================================================================

-- 4.1 Insertar Tenant de prueba 'Demostración Celulares' si no existe
INSERT INTO tenants (nombre_comercial, slug, email_contacto, telefono, plan, activo, fecha_creacion)
VALUES ('Demostración Celulares', 'demo-celulares', 'contacto@democelulares.com', '5512345678', 'pro', TRUE, NOW())
ON CONFLICT (slug) DO NOTHING;

-- 4.2 Insertar Sucursal Matriz si no existe
DO $$
DECLARE
    v_tenant_id INTEGER;
    v_sucursal_id INTEGER;
BEGIN
    SELECT id INTO v_tenant_id FROM tenants WHERE slug = 'demo-celulares' LIMIT 1;

    IF v_tenant_id IS NOT NULL THEN
        -- Insertar o buscar sucursal matriz
        SELECT id INTO v_sucursal_id FROM sucursales WHERE tenant_id = v_tenant_id AND es_matriz = TRUE LIMIT 1;
        IF v_sucursal_id IS NULL THEN
            INSERT INTO sucursales (tenant_id, nombre_sucursal, direccion, telefono, es_matriz, fecha_registro)
            VALUES (v_tenant_id, 'Sucursal Matriz Centro', 'Av. Principal #100, Col. Centro', '5512345678', TRUE, NOW())
            RETURNING id INTO v_sucursal_id;
        END IF;

        -- Insertar o verificar configuración de tienda
        IF NOT EXISTS (SELECT 1 FROM configuracion_tienda WHERE tenant_id = v_tenant_id) THEN
            INSERT INTO configuracion_tienda (tenant_id, logo_url, encabezado_ticket, pie_ticket_garantia, whatsapp_notificaciones, fecha_actualizacion)
            VALUES (
                v_tenant_id,
                '/static/img/logo.png',
                'Demostración Celulares | Compra y Venta Móvil',
                'Garantía de 30 días válida únicamente con este comprobante original.',
                '525512345678',
                NOW()
            );
        END IF;

        -- 4.3 Backfill: Asignar registros huérfanos históricos al tenant demo
        UPDATE equipos SET tenant_id = v_tenant_id, sucursal_id = v_sucursal_id WHERE tenant_id IS NULL;
        UPDATE ventas SET tenant_id = v_tenant_id, sucursal_id = v_sucursal_id WHERE tenant_id IS NULL;
        UPDATE reparaciones SET tenant_id = v_tenant_id, sucursal_id = v_sucursal_id WHERE tenant_id IS NULL;
        UPDATE accesorios SET tenant_id = v_tenant_id, sucursal_id = v_sucursal_id WHERE tenant_id IS NULL;
        UPDATE cortes_caja SET tenant_id = v_tenant_id, sucursal_id = v_sucursal_id WHERE tenant_id IS NULL;
        UPDATE clientes SET tenant_id = v_tenant_id WHERE tenant_id IS NULL;
        UPDATE usuarios SET tenant_id = v_tenant_id WHERE tenant_id IS NULL;
    END IF;
END $$;

COMMIT;

-- Verificación final
SELECT 'Migración Multi-Tenant PostgreSQL completada exitosamente' AS resultado,
       (SELECT COUNT(*) FROM tenants) AS total_tenants,
       (SELECT COUNT(*) FROM sucursales) AS total_sucursales,
       (SELECT COUNT(*) FROM configuracion_tienda) AS total_configs;
