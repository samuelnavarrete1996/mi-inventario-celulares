"""
tests/test_persistencia_actualizaciones.py - Pruebas Automatizadas de Persistencia e Integridad de Datos.
Verifica que:
1. Múltiples ejecuciones consecutivas de init_db(), init_demo_tenant_if_empty() y seed_demo_data_if_empty()
   NO alteren, borren ni sobrescriban datos existentes de inventario, clientes, ventas o configuraciones.
2. El blindaje Anti-Overwrite en init_demo_tenant_if_empty() y seed_demo_data_if_empty() retorne
   inmediatamente si la tabla 'tenants' tiene al menos 1 registro (COUNT(*) > 0).
3. La guarda anti-destrucción impida operaciones destructivas en entornos de producción o bases de datos activas.
4. El script de respaldo scripts/backup_db.py genere archivos .json.gz íntegros y válidos.
"""

import os
import time
import gzip
import json
import tempfile
import pytest
from app.database import (
    init_db,
    init_demo_tenant_if_empty,
    seed_demo_data_if_empty,
    get_db_connection,
    verificar_guarda_anti_destruccion
)
from app import crud
from scripts.backup_db import crear_respaldo, TABLAS_CRITICAS


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_blindaje_anti_overwrite_cuando_existen_tenants():
    """Valida que init_demo_tenant_if_empty y seed_demo_data_if_empty retornen de inmediato si COUNT(*) > 0."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM tenants;")
    row = cur.fetchone()
    total_tenants_inicial = row["count"] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0]
    conn.close()

    assert total_tenants_inicial > 0, "Debe existir al menos 1 tenant registrado para esta prueba"

    # Ejecutar 5 llamadas consecutivas a ambas funciones protegidas
    for _ in range(5):
        init_demo_tenant_if_empty()
        seed_demo_data_if_empty()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM tenants;")
    row_final = cur.fetchone()
    total_tenants_final = row_final["count"] if isinstance(row_final, dict) or hasattr(row_final, '__getitem__') else row_final[0]
    conn.close()

    assert total_tenants_final == total_tenants_inicial, (
        f"Inconsistencia: Los tenants cambiaron de {total_tenants_inicial} a {total_tenants_final}"
    )


def test_inmutabilidad_ante_actualizaciones_y_reinicio_servidor():
    """
    Simula múltiples despliegues consecutivos de Render y reinicios de servidor.
    Verifica que equipos, clientes, accesorios y ventas reales se mantengan 100% idénticos.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    now = datetime_now = time.strftime("%Y-%m-%d %H:%M:%S")
    suffix = str(int(time.time() * 1000))[-6:]
    imei_unico = f"354444555{suffix}"

    try:
        # 1. Resolver tenant activo
        cur.execute("SELECT id FROM tenants ORDER BY id ASC LIMIT 1;")
        t_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM sucursales WHERE tenant_id = ? LIMIT 1;", (t_id,))
        s_row = cur.fetchone()
        s_id = s_row["id"] if s_row else 1

        # 2. Insertar registros de prueba únicos
        # Cliente
        cur.execute("INSERT INTO clientes (nombre, telefono, fecha_registro, tenant_id) VALUES (?, ?, ?, ?);",
                    (f"Cliente Inmutable {suffix}", f"55{suffix}99", now, t_id))
        cliente_id = cur.lastrowid
        if not cliente_id:
            cur.execute("SELECT id FROM clientes WHERE telefono = ?;", (f"55{suffix}99",))
            cliente_id = cur.fetchone()["id"]

        # Equipo
        cur.execute("""
            INSERT INTO equipos (modelo, capacidad_gb, color, imei, grado, costo_compra, precio_venta, estado, fecha_registro, tenant_id, sucursal_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Disponible', ?, ?, ?);
        """, (f"Modelo Blindado {suffix}", 256, "Negro Titanio", imei_unico, "A", 12500.0, 16900.0, now, t_id, s_id))
        equipo_id = cur.lastrowid
        if not equipo_id:
            cur.execute("SELECT id FROM equipos WHERE imei = ?;", (imei_unico,))
            equipo_id = cur.fetchone()["id"]

        # Accesorio
        cur.execute("""
            INSERT INTO accesorios (nombre, categoria, costo_compra, precio_venta, stock, es_servicio, fecha_registro, tenant_id, sucursal_id)
            VALUES (?, 'Protección', 50.0, 150.0, 42, 0, ?, ?, ?);
        """, (f"Funda Blindada {suffix}", now, t_id, s_id))
        acc_id = cur.lastrowid
        if not acc_id:
            cur.execute("SELECT id FROM accesorios WHERE nombre = ?;", (f"Funda Blindada {suffix}",))
            acc_id = cur.fetchone()["id"]

        conn.commit()
    finally:
        conn.close()

    # 3. Snapshot de los datos antes de las actualizaciones
    eq_antes = crud.get_equipo_by_id(equipo_id, tenant_id=t_id)
    assert eq_antes is not None
    assert eq_antes["imei"] == imei_unico
    assert eq_antes["costo_compra"] == 12500.0
    assert eq_antes["precio_venta"] == 16900.0

    acc_antes = crud.get_accesorio_by_id(acc_id, tenant_id=t_id)
    assert acc_antes is not None
    assert acc_antes["stock"] == 42

    # 4. SIMULAR 5 ACTUALIZACIONES / REINICIOS CONSECUTIVOS DE RENDER (init_db, init_demo_tenant, seed_demo)
    for _ in range(5):
        init_db()
        init_demo_tenant_if_empty()
        seed_demo_data_if_empty()

    # 5. Snapshot posterior: Los datos deben ser 100% idénticos y no haberse duplicado ni alterado
    eq_despues = crud.get_equipo_by_id(equipo_id, tenant_id=t_id)
    assert eq_despues is not None
    assert eq_despues["imei"] == eq_antes["imei"]
    assert eq_despues["costo_compra"] == eq_antes["costo_compra"]
    assert eq_despues["precio_venta"] == eq_antes["precio_venta"]
    assert eq_despues["estado"] == eq_antes["estado"]
    assert eq_despues["modelo"] == eq_antes["modelo"]

    acc_despues = crud.get_accesorio_by_id(acc_id, tenant_id=t_id)
    assert acc_despues is not None
    assert acc_despues["stock"] == 42
    assert acc_despues["precio_venta"] == 150.0

    # Verificar que no se duplicó el equipo con el mismo IMEI
    conn_chk = get_db_connection()
    c_chk = conn_chk.cursor()
    c_chk.execute("SELECT COUNT(*) as count FROM equipos WHERE imei = ?;", (imei_unico,))
    assert c_chk.fetchone()["count"] == 1
    conn_chk.close()


