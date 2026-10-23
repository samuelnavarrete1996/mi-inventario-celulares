"""
Cliente y Pool de Conexiones PostgreSQL para Arquitectura SaaS Multi-Tenant.
Compatible con Supabase, Render, AWS RDS y PostgreSQL estándar.
Utiliza SQLAlchemy QueuePool para connection pooling de alto rendimiento,
con reconexión automática (pool_pre_ping) y reciclaje de conexiones inactivas.
Emula la interfaz estándar de conexión y cursor de Python (PEP 249 / sqlite3.Row).
"""

import os
import re
from typing import Any, List, Dict, Optional, Tuple

_pg_engine = None

class PostgresRow:
    """
    Fila emulada compatible con sqlite3.Row y TursoRow.
    Permite acceso por índice numérico (row[0]), por nombre de columna (row['col']),
    como diccionario nativo (dict(row)), row.get('col', default), row.keys(), etc.
    """
    def __init__(self, cols: List[str], values: List[Any]):
        self._cols = cols
        self._values = list(values)
        self._mapping = {c: v for c, v in zip(cols, values)}
        self._lower_mapping = {c.lower(): v for c, v in zip(cols, values)}

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, int):
            return self._values[item]
        if item in self._mapping:
            return self._mapping[item]
        if isinstance(item, str) and item.lower() in self._lower_mapping:
            return self._lower_mapping[item.lower()]
        raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._mapping:
            return self._mapping[key]
        return self._lower_mapping.get(key.lower(), default)

    def keys(self) -> List[str]:
        return self._cols

    def values(self) -> List[Any]:
        return self._values

    def items(self):
        return self._mapping.items()

    def __iter__(self):
        return iter(self._cols)

    def __len__(self) -> int:
        return len(self._cols)

    def __contains__(self, key: str) -> bool:
        return key in self._mapping or (isinstance(key, str) and key.lower() in self._lower_mapping)

    def __repr__(self) -> str:
        return f"<PostgresRow {self._mapping}>"


