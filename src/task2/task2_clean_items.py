# Task 2 - Repair corrupted item-level monetary values before aggregation

import csv
import os
import sqlite3
import statistics

SOURCE_DB = "marketplace.sqlite"
CLEAN_DB = "outputs/intermediate/items_clean.sqlite"
SUMMARY_OUT = "outputs/evidence/task2_item_repair_summary.csv"
RECONCILIATION_OUT = "outputs/evidence/task2_item_repair_reconciliation.csv"
REPAIRS_OUT = "outputs/evidence/task2_item_repairs.csv"
VERIFICATION_OUT = "outputs/evidence/task2_item_repair_verification.csv"

EXACT_RATIO_TOLERANCE = 0.01

NEGATED_TOLERANCE = {
    "price": 0.20,
    "freight_value": 0.05,
}

SCALE_FACTOR = 1000

MONETARY_COLUMNS = [
    "price",
    "freight_value",
]

SCALED_MIN_VALUE = {
    "price": 10000.0,
    "freight_value": 1000.0,
}

DEFECT_FAMILIES = [
    "scaled",
    "negated",
    "missing",
]

REPAIRABLE_DEFECTS = [
    "scaled",
    "negated",
]


def to_cents(value):
    return int(round(value * 100))


def is_scaled_amount(value):
    return to_cents(value) % SCALE_FACTOR == 0


def classify(column, value):
    if value is None:
        return "missing"

    if value < 0:
        return "negated"

    if value >= SCALED_MIN_VALUE[column] and is_scaled_amount(value):
        return "scaled"

    return None


def repair(value, defect):
    if defect == "scaled":
        return round(value / SCALE_FACTOR, 2)

    if defect == "negated":
        return round(abs(value), 2)

    return None


os.makedirs("outputs/intermediate", exist_ok=True)
os.makedirs("outputs/evidence", exist_ok=True)

if os.path.exists(CLEAN_DB):
    os.remove(CLEAN_DB)

with sqlite3.connect(SOURCE_DB) as source_conn:
    source_conn.row_factory = sqlite3.Row
    source_rows = source_conn.execute(
        "SELECT * FROM order_items ORDER BY order_id, order_item_id"
    ).fetchall()

defect_counts = {
    column: {defect: 0 for defect in DEFECT_FAMILIES}
    for column in MONETARY_COLUMNS
}

original_totals = {column: 0.0 for column in MONETARY_COLUMNS}
repaired_totals = {column: 0.0 for column in MONETARY_COLUMNS}
correction_totals = {column: 0.0 for column in MONETARY_COLUMNS}

clean_rows = []
repair_records = []
multi_defect_rows = 0

for row in source_rows:
    values = {}
    defects = {}

    for column in MONETARY_COLUMNS:
        original = row[column]
        defect = classify(column, original)
        defects[column] = defect

        if defect is None:
            values[column] = original
        else:
            defect_counts[column][defect] += 1
            values[column] = repair(original, defect)

        if original is not None:
            original_totals[column] += original

        if values[column] is not None:
            repaired_totals[column] += values[column]

        if defect in REPAIRABLE_DEFECTS:
            correction_totals[column] += values[column] - original

            repair_records.append(
                (
                    row["order_id"],
                    row["order_item_id"],
                    column,
                    defect,
                    original,
                    values[column],
                )
            )

    flagged = [
        column
        for column in MONETARY_COLUMNS
        if defects[column] is not None
    ]

    if len(flagged) > 1:
        multi_defect_rows += 1

    clean_rows.append(
        (
            row["order_id"],
            row["order_item_id"],
            row["product_id"],
            row["seller_id"],
            row["shipping_limit_date"],
            row["price"],
            row["freight_value"],
            values["price"],
            values["freight_value"],
            defects["price"],
            defects["freight_value"],
        )
    )

