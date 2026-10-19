# 🛡️ REPORTE FINAL DE AUDITORÍA DE CIBERSEGURIDAD Y HARDENING (FASE 2 - ARGON)

**Sistema Auditado:** Mi Inventario Celulares - Samuel Navarrete (POS, Inventario, Catálogo Mayorista y Taller Técnico)  
**Versión Resultante:** `2.1.0 (Hardened Phase 2)`  
**Fecha de Auditoría:** 19 de Octubre de 2026  
**Especialista Auditor:** Argon — Lead Application Security & Penetration Testing Specialist  
**Metodología:** White-Box SAST (Static Application Security Testing), Revisión Criptográfica, Análisis de Concurrencia (TOCTOU) y Pruebas Dinámicas Automatizadas (DAST / Pytest + HTTPX ASGI)  

---

## 1. RESUMEN EJECUTIVO

Se completó la **Segunda Auditoría Exhaustiva de Seguridad (Fase 2)** sobre la totalidad del código fuente backend (`app/*.py`, `app/routers/*.py`) y frontend (`app/static/js/*.js`, `app/static/catalogo.html`, `app/static/index.html`, `app/static/service-worker.js`), así como sobre la infraestructura de despliegue (`Dockerfile`, `render.yaml`, `requirements.txt`).

Tras validar que las **11 vulnerabilidades de la Fase 1 (V-01 a V-11)** fueron correctamente mitigadas, la auditoría profunda de Fase 2 identificó y remedió directamente en el código **6 nuevos hallazgos de seguridad y concurrencia (V-12 a V-17)** que habían pasado desapercibidos en la primera iteración, incluyendo fugas residuales de costos financieros en los endpoints de garantías, condiciones de carrera (TOCTOU) en ventas y abonos simultáneos, vectores de DOM-based / Stored XSS en la renderización dinámica del frontend, canales laterales de temporización (Timing Attacks) en el login, ausencia de revocación server-side de tokens JWT al cerrar sesión y exposición de mensajes de excepción internos.

### Indicadores Globales de Cumplimiento:
- **Vulnerabilidades Fase 1 Verificadas:** 11 / 11 (100% Mitigadas)
- **Nuevos Hallazgos Fase 2 Identificados y Remediados:** 6 / 6 (3 Altas, 3 Medias — 100% Corregidas en código)
- **Migración Criptográfica:** Implementado **Argon2id** (parámetros OWASP: `t=2, m=19456 KiB [19 MiB], p=1`) con retrocompatibilidad transparente para hashes legados `PBKDF2-HMAC-SHA256` y actualización automática en caliente al iniciar sesión.
- **Suite de Pruebas Automatizadas:** **33 / 33 pruebas pasando al 100%** (las 30 pruebas operativas y de seguridad originales más 3 nuevas baterías de pruebas de Fase 2).

---

## 2. MATRIZ DE HALLAZGOS Y REMEDIACIONES APLICADAS EN FASE 2

