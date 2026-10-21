# 🚀 Arquitectura SaaS Multi-Tenant y Guía de Migración a PostgreSQL (Supabase)

Este documento detalla la evolución arquitectónica del sistema de Punto de Venta e Inventario (**Mi Inventario Celulares**) hacia una plataforma **SaaS Multi-Tenant** lista para producción en la nube con **PostgreSQL / Supabase**, manteniendo al 100% la compatibilidad hacia atrás con **SQLite local** (`inventario.db`) y **Turso Cloud**.

---

## 🏛️ 1. Visión General de la Arquitectura Multi-Tenant

La plataforma ha sido rediseñada para soportar múltiples empresas suscriptoras (**Tenants**) y múltiples puntos de venta (**Sucursales**) dentro de la misma base de datos relacional, con aislamiento lógico de datos y connection pooling de alto rendimiento.

```
                     ┌──────────────────────────────────────────────┐
                     │          TENANTS (Empresas SaaS)             │
                     │  id, nombre_comercial, slug, plan, activo... │
                     └───────┬──────────────────────────────┬───────┘
                             │ 1:N                          │ 1:1
                             ▼                              ▼
              ┌─────────────────────────────┐  ┌───────────────────────────────┐
              │         SUCURSALES          │  │     CONFIGURACION_TIENDA      │
              │  id, tenant_id, nombre,     │  │  id, tenant_id, logo_url,    │
              │  direccion, es_matriz...    │  │  ticket, whatsapp_notif...    │
              └──────────────┬──────────────┘  └───────────────────────────────┘
                             │ 1:N
                             ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                        TABLAS TRANSACCIONALES SCOPED                        │
 │  • equipos             (tenant_id, sucursal_id)                             │
 │  • ventas              (tenant_id, sucursal_id)                             │
 │  • reparaciones        (tenant_id, sucursal_id)                             │
 │  • accesorios          (tenant_id, sucursal_id)                             │
 │  • cortes_caja         (tenant_id, sucursal_id)                             │
 │  • clientes / usuarios (tenant_id)                                          │
 └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🗄️ 2. Motor Dual y Connection Pooling

El sistema detecta automáticamente el motor de base de datos a través de la variable de entorno `DATABASE_URL`:

1. **PostgreSQL / Supabase (`DATABASE_URL=postgresql://...` o `postgres://...`)**:
   - Activa el motor con **Connection Pooling** respaldado por SQLAlchemy `QueuePool` y driver `psycopg2-binary`.
   - **`pool_pre_ping=True`**: Verifica que cada conexión esté viva antes de entregarla, evitando desconexiones por inactividad de PgBouncer en Supabase.
   - **`pool_recycle=300`**: Recicla automáticamente conexiones inactivas cada 5 minutos.
   - **Emulación de interfaz (`PostgresConnection` / `PostgresCursor`)**: Traduce automáticamente placeholders `?` a `%s`, expresiones de fecha SQLite (`date('now')` → `CURRENT_DATE`), gestiona `lastrowid` mediante `RETURNING id` y soporta lectura como diccionario (`row['campo']`, `dict(row)`).
2. **Fallback Local SQLite (`inventario.db`)**:
   - Si no existe `DATABASE_URL` o no inicia con `postgres`, el sistema utiliza SQLite en modo `WAL` (`Write-Ahead Logging`) y `busy_timeout = 10000ms`, garantizando que el desarrollo local siga funcionando sin dependencias externas.

---

## 📋 3. Tablas Maestras Agregadas

### 3.1 `tenants` (Negocios / Empresas Suscriptoras)
| Columna | Tipo Postgres | Tipo SQLite | Restricciones | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `SERIAL PRIMARY KEY` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Único | Identificador numérico del tenant |
| `nombre_comercial` | `VARCHAR(150)` | `TEXT` | `NOT NULL` | Nombre comercial de la empresa |
| `slug` | `VARCHAR(60)` | `TEXT` | `UNIQUE NOT NULL` | Identificador único para URL/subdominio |
| `email_contacto` | `VARCHAR(120)` | `TEXT` | Opcional | Correo electrónico de contacto |
| `telefono` | `VARCHAR(30)` | `TEXT` | Opcional | Teléfono principal de contacto |
| `plan` | `VARCHAR(50)` | `TEXT` | `DEFAULT 'basico'` | Plan: `gratis`, `basico`, `pro`, `enterprise` |
| `activo` | `BOOLEAN` | `INTEGER` | `DEFAULT TRUE / 1` | Bandera de estado activo/inactivo |
| `fecha_creacion` | `TIMESTAMP` | `TEXT` | `NOT NULL` | Fecha y hora de creación |

