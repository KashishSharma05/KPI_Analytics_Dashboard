"""Run a .sql file against the project database.

Run with:  python -m src.run_sql sql/02_clean.sql
"""

import sys
import time

from src.db import run_sql_file


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m src.run_sql <path to .sql file>")
        sys.exit(1)

    path = sys.argv[1]
    start = time.time()
    run_sql_file(path)
    print(f"Ran {path} in {time.time() - start:.1f} seconds.")


if __name__ == "__main__":
    main()