| ID | Hallazgo / Vulnerabilidad | Severidad | Archivo(s) Afectado(s) | Vector de Riesgo Detectado | Remediación Aplicada en Código |
|---|---|---|---|---|---|
| **V-12** | Fuga de Costos de Compra (`costo_compra`) en Garantías, Historial 360° IMEI y Métricas de Dashboard | 🟠 **ALTA** | `app/routers/garantias.py`, `app/routers/reportes.py`, `app/crud.py` | `GET /api/garantias/verificar-imei` y `GET /api/garantias/historial-imei/{imei}` devolvían el diccionario crudo sin invocar `sanitizar_datos_sensibles()`, exponiendo `costo_compra` al rol `vendedor` tanto en la raíz como en `eventos[0].detalles.costo_compra`. En `/api/reportes/dashboard`, se limpiaba una clave inexistente (`cantidad_equipos_vendidos` en lugar de `equipos_vendidos_mes`) y se exponía `desglose_metodos_pago`. | Se aplicó `sanitizar_datos_sensibles(..., user)` en los 4 endpoints de `garantias.py` y se ocultaron `equipos_vendidos_mes` y `desglose_metodos_pago` para perfiles no-dueño en `reportes.py`. |
| **V-13** | Condiciones de Carrera (TOCTOU / Race Conditions) en Ventas Simultáneas, Stock, Abonos y Cortes de Caja | 🟠 **ALTA** | `app/crud.py`, `app/database.py` | `registrar_venta_carrito` usaba `BEGIN TRANSACTION` diferido y actualizaba `equipos` y `accesorios` sin condición atómica (`WHERE estado = 'Disponible'` / `WHERE stock >= ?`) ni verificación de `cursor.rowcount`. Dos ventas simultáneas podían vender dos veces el mismo IMEI o dejar stock negativo. Asimismo, `abonar_reparacion` y `guardar_corte_caja` abrían múltiples conexiones no atómicas. | Se habilitó `PRAGMA journal_mode=WAL` y `PRAGMA busy_timeout=10000` en `database.py`, transacciones `BEGIN IMMEDIATE` y sentencias Compare-And-Swap (`WHERE id = ? AND estado = 'Disponible'` y `WHERE id = ? AND stock >= ?` validando `cursor.rowcount == 1`) en `crud.py`. |
| **V-14** | DOM-Based y Stored XSS en Renderización Dinámica de Tablas, Alertas y Catálogo | 🟠 **ALTA** | `app/static/js/*.js`, `app/static/catalogo.html` | Las plantillas `.innerHTML` en `inventario.js` (incluyendo errores de importación Excel/CSV), `pos.js`, `reparaciones.js`, `accesorios.js`, `garantias.js`, `caja.js`, `reportes.js`, `app.js` (`showToast`) y `catalogo.html` interpolaban nombres de clientes, modelos, fallas, notas y `imagen_url` sin escapado HTML ni validación de esquema URL. | Se implementaron `App.escapeHtml()`, `App.escapeJsArg()` y `App.sanitizeUrl()` en `app.js` y `catalogo.html`, sanitizando todas las interpolaciones en el DOM y atributos `onclick`. |
| **V-15** | Hashing PBKDF2, Timing Attack en Enumeración de Usuarios, Clave JWT Compartida y Falta de Revocación en Logout | 🟡 **MEDIA / ALTA** | `app/security.py`, `app/routers/auth.py`, `requirements.txt` | 1) Cuando un `username` no existía en `/api/auth/login`, se omitía el cálculo KDF, creando un canal lateral de tiempo. 2) `JWT_SECRET` reutilizaba directamente `ADMIN_DELETE_PASSWORD` si no se definía por separado. 3) `/api/auth/logout` borraba la cookie del cliente pero no invalidaba el `jti` en el servidor. 4) Uso exclusivo de PBKDF2 frente a Argon2id. | 1) Migración a **Argon2id** (`argon2-cffi` / `libargon2`) con retrocompatibilidad PBKDF2 y re-hashing automático en login. 2) Verificación señuelo (`verify_dummy_secret`) en tiempo constante. 3) Derivación HMAC separada para `JWT_SECRET`. 4) Tabla `revoked_tokens` (`jti` denylist) en SQLite para revocación inmediata en logout. |
| **V-16** | Validaciones Faltantes en Modelos `*Update`, Inyección de `NaN`/`Inf`, Límites de Subida de Archivos y Bug de Importación | 🟡 **MEDIA** | `app/models.py`, `app/crud.py`, `app/excel_importer.py`, `app/routers/inventario.py`, `app/routers/backup.py`, `app/routers/clientes.py` | 1) `EquipoUpdate`, `AccesorioUpdate` y `ReparacionUpdate` permitían precios/stocks negativos y grados/estados inválidos. 2) Flotantes aceptaban `NaN`/`Infinity`. 3) `crud.update_equipo` carecía de lista blanca explícita `COLUMNAS_PERMITIDAS_EQUIPO`. 4) Subidas de Excel y `.db` sin tope de RAM ni `PRAGMA integrity_check`. 5) Faltaba importar `Optional` en `app/excel_importer.py`. | 1) Validadores estrictos y rechazo de `NaN`/`Inf` en `models.py`. 2) Lista blanca `COLUMNAS_PERMITIDAS_EQUIPO` y `COLUMNAS_PERMITIDAS_ACCESORIO` en `crud.py`. 3) Límites de 10 MB (Excel) y 50 MB (`.db`) + `PRAGMA integrity_check` en `backup.py`. 4) Corrección de `Optional` en `excel_importer.py`. |
| **V-17** | Exposición de Mensajes de Excepción Internos en Errores HTTP 500 y Cabeceras CSP / HSTS | 🟡 **MEDIA** | `app/main.py`, `app/routers/garantias.py`, `app/routers/caja.py`, `app/routers/backup.py`, `app/routers/accesorios.py`, `app/routers/reparaciones.py` | Bloques `except Exception as e:` devolvían `str(e)` directamente al cliente en respuestas 500/400, pudiendo filtrar rutas del contenedor, errores SQL o URLs de Turso. Faltaban cabeceras `Content-Security-Policy` y `Strict-Transport-Security` y manejador global de excepciones. | Se eliminó `str(e)` en respuestas 500, se añadió `@app.exception_handler(Exception)` en `main.py`, se incorporaron `Content-Security-Policy` y `Strict-Transport-Security`, y se ocultó `/docs` automáticamente cuando corre en entorno Render (`RENDER=true`). |

