# Task 5 - Rebuild and validate the complete assignment pipeline

import csv
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

OUTPUTS = ROOT / "outputs"
INTERMEDIATE = OUTPUTS / "intermediate"
FINAL = OUTPUTS / "final"
FIGURES = OUTPUTS / "figures"
EVIDENCE = OUTPUTS / "evidence"
TABLES = OUTPUTS / "tables"

DATABASE = ROOT / "marketplace.sqlite"
EXECUTION_LOG = EVIDENCE / "pipeline_execution.csv"
SQL_RUNNER = "src/common/run_sql_script.py"


def require_file(relative_path):
    path = ROOT / relative_path

    if not path.exists():
        raise FileNotFoundError(
            f"Required file does not exist: {relative_path}"
        )


def check_required_files():
    required = [
        "data/raw.sql",
        "setup_db.py",
        "requirements.txt",
        "README.md",
        "docs/decisions.md",
        "sql/task1_build_order_level.sql",
        "sql/task1_validate_order_level.sql",
        "sql/task2_profile_data_quality.sql",
        "sql/task2_validate_clean_data.sql",
        "src/common/run_sql_script.py",
        "src/task1/task1_measure_resources.py",
        "src/task1/task1_benchmark_loading.py",
        "src/task2/task2_clean_items.py",
        "src/task2/task2_clean_products.py",
        "src/task2/task2_validate_timestamps.py",
        "src/task2/task2_assess_label_reliability.py",
        "src/task2/task2_label_sensitivity.py",
        "src/task2/task2_clean_orders.py",
        "src/task3/task3_exploratory_analysis.py",
        "src/task3/task3_validate_findings.py",
        "src/task4/task4_audit_feature_eligibility.py",
        "src/task4/task4_audit_numeric_quality.py",
        "src/task4/task4_audit_numeric_outliers.py",
        "src/task4/task4_build_features.py",
        "src/task4/task4_validate_features.py",
        "src/task5/measure_pipeline_resources.py",
        "src/task5/capture_environment.py",
    ]

    for path in required:
        require_file(path)


def reset_generated_outputs():
    if DATABASE.exists():
        DATABASE.unlink()

    if OUTPUTS.exists():
        shutil.rmtree(OUTPUTS)

    for directory in [
        INTERMEDIATE,
        FINAL,
        FIGURES,
        EVIDENCE,
        TABLES,
    ]:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def run_command(
    name,
    command,
    execution_rows,
    stdout_path=None,
):
    print()
    print(f"=== {name} ===")

    start = time.perf_counter()

    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    elapsed = (
        time.perf_counter()
        - start
    )

    if stdout_path is not None:
        path = ROOT / stdout_path

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            result.stdout,
            encoding="utf-8",
        )

    if result.stdout.strip():
        print(result.stdout.rstrip())

    if result.stderr.strip():
        print(
            result.stderr.rstrip(),
            file=sys.stderr,
        )

    execution_rows.append(
        {
            "step": name,
            "command": " ".join(["python3"] + command[1:]),
            "runtime_seconds": elapsed,
            "return_code": result.returncode,
            "status": (
                "passed"
                if result.returncode == 0
                else "failed"
            ),
        }
    )

    if result.returncode != 0:
        write_execution_log(
            execution_rows
        )

        raise RuntimeError(
            f"Pipeline step failed: {name}"
        )


