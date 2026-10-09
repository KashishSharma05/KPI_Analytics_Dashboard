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


if __name__ == "__main__":
    # Quick connection test: python -m src.db
    with get_engine().connect() as connection:
        version = connection.execute(text("SELECT version()")).scalar()
        print("Connected to:", version)
