"""Small helpers for working with the SQLite database and the named-query file."""
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "retail.db"
QUERY_FILE = ROOT / "sql" / "analysis_queries.sql"


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def load_queries(path: Path = QUERY_FILE) -> dict[str, str]:
    """Parse '-- name: xyz' blocks from a .sql file into {name: sql}."""
    queries, name, buf = {}, None, []
    for line in path.read_text().splitlines():
        m = re.match(r"--\s*name:\s*(\w+)", line)
        if m:
            if name:
                queries[name] = "\n".join(buf).strip()
            name, buf = m.group(1), []
        elif name:
            buf.append(line)
    if name:
        queries[name] = "\n".join(buf).strip()
    return queries


def run_query(con: sqlite3.Connection, name: str) -> pd.DataFrame:
    return pd.read_sql_query(load_queries()[name], con)
