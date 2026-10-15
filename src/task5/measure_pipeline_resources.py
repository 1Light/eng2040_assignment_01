# Task 5 - Measure pipeline resources in isolated clean workspaces

import csv
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CANONICAL_OUTPUTS = ROOT / "outputs"
CANONICAL_EVIDENCE = CANONICAL_OUTPUTS / "evidence"
RESOURCE_OUT = (
    CANONICAL_EVIDENCE
    / "task5_pipeline_resource_comparison.csv"
)

SQL_RUNNER = "src/common/run_sql_script.py"

STAGES = [
    {
        "name": "Build source SQLite database",
        "type": "command",
        "command": [
            sys.executable,
            "setup_db.py",
        ],
    },
    {
        "name": "Task 2 item-value repair (runs before the Task 1 build)",
        "type": "command",
        "command": [
            sys.executable,
            "src/task2/task2_clean_items.py",
        ],
    },
    {
        "name": "Task 2 catalogue repair (runs before the Task 1 build)",
        "type": "command",
        "command": [
            sys.executable,
            "src/task2/task2_clean_products.py",
        ],
    },
    {
        "name": "Task 1 resource measurement and order-level build",
        "type": "command",
        "command": [
            sys.executable,
            "src/task1/task1_measure_resources.py",
        ],
    },
    {
        "name": "Task 1 loading benchmark",
        "type": "command",
        "command": [
            sys.executable,
            "src/task1/task1_benchmark_loading.py",
        ],
    },
    {
        "name": "Task 1 validation",
        "type": "sql",
        "sql": "sql/task1_validate_order_level.sql",
    },
    {
        "name": "Task 2 data-quality profile",
        "type": "sql",
        "sql": "sql/task2_profile_data_quality.sql",
    },
    {
        "name": "Task 2 timestamp validation",
        "type": "command",
        "command": [
            sys.executable,
            "src/task2/task2_validate_timestamps.py",
        ],
    },
    {
        "name": "Task 2 label reliability assessment",
        "type": "command",
        "command": [
            sys.executable,
            "src/task2/task2_assess_label_reliability.py",
        ],
    },
    {
        "name": "Task 2 label sensitivity",
        "type": "command",
        "command": [
            sys.executable,
            "src/task2/task2_label_sensitivity.py",
        ],
    },
    {
        "name": "Task 2 clean order records",
        "type": "command",
        "command": [
            sys.executable,
            "src/task2/task2_clean_orders.py",
        ],
    },
    {
        "name": "Task 2 clean-data validation",
        "type": "sql",
        "sql": "sql/task2_validate_clean_data.sql",
    },
    {
        "name": "Task 3 exploratory analysis",
        "type": "command",
        "command": [
            sys.executable,
            "src/task3/task3_exploratory_analysis.py",
        ],
    },
    {
        "name": "Task 3 robustness validation",
        "type": "command",
        "command": [
            sys.executable,
            "src/task3/task3_validate_findings.py",
        ],
    },
    {
        "name": "Task 4 feature eligibility audit",
        "type": "command",
        "command": [
            sys.executable,
            "src/task4/task4_audit_feature_eligibility.py",
        ],
    },
    {
        "name": "Task 4 numerical quality audit",
        "type": "command",
        "command": [
            sys.executable,
            "src/task4/task4_audit_numeric_quality.py",
        ],
    },
    {
        "name": "Task 4 numerical outlier audit",
        "type": "command",
        "command": [
            sys.executable,
            "src/task4/task4_audit_numeric_outliers.py",
        ],
    },
    {
        "name": "Task 4 feature build",
        "type": "command",
        "command": [
            sys.executable,
            "src/task4/task4_build_features.py",
        ],
    },
    {
        "name": "Task 4 feature validation",
        "type": "command",
        "command": [
            sys.executable,
            "src/task4/task4_validate_features.py",
        ],
    },
]


def safe_directory_size(path):
    path = Path(path)

    try:
        if not path.exists():
            return 0
    except FileNotFoundError:
        return 0

    try:
        if path.is_file():
            return path.stat().st_size
    except FileNotFoundError:
        return 0

    total = 0
    stack = [path]

    while stack:
        current = stack.pop()

        try:
            entries = list(
                os.scandir(current)
            )
        except (
            FileNotFoundError,
            NotADirectoryError,
            PermissionError,
        ):
            continue

        for entry in entries:
            try:
                if entry.is_symlink():
                    continue

                if entry.is_dir(
                    follow_symlinks=False
                ):
                    stack.append(
                        Path(entry.path)
                    )

                elif entry.is_file(
                    follow_symlinks=False
                ):
                    total += entry.stat(
                        follow_symlinks=False
                    ).st_size

            except (
                FileNotFoundError,
                PermissionError,
            ):
                continue

    return total


