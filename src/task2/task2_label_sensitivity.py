# Task 2 - Measure sensitivity of delivery-label reliability rules

import csv
import os
import sqlite3
from datetime import datetime

SOURCE_DB = "outputs/intermediate/order_level.sqlite"
EVIDENCE_OUT = "outputs/evidence/task2_label_sensitivity.csv"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_timestamp(value):
    if value is None:
        return None

    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return None


def summarize(name, labels):
    labeled = len(labels)
    late = sum(labels)
    on_time = labeled - late

    return {
        "rule": name,
        "labeled_orders": labeled,
        "late_orders": late,
        "on_time_orders": on_time,
        "late_rate": late / labeled if labeled else None,
    }


os.makedirs("outputs/evidence", exist_ok=True)

with sqlite3.connect(SOURCE_DB) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM order_level").fetchall()

minimal_labels = []
primary_labels = []
carrier_strict_labels = []

for row in rows:
    status = row["order_status"].strip().lower()

    if status != "delivered":
        continue

    purchase = parse_timestamp(row["order_purchase_timestamp"])
    approved = parse_timestamp(row["order_approved_at"])
    carrier = parse_timestamp(row["order_delivered_carrier_date"])
    delivered = parse_timestamp(row["order_delivered_customer_date"])
    estimated = parse_timestamp(row["order_estimated_delivery_date"])

    if delivered is None or estimated is None:
        continue

    label = int(delivered.date() > estimated.date())

    minimal_labels.append(label)

    primary_reliable = (
        purchase is not None
        and approved is not None
        and delivered >= purchase
        and delivered >= approved
        and estimated >= purchase
        and estimated >= approved
    )

    if primary_reliable:
        primary_labels.append(label)

    carrier_strict_reliable = (
        primary_reliable
        and carrier is not None
        and carrier >= approved
        and delivered >= carrier
    )

    if carrier_strict_reliable:
        carrier_strict_labels.append(label)


results = [
    summarize(
        "minimal_valid_delivery_and_estimate",
        minimal_labels,
    ),
    summarize(
        "primary_purchase_approval_chronology",
        primary_labels,
    ),
    summarize(
        "carrier_strict_chronology",
        carrier_strict_labels,
    ),
]

primary_count = results[1]["labeled_orders"]
primary_rate = results[1]["late_rate"]

for result in results:
    result["orders_difference_from_primary"] = (
        result["labeled_orders"] - primary_count
    )

    result["late_rate_difference_from_primary"] = (
        result["late_rate"] - primary_rate
        if result["late_rate"] is not None
        else None
    )


with open(EVIDENCE_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=[
            "rule",
            "labeled_orders",
            "late_orders",
            "on_time_orders",
            "late_rate",
            "orders_difference_from_primary",
            "late_rate_difference_from_primary",
        ],
    )

    writer.writeheader()
    writer.writerows(results)


print("=== Label sensitivity ===")

for result in results:
    print(
        f"{result['rule']}: "
        f"labeled={result['labeled_orders']}, "
        f"late={result['late_orders']}, "
        f"on_time={result['on_time_orders']}, "
        f"late_rate={result['late_rate']:.4%}, "
        f"orders_vs_primary="
        f"{result['orders_difference_from_primary']}"
    )

print(f"\nevidence_file={EVIDENCE_OUT}")