def _convert_sql_for_postgres(sql: str) -> str:
    """
    Convierte sintaxis SQLite a sintaxis PostgreSQL:
    1. Reemplaza '?' por '%s' únicamente fuera de literales de cadena.
    2. Traduce funciones de fecha y tiempo de SQLite a PostgreSQL.
    """
    # 1. Reemplazar '?' por '%s' respetando comillas simples
    out = []
    in_quote = False
    for char in sql:
        if char == "'":
            in_quote = not in_quote
            out.append(char)
        elif char == '?' and not in_quote:
            out.append('%s')
        else:
            out.append(char)
    res = "".join(out)

    # 2. Traducción de tipos y constraints SQLite -> PostgreSQL
    res = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "SERIAL PRIMARY KEY", res, flags=re.I)

    # 3. Diferencia de fechas julianday SQLite -> PostgreSQL (debe procesarse ANTES de reemplazar date('now'...))
    res = re.sub(
        r"CAST\s*\(\s*ROUND\s*\(\s*julianday\s*\(\s*(?:date\s*\(\s*)?([^)]+?)\s*\)?\s*\)\s*-\s*julianday\s*\(\s*(?:date\s*\(\s*'now'\s*,\s*'localtime'\s*\)|CURRENT_DATE)\s*\)\s*\)\s*AS\s*INTEGER\s*\)",
        r"((\1)::date - CURRENT_DATE)::integer",
        res,
        flags=re.I
    )
    res = re.sub(
        r"CAST\s*\(\s*ROUND\s*\(\s*julianday\s*\(\s*date\(([^)]+)\)\s*\)\s*-\s*julianday\s*\(\s*date\(([^)]+)\)\s*\)\s*\)\s*AS\s*INTEGER\s*\)",
        r"((\1)::date - (\2)::date)::integer",
        res,
        flags=re.I
    )
    # Limpieza de cualquier llamada residual a julianday(...)
    res = re.sub(
        r"julianday\s*\(\s*(?:date\s*\(\s*)?([^)]+?)\s*\)?\s*\)",
        r"(\1)::date",
        res,
        flags=re.I
    )

    # 4. Traducción de funciones de fecha SQLite -> PostgreSQL
    res = re.sub(r"date\('now',\s*'-30 days',\s*'localtime'\)", "(CURRENT_DATE - INTERVAL '30 days')", res, flags=re.I)
    res = re.sub(r"date\('now',\s*'localtime'\)", "CURRENT_DATE", res, flags=re.I)
    res = re.sub(r"date\('now'\)", "CURRENT_DATE", res, flags=re.I)

    # Parser robusto para strftime(...) con soporte de paréntesis anidados (ej. COALESCE(...))
    pattern_strftime = re.compile(r"strftime\s*\(", re.IGNORECASE)
    pos = 0
    while True:
        match = pattern_strftime.search(res, pos)
        if not match:
            break
        start_idx = match.start()
        open_paren_idx = match.end() - 1

        depth = 1
        i = open_paren_idx + 1
        in_squote = False
        while i < len(res) and depth > 0:
            char = res[i]
            if char == "'":
                in_squote = not in_squote
            elif not in_squote:
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
            i += 1

        if depth != 0:
            pos = match.end()
            continue

        args_str = res[open_paren_idx + 1:i - 1].strip()
        m_fmt = re.match(r"^(['\"])(%Y(?:-%m(?:-%d)?)?)\1\s*,\s*(.+)$", args_str, re.DOTALL | re.IGNORECASE)
        if m_fmt:
            fmt = m_fmt.group(2)
            expr = m_fmt.group(3).strip()
            length = 7 if fmt == "%Y-%m" else (10 if fmt == "%Y-%m-%d" else 4)
            replacement = f"SUBSTR(({expr})::text, 1, {length})"
            res = res[:start_idx] + replacement + res[i:]
            pos = start_idx + len(replacement)
        else:
            pos = i

    # Parser robusto para substr(...) con soporte de expresiones anidadas
    pattern_substr = re.compile(r"\bsubstr\s*\(", re.IGNORECASE)
    pos = 0
    while True:
        match = pattern_substr.search(res, pos)
        if not match:
            break
        start_idx = match.start()
        open_paren_idx = match.end() - 1

        depth = 1
        i = open_paren_idx + 1
        in_squote = False
        while i < len(res) and depth > 0:
            char = res[i]
            if char == "'":
                in_squote = not in_squote
            elif not in_squote:
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
            i += 1

        if depth != 0:
            pos = match.end()
            continue

        args_str = res[open_paren_idx + 1:i - 1].strip()
        m_args = re.match(r"^(.+?)\s*,\s*(\d+)\s*,\s*(\d+)$", args_str, re.DOTALL)
        if m_args:
            expr = m_args.group(1).strip()
            start_num = m_args.group(2)
            len_num = m_args.group(3)
            if expr.endswith("::text"):
                replacement = f"SUBSTR({expr}, {start_num}, {len_num})"
            else:
                replacement = f"SUBSTR(({expr})::text, {start_num}, {len_num})"
            res = res[:start_idx] + replacement + res[i:]
            pos = start_idx + len(replacement)
        else:
            pos = i

    res = re.sub(r"\bdate\s*\(\s*([a-zA-Z0-9_.%]+)\s*\)", r"SUBSTR((\1)::text, 1, 10)", res, flags=re.I)
    return res