def copy_source_repository(destination):
    excluded_names = {
        ".git",
        ".DS_Store",
        "__pycache__",
        "marketplace.sqlite",
        "outputs",
    }

    def ignore(directory, names):
        ignored = []

        for name in names:
            if name in excluded_names:
                ignored.append(name)

            elif name.endswith(".pyc"):
                ignored.append(name)

        return ignored

    shutil.copytree(
        ROOT,
        destination,
        ignore=ignore,
    )


def prepare_workspace(workspace):
    outputs = workspace / "outputs"

    for directory in [
        outputs / "intermediate",
        outputs / "final",
        outputs / "figures",
        outputs / "evidence",
        outputs / "tables",
    ]:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def generated_storage_size(workspace):
    return (
        safe_directory_size(
            workspace / "marketplace.sqlite"
        )
        + safe_directory_size(
            workspace / "outputs"
        )
    )


def intermediate_storage_size(workspace):
    return safe_directory_size(
        workspace
        / "outputs"
        / "intermediate"
    )


def peak_rss_bytes(usage):
    if sys.platform == "darwin":
        return int(usage.ru_maxrss)

    return int(usage.ru_maxrss * 1024)


def run_measured_child(
    command,
    workspace,
    environment,
):
    with tempfile.TemporaryFile(
        mode="w+",
        encoding="utf-8",
    ) as stdout_file, tempfile.TemporaryFile(
        mode="w+",
        encoding="utf-8",
    ) as stderr_file:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
            env=environment,
        )

        _, status, usage = os.wait4(
            process.pid,
            0,
        )

        process.returncode = (
            os.waitstatus_to_exitcode(status)
        )

        stdout_file.seek(0)
        stderr_file.seek(0)

        return (
            process.returncode,
            stdout_file.read(),
            stderr_file.read(),
            peak_rss_bytes(usage),
        )


def monitor_temp_directory(
    path,
    stop_event,
    result,
):
    peak = 0
    samples = 0

    while not stop_event.is_set():
        current = safe_directory_size(
            path
        )

        peak = max(
            peak,
            current,
        )

        samples += 1

        time.sleep(0.005)

    current = safe_directory_size(
        path
    )

    peak = max(
        peak,
        current,
    )

    samples += 1

    result["peak_bytes"] = peak
    result["samples"] = samples


def execute_stage(
    workspace,
    stage,
):
    saved_before = (
        generated_storage_size(
            workspace
        )
    )

    stage_temp_root = (
        workspace
        / ".task5_temp"
    )

    stage_temp_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="stage_",
        dir=stage_temp_root,
    ) as temp_directory:
        temp_path = Path(
            temp_directory
        )

        environment = os.environ.copy()

        environment["TMPDIR"] = (
            str(temp_path)
        )

        environment["TMP"] = (
            str(temp_path)
        )

        environment["TEMP"] = (
            str(temp_path)
        )

        stop_event = threading.Event()

        temp_result = {
            "peak_bytes": 0,
            "samples": 0,
        }

        monitor = threading.Thread(
            target=monitor_temp_directory,
            args=(
                temp_path,
                stop_event,
                temp_result,
            ),
            daemon=True,
        )

        monitor.start()

        start = time.perf_counter()

        if stage["type"] == "command":
            command = stage["command"]

        else:
            command = [
                sys.executable,
                SQL_RUNNER,
                str(
                    workspace
                    / "marketplace.sqlite"
                ),
                stage["sql"],
            ]

        (
            return_code,
            stage_stdout,
            stage_stderr,
            peak_memory,
        ) = run_measured_child(
            command,
            workspace,
            environment,
        )

        runtime = (
            time.perf_counter()
            - start
        )

        stop_event.set()
        monitor.join()

        if return_code != 0:
            if stage_stdout.strip():
                print(
                    stage_stdout
                )

            if stage_stderr.strip():
                print(
                    stage_stderr,
                    file=sys.stderr,
                )

            raise RuntimeError(
                "Resource profiling failed at "
                f"{stage['name']}"
            )

        if temp_result["samples"] == 0:
            raise RuntimeError(
                "Temporary-storage monitor "
                f"recorded no samples for "
                f"{stage['name']}."
            )

        peak_temp = (
            temp_result[
                "peak_bytes"
            ]
        )

    shutil.rmtree(
        stage_temp_root,
        ignore_errors=True,
    )

    saved_after = (
        generated_storage_size(
            workspace
        )
    )

    return {
        "runtime_seconds": runtime,
        "peak_memory_bytes": peak_memory,
        "peak_temp_storage_bytes": peak_temp,
        "saved_storage_before_bytes": saved_before,
        "saved_storage_after_bytes": saved_after,
        "saved_storage_change_bytes": (
            saved_after
            - saved_before
        ),
        "intermediate_storage_after_bytes": (
            intermediate_storage_size(
                workspace
            )
        ),
    }