def run_sql(
    name,
    sql_file,
    execution_rows,
    stdout_path,
):
    print()
    print(f"=== {name} ===")

    start = time.perf_counter()

    result = subprocess.run(
        [
            sys.executable,
            SQL_RUNNER,
            str(DATABASE),
            sql_file,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    elapsed = (
        time.perf_counter()
        - start
    )

    output_path = ROOT / stdout_path

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        result.stdout,
        encoding="utf-8",
    )

    if result.stdout.strip():
        print(result.stdout.rstrip())

    if result.stderr.strip():
        print(
            result.stderr.rstrip(),
            file=sys.stderr,
        )

    execution_rows.append(
        {
            "step": name,
            "command": (
                f"python3 {SQL_RUNNER} marketplace.sqlite {sql_file}"
            ),
            "runtime_seconds": elapsed,
            "return_code": result.returncode,
            "status": (
                "passed"
                if result.returncode == 0
                else "failed"
            ),
        }
    )

    if result.returncode != 0:
        write_execution_log(
            execution_rows
        )

        raise RuntimeError(
            f"Pipeline step failed: {name}"
        )


def write_execution_log(rows):
    EXECUTION_LOG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with EXECUTION_LOG.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "step",
                "command",
                "runtime_seconds",
                "return_code",
                "status",
            ],
        )

        writer.writeheader()
        writer.writerows(rows)


def validate_final_outputs():
    required_outputs = [
        "marketplace.sqlite",
        "outputs/intermediate/items_clean.sqlite",
        "outputs/intermediate/catalogue_clean.sqlite",
        "outputs/intermediate/order_level.sqlite",
        "outputs/intermediate/order_level_clean.sqlite",
        "outputs/tables/task3_delay_summary.csv",
        "outputs/tables/task3_lead_time_analysis.csv",
        "outputs/tables/task3_state_analysis.csv",
        "outputs/tables/task3_state_data_quality.csv",
        "outputs/tables/task3_state_priority.csv",
        "outputs/tables/task3_lead_time_within_state.csv",
        "outputs/tables/task3_lead_time_confound_summary.csv",
        "outputs/figures/task3_delay_distribution.png",
        "outputs/figures/task3_lead_time_vs_late_rate.png",
        "outputs/figures/task3_state_late_rates.png",
        "outputs/figures/task3_lead_time_confound.png",
        "outputs/final/task4_features.csv",
        "outputs/final/task4_order_ids.csv",
        "outputs/final/task4_labels.csv",
        "outputs/evidence/task1_resources.csv",
        "outputs/evidence/task1_loading_benchmark.csv",
        "outputs/evidence/task1_validation.txt",
        "outputs/evidence/task2_data_quality_profile.txt",
        "outputs/evidence/task2_item_repair_summary.csv",
        "outputs/evidence/task2_item_repair_reconciliation.csv",
        "outputs/evidence/task2_item_repairs.csv",
        "outputs/evidence/task2_item_repair_verification.csv",
        "outputs/evidence/task2_catalogue_repair_summary.csv",
        "outputs/evidence/task2_catalogue_repairs.csv",
        "outputs/evidence/task2_catalogue_coverage.csv",
        "outputs/evidence/task2_timestamp_validation.csv",
        "outputs/evidence/task2_label_reliability.csv",
        "outputs/evidence/task2_label_sensitivity.csv",
        "outputs/evidence/task2_cleaning_summary.csv",
        "outputs/evidence/task2_label_exclusions.csv",
        "outputs/evidence/task2_clean_validation.txt",
        "outputs/evidence/task3_sensitivity.csv",
        "outputs/evidence/task3_lead_time_robustness.csv",
        "outputs/evidence/task3_state_validity.csv",
        "outputs/evidence/task3_state_sensitivity.csv",
        "outputs/evidence/task3_within_state_robustness.csv",
        "outputs/evidence/task4_feature_eligibility.csv",
        "outputs/evidence/task4_candidate_feature_summary.csv",
        "outputs/evidence/task4_source_column_coverage.csv",
        "outputs/evidence/task4_numeric_quality_summary.csv",
        "outputs/evidence/task4_numeric_quality_label_association.csv",
        "outputs/evidence/task4_numeric_quality_state_association.csv",
        "outputs/evidence/task4_numeric_outlier_summary.csv",
        "outputs/evidence/task4_feature_dictionary.csv",
        "outputs/evidence/task4_feature_build_summary.csv",
        "outputs/evidence/task4_feature_validation.csv",
        "outputs/evidence/task5_pipeline_resource_comparison.csv",
        "outputs/evidence/task5_environment.csv",
    ]

    missing = [
        path
        for path in required_outputs
        if not (ROOT / path).exists()
    ]

    if missing:
        raise RuntimeError(
            "Pipeline completed but required outputs are missing: "
            + ", ".join(missing)
        )