---

## 3. DETALLE TÉCNICO POR DOMINIO AUDITADO

### 3.1. Auditoría de `app/security.py` y `app/routers/auth.py`
1. **Migración a Argon2id con Retrocompatibilidad Transparente:**
   - `hash_secret()` genera ahora hashes **Argon2id** con prefijo `argon2id$` empleando parámetros recomendados por OWASP (`time_cost=2`, `memory_cost=19456 KiB` [19 MiB], `parallelism=1`, `hash_len=32`, sal criptográfica de 128 bits).
   - `verify_secret()` detecta automáticamente si el hash almacenado es Argon2id (`argon2id$...`) o un hash heredado `PBKDF2-HMAC-SHA256` de 64 caracteres hexadecimales, verificándolo en tiempo constante mediante `hmac.compare_digest`.
   - En `/api/auth/login`, cuando un usuario con hash legado inicia sesión exitosamente, su registro en la tabla `usuarios` se actualiza automáticamente a Argon2id sin interrumpir su flujo.
2. **Resistencia a Timing Attacks (Enumeración de Usuarios y Cortocircuitos):**
   - Se añadió `verify_dummy_secret()` contra un hash Argon2id precalculado cuando el `username` consultado no existe en la base de datos, igualando el costo computacional entre usuarios existentes e inexistentes.
   - Se eliminó el cortocircuito booleano en la evaluación de variantes con punto final (`_verify_secret_with_dot_tolerance`) y en la comparación de la contraseña maestra (`_verify_master_password_constant_time`).
3. **Separación de Claves y Revocación Server-Side de Sesiones (`jti`):**
   - Si no se define `JWT_SECRET` en el entorno, la clave de firma del JWT ya no reutiliza en crudo `ADMIN_DELETE_PASSWORD`, sino que deriva una subclave unidireccional mediante `HMAC-SHA256(key=b"SN-POS-JWT-SIGNING-KEY-V2", msg=...)`.
   - Se creó la tabla persistente `revoked_tokens (jti TEXT PRIMARY KEY, exp INTEGER)` en la base SQLite de control de sesiones. Al invocar `POST /api/auth/logout`, el `jti` del token queda registrado en la lista negra y es rechazado inmediatamente por `decode_access_token()` aunque el token sea reenviado por cabecera `Authorization: Bearer` o cookie clonada.

