"""Database connection helper.

Every script in this project gets its database connection from here,
so the connection details live in exactly one place (the .env file).
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Read the .env file and put its values into environment variables.
load_dotenv()


def get_engine():
    """Return a SQLAlchemy engine connected to the project database."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing. Copy .env.example to .env and fill it in.")
    return create_engine(database_url)


def run_sql_file(path):
    """Run every statement in a .sql file inside one transaction."""
    with open(path, encoding="utf-8") as sql_file:
        sql = sql_file.read()

    # The low-level connection sends the file to PostgreSQL exactly as written.
    # (Through SQLAlchemy, a "%" inside the SQL would be read as a parameter marker.)
    connection = get_engine().raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
        connection.commit()  # save only if the whole file ran without an error
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    # Quick connection test: python -m src.db
    with get_engine().connect() as connection:
        version = connection.execute(text("SELECT version()")).scalar()
        print("Connected to:", version)
