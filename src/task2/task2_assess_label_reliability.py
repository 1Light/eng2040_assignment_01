# Task 2 - Assess delivery-label reliability

import csv
import os
import sqlite3
from collections import Counter
from datetime import datetime

SOURCE_DB = "outputs/intermediate/order_level.sqlite"
EVIDENCE_OUT = "outputs/evidence/task2_label_reliability.csv"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_timestamp(value):
    if value is None:
        return None

    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return None


os.makedirs("outputs/evidence", exist_ok=True)

with sqlite3.connect(SOURCE_DB) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM order_level").fetchall()

counts = Counter()

for row in rows:
    status = row["order_status"].strip().lower()

    purchase_raw = row["order_purchase_timestamp"]
    approved_raw = row["order_approved_at"]
    carrier_raw = row["order_delivered_carrier_date"]
    delivered_raw = row["order_delivered_customer_date"]
    estimated_raw = row["order_estimated_delivery_date"]

    purchase = parse_timestamp(purchase_raw)
    approved = parse_timestamp(approved_raw)
    carrier = parse_timestamp(carrier_raw)
    delivered = parse_timestamp(delivered_raw)
    estimated = parse_timestamp(estimated_raw)

    counts["total_orders"] += 1

    if status == "delivered":
        counts["status_delivered"] += 1
    else:
        counts["status_not_delivered"] += 1

    if delivered_raw is None:
        counts["missing_delivery_timestamp"] += 1
    elif delivered is None:
        counts["invalid_delivery_timestamp"] += 1

    if estimated_raw is None:
        counts["missing_estimated_timestamp"] += 1
    elif estimated is None:
        counts["invalid_estimated_timestamp"] += 1

    if (
        status == "delivered"
        and delivered is not None
        and estimated is not None
    ):
        counts["delivered_with_valid_label_timestamps"] += 1

        if delivered.date() > estimated.date():
            counts["candidate_late"] += 1
        else:
            counts["candidate_on_time"] += 1

        if purchase is None:
            counts["candidate_missing_or_invalid_purchase"] += 1

        if approved is None:
            counts["candidate_missing_or_invalid_approval"] += 1

        if carrier is None:
            counts["candidate_missing_or_invalid_carrier"] += 1

        if purchase is not None and delivered < purchase:
            counts["candidate_delivery_before_purchase"] += 1

        if approved is not None and delivered < approved:
            counts["candidate_delivery_before_approval"] += 1

        if carrier is not None and delivered < carrier:
            counts["candidate_delivery_before_carrier"] += 1

        if purchase is not None and estimated < purchase:
            counts["candidate_estimate_before_purchase"] += 1

        if approved is not None and estimated < approved:
            counts["candidate_estimate_before_approval"] += 1

        chronology_reliable = (
            purchase is not None
            and approved is not None
            and delivered >= purchase
            and delivered >= approved
            and estimated >= purchase
            and estimated >= approved
        )

        if chronology_reliable:
            counts["candidate_chronology_reliable"] += 1

            if delivered.date() > estimated.date():
                counts["reliable_late"] += 1
            else:
                counts["reliable_on_time"] += 1
        else:
            counts["candidate_chronology_unreliable"] += 1


with open(EVIDENCE_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["metric", "value"])

    for metric in sorted(counts):
        writer.writerow([metric, counts[metric]])


print("=== Delivery-label reliability assessment ===")

for metric in sorted(counts):
    print(f"{metric}={counts[metric]}")

print(f"\nevidence_file={EVIDENCE_OUT}")