def run_pass(pass_name):
    print()
    print(
        f"=== {pass_name} ==="
    )

    with tempfile.TemporaryDirectory(
        prefix="eng2040_profile_"
    ) as temporary_root:
        workspace = (
            Path(temporary_root)
            / "repository"
        )

        copy_source_repository(
            workspace
        )

        prepare_workspace(
            workspace
        )

        results = []

        for index, stage in enumerate(
            STAGES,
            start=1,
        ):
            print(
                f"[{index}/{len(STAGES)}] "
                f"{stage['name']}"
            )

            metrics = execute_stage(
                workspace,
                stage,
            )

            results.append(
                {
                    "step": stage["name"],
                    **metrics,
                }
            )

            print(
                "  runtime="
                f"{metrics['runtime_seconds']:.4f}s"
            )

            print(
                "  peak_memory="
                f"{metrics['peak_memory_bytes'] / 1024 / 1024:.2f} MiB"
            )

            print(
                "  peak_temp="
                f"{metrics['peak_temp_storage_bytes'] / 1024 / 1024:.2f} MiB"
            )

            print(
                "  saved_after="
                f"{metrics['saved_storage_after_bytes'] / 1024 / 1024:.2f} MiB"
            )

        return results


def compare_passes(
    estimate_rows,
    measured_rows,
):
    if len(estimate_rows) != len(
        measured_rows
    ):
        raise RuntimeError(
            "Profiling passes have "
            "different stage counts."
        )

    rows = []

    for estimated, measured in zip(
        estimate_rows,
        measured_rows,
    ):
        if (
            estimated["step"]
            != measured["step"]
        ):
            raise RuntimeError(
                "Profiling pass stage mismatch."
            )

        rows.append(
            {
                "step": estimated["step"],
                "estimated_runtime_seconds": (
                    estimated[
                        "runtime_seconds"
                    ]
                ),
                "measured_runtime_seconds": (
                    measured[
                        "runtime_seconds"
                    ]
                ),
                "runtime_difference_seconds": (
                    measured[
                        "runtime_seconds"
                    ]
                    - estimated[
                        "runtime_seconds"
                    ]
                ),
                "estimated_peak_memory_bytes": (
                    estimated[
                        "peak_memory_bytes"
                    ]
                ),
                "measured_peak_memory_bytes": (
                    measured[
                        "peak_memory_bytes"
                    ]
                ),
                "memory_difference_bytes": (
                    measured[
                        "peak_memory_bytes"
                    ]
                    - estimated[
                        "peak_memory_bytes"
                    ]
                ),
                "estimated_peak_temp_storage_bytes": (
                    estimated[
                        "peak_temp_storage_bytes"
                    ]
                ),
                "measured_peak_temp_storage_bytes": (
                    measured[
                        "peak_temp_storage_bytes"
                    ]
                ),
                "temp_storage_difference_bytes": (
                    measured[
                        "peak_temp_storage_bytes"
                    ]
                    - estimated[
                        "peak_temp_storage_bytes"
                    ]
                ),
                "estimated_saved_storage_after_bytes": (
                    estimated[
                        "saved_storage_after_bytes"
                    ]
                ),
                "measured_saved_storage_after_bytes": (
                    measured[
                        "saved_storage_after_bytes"
                    ]
                ),
                "saved_storage_difference_bytes": (
                    measured[
                        "saved_storage_after_bytes"
                    ]
                    - estimated[
                        "saved_storage_after_bytes"
                    ]
                ),
                "measured_saved_storage_change_bytes": (
                    measured[
                        "saved_storage_change_bytes"
                    ]
                ),
                "measured_intermediate_storage_after_bytes": (
                    measured[
                        "intermediate_storage_after_bytes"
                    ]
                ),
            }
        )

    return rows


def write_results(rows):
    CANONICAL_EVIDENCE.mkdir(
        parents=True,
        exist_ok=True,
    )

    with RESOURCE_OUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=list(
                rows[0].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(rows)


def main():
    if not (ROOT / SQL_RUNNER).exists():
        raise RuntimeError(
            f"Required script does not exist: {SQL_RUNNER}"
        )

    print(
        "Task 5 isolated resource profiling"
    )

    print(
        "Canonical repository outputs "
        "will not be modified."
    )

    print(
        "Estimate = first isolated clean pass"
    )

    print(
        "Measured = second isolated clean pass"
    )

    print(
        "Peak memory = per-stage child rusage via os.wait4"
    )

    estimate_rows = run_pass(
        "Estimate calibration pass"
    )

    measured_rows = run_pass(
        "Measured verification pass"
    )

    comparison = compare_passes(
        estimate_rows,
        measured_rows,
    )

    write_results(
        comparison
    )

    print()

    print(
        "=== Resource profiling complete ==="
    )

    print(
        f"steps_profiled="
        f"{len(comparison)}"
    )

    print(
        "canonical_outputs_preserved=yes"
    )

    print(
        "resource_comparison="
        "outputs/evidence/"
        "task5_pipeline_resource_comparison.csv"
    )


if __name__ == "__main__":
    main()