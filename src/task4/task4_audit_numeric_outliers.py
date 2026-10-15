# Task 4 - Audit extreme numerical feature values

import os
import sqlite3

import pandas as pd

SOURCE_DB = "outputs/intermediate/order_level_clean.sqlite"

OUTLIER_SUMMARY_OUT = "outputs/evidence/task4_numeric_outlier_summary.csv"

NUMERIC_COLUMNS = [
    "total_item_price",
    "total_freight_value",
]

AUDIT_STAGES = {
    "raw": "{column}_raw",
    "repaired": "{column}",
}

THRESHOLDS = [
    0.95,
    0.975,
    0.99,
    0.995,
    0.999,
]


def load_data():
    with sqlite3.connect(SOURCE_DB) as conn:
        data = pd.read_sql_query(
            "SELECT * FROM order_level_clean",
            conn,
        )

    return data.loc[
        data["delivery_label_eligible"] == 1
    ].copy()


def build_outlier_summary(data):
    rows = []

    for column in NUMERIC_COLUMNS:
        for stage, pattern in AUDIT_STAGES.items():
            source_column = pattern.format(column=column)

            numeric = pd.to_numeric(
                data[source_column],
                errors="coerce",
            )

            positive = numeric[numeric > 0]

            for quantile in THRESHOLDS:
                threshold = positive.quantile(
                    quantile
                )

                above = positive[
                    positive > threshold
                ]

                rows.append(
                    {
                        "column": column,
                        "stage": stage,
                        "source_column": source_column,
                        "quantile": quantile,
                        "threshold": threshold,
                        "orders_above_threshold": len(above),
                        "share_of_positive_orders_above_threshold": (
                            len(above) / len(positive)
                        ),
                        "maximum": positive.max(),
                        "maximum_to_median_ratio": (
                            positive.max() / positive.median()
                        ),
                    }
                )

    result = pd.DataFrame(rows)

    result.to_csv(
        OUTLIER_SUMMARY_OUT,
        index=False,
    )

    return result


def main():
    os.makedirs(
        "outputs/evidence",
        exist_ok=True,
    )

    data = load_data()

    summary = build_outlier_summary(
        data
    )

    print(
        "=== Task 4 numerical outlier audit ==="
    )

    for column in NUMERIC_COLUMNS:
        for stage in AUDIT_STAGES:
            print()
            print(f"column={column}")
            print(f"stage={stage}")

            subset = summary[
                (summary["column"] == column)
                & (summary["stage"] == stage)
            ]

            for row in subset.itertuples():
                print(
                    f"q{row.quantile:.3f}="
                    f"{row.threshold:.2f}, "
                    f"above={row.orders_above_threshold}"
                )

            print(
                "max_to_median_ratio="
                f"{subset['maximum_to_median_ratio'].iloc[0]:.1f}"
            )

    print()
    print(
        f"outlier_summary="
        f"{OUTLIER_SUMMARY_OUT}"
    )


if __name__ == "__main__":
    main()