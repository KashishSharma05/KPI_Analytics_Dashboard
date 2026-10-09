"""Safety layer between the LLM and the database.

The LLM writes SQL. Before any of it runs, check_sql() makes sure it is
a single read-only SELECT on the mart schema. Then run_readonly() runs it
as a database user that can only read mart.

Two independent layers, so one mistake is not enough to cause damage:
  1. this code rejects anything that is not a plain SELECT
  2. the database user analyst_readonly has no permission to change data

Self-test:  python -m src.ai.sql_guard
"""

import pandas as pd
import psycopg2
import sqlglot
from sqlglot import exp

from src.db import get_engine

MAX_ROWS = 500
READONLY_USER = "analyst_readonly"

# Statement types that change data or structure. Looked up by name so the
# list still works if a class does not exist in this sqlglot version.
BLOCKED_STATEMENTS = tuple(
    getattr(exp, name)
    for name in [
        "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "AlterTable",
        "TruncateTable", "Grant", "Revoke", "Copy", "Command", "Set", "Transaction",
        "Commit", "Rollback", "Into", "Lock",
    ]
    if hasattr(exp, name)
)

# Functions that read files, call other servers, pause the server or change settings.
BLOCKED_FUNCTIONS = {"dblink", "lo_import", "lo_export", "set_config", "query_to_xml", "copy"}


class UnsafeSQLError(Exception):
    """Raised when LLM-written SQL is not allowed to run."""


def get_allowed_tables():
    """Names of every table and view in the mart schema."""
    sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'mart'"
    return set(pd.read_sql(sql, get_engine())["table_name"])


def check_sql(sql, allowed_tables):
    """Return a safe version of the SQL (with a row limit), or raise UnsafeSQLError."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as error:
        raise UnsafeSQLError(f"SQL could not be parsed: {error}") from error

    # Rule 1: exactly one statement. Blocks "SELECT 1; DROP TABLE x".
    if len(statements) != 1:
        raise UnsafeSQLError("Only one SQL statement is allowed.")
    statement = statements[0]

    # Rule 2: the statement must be a SELECT (a UNION of SELECTs is fine).
    if not isinstance(statement, (exp.Select, exp.Union)):
        raise UnsafeSQLError("Only SELECT statements are allowed.")

    # Rule 3: nothing that writes may be hidden anywhere inside the query.
    for node in statement.walk():
        if isinstance(node, BLOCKED_STATEMENTS):
            raise UnsafeSQLError(f"Not allowed in a query: {type(node).__name__.upper()}")

    # Rule 4: no dangerous functions.
    for function in statement.find_all(exp.Func):
        name = (function.name or function.sql_name()).lower()
        if name.startswith("pg_") or name in BLOCKED_FUNCTIONS:
            raise UnsafeSQLError(f"Function not allowed: {name}")

    # Rule 5: only tables of the mart schema (or CTEs defined in the query itself).
    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if table.catalog:
            raise UnsafeSQLError("Cross-database references are not allowed.")
        if table.db:
            if table.db.lower() != "mart":
                raise UnsafeSQLError(f"Schema not allowed: {table.db}")
        elif table.name in cte_names:
            continue
        if table.name not in allowed_tables:
            raise UnsafeSQLError(f"Table not allowed: {table.name}")

    # Rule 6: never return more than MAX_ROWS rows.
    if statement.args.get("limit") is None:
        statement = statement.limit(MAX_ROWS)

    return statement.sql(dialect="postgres")


def run_readonly(safe_sql):
    """Run already-checked SQL as the read-only user and return a DataFrame."""
    # Same server and database as the project, but logged in as the read-only user.
    url = get_engine().url
    connection = psycopg2.connect(host=url.host, port=url.port, dbname=url.database, user=READONLY_USER)
    try:
        connection.set_session(readonly=True)  # the transaction itself refuses writes
        with connection.cursor() as cursor:
            cursor.execute(safe_sql)
            columns = [column.name for column in cursor.description]
            return pd.DataFrame(cursor.fetchall(), columns=columns)
    finally:
        connection.close()


# Attacks and tricks the guard must stop, and normal queries it must allow.
SELF_TEST = [
    ("DROP TABLE mart.fact_orders", False),
    ("DELETE FROM fact_orders", False),
    ("UPDATE fact_orders SET order_revenue = 0", False),
    ("INSERT INTO fact_orders (order_id) VALUES ('x')", False),
    ("SELECT 1; DROP TABLE fact_orders", False),
    ("TRUNCATE fact_orders", False),
    ("CREATE TABLE mart.copy AS SELECT * FROM fact_orders", False),
    ("SELECT * INTO backup FROM fact_orders", False),
    ("SELECT * FROM clean.orders", False),
    ("SELECT * FROM raw.customers", False),
    ("SELECT * FROM pg_catalog.pg_user", False),
    ("SELECT * FROM information_schema.tables", False),
    ("SELECT pg_sleep(60)", False),
    ("SELECT pg_read_file('/etc/passwd')", False),
    ("WITH d AS (DELETE FROM fact_orders RETURNING *) SELECT * FROM d", False),
    ("GRANT ALL ON fact_orders TO analyst_readonly", False),
    ("SELECT COUNT(*) FROM fact_orders", True),
    ("SELECT year_month, revenue FROM mart.kpi_monthly ORDER BY 1", True),
    ("WITH t AS (SELECT category FROM dim_product) SELECT COUNT(*) FROM t", True),
]


def main():
    allowed_tables = get_allowed_tables()
    passed = 0
    for sql, should_be_allowed in SELF_TEST:
        try:
            check_sql(sql, allowed_tables)
            was_allowed, reason = True, "allowed"
        except UnsafeSQLError as error:
            was_allowed, reason = False, f"blocked: {error}"
        ok = was_allowed == should_be_allowed
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {sql[:62]:62s}  {reason[:60]}")
    print(f"\n{passed} of {len(SELF_TEST)} guard tests passed.")

    # Second layer: even with the guard bypassed, the database user cannot write.
    try:
        run_readonly("DELETE FROM mart.fact_orders")
        print("Database layer: FAIL - the read-only user was able to delete!")
    except Exception as error:
        print("Database layer: PASS - write refused by PostgreSQL:", str(error).splitlines()[0])


if __name__ == "__main__":
    main()
