# Task 2 - Validate timestamps and chronology

import csv
import os
import sqlite3
from datetime import datetime

SOURCE_DB = "outputs/intermediate/order_level.sqlite"
EVIDENCE_OUT = "outputs/evidence/task2_timestamp_validation.csv"

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

TIMESTAMP_COLUMNS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def parse_timestamp(value):
    if value is None:
        return None, "missing"

    try:
        parsed = datetime.strptime(value, TIMESTAMP_FORMAT)
        return parsed, "valid"
    except (TypeError, ValueError):
        return None, "invalid"


os.makedirs("outputs/evidence", exist_ok=True)

with sqlite3.connect(SOURCE_DB) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM order_level").fetchall()

timestamp_counts = {
    column: {
        "missing": 0,
        "invalid": 0,
        "valid": 0,
    }
    for column in TIMESTAMP_COLUMNS
}

chronology_counts = {
    "approval_before_purchase": 0,
    "carrier_before_approval": 0,
    "delivery_before_carrier": 0,
    "delivery_before_purchase": 0,
    "estimated_before_purchase": 0,
    "estimated_before_approval": 0,
}

invalid_examples = []

for row in rows:
    parsed = {}

    for column in TIMESTAMP_COLUMNS:
        value = row[column]
        parsed_value, status = parse_timestamp(value)

        timestamp_counts[column][status] += 1
        parsed[column] = parsed_value

        if status == "invalid" and len(invalid_examples) < 50:
            invalid_examples.append(
                {
                    "order_id": row["order_id"],
                    "column": column,
                    "value": value,
                }
            )

    purchase = parsed["order_purchase_timestamp"]
    approved = parsed["order_approved_at"]
    carrier = parsed["order_delivered_carrier_date"]
    delivered = parsed["order_delivered_customer_date"]
    estimated = parsed["order_estimated_delivery_date"]

    if purchase is not None and approved is not None and approved < purchase:
        chronology_counts["approval_before_purchase"] += 1

    if approved is not None and carrier is not None and carrier < approved:
        chronology_counts["carrier_before_approval"] += 1

    if carrier is not None and delivered is not None and delivered < carrier:
        chronology_counts["delivery_before_carrier"] += 1

    if purchase is not None and delivered is not None and delivered < purchase:
        chronology_counts["delivery_before_purchase"] += 1

    if purchase is not None and estimated is not None and estimated < purchase:
        chronology_counts["estimated_before_purchase"] += 1

    if approved is not None and estimated is not None and estimated < approved:
        chronology_counts["estimated_before_approval"] += 1


with open(EVIDENCE_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)

    writer.writerow(["section", "metric", "value"])

    for column, counts in timestamp_counts.items():
        for status, value in counts.items():
            writer.writerow(
                [
                    "timestamp_parse",
                    f"{column}_{status}",
                    value,
                ]
            )

    for metric, value in chronology_counts.items():
        writer.writerow(
            [
                "chronology",
                metric,
                value,
            ]
        )


print("=== Strict timestamp validation ===")

for column, counts in timestamp_counts.items():
    print(
        f"{column}: "
        f"valid={counts['valid']}, "
        f"missing={counts['missing']}, "
        f"invalid={counts['invalid']}"
    )

print("\n=== Chronology checks ===")

for metric, value in chronology_counts.items():
    print(f"{metric}={value}")

print("\n=== Invalid timestamp examples ===")

if invalid_examples:
    for example in invalid_examples:
        print(
            f"{example['order_id']} | "
            f"{example['column']} | "
            f"{example['value']}"
        )
else:
    print("none")

print(f"\nevidence_file={EVIDENCE_OUT}")