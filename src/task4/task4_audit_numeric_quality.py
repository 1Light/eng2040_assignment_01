# Task 4 - Audit numerical feature quality

import os
import sqlite3

import pandas as pd

SOURCE_DB = "outputs/intermediate/order_level_clean.sqlite"

SUMMARY_OUT = "outputs/evidence/task4_numeric_quality_summary.csv"
LABEL_ASSOCIATION_OUT = "outputs/evidence/task4_numeric_quality_label_association.csv"
STATE_ASSOCIATION_OUT = "outputs/evidence/task4_numeric_quality_state_association.csv"

NUMERIC_COLUMNS = [
    "total_item_price",
    "total_freight_value",
]

AUDIT_STAGES = {
    "raw": "{column}_raw",
    "repaired": "{column}",
}


def load_data():
    with sqlite3.connect(SOURCE_DB) as conn:
        data = pd.read_sql_query(
            "SELECT * FROM order_level_clean",
            conn,
        )

    return data.loc[
        data["delivery_label_eligible"] == 1
    ].copy()


def quality_category(series):
    numeric = pd.to_numeric(
        series,
        errors="coerce",
    )

    result = pd.Series(
        "positive",
        index=series.index,
        dtype="object",
    )

    result.loc[numeric.isna()] = "missing"
    result.loc[numeric == 0] = "zero"
    result.loc[numeric < 0] = "negative"

    return result


def build_summary(data):
    rows = []

    for column in NUMERIC_COLUMNS:
        for stage, pattern in AUDIT_STAGES.items():
            source_column = pattern.format(column=column)

            numeric = pd.to_numeric(
                data[source_column],
                errors="coerce",
            )

            positive = numeric[numeric > 0]

            rows.append(
                {
                    "column": column,
                    "stage": stage,
                    "source_column": source_column,
                    "retained_orders": len(data),
                    "missing_count": int(numeric.isna().sum()),
                    "zero_count": int((numeric == 0).sum()),
                    "negative_count": int((numeric < 0).sum()),
                    "positive_count": int((numeric > 0).sum()),
                    "positive_min": positive.min(),
                    "positive_p01": positive.quantile(0.01),
                    "positive_p05": positive.quantile(0.05),
                    "positive_median": positive.median(),
                    "positive_p95": positive.quantile(0.95),
                    "positive_p99": positive.quantile(0.99),
                    "positive_max": positive.max(),
                }
            )

    result = pd.DataFrame(rows)
    result.to_csv(SUMMARY_OUT, index=False)

    return result


def build_label_association(data):
    rows = []

    for column in NUMERIC_COLUMNS:
        for stage, pattern in AUDIT_STAGES.items():
            source_column = pattern.format(column=column)

            categories = quality_category(
                data[source_column]
            )

            working = pd.DataFrame(
                {
                    "quality_category": categories,
                    "label": data[
                        "delivered_after_estimate"
                    ].astype(int),
                }
            )

            for category, group in working.groupby(
                "quality_category",
                sort=True,
            ):
                orders = len(group)
                late_orders = int(group["label"].sum())

                rows.append(
                    {
                        "column": column,
                        "stage": stage,
                        "quality_category": category,
                        "orders": orders,
                        "late_orders": late_orders,
                        "late_rate": (
                            late_orders / orders
                            if orders > 0
                            else None
                        ),
                    }
                )

    result = pd.DataFrame(rows)
    result.to_csv(
        LABEL_ASSOCIATION_OUT,
        index=False,
    )

    return result


def build_state_association(data):
    rows = []

    for column in NUMERIC_COLUMNS:
        categories = quality_category(
            data[column]
        )

        working = pd.DataFrame(
            {
                "customer_state": data[
                    "customer_state"
                ],
                "quality_category": categories,
            }
        )

        invalid = working[
            working["quality_category"].isin(
                ["missing", "negative"]
            )
        ]

        grouped = (
            invalid.groupby(
                [
                    "customer_state",
                    "quality_category",
                ],
                dropna=False,
            )
            .size()
            .reset_index(name="orders")
        )

        grouped.insert(
            0,
            "column",
            column,
        )

        rows.append(grouped)

    result = pd.concat(
        rows,
        ignore_index=True,
    )

    result.to_csv(
        STATE_ASSOCIATION_OUT,
        index=False,
    )

    return result


def main():
    os.makedirs(
        "outputs/evidence",
        exist_ok=True,
    )

    data = load_data()

    summary = build_summary(data)
    label_association = build_label_association(data)
    state_association = build_state_association(data)

    print("=== Task 4 numerical quality audit ===")
    print(f"retained_orders={len(data)}")

    for row in summary.itertuples():
        print()
        print(f"column={row.column}")
        print(f"stage={row.stage}")
        print(f"missing_count={row.missing_count}")
        print(f"zero_count={row.zero_count}")
        print(f"negative_count={row.negative_count}")
        print(f"positive_count={row.positive_count}")
        print(f"positive_median={row.positive_median}")
        print(f"positive_p95={row.positive_p95}")
        print(f"positive_p99={row.positive_p99}")
        print(f"positive_max={row.positive_max}")

    print()
    print("Missingness association with late delivery:")

    repaired = label_association[
        label_association["stage"] == "repaired"
    ]

    for row in repaired.itertuples():
        print(
            f"{row.column} {row.quality_category}: "
            f"orders={row.orders} late_rate={row.late_rate:.4f}"
        )

    print()
    print(f"summary={SUMMARY_OUT}")
    print(
        "label_association="
        f"{LABEL_ASSOCIATION_OUT}"
    )
    print(
        "state_association="
        f"{STATE_ASSOCIATION_OUT}"
    )


if __name__ == "__main__":
    main()