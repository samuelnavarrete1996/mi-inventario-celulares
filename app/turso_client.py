"""
Cliente Turso HTTP Database para Python puro.
Permite conectar a Turso / libSQL Database mediante la API HTTP Pipeline
sin necesidad de compilar paquetes nativos C/Rust ni dependencias pesadas.
Emula la interfaz estándar de sqlite3 (Connection, Cursor, Row).
"""

import os
import base64
import requests
from typing import Any, List, Dict, Optional, Tuple

class TursoRow:
    """Emula sqlite3.Row con acceso por índice o por nombre de columna y dict()."""
    def __init__(self, cols: List[str], values: List[Any]):
        self._cols = cols
        self._values = values
        self._mapping = {c: v for c, v in zip(cols, values)}

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._values[item]
        return self._mapping[item]

    def get(self, key: str, default: Any = None) -> Any:
        return self._mapping.get(key, default)

    def keys(self) -> List[str]:
        return self._cols

    def values(self) -> List[Any]:
        return self._values

    def items(self):
        return self._mapping.items()

    def __iter__(self):
        # Permite que dict(row) funcione igual que con sqlite3.Row
        return iter(self._cols)

    def __len__(self) -> int:
        return len(self._cols)

    def __contains__(self, key: str) -> bool:
        return key in self._mapping

    def __repr__(self) -> str:
        return f"<TursoRow {self._mapping}>"


def _format_turso_arg(val: Any) -> Dict[str, Any]:
    """Convierte un valor de Python al formato esperado por la API de Turso."""
    if val is None:
        return {"type": "null"}
    elif isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    elif isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    elif isinstance(val, float):
        return {"type": "float", "value": float(val)}
    elif isinstance(val, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(val).decode("ascii")}
    else:
        return {"type": "text", "value": str(val)}


def _parse_turso_val(item: Dict[str, Any]) -> Any:
    """Convierte un valor retornado por Turso a tipo Python nativo."""
    val_type = item.get("type")
    if val_type == "null":
        return None
    elif val_type == "integer":
        return int(item.get("value", 0))
    elif val_type == "float":
        return float(item.get("value", 0.0))
    elif val_type == "blob":
        b64 = item.get("base64", "")
        return base64.b64decode(b64)
    else:
        return item.get("value")