### 3.2. Auditoría de `app/routers/` (RBAC, IDOR y Validaciones)
1. **Erradicación de Fuga de Costos en Garantías (`app/routers/garantias.py`):**
   - Se envolvió la salida de `/api/garantias/verificar-imei`, `/api/garantias/devolucion`, `/api/garantias` y `/api/garantias/historial-imei/{imei}` con `sanitizar_datos_sensibles(resultado, user)`. Un vendedor puede operar garantías y consultar la trazabilidad 360° del IMEI, pero todos los campos `costo_compra` y `margen_proyectado` se entregan como `null`.
2. **Sanitización Completa del Dashboard (`app/routers/reportes.py`):**
   - Se corrigió el nombre de la propiedad `equipos_vendidos_mes` y se vació el diccionario `desglose_metodos_pago` cuando el usuario autenticado no tiene el rol `dueno`.
3. **Protección en Restauración de Base de Datos e Importación Excel (`app/routers/backup.py`, `app/routers/inventario.py`):**
   - Se impuso lectura acotada (`await file.read(MAX_BYTES + 1)`) con HTTP `413 Request Entity Too Large` (10 MB para hojas Excel/CSV y 50 MB para respaldos `.db`).
   - En `/api/backup/restaurar-db`, antes de sobrescribir la base de datos activa, el archivo subido se escribe en un archivo temporal aislado y se ejecuta `PRAGMA integrity_check;` para garantizar que no esté corrupto, limpiando además los archivos residuales `-wal` y `-shm`.

### 3.3. Auditoría de `app/static/js/` y `app/static/catalogo.html` (DOM-Based XSS)
- Se incorporaron las funciones `App.escapeHtml()`, `App.escapeJsArg()` y `App.sanitizeUrl()` en `app/static/js/app.js` y sus homólogas en `app/static/catalogo.html`.
- Se blindaron todas las vistas dinámicas (`inventario.js`, `pos.js`, `reparaciones.js`, `accesorios.js`, `garantias.js`, `caja.js`, `reportes.js`, `app.js` y `catalogo.html`) para impedir la ejecución de JavaScript arbitrario inyectado a través de nombres de clientes, descripciones de fallas, códigos/patrones de desbloqueo, notas de corte de caja, errores de importación CSV/Excel o URLs de imágenes con esquemas peligrosos (`javascript:`).

### 3.4. Auditoría de `app/database.py` y `app/crud.py` (SQLi y Race Conditions)
- **Prevención de Inyección SQL:** Se verificó que el 100% de las consultas usan parámetros ligados (`?`). Como defensa en profundidad adicional a `COLUMNAS_PERMITIDAS_REPARACION`, se añadieron las listas blancas explícitas `COLUMNAS_PERMITIDAS_EQUIPO`, `COLUMNAS_PERMITIDAS_ACCESORIO` y `TABLAS_PERMITIDAS_EXPORTACION`.
- **Prevención de Condiciones de Carrera (TOCTOU):**
  - En `registrar_venta_carrito`, la transacción inicia con `BEGIN IMMEDIATE;` y ejecuta actualizaciones atómicas condicionales:
    - `UPDATE equipos SET estado = 'Vendido' WHERE id = ? AND estado = 'Disponible'` (verificando `cursor.rowcount == 1`).
    - `UPDATE accesorios SET stock = stock - ? WHERE id = ? AND stock >= ?` (verificando `cursor.rowcount == 1`).
  - Si dos vendedores intentan cobrar el mismo equipo o agotar el último accesorio simultáneamente, la segunda transacción hace `ROLLBACK` limpio y devuelve HTTP 400 sin duplicar la venta ni dejar stock negativo.
  - En `abonar_reparacion` y `guardar_corte_caja`, la lectura y escritura se unificaron dentro de una misma conexión transaccional con `BEGIN IMMEDIATE`.

---

## 4. RESULTADOS DE LA SUITE DE PRUEBAS AUTOMATIZADAS

Se ejecutó la suite completa de pruebas automatizadas incluyendo las nuevas pruebas de seguridad de Fase 2:

```bash
python -m pytest test_seguridad_rbac.py test_sistema.py test_mejoras.py test_nuevas_mejoras.py -v
```