class PostgresCursor:
    """Cursor compatible con la API de sqlite3 para PostgreSQL."""
    def __init__(self, connection: 'PostgresConnection', pg_cursor: Any):
        self.connection = connection
        self.cursor = pg_cursor
        self.lastrowid: Optional[int] = None
        self._rows: List[PostgresRow] = []
        self._idx: int = 0

    @property
    def rowcount(self) -> int:
        return self.cursor.rowcount

    @property
    def description(self) -> Optional[List[Tuple]]:
        return self.cursor.description

    def execute(self, sql: str, params: Optional[Any] = None) -> 'PostgresCursor':
        clean_sql = sql.strip()
        sql_upper = clean_sql.upper()

        # Interceptar PRAGMAs de SQLite
        if sql_upper.startswith("PRAGMA TABLE_INFO("):
            match = re.search(r"table_info\s*\(\s*['\"]?(\w+)['\"]?\s*\)", clean_sql, re.I)
            if match:
                table_name = match.group(1).lower()
                query = """
                SELECT column_name AS name, data_type AS type,
                       CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull,
                       column_default AS dflt_value,
                       CASE WHEN is_identity = 'YES' THEN 1 ELSE 0 END AS pk
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
                """
                self.cursor.execute(query, (table_name,))
                self._load_results()
                return self

        if sql_upper.startswith("PRAGMA"):
            # Sentencias como PRAGMA busy_timeout, foreign_keys, journal_mode son no-op en Postgres
            self._rows = []
            self._idx = 0
            return self

        # Interceptar transacciones manuales ya controladas
        if sql_upper in ("BEGIN IMMEDIATE;", "BEGIN IMMEDIATE", "BEGIN TRANSACTION;", "BEGIN TRANSACTION"):
            self._rows = []
            self._idx = 0
            return self

        # Convertir placeholders y sintaxis SQL
        converted_sql = _convert_sql_for_postgres(clean_sql)

        # Capturar lastrowid en sentencias INSERT
        is_insert = converted_sql.strip().upper().startswith("INSERT INTO")
        has_returning = "RETURNING" in converted_sql.upper()

        if is_insert and not has_returning:
            clean_insert_sql = converted_sql.strip().rstrip(";")
            converted_sql = clean_insert_sql + " RETURNING id;"
            norm_params = tuple(params) if isinstance(params, (list, tuple)) else params
            if params is not None:
                self.cursor.execute(converted_sql, norm_params)
            else:
                self.cursor.execute(converted_sql)
            try:
                res = self.cursor.fetchone()
                if res:
                    self.lastrowid = res[0] if isinstance(res, (tuple, list)) else (res.get("id") if hasattr(res, "get") else res[0])
            except Exception:
                self.lastrowid = None
            self._rows = []
            self._idx = 0
            return self

        # Ejecución estándar
        if params is not None:
            norm_params = tuple(params) if isinstance(params, (list, tuple)) else params
            self.cursor.execute(converted_sql, norm_params)
        else:
            self.cursor.execute(converted_sql)

        self._load_results()
        return self

    def executemany(self, sql: str, params_seq: Any) -> 'PostgresCursor':
        clean_sql = sql.strip()
        converted_sql = _convert_sql_for_postgres(clean_sql)
        self.cursor.executemany(converted_sql, params_seq)
        self._rows = []
        self._idx = 0
        return self

    def _load_results(self):
        self._rows = []
        self._idx = 0
        if self.cursor.description:
            cols = [desc[0] for desc in self.cursor.description]
            try:
                raw_rows = self.cursor.fetchall()
                self._rows = [PostgresRow(cols, r) for r in raw_rows]
            except Exception:
                self._rows = []

    def fetchone(self) -> Optional[PostgresRow]:
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self) -> List[PostgresRow]:
        if self._idx < len(self._rows):
            rows = self._rows[self._idx:]
            self._idx = len(self._rows)
            return rows
        return []

    def fetchmany(self, size: int = 1) -> List[PostgresRow]:
        end = min(self._idx + size, len(self._rows))
        rows = self._rows[self._idx:end]
        self._idx = end
        return rows

    def close(self):
        try:
            self.cursor.close()
        except Exception:
            pass


class PostgresConnection:
    """
    Envoltura de conexión PostgreSQL con connection pooling respaldado por SQLAlchemy.
    Al llamar a conn.close(), la conexión física se retorna limpiamente al pool.
    """
    def __init__(self, raw_conn: Any):
        self._raw_conn = raw_conn

    def cursor(self) -> PostgresCursor:
        pg_cur = self._raw_conn.cursor()
        return PostgresCursor(self, pg_cur)

    def execute(self, sql: str, params: Optional[Any] = None) -> PostgresCursor:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql: str, params_seq: Any) -> PostgresCursor:
        cur = self.cursor()
        cur.executemany(sql, params_seq)
        return cur

    def commit(self):
        self._raw_conn.commit()

    def rollback(self):
        self._raw_conn.rollback()

    def close(self):
        try:
            self._raw_conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


def reset_postgres_engine():
    """Descarta el pool actual para permitir reconexión tras cambiar DATABASE_URL."""
    global _pg_engine
    if _pg_engine is not None:
        try:
            _pg_engine.dispose()
        except Exception:
            pass
        _pg_engine = None


def get_postgres_engine():
    """Inicializa y retorna el motor SQLAlchemy con connection pooling configurado."""
    global _pg_engine
    if _pg_engine is None:
        raw_url = os.environ.get("DATABASE_URL", "").strip()
        if raw_url.startswith("postgres://"):
            raw_url = raw_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+"):
            raw_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        pool_size = int(os.environ.get("DATABASE_POOL_SIZE", "10"))
        max_overflow = int(os.environ.get("DATABASE_MAX_OVERFLOW", "20"))
        timeout = float(os.environ.get("DATABASE_POOL_TIMEOUT", "30.0"))
        recycle = int(os.environ.get("DATABASE_POOL_RECYCLE", "300"))

        from sqlalchemy import create_engine
        from sqlalchemy.pool import QueuePool

        _pg_engine = create_engine(
            raw_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=timeout,
            pool_recycle=recycle,
            pool_pre_ping=True
        )
    return _pg_engine


def get_postgres_connection() -> PostgresConnection:
    """Obtiene una conexión activa desde el connection pool de PostgreSQL."""
    engine = get_postgres_engine()
    raw_conn = engine.raw_connection()
    return PostgresConnection(raw_conn)
