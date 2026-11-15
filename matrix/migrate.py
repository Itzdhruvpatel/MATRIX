"""Copy everything from the local SQLite file into PostgreSQL (for example Supabase).

    DATABASE_URL=postgresql://... python -m matrix.migrate [path/to/matrix.db]

Safe to run again: rows that already exist are skipped. Users and passwords are copied too
(passwords are stored hashed, never in plain text).
"""
import sqlite3
import sys

from matrix import db

TABLES = ["stock_prices", "funds", "fund_navs", "data_issues", "pipeline_runs", "users",
          "announcements", "deals", "alerts", "watchlist", "stock_scores", "transactions", "journal"]
SERIAL_TABLES = ["data_issues", "pipeline_runs", "alerts", "transactions", "journal"]


def copy_table(src: sqlite3.Connection, pg, table: str) -> int:
    cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
    col_list = ", ".join(cols)
    raw = pg._c  # the psycopg connection inside db.PgConnection
    with raw.cursor() as cur:
        # Load into a temporary copy first, then insert only the rows that are new.
        cur.execute(f"CREATE TEMP TABLE IF NOT EXISTS _in_{table} (LIKE {table} INCLUDING DEFAULTS)")
        cur.execute(f"TRUNCATE _in_{table}")
        n = 0
        with cur.copy(f"COPY _in_{table} ({col_list}) FROM STDIN") as cp:
            for row in src.execute(f"SELECT {col_list} FROM {table}"):
                cp.write_row(tuple(row))
                n += 1
        cur.execute(f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM _in_{table} ON CONFLICT DO NOTHING")
        added = cur.rowcount
        if table in SERIAL_TABLES:  # keep new ids above the copied ones
            cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'),"
                        f" GREATEST((SELECT COALESCE(MAX(id), 0) FROM {table}), 1))")
    print(f"{table}: {n} rows read, {added} new")
    return added


def main(path: str = str(db.DEFAULT_PATH)) -> None:
    pg = db.connect()
    if not isinstance(pg, db.PgConnection):
        sys.exit("Set DATABASE_URL to your PostgreSQL connection string first.")
    src = db.connect(path)
    for table in TABLES:
        copy_table(src, pg, table)
    print("Done.")


if __name__ == "__main__":
    main(*sys.argv[1:2])