### 3.2 `sucursales` (Puntos de Venta Físicos o Bodegas)
| Columna | Tipo Postgres | Tipo SQLite | Restricciones | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `SERIAL PRIMARY KEY` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Único | Identificador de la sucursal |
| `tenant_id` | `INTEGER` | `INTEGER` | `FK tenants(id) ON DELETE CASCADE` | Tenant al que pertenece |
| `nombre_sucursal` | `VARCHAR(100)` | `TEXT` | `NOT NULL` | Nombre de la tienda o sucursal |
| `direccion` | `VARCHAR(255)` | `TEXT` | Opcional | Dirección física del local |
| `telefono` | `VARCHAR(30)` | `TEXT` | Opcional | Teléfono de atención al cliente |
| `es_matriz` | `BOOLEAN` | `INTEGER` | `DEFAULT TRUE / 1` | `True` si es la sucursal principal |
| `fecha_registro` | `TIMESTAMP` | `TEXT` | `NOT NULL` | Fecha de alta |

### 3.3 `configuracion_tienda` (Personalización y Tickets)
| Columna | Tipo Postgres | Tipo SQLite | Restricciones | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `SERIAL PRIMARY KEY` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Único | Identificador del registro |
| `tenant_id` | `INTEGER` | `INTEGER` | `FK UNIQUE ON DELETE CASCADE` | 1 configuración por tenant |
| `logo_url` | `VARCHAR(500)` | `TEXT` | Opcional | URL del logotipo de la tienda |
| `encabezado_ticket` | `VARCHAR(300)` | `TEXT` | Opcional | Texto en la cabecera del recibo |
| `pie_ticket_garantia`| `VARCHAR(500)` | `TEXT` | Opcional | Póliza legal de garantía en ticket |
| `whatsapp_notificaciones`| `VARCHAR(30)` | `TEXT` | Opcional | Teléfono para mensajes de cobro/venta |
| `fecha_actualizacion` | `TIMESTAMP` | `TEXT` | `NOT NULL` | Última actualización |

---

## 🔑 4. Columnas Multi-Tenant en Tablas Existentes

Se agregaron las columnas `tenant_id` y `sucursal_id` con índices compuestos de alto rendimiento:

- **`equipos`**: `tenant_id`, `sucursal_id` → Índice `idx_equipos_tenant_sucursal`
- **`ventas`**: `tenant_id`, `sucursal_id` → Índice `idx_ventas_tenant_sucursal`
- **`reparaciones`**: `tenant_id`, `sucursal_id` → Índice `idx_reparaciones_tenant_sucursal`
- **`accesorios`**: `tenant_id`, `sucursal_id` → Índice `idx_accesorios_tenant_sucursal`
- **`cortes_caja`**: `tenant_id`, `sucursal_id` → Índice `idx_cortes_caja_tenant_sucursal`
- **`clientes`**: `tenant_id` → Índice `idx_clientes_tenant`
- **`usuarios`**: `tenant_id` → Índice `idx_usuarios_tenant`
- **`caja_cortes`**: Vista SQL de compatibilidad alias sobre `cortes_caja`.

---

## 🛡️ 5. Función de Inicialización y Backfill Automático

Para garantizar que **ningún dato previo se pierda ni se rompa la aplicación**:
La función `init_demo_tenant_if_empty()` se ejecuta automáticamente durante el inicio:
1. Crea el tenant por defecto: **`Demostración Celulares`** (slug: `demo-celulares`).
2. Crea su sucursal matriz: **`Sucursal Matriz Centro`**.
3. Inicializa la configuración de ticket de tienda.
4. **Backfill automático**: Actualiza todos los registros preexistentes con `tenant_id IS NULL` asignándoles el `tenant_id` y `sucursal_id` del tenant demo.