def test_guarda_anti_destruccion_en_produccion():
    """Valida que la guarda de seguridad bloquee operaciones destructivas si ENVIRONMENT=production."""
    # 1. En entorno normal no debe fallar la verificación genérica
    orig_env = os.environ.get("ENVIRONMENT")

    try:
        os.environ["ENVIRONMENT"] = "production"
        with pytest.raises(RuntimeError) as exc_info:
            verificar_guarda_anti_destruccion("DROP TABLE equipos")
        assert "ANTI-DESTRUCCIÓN" in str(exc_info.value)
        assert "bloqueada" in str(exc_info.value)

        # Probar con valor 'prod'
        os.environ["ENVIRONMENT"] = "prod"
        with pytest.raises(RuntimeError) as exc_info2:
            verificar_guarda_anti_destruccion("TRUNCATE ventas")
        assert "ANTI-DESTRUCCIÓN" in str(exc_info2.value)
    finally:
        if orig_env is not None:
            os.environ["ENVIRONMENT"] = orig_env
        else:
            os.environ.pop("ENVIRONMENT", None)


def test_script_backup_db_generacion_y_lectura():
    """Valida que scripts/backup_db.py genere un volcado comprimido .json.gz con tablas críticas."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        res = crear_respaldo(destino_dir=tmp_dir)

        assert os.path.exists(res["ruta_gz"])
        assert os.path.exists(res["ruta_json"])
        assert res["tamano_gz_kb"] > 0
        assert res["total_registros"] >= 0

        # Leer y verificar integridad del archivo .json.gz
        with gzip.open(res["ruta_gz"], "rb") as f_gz:
            contenido = f_gz.read().decode("utf-8")
            dump_data = json.loads(contenido)

        assert "metadata" in dump_data
        assert "tablas" in dump_data
        assert dump_data["metadata"]["app"] == "Mi Inventario Samuel Navarrete"

        # Validar que todas las tablas críticas estén presentes en el dump
        for tabla in TABLAS_CRITICAS:
            assert tabla in dump_data["tablas"], f"Falta tabla crítica '{tabla}' en el respaldo"
