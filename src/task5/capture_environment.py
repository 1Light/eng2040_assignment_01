# Task 5 - Capture the reproducibility environment

import csv
import platform
import sqlite3
import sys
from pathlib import Path

import matplotlib
import numpy
import pandas

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs/evidence/task5_environment.csv"

SQL_RUNNER = "src/common/run_sql_script.py"


def main():
    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = [
        {
            "component": "python",
            "version": platform.python_version(),
            "detail": Path(sys.executable).name,
        },
        {
            "component": "platform",
            "version": platform.platform(),
            "detail": "",
        },
        {
            "component": "machine",
            "version": platform.machine(),
            "detail": "",
        },
        {
            "component": "pandas",
            "version": pandas.__version__,
            "detail": "",
        },
        {
            "component": "numpy",
            "version": numpy.__version__,
            "detail": "",
        },
        {
            "component": "matplotlib",
            "version": matplotlib.__version__,
            "detail": "",
        },
        {
            "component": "sqlite_engine",
            "version": sqlite3.sqlite_version,
            "detail": "bundled with the Python standard library",
        },
        {
            "component": "sql_execution",
            "version": "python_stdlib_sqlite3",
            "detail": SQL_RUNNER,
        },
        {
            "component": "external_binaries_required",
            "version": "none",
            "detail": "SQL and resource measurement use the Python standard library only",
        },
    ]

    with OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "component",
                "version",
                "detail",
            ],
        )

        writer.writeheader()
        writer.writerows(rows)

    print("=== Task 5 environment ===")

    for row in rows:
        print(
            f"{row['component']}="
            f"{row['version']}"
        )

    print(
        "environment="
        "outputs/evidence/task5_environment.csv"
    )


if __name__ == "__main__":
    main()