# Task 2 - Clean order records and construct reliable delivery labels

import csv
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

SOURCE_DB = "outputs/intermediate/order_level.sqlite"
CLEAN_DB = "outputs/intermediate/order_level_clean.sqlite"
SUMMARY_OUT = "outputs/evidence/task2_cleaning_summary.csv"
EXCLUSIONS_OUT = "outputs/evidence/task2_label_exclusions.csv"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
SHIFTED_DELIVERY_OFFSET = timedelta(days=7)

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
        return datetime.strptime(value, TIMESTAMP_FORMAT), "valid"
    except (TypeError, ValueError):
        return None, "invalid"


def normalize_status(value):
    if value is None:
        return None
    value = value.strip().lower()
    return value or None


def normalize_state(value):
    if value is None:
        return None
    value = value.strip().upper()
    return value or None


os.makedirs("outputs/intermediate", exist_ok=True)
os.makedirs("outputs/evidence", exist_ok=True)

if os.path.exists(CLEAN_DB):
    os.remove(CLEAN_DB)

with sqlite3.connect(SOURCE_DB) as source_conn:
    source_conn.row_factory = sqlite3.Row
    source_rows = source_conn.execute(
        "SELECT * FROM order_level ORDER BY order_id"
    ).fetchall()

summary = Counter()
exclusions = []
clean_rows = []