---

## ⚙️ 6. Variables de Entorno

Configura en tu archivo `.env` o en las variables de entorno de Render / Supabase:

```env
# URL de conexión PostgreSQL (Supabase / Render / AWS RDS)
DATABASE_URL=postgresql://postgres:[TU_PASSWORD]@[DB_HOST].supabase.co:5432/postgres

# Parámetros opcionales de Connection Pooling
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
DATABASE_POOL_TIMEOUT=30.0
DATABASE_POOL_RECYCLE=300
```

> **Nota para Supabase:** Si utilizas el Connection Pooler de Supabase (puerto 6543 en modo Transaction), puedes usar tanto la URL directa como la del pooler.

---

## 🚀 7. Cómo Ejecutar la Migración

### Opción A: Mediante el Script Automatizado (Recomendado)

Ejecuta el asistente CLI de migración en la terminal:

```bash
# 1. Ejecutar sobre la conexión configurada en .env (Postgres o SQLite)
python migrations/run_migration.py

# 2. O pasar explícitamente la URL de Supabase / Postgres:
python migrations/run_migration.py --database-url "postgresql://postgres:mypassword@db.supabase.co:5432/postgres"
```

El script mostrará:
```text
======================================================================
>>> EJECUTANDO MIGRACION MULTI-TENANT SAAS
[*] Motor de Base de Datos Detectado: PostgreSQL (Supabase / Cloud)
======================================================================

[1/3] Aplicando esquema de tablas maestras y columnas tenant_id / sucursal_id...
  [OK] Tablas maestras 'tenants', 'sucursales' y 'configuracion_tienda' listas.
  [OK] Columnas tenant_id y sucursal_id verificadas con índices.

[2/3] Verificando tenant de prueba 'Demostracion Celulares' y asignando registros...
  [OK] Tenant demo verificado.
  [OK] Sucursal Matriz y configuracion de tienda listas.
  [OK] Registros existentes asignados al tenant por defecto.

[3/3] Consultando estadisticas de la base de datos...
  * Tenants registrados: 1
  * Sucursales activas:  1
  * Configuraciones:     1
  * Tabla equipos       : 12 registros (12 con tenant asignado)
  * Tabla ventas        : 5 registros (5 con tenant asignado)
  * Tabla reparaciones  : 2 registros (2 con tenant asignado)
  * Tabla accesorios    : 301 registros (301 con tenant asignado)
  * Tabla cortes_caja   : 1 registros (1 con tenant asignado)

======================================================================
[OK] MIGRACION COMPLETADA EXITOSAMENTE SIN ERRORES
======================================================================
```

---

### Opción B: Directo en Supabase SQL Editor

Si prefieres ejecutar el script SQL manualmente en la consola web de Supabase:
1. Abre tu proyecto en [Supabase Dashboard](https://supabase.com/dashboard).
2. Ve a la sección **SQL Editor**.
3. Abre o copia el contenido del archivo [`migrations/001_multi_tenant_postgres.sql`](migrations/001_multi_tenant_postgres.sql).
4. Haz clic en **Run**.

---

### Opción C: En SQLite Local

Para desarrollo local sin Docker ni PostgreSQL:
No requieres hacer nada manual. Al arrancar la aplicación (`python run.py`), `init_db()` detecta SQLite, aplica la migración estructural y siembra el tenant demo automáticamente.

---

## 🧪 8. Verificación y Pruebas Automatizadas

Se incluyó una suite de pruebas específica para la capa multi-tenant y los adaptadores de PostgreSQL:

```bash
# Ejecutar pruebas de la arquitectura Multi-Tenant
pytest test_multitenant_postgres.py -v

# Ejecutar la suite completa del sistema
pytest -v
```

Todas las pruebas validan:
- Creación y unicidad del tenant demo.
- Modelos Pydantic de `TenantCreate`, `SucursalCreate` y `ConfiguracionTiendaCreate`.
- Conversión transparente de sintaxis SQL (placeholders, tipos de datos y fechas).
- Convivencia sin fricción entre SQLite local y PostgreSQL Supabase.