def main():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError(
            "Run this command from the repository root: "
            "python3 run_pipeline.py"
        )

    check_required_files()
    reset_generated_outputs()

    execution_rows = []

    pipeline_start = time.perf_counter()

    run_command(
        "Build source SQLite database",
        [
            sys.executable,
            "setup_db.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 2 item-value repair (runs before the Task 1 build)",
        [
            sys.executable,
            "src/task2/task2_clean_items.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 2 catalogue repair (runs before the Task 1 build)",
        [
            sys.executable,
            "src/task2/task2_clean_products.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 1 resource measurement and order-level build",
        [
            sys.executable,
            "src/task1/task1_measure_resources.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 1 loading benchmark",
        [
            sys.executable,
            "src/task1/task1_benchmark_loading.py",
        ],
        execution_rows,
    )

    run_sql(
        "Task 1 validation",
        "sql/task1_validate_order_level.sql",
        execution_rows,
        "outputs/evidence/task1_validation.txt",
    )

    run_sql(
        "Task 2 data-quality profile",
        "sql/task2_profile_data_quality.sql",
        execution_rows,
        "outputs/evidence/task2_data_quality_profile.txt",
    )

    run_command(
        "Task 2 timestamp validation",
        [
            sys.executable,
            "src/task2/task2_validate_timestamps.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 2 label reliability assessment",
        [
            sys.executable,
            "src/task2/task2_assess_label_reliability.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 2 label sensitivity",
        [
            sys.executable,
            "src/task2/task2_label_sensitivity.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 2 clean order records",
        [
            sys.executable,
            "src/task2/task2_clean_orders.py",
        ],
        execution_rows,
    )

    run_sql(
        "Task 2 clean-data validation",
        "sql/task2_validate_clean_data.sql",
        execution_rows,
        "outputs/evidence/task2_clean_validation.txt",
    )

    run_command(
        "Task 3 exploratory analysis",
        [
            sys.executable,
            "src/task3/task3_exploratory_analysis.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 3 robustness validation",
        [
            sys.executable,
            "src/task3/task3_validate_findings.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 4 feature eligibility audit",
        [
            sys.executable,
            "src/task4/task4_audit_feature_eligibility.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 4 numerical quality audit",
        [
            sys.executable,
            "src/task4/task4_audit_numeric_quality.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 4 numerical outlier audit",
        [
            sys.executable,
            "src/task4/task4_audit_numeric_outliers.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 4 feature build",
        [
            sys.executable,
            "src/task4/task4_build_features.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 4 feature validation",
        [
            sys.executable,
            "src/task4/task4_validate_features.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 5 isolated resource profiling",
        [
            sys.executable,
            "src/task5/measure_pipeline_resources.py",
        ],
        execution_rows,
    )

    run_command(
        "Task 5 environment capture",
        [
            sys.executable,
            "src/task5/capture_environment.py",
        ],
        execution_rows,
    )

    validate_final_outputs()

    total_runtime = (
        time.perf_counter()
        - pipeline_start
    )

    execution_rows.append(
        {
            "step": "Complete pipeline",
            "command": "python3 run_pipeline.py",
            "runtime_seconds": total_runtime,
            "return_code": 0,
            "status": "passed",
        }
    )

    write_execution_log(
        execution_rows
    )

    print()
    print("=== Pipeline complete ===")

    print(
        f"steps_completed="
        f"{len(execution_rows) - 1}"
    )

    print(
        f"total_runtime_seconds="
        f"{total_runtime:.3f}"
    )

    print(
        "execution_log="
        "outputs/evidence/pipeline_execution.csv"
    )


if __name__ == "__main__":
    main()