with sqlite3.connect(CLEAN_DB) as clean_conn:
    clean_conn.execute(
        """
        CREATE TABLE order_items_clean (
            order_id TEXT NOT NULL,
            order_item_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            shipping_limit_date TEXT,
            price_raw REAL,
            freight_value_raw REAL,
            price REAL,
            freight_value REAL,
            price_defect TEXT,
            freight_value_defect TEXT,
            PRIMARY KEY (order_id, order_item_id)
        )
        """
    )

    clean_conn.executemany(
        """
        INSERT INTO order_items_clean VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        clean_rows,
    )

    clean_conn.commit()

verification_rows = []

for column in MONETARY_COLUMNS:
    clean_by_product = {}
    clean_values = []

    for row in clean_rows:
        value = row[5] if column == "price" else row[6]
        defect = row[9] if column == "price" else row[10]
        product_id = row[2]

        if defect is None and value is not None and value > 0:
            clean_by_product.setdefault(product_id, []).append(value)
            clean_values.append(value)

    product_median = {
        product_id: statistics.median(values)
        for product_id, values in clean_by_product.items()
    }

    exact = 0
    near = 0
    without_reference = 0

    for row in clean_rows:
        raw = row[5] if column == "price" else row[6]
        defect = row[9] if column == "price" else row[10]

        if defect != "scaled":
            continue

        reference = product_median.get(row[2])

        if reference is None:
            without_reference += 1
            continue

        ratio = raw / reference

        if abs(ratio - SCALE_FACTOR) <= SCALE_FACTOR * EXACT_RATIO_TOLERANCE:
            exact += 1
        else:
            near += 1

    coincidences = sum(
        1
        for value in clean_values
        if value < SCALED_MIN_VALUE[column] and is_scaled_amount(value)
    )

    verification_rows.append(
        {
            "column": column,
            "check": "scaled_ratio_exactly_1000",
            "value": exact,
            "basis": "flagged rows with a clean same-product reference",
        }
    )

    verification_rows.append(
        {
            "column": column,
            "check": "scaled_ratio_near_1000",
            "value": near,
            "basis": "flagged rows with a clean same-product reference",
        }
    )

    verification_rows.append(
        {
            "column": column,
            "check": "scaled_without_reference",
            "value": without_reference,
            "basis": "flagged rows whose product has no clean value",
        }
    )

    verification_rows.append(
        {
            "column": column,
            "check": "exactness_coincidence_rate",
            "value": round(coincidences / len(clean_values), 4),
            "basis": f"clean values below {SCALED_MIN_VALUE[column]:.0f}",
        }
    )

negated_within = {column: 0 for column in MONETARY_COLUMNS}
negated_compared = {column: 0 for column in MONETARY_COLUMNS}

price_reference = {}
price_clean = {}

for row in clean_rows:
    if row[9] is None and row[5] is not None and row[5] > 0:
        price_clean.setdefault(row[2], []).append(row[5])

for product_id, values in price_clean.items():
    price_reference[product_id] = statistics.median(values)

for row in clean_rows:
    if row[9] != "negated":
        continue

    reference = price_reference.get(row[2])

    if reference is None:
        continue

    negated_compared["price"] += 1

    if abs(abs(row[5]) - reference) <= reference * NEGATED_TOLERANCE["price"]:
        negated_within["price"] += 1

freight_sibling = {}

for row in clean_rows:
    if row[10] is None and row[6] is not None and row[6] > 0:
        freight_sibling.setdefault(row[0], []).append(row[6])

for row in clean_rows:
    if row[10] != "negated":
        continue

    siblings = freight_sibling.get(row[0])

    if not siblings:
        continue

    reference = statistics.median(siblings)
    negated_compared["freight_value"] += 1

    if abs(abs(row[6]) - reference) <= reference * NEGATED_TOLERANCE["freight_value"]:
        negated_within["freight_value"] += 1

for column in MONETARY_COLUMNS:
    verification_rows.append(
        {
            "column": column,
            "check": "negated_magnitude_matches_reference",
            "value": round(
                negated_within[column] / negated_compared[column], 4
            ),
            "basis": (
                f"{negated_compared[column]} negated rows with a reference, "
                f"within {NEGATED_TOLERANCE[column]:.0%}"
            ),
        }
    )

with open(VERIFICATION_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=["column", "check", "value", "basis"],
    )

    writer.writeheader()
    writer.writerows(verification_rows)

with open(SUMMARY_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(
        [
            "column",
            "defect",
            "item_rows",
            "share_of_item_rows",
            "repaired",
        ]
    )

    for column in MONETARY_COLUMNS:
        for defect in DEFECT_FAMILIES:
            count = defect_counts[column][defect]

            writer.writerow(
                [
                    column,
                    defect,
                    count,
                    round(count / len(clean_rows), 6),
                    "yes" if defect in REPAIRABLE_DEFECTS else "no",
                ]
            )

    writer.writerow(
        [
            "all",
            "item_rows_total",
            len(clean_rows),
            1.0,
            "",
        ]
    )

    writer.writerow(
        [
            "all",
            "item_rows_with_multiple_defects",
            multi_defect_rows,
            "",
            "",
        ]
    )

with open(RECONCILIATION_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(
        [
            "column",
            "original_total",
            "repaired_total",
            "observed_difference",
            "sum_of_recorded_corrections",
            "reconciles",
        ]
    )

    for column in MONETARY_COLUMNS:
        observed = repaired_totals[column] - original_totals[column]
        expected = correction_totals[column]

        writer.writerow(
            [
                column,
                round(original_totals[column], 2),
                round(repaired_totals[column], 2),
                round(observed, 2),
                round(expected, 2),
                "yes" if abs(observed - expected) < 0.01 else "no",
            ]
        )

with open(REPAIRS_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(
        [
            "order_id",
            "order_item_id",
            "column",
            "defect",
            "original_value",
            "repaired_value",
        ]
    )
    writer.writerows(repair_records)

if multi_defect_rows:
    raise SystemExit(
        f"Defect families are not mutually exclusive: {multi_defect_rows} item rows "
        "carry more than one flag. Review the detection thresholds before continuing."
    )

for column in MONETARY_COLUMNS:
    observed = repaired_totals[column] - original_totals[column]

    if abs(observed - correction_totals[column]) >= 0.01:
        raise SystemExit(
            f"Repaired {column} total does not reconcile with recorded corrections. "
            "An unflagged value changed during repair."
        )

print("=== Task 2 item-value repair ===")
print(f"item_rows={len(clean_rows)}")

for column in MONETARY_COLUMNS:
    for defect in DEFECT_FAMILIES:
        print(f"{column}_{defect}={defect_counts[column][defect]}")

print(f"item_rows_with_multiple_defects={multi_defect_rows}")
print(f"repairs_applied={len(repair_records)}")

for column in MONETARY_COLUMNS:
    print(
        f"{column}_total_original={original_totals[column]:.2f} "
        f"repaired={repaired_totals[column]:.2f} "
        f"correction={correction_totals[column]:.2f}"
    )

print(f"\nclean_database={CLEAN_DB}")
print(f"summary_file={SUMMARY_OUT}")
print(f"reconciliation_file={RECONCILIATION_OUT}")
print(f"repairs_file={REPAIRS_OUT}")
print(f"verification_file={VERIFICATION_OUT}")