class TursoCursor:
    """Cursor compatible con sqlite3.Cursor."""
    def __init__(self, connection: 'TursoConnection'):
        self.connection = connection
        self._rows: List[TursoRow] = []
        self._idx: int = 0
        self.lastrowid: Optional[int] = None
        self.rowcount: int = 0
        self.description: Optional[List[Tuple]] = None

    def execute(self, sql: str, params: Optional[Any] = None) -> 'TursoCursor':
        """Ejecuta una sentencia SQL en Turso."""
        sql = sql.strip()
        # Si es un PRAGMA que no aplica en HTTP, simular éxito silencioso
        if sql.upper().startswith("PRAGMA FOREIGN_KEYS"):
            return self

        stmt: Dict[str, Any] = {"sql": sql}
        if params is not None:
            if isinstance(params, (list, tuple)):
                stmt["args"] = [_format_turso_arg(p) for p in params]
            elif isinstance(params, dict):
                stmt["named_args"] = [
                    {"name": f":{k}" if not k.startswith(":") else k, "value": _format_turso_arg(v)}
                    for k, v in params.items()
                ]

        res = self.connection._send_request([{"type": "execute", "stmt": stmt}])
        
        # Procesar resultado
        result_item = res[0]
        if result_item.get("type") == "error":
            err = result_item.get("error", {})
            msg = err.get("message", "Error desconocido en Turso")
            raise Exception(f"Turso SQLite Error: {msg}")

        resp_obj = result_item.get("response", {}).get("result", {})
        
        raw_cols = resp_obj.get("cols", [])
        self.description = [(c.get("name"), None, None, None, None, None, None) for c in raw_cols]
        col_names = [c.get("name") for c in raw_cols]

        raw_rows = resp_obj.get("rows", [])
        self._rows = []
        for r in raw_rows:
            parsed_vals = [_parse_turso_val(col_item) for col_item in r]
            self._rows.append(TursoRow(col_names, parsed_vals))
        
        self._idx = 0
        self.rowcount = resp_obj.get("affected_row_count", 0)
        
        raw_last_id = resp_obj.get("last_insert_rowid")
        self.lastrowid = int(raw_last_id) if raw_last_id is not None else None

        return self

    def executemany(self, sql: str, seq_of_params: List[Any]) -> 'TursoCursor':
        """Ejecuta múltiples sentencias SQL en un solo batch HTTP."""
        if not seq_of_params:
            return self

        requests_batch = []
        for params in seq_of_params:
            stmt: Dict[str, Any] = {"sql": sql}
            if isinstance(params, (list, tuple)):
                stmt["args"] = [_format_turso_arg(p) for p in params]
            requests_batch.append({"type": "execute", "stmt": stmt})

        res = self.connection._send_request(requests_batch)
        total_affected = 0
        last_id = None
        for item in res:
            if item.get("type") == "error":
                err = item.get("error", {})
                raise Exception(f"Turso SQLite Error in batch: {err.get('message')}")
            resp_obj = item.get("response", {}).get("result", {})
            total_affected += resp_obj.get("affected_row_count", 0)
            if resp_obj.get("last_insert_rowid") is not None:
                last_id = int(resp_obj.get("last_insert_rowid"))

        self.rowcount = total_affected
        self.lastrowid = last_id
        self._rows = []
        self._idx = 0
        return self

    def fetchone(self) -> Optional[TursoRow]:
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self) -> List[TursoRow]:
        if self._idx == 0:
            self._idx = len(self._rows)
            return self._rows
        remaining = self._rows[self._idx:]
        self._idx = len(self._rows)
        return remaining

    def fetchmany(self, size: int = 1) -> List[TursoRow]:
        end = min(self._idx + size, len(self._rows))
        slice_rows = self._rows[self._idx:end]
        self._idx = end
        return slice_rows

    def close(self):
        self._rows = []
        self._idx = 0


# Variable de sesión HTTP compartida para mantener conexiones vivas (Keep-Alive)
_GLOBAL_SESSION: Optional[requests.Session] = None

def _get_shared_session() -> requests.Session:
    global _GLOBAL_SESSION
    if _GLOBAL_SESSION is None:
        _GLOBAL_SESSION = requests.Session()
    return _GLOBAL_SESSION


class TursoConnection:
    """Conexión compatible con sqlite3.Connection usando Turso HTTP Pipeline."""
    def __init__(self, db_url: str, auth_token: str):
        # Convertir libsql:// a https://
        clean_url = db_url.strip()
        if clean_url.startswith("libsql://"):
            clean_url = "https://" + clean_url[len("libsql://"):]
        elif clean_url.startswith("http://"):
            clean_url = "https://" + clean_url[len("http://"):]
        elif not clean_url.startswith("https://"):
            clean_url = "https://" + clean_url

        if not clean_url.endswith("/v2/pipeline"):
            clean_url = clean_url.rstrip("/") + "/v2/pipeline"

        self.pipeline_url = clean_url
        self.auth_token = auth_token.strip()
        self.row_factory = TursoRow
        self._closed = False

    def _send_request(self, requests_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self._closed:
            raise Exception("Cannot operate on a closed database connection")

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }
        
        # Siempre cerramos el stream para evitar dejar conexiones colgadas en el server
        full_requests = list(requests_list) + [{"type": "close"}]
        body = {"requests": full_requests}

        session = _get_shared_session()
        resp = session.post(self.pipeline_url, json=body, headers=headers, timeout=20)
        
        if resp.status_code != 200:
            raise Exception(f"Error conectando a Turso (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        results = data.get("results", [])
        return results

    def cursor(self) -> TursoCursor:
        return TursoCursor(self)

    def execute(self, sql: str, params: Optional[Any] = None) -> TursoCursor:
        c = self.cursor()
        c.execute(sql, params)
        return c

    def commit(self):
        """Turso opera con autocommit en llamadas HTTP de sentencia individual."""
        pass

    def rollback(self):
        pass

    def close(self):
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
