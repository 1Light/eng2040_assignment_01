#!/usr/bin/env python3
"""Load the supplied SQL into a new SQLite database. Requires Python 3.10+."""
import argparse
import os
from pathlib import Path
import sqlite3
import sys

HERE = Path(__file__).resolve().parent


def populate(sql_path: Path, db_path: Path) -> tuple[int, int]:
    """Import faithfully; never replace an existing destination."""
    sql = sql_path.read_text(encoding="utf-8")
    # Exclusive creation refuses existing files, including symbolic links.
    with db_path.open("xb") as created:
        identity = os.fstat(created.fileno())

    connection = None
    try:
        connection = sqlite3.connect(db_path)
        connection.executescript(sql)
        connection.commit()
        tables = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        row_count = 0
        for (name,) in tables:
            quoted = '"' + name.replace('"', '""') + '"'
            row_count += connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
        return len(tables), row_count
    except BaseException:
        if connection is not None:
            connection.close()
            connection = None
        # Remove only the destination file this run created, never a replacement.
        try:
            current = db_path.lstat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                db_path.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        if connection is not None:
            connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sql", type=Path, default=HERE / "data" / "raw.sql",
        help="SQL input (default: data/raw.sql beside this script).",
    )
    parser.add_argument(
        "--db", type=Path, default=HERE / "marketplace.sqlite",
        help="New database (default: marketplace.sqlite beside this script).",
    )
    args = parser.parse_args()
    sql_path = args.sql.expanduser().resolve()
    db_path = args.db.expanduser().absolute()
    try:
        tables, rows = populate(sql_path, db_path)
    except FileExistsError:
        print(f"Database already exists; nothing was changed: {db_path}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error, UnicodeError) as error:
        print(f"Could not create database: {error}", file=sys.stderr)
        return 1
    print(f"Created {db_path}")
    print(f"Loaded {tables:,} tables and {rows:,} rows from {sql_path.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