for row in source_rows:
    summary["source_orders"] += 1

    normalized_status = normalize_status(row["order_status"])
    normalized_state = normalize_state(row["customer_state"])

    if normalized_status != row["order_status"]:
        summary["status_values_normalized"] += 1

    if normalized_state != row["customer_state"]:
        summary["state_values_normalized"] += 1

    if row["items_with_missing_price"]:
        summary["orders_with_missing_item_price"] += 1

    if row["items_with_missing_freight"]:
        summary["orders_with_missing_item_freight"] += 1

    if row["items_repaired"]:
        summary["orders_with_repaired_item_values"] += 1
        summary["item_values_repaired"] += row["items_repaired"]

    if row["total_item_price"] is None:
        summary["orders_without_usable_item_price_total"] += 1

    if row["total_freight_value"] is None:
        summary["orders_without_usable_freight_total"] += 1

    if row["items_with_missing_product_reference"]:
        summary["orders_with_unmatched_product_reference"] += 1

    if row["items_with_missing_seller_reference"]:
        summary["orders_with_unmatched_seller_reference"] += 1

    if row["total_product_weight_g"] is None:
        summary["orders_without_usable_weight_total"] += 1

    if row["total_product_volume_cm3"] is None:
        summary["orders_without_usable_volume_total"] += 1

    if row["primary_product_category"] is None:
        summary["orders_without_product_category"] += 1

    if row["items_with_known_seller_state"] == 0:
        summary["orders_without_known_seller_state"] += 1
    elif row["items_from_customer_state"] == row["items_with_known_seller_state"]:
        summary["orders_shipped_entirely_from_customer_state"] += 1
    elif row["items_from_customer_state"] == 0:
        summary["orders_shipped_entirely_from_other_states"] += 1
    else:
        summary["orders_shipped_from_mixed_states"] += 1

    parsed = {}
    parse_status = {}

    for column in TIMESTAMP_COLUMNS:
        parsed[column], parse_status[column] = parse_timestamp(row[column])

        if parse_status[column] == "invalid":
            summary[f"{column}_invalid"] += 1

        if parse_status[column] == "missing":
            summary[f"{column}_missing"] += 1

    purchase = parsed["order_purchase_timestamp"]
    approved = parsed["order_approved_at"]
    carrier = parsed["order_delivered_carrier_date"]
    delivered = parsed["order_delivered_customer_date"]
    estimated = parsed["order_estimated_delivery_date"]

    exclusion_reasons = []

    if normalized_status != "delivered":
        exclusion_reasons.append("status_not_delivered")
    else:
        if purchase is None:
            exclusion_reasons.append(
                "missing_or_invalid_purchase_timestamp"
            )

        if approved is None:
            exclusion_reasons.append(
                "missing_or_invalid_approval_timestamp"
            )

        if delivered is None:
            exclusion_reasons.append(
                "missing_or_invalid_delivery_timestamp"
            )

        if estimated is None:
            exclusion_reasons.append(
                "missing_or_invalid_estimated_timestamp"
            )

        if purchase is not None and approved is not None:
            if approved < purchase:
                exclusion_reasons.append("approval_before_purchase")

        if purchase is not None and delivered is not None:
            if delivered < purchase:
                exclusion_reasons.append("delivery_before_purchase")

        if approved is not None and delivered is not None:
            if delivered < approved:
                exclusion_reasons.append("delivery_before_approval")

        if purchase is not None and estimated is not None:
            if estimated < purchase:
                exclusion_reasons.append("estimate_before_purchase")

        if approved is not None and estimated is not None:
            if estimated < approved:
                exclusion_reasons.append("estimate_before_approval")

    delivery_before_approval_offset_days = None
    delivery_shift_pattern = None

    if delivered is not None and approved is not None and delivered < approved:
        offset = approved - delivered

        delivery_before_approval_offset_days = (
            offset.total_seconds() / 86400
        )

        summary["orders_with_delivery_before_approval"] += 1

        if offset == SHIFTED_DELIVERY_OFFSET:
            delivery_shift_pattern = "delivery_shifted_seven_days_before_approval"
            summary["orders_with_seven_day_delivery_shift"] += 1

            if estimated is not None:
                if delivered.date() > estimated.date():
                    summary["seven_day_shift_orders_that_would_be_late"] += 1
                else:
                    summary["seven_day_shift_orders_that_would_be_on_time"] += 1
        else:
            delivery_shift_pattern = "other_delivery_before_approval"
            summary["orders_with_other_delivery_before_approval"] += 1

    label = None

    if not exclusion_reasons:
        label = int(delivered.date() > estimated.date())
        summary["label_eligible_orders"] += 1

        if label == 1:
            summary["late_orders"] += 1
        else:
            summary["on_time_orders"] += 1
    else:
        summary["label_excluded_orders"] += 1

        for reason in exclusion_reasons:
            summary[f"exclusion_{reason}"] += 1

        exclusions.append(
            (
                row["order_id"],
                "|".join(exclusion_reasons),
            )
        )

    clean_rows.append(
        (
            row["order_id"],
            row["customer_id"],
            normalized_status,
            row["order_purchase_timestamp"],
            row["order_approved_at"],
            row["order_delivered_carrier_date"],
            row["order_delivered_customer_date"],
            row["order_estimated_delivery_date"],
            purchase.isoformat(sep=" ") if purchase else None,
            approved.isoformat(sep=" ") if approved else None,
            carrier.isoformat(sep=" ") if carrier else None,
            delivered.isoformat(sep=" ") if delivered else None,
            estimated.isoformat(sep=" ") if estimated else None,
            row["customer_unique_id"],
            row["customer_zip_code_prefix"],
            row["customer_city"],
            normalized_state,
            row["item_count"],
            row["distinct_product_count"],
            row["distinct_seller_count"],
            row["total_item_price"],
            row["total_freight_value"],
            row["total_item_price_raw"],
            row["total_freight_value_raw"],
            row["items_with_missing_price"],
            row["items_with_missing_freight"],
            row["items_repaired"],
            row["total_product_weight_g"],
            row["max_product_weight_g"],
            row["total_product_volume_cm3"],
            row["max_product_volume_cm3"],
            row["avg_product_photos_qty"],
            row["items_with_missing_product_reference"],
            row["items_with_missing_weight"],
            row["items_with_missing_volume"],
            row["distinct_category_count"],
            row["primary_product_category"],
            row["primary_product_category_english"],
            row["items_with_missing_seller_reference"],
            row["distinct_seller_state_count"],
            row["primary_seller_state"],
            row["items_from_customer_state"],
            row["items_with_known_seller_state"],
            delivery_before_approval_offset_days,
            delivery_shift_pattern,
            row["payment_row_count"],
            row["payment_type_count"],
            row["total_payment_value"],
            row["max_payment_installments"],
            row["review_count"],
            row["avg_review_score"],
            row["min_review_score"],
            row["max_review_score"],
            label,
            1 if label is not None else 0,
            "|".join(exclusion_reasons) if exclusion_reasons else None,
        )
    )

