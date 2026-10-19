"""
conftest.py - Configuración de pruebas automatizadas aisladas.
Garantiza que la suite de pruebas SIEMPRE se ejecute sobre una base de datos SQLite temporal y limpia,
impidiendo cualquier interacción con Turso Cloud o con la base de datos de producción.
"""
import os
import tempfile
import pytest

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f"pytest_isolated_inventario_{os.getpid()}.db")

# Forzar aislamiento antes de que cualquier módulo de app sea importado
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["DATABASE_PATH"] = _TEST_DB_PATH
os.environ["ADMIN_DELETE_PASSWORD"] = "erYHE7yse"
os.environ["SEED_DEMO_DATA"] = "1"

@pytest.fixture(scope="session", autouse=True)
def setup_isolated_test_db():
    """Inicializa la base de datos de prueba temporal y la elimina al finalizar la sesión."""
    from app.database import init_db, seed_demo_data_if_empty
    init_db()
    seed_demo_data_if_empty()
    yield
    if os.path.exists(_TEST_DB_PATH):
        try:
            os.remove(_TEST_DB_PATH)
        except Exception:
            pass
