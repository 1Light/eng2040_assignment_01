# Task 1 - Measure runtime, memory, and storage

import csv
import os
import resource
import sqlite3
import subprocess
import sys
import time

SOURCE_DB = "marketplace.sqlite"
ITEMS_DB = "outputs/intermediate/items_clean.sqlite"
CATALOGUE_DB = "outputs/intermediate/catalogue_clean.sqlite"
DERIVED_DB = "outputs/intermediate/order_level.sqlite"
BUILD_SQL = "sql/task1_build_order_level.sql"
VALIDATE_SQL = "sql/task1_validate_order_level.sql"
SQL_RUNNER = "src/common/run_sql_script.py"
EVIDENCE_OUT = "outputs/evidence/task1_resources.csv"

REQUIRED_INPUTS = {
    ITEMS_DB: ("order_items_clean", "src/task2/task2_clean_items.py"),
    CATALOGUE_DB: ("products_clean", "src/task2/task2_clean_products.py"),
}


def require_sql_runner():
    if not os.path.exists(SQL_RUNNER):
        raise SystemExit(
            f"Required script does not exist: {SQL_RUNNER}."
        )


def file_size_bytes(path):
    return os.path.getsize(path) if os.path.exists(path) else 0


def require_input_databases():
    for database, (table, producer) in REQUIRED_INPUTS.items():
        if not os.path.exists(database):
            raise SystemExit(
                f"Required input does not exist: {database}. "
                f"Run {producer} before the Task 1 build."
            )

        with sqlite3.connect(database) as conn:
            present = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()[0]

        if not present:
            raise SystemExit(
                f"Table {table} is missing from {database}. "
                f"Run {producer} before the Task 1 build."
            )


def run_sql_script(database, script):
    start = time.perf_counter()

    completed = subprocess.run(
        [
            sys.executable,
            SQL_RUNNER,
            database,
            script,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    elapsed = time.perf_counter() - start

    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)

    return elapsed


def peak_child_memory_bytes():
    value = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss

    if sys.platform == "darwin":
        return int(value)

    return int(value * 1024)


os.makedirs("outputs/evidence", exist_ok=True)

require_sql_runner()
require_input_databases()

source_size = file_size_bytes(SOURCE_DB)
items_size = file_size_bytes(ITEMS_DB)
catalogue_size = file_size_bytes(CATALOGUE_DB)

if os.path.exists(DERIVED_DB):
    os.remove(DERIVED_DB)

build_runtime = run_sql_script(SOURCE_DB, BUILD_SQL)
derived_size = file_size_bytes(DERIVED_DB)

validation_runtime = run_sql_script(SOURCE_DB, VALIDATE_SQL)
peak_memory_bytes = peak_child_memory_bytes()

with sqlite3.connect(SOURCE_DB) as conn:
    source_rows = conn.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

with sqlite3.connect(ITEMS_DB) as conn:
    items_rows = conn.execute(
        "SELECT COUNT(*) FROM order_items_clean"
    ).fetchone()[0]

with sqlite3.connect(CATALOGUE_DB) as conn:
    product_rows = conn.execute(
        "SELECT COUNT(*) FROM products_clean"
    ).fetchone()[0]

with sqlite3.connect(DERIVED_DB) as conn:
    derived_rows = conn.execute(
        "SELECT COUNT(*) FROM order_level"
    ).fetchone()[0]

rows = [
    ("source_orders", source_rows, "rows"),
    ("repaired_item_rows", items_rows, "rows"),
    ("cleaned_product_rows", product_rows, "rows"),
    ("derived_orders", derived_rows, "rows"),
    ("build_runtime", f"{build_runtime:.6f}", "seconds"),
    ("validation_runtime", f"{validation_runtime:.6f}", "seconds"),
    ("peak_child_process_memory", peak_memory_bytes, "bytes"),
    ("source_database_size", source_size, "bytes"),
    ("repaired_items_database_size", items_size, "bytes"),
    ("catalogue_database_size", catalogue_size, "bytes"),
    ("derived_database_size", derived_size, "bytes"),
    ("input_storage_read", source_size + items_size + catalogue_size, "bytes"),
]

with open(EVIDENCE_OUT, "w", newline="", encoding="utf-8") as evidence_file:
    writer = csv.writer(evidence_file)
    writer.writerow(["metric", "value", "unit"])
    writer.writerows(rows)

print(f"build_runtime_seconds={build_runtime:.6f}")
print(f"validation_runtime_seconds={validation_runtime:.6f}")
print(f"peak_child_process_memory_bytes={peak_memory_bytes}")
print(f"peak_child_process_memory_mib={peak_memory_bytes / (1024 ** 2):.2f}")
print(f"source_database_size_bytes={source_size}")
print(f"repaired_items_database_size_bytes={items_size}")
print(f"catalogue_database_size_bytes={catalogue_size}")
print(f"derived_database_size_bytes={derived_size}")
print(f"derived_database_size_mib={derived_size / (1024 ** 2):.2f}")
print(f"evidence_file={EVIDENCE_OUT}")