"""A copy of the mart schema in one DuckDB file, for the hosted website.

Build the file:  python -m src.ai.hosted

The hosted site has no PostgreSQL server. So that the Ask-your-data chat
still works there, every mart table and view is copied into
app/data/mart.duckdb. DuckDB is a database that runs inside the Python
process and reads one file, so the site needs no server.

The assistant itself does not change: the LLM still writes PostgreSQL,
the same safety check runs, and only the last step differs. The checked
query is translated to DuckDB's dialect and run on this file, which is
opened read-only.
"""

import json
import os

import sqlglot
from dotenv import load_dotenv
from sqlglot import exp

load_dotenv()  # so DATABASE_URL from the .env file is known before use_hosted_copy() is asked

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MART_FILE = os.path.join(PROJECT_DIR, "app", "data", "mart.duckdb")
SCHEMA_FILE = os.path.join(PROJECT_DIR, "app", "data", "mart_schema.json")

_connection = None


def use_hosted_copy():
    """True when there is no PostgreSQL database configured, but the DuckDB copy exists."""
    return not os.getenv("DATABASE_URL") and os.path.exists(MART_FILE)


def get_connection():
    """Open the file once, read-only, with file and network access switched off."""
    global _connection
    if _connection is None:
        import duckdb

        _connection = duckdb.connect(MART_FILE, read_only=True)
        _connection.execute("SET enable_external_access = false")
        _connection.execute("SET lock_configuration = true")  # the settings above cannot be changed back
    return _connection


def load_schema():
    """Table names, column names and PostgreSQL types, saved when the file was built."""
    with open(SCHEMA_FILE, encoding="utf-8") as schema_file:
        return json.load(schema_file)


def get_allowed_tables():
    return set(load_schema())


def describe_schema():
    """The same one-line-per-table text the assistant gets from PostgreSQL."""
    lines = []
    for table_name, columns in sorted(load_schema().items()):
        column_list = ", ".join(f"{column['name']} {column['type']}" for column in columns)
        lines.append(f"- {table_name}({column_list})")
    return "\n".join(lines)


def run_readonly(safe_sql):
    """Translate already-checked PostgreSQL to DuckDB, run it and return a DataFrame."""
    statement = sqlglot.parse_one(safe_sql, read="postgres")
    # PostgreSQL's plain NUMERIC keeps every decimal place, DuckDB's keeps only three,
    # which can change the last digit of a rounded rate. A float keeps enough places.
    for cast in statement.find_all(exp.Cast):
        if cast.to.this == exp.DataType.Type.DECIMAL and not cast.to.expressions:
            cast.set("to", exp.DataType.build("double"))
    duckdb_sql = statement.sql(dialect="duckdb")
    # A cursor per query, so two visitors asking at the same time do not share one.
    return get_connection().cursor().execute(duckdb_sql).df()


def build():
    """Copy every mart table and view from PostgreSQL into a new DuckDB file."""
    import duckdb
    import pandas as pd

    from src.db import get_engine

    engine = get_engine()
    columns = pd.read_sql(
        """SELECT table_name, column_name, data_type
           FROM information_schema.columns
           WHERE table_schema = 'mart'
           ORDER BY table_name, ordinal_position""",
        engine,
    )
    schema = {
        table_name: [{"name": row.column_name, "type": row.data_type} for row in group.itertuples()]
        for table_name, group in columns.groupby("table_name")
    }

    if os.path.exists(MART_FILE):
        os.remove(MART_FILE)
    url = engine.url
    target = duckdb.connect(MART_FILE)
    target.execute("INSTALL postgres")
    target.execute("LOAD postgres")
    target.execute(
        f"ATTACH 'host={url.host} port={url.port} dbname={url.database} user={url.username}' "
        "AS pg (TYPE postgres, READ_ONLY)"
    )
    for table_name in schema:
        # Views are stored as plain tables: their rows are fixed once the pipeline has run.
        target.execute(f'CREATE TABLE main."{table_name}" AS SELECT * FROM pg.mart."{table_name}"')
        rows = target.execute(f'SELECT COUNT(*) FROM main."{table_name}"').fetchone()[0]
        print(f"  {table_name:30s} {rows:>8,} rows")
    target.execute("DETACH pg")
    target.close()

    with open(SCHEMA_FILE, "w", encoding="utf-8") as schema_file:
        json.dump(schema, schema_file, indent=1)
    print(f"Wrote {MART_FILE} ({os.path.getsize(MART_FILE) / 1e6:.1f} MB)")


if __name__ == "__main__":
    build()