### Desglose de Ejecución (33 / 33 PASSED — 100%):
- `test_seguridad_rbac.py` (14 pruebas):
  - `test_login_vendedor_con_contrasena_inicio` — **PASSED**
  - `test_pin_1234_queda_bloqueado_y_rechazado` — **PASSED**
  - `test_login_dueno_con_credenciales` — **PASSED**
  - `test_rate_limiting_fuerza_bruta` — **PASSED**
  - `test_anti_fuga_f12_equipos_vendedor` — **PASSED**
  - `test_dueno_recibe_costos_completos` — **PASSED**
  - `test_vendedor_bloqueado_reportes_ventas` — **PASSED**
  - `test_dueno_accede_reportes_ventas` — **PASSED**
  - `test_dashboard_sanitizado_para_vendedor` — **PASSED**
  - `test_backups_restringidos_solo_dueno` — **PASSED**
  - `test_logout_cierra_sesion` (incluye prueba anti-replay de JWT revocado) — **PASSED**
  - `test_argon2id_hashing_y_retrocompatibilidad_pbkdf2` (Nuevo Fase 2) — **PASSED**
  - `test_anti_fuga_costos_en_garantias_e_historial_imei_vendedor` (Nuevo Fase 2) — **PASSED**
  - `test_validaciones_estrictas_update_y_cabeceras_csp` (Nuevo Fase 2) — **PASSED**
- `test_sistema.py` (10 pruebas operativas de inventario, POS, pagos combinados, Excel y garantías) — **10 / 10 PASSED**
- `test_mejoras.py` (6 pruebas de accesorios, cortes de caja Z, historial 360° IMEI, aging stock y backups) — **6 / 6 PASSED**
- `test_nuevas_mejoras.py` (3 pruebas de flujo completo de taller de reparaciones, privacidad de catálogo público y PWA) — **3 / 3 PASSED**

---

## 5. RECOMENDACIONES DE BUENAS PRÁCTICAS PARA EL ENTORNO DE PRODUCCIÓN (RENDER / TURSO)

1. **Definición Explícita de Secretos en Render (`Environment Variables`):**
   - Configurar en el panel de Render tres secretos independientes de alta entropía:
     - `JWT_SECRET`: Cadena aleatoria de 64 caracteres hexadecimales (`python -c "import secrets; print(secrets.token_hex(32))"`). Así las sesiones firmadas no cambian entre reinicios del contenedor y están completamente desacopladas de la contraseña administrativa.
     - `ADMIN_DELETE_PASSWORD`: Contraseña exclusiva del Dueño (`admin`).
     - `VENDEDOR_PASSWORD`: Contraseña operativa del mostrador.
   - Definir `ALLOWED_ORIGINS=https://tu-dominio-oficial.onrender.com` para restringir CORS exclusivamente al dominio productivo.
2. **Persistencia en la Nube con Turso (libSQL) y Respaldos Externos:**
   - Dado que el plan gratuito de Render utiliza un sistema de archivos efímero que se reinicia en cada despliegue, mantener siempre configuradas las variables `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN` en producción, y descargar periódicamente el respaldo JSON (`/api/backup/exportar-json`) antes de realizar cargas masivas.
3. **Cifrado en Reposo de Códigos/Patrones de Clientes (`codigo_patron`):**
   - El campo `codigo_patron` en la tabla `reparaciones` almacena el PIN o patrón de desbloqueo del teléfono del cliente para pruebas técnicas en el taller. Como mejora evolutiva, se recomienda limpiar automáticamente (`NULL`) el campo `codigo_patron` cuando la orden pase al estado `'Entregado'` o `'Cancelado'`, minimizando la retención histórica de credenciales de dispositivos de clientes.
4. **Monitoreo y Rotación de Sesiones:**
   - Mantener `ENABLE_API_DOCS=0` en producción (ahora desactivado automáticamente cuando `RENDER` está presente en el entorno) para evitar exponer el esquema OpenAPI (`/docs` y `/openapi.json`) a escáneres automatizados.