with sqlite3.connect(CLEAN_DB) as clean_conn:
    clean_conn.execute(
        """
        CREATE TABLE order_level_clean (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            order_status TEXT,
            order_purchase_timestamp_raw TEXT,
            order_approved_at_raw TEXT,
            order_delivered_carrier_date_raw TEXT,
            order_delivered_customer_date_raw TEXT,
            order_estimated_delivery_date_raw TEXT,
            order_purchase_timestamp TEXT,
            order_approved_at TEXT,
            order_delivered_carrier_date TEXT,
            order_delivered_customer_date TEXT,
            order_estimated_delivery_date TEXT,
            customer_unique_id TEXT,
            customer_zip_code_prefix TEXT,
            customer_city TEXT,
            customer_state TEXT,
            item_count INTEGER NOT NULL,
            distinct_product_count INTEGER NOT NULL,
            distinct_seller_count INTEGER NOT NULL,
            total_item_price REAL,
            total_freight_value REAL,
            total_item_price_raw REAL,
            total_freight_value_raw REAL,
            items_with_missing_price INTEGER NOT NULL,
            items_with_missing_freight INTEGER NOT NULL,
            items_repaired INTEGER NOT NULL,
            total_product_weight_g REAL,
            max_product_weight_g REAL,
            total_product_volume_cm3 REAL,
            max_product_volume_cm3 REAL,
            avg_product_photos_qty REAL,
            items_with_missing_product_reference INTEGER NOT NULL,
            items_with_missing_weight INTEGER NOT NULL,
            items_with_missing_volume INTEGER NOT NULL,
            distinct_category_count INTEGER NOT NULL,
            primary_product_category TEXT,
            primary_product_category_english TEXT,
            items_with_missing_seller_reference INTEGER NOT NULL,
            distinct_seller_state_count INTEGER NOT NULL,
            primary_seller_state TEXT,
            items_from_customer_state INTEGER NOT NULL,
            items_with_known_seller_state INTEGER NOT NULL,
            delivery_before_approval_offset_days REAL,
            delivery_shift_pattern TEXT,
            payment_row_count INTEGER NOT NULL,
            payment_type_count INTEGER NOT NULL,
            total_payment_value INTEGER,
            max_payment_installments INTEGER,
            review_count INTEGER NOT NULL,
            avg_review_score REAL,
            min_review_score INTEGER,
            max_review_score INTEGER,
            delivered_after_estimate INTEGER,
            delivery_label_eligible INTEGER NOT NULL,
            delivery_label_exclusion_reasons TEXT
        )
        """
    )

    clean_conn.executemany(
        """
        INSERT INTO order_level_clean VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        )
        """,
        clean_rows,
    )

    clean_conn.commit()

summary["clean_orders"] = len(clean_rows)

with open(SUMMARY_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["metric", "value"])

    for metric in sorted(summary):
        writer.writerow([metric, summary[metric]])

with open(EXCLUSIONS_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["order_id", "exclusion_reasons"])
    writer.writerows(exclusions)

print("=== Task 2 cleaning summary ===")

for metric in sorted(summary):
    print(f"{metric}={summary[metric]}")

print(f"\nclean_database={CLEAN_DB}")
print(f"summary_file={SUMMARY_OUT}")
print(f"exclusions_file={EXCLUSIONS_OUT}")