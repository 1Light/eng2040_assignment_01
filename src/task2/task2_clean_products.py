# Task 2 - Repair catalogue defects in products and sellers before aggregation

import csv
import os
import sqlite3

SOURCE_DB = "marketplace.sqlite"
CLEAN_DB = "outputs/intermediate/catalogue_clean.sqlite"
SUMMARY_OUT = "outputs/evidence/task2_catalogue_repair_summary.csv"
REPAIRS_OUT = "outputs/evidence/task2_catalogue_repairs.csv"
COVERAGE_OUT = "outputs/evidence/task2_catalogue_coverage.csv"

SCALE_FACTOR = 1000
MISSING_SENTINEL = -1

SCALED_COLUMNS = {
    "product_weight_g": 50000.0,
    "product_length_cm": 1000.0,
    "product_height_cm": 1000.0,
    "product_width_cm": 1000.0,
}

SENTINEL_COLUMNS = [
    "product_name_lenght",
    "product_description_lenght",
    "product_photos_qty",
]

PRODUCT_NUMERIC_COLUMNS = list(SCALED_COLUMNS) + SENTINEL_COLUMNS

DEFECT_FAMILIES = [
    "scaled",
    "negated",
    "sentinel_missing",
    "missing",
]

REPAIRABLE_DEFECTS = [
    "scaled",
    "negated",
]

VALID_BRAZIL_STATE_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF",
    "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS",
    "RO", "RR", "SC", "SP", "SE", "TO",
}


def is_scaled_amount(value):
    return value % SCALE_FACTOR == 0


def classify(column, value):
    if value is None:
        return "missing"

    if column in SENTINEL_COLUMNS:
        if value == MISSING_SENTINEL:
            return "sentinel_missing"

        return None

    if value < 0:
        return "negated"

    if value >= SCALED_COLUMNS[column] and is_scaled_amount(value):
        return "scaled"

    return None


def repair(value, defect):
    if defect == "scaled":
        return value / SCALE_FACTOR

    if defect == "negated":
        return abs(value)

    return None


def normalize_text(value, upper=False):
    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    return value.upper() if upper else value.lower()


os.makedirs("outputs/intermediate", exist_ok=True)
os.makedirs("outputs/evidence", exist_ok=True)

if os.path.exists(CLEAN_DB):
    os.remove(CLEAN_DB)

with sqlite3.connect(SOURCE_DB) as source_conn:
    source_conn.row_factory = sqlite3.Row

    product_rows = source_conn.execute(
        "SELECT * FROM products ORDER BY product_id"
    ).fetchall()

    seller_rows = source_conn.execute(
        "SELECT * FROM sellers ORDER BY seller_id"
    ).fetchall()

    translation_rows = source_conn.execute(
        "SELECT * FROM category_translation"
    ).fetchall()

    item_rows = source_conn.execute(
        "SELECT DISTINCT product_id, seller_id FROM order_items"
    ).fetchall()

translation = {
    normalize_text(row["product_category_name"]): row["product_category_name_english"]
    for row in translation_rows
}

defect_counts = {
    column: {defect: 0 for defect in DEFECT_FAMILIES}
    for column in PRODUCT_NUMERIC_COLUMNS
}

clean_products = []
repair_records = []
incomplete_measurement_rows = 0
incomplete_description_rows = 0
untranslated_categories = set()

for row in product_rows:
    values = {}
    defects = {}

    for column in PRODUCT_NUMERIC_COLUMNS:
        original = row[column]
        defect = classify(column, original)
        defects[column] = defect

        if defect is None:
            values[column] = original
        else:
            defect_counts[column][defect] += 1
            values[column] = repair(original, defect)

        if defect in REPAIRABLE_DEFECTS:
            repair_records.append(
                (
                    "products",
                    row["product_id"],
                    column,
                    defect,
                    original,
                    values[column],
                )
            )

    if all(values[column] is None for column in SCALED_COLUMNS):
        incomplete_measurement_rows += 1

    if all(values[column] is None for column in SENTINEL_COLUMNS):
        incomplete_description_rows += 1

    category = normalize_text(row["product_category_name"])
    category_english = translation.get(category)

    if category is not None and category_english is None:
        untranslated_categories.add(category)

    if (
        values["product_length_cm"] is not None
        and values["product_height_cm"] is not None
        and values["product_width_cm"] is not None
    ):
        volume = (
            values["product_length_cm"]
            * values["product_height_cm"]
            * values["product_width_cm"]
        )
    else:
        volume = None

    clean_products.append(
        (
            row["product_id"],
            row["product_category_name"],
            category,
            category_english,
            row["product_weight_g"],
            row["product_length_cm"],
            row["product_height_cm"],
            row["product_width_cm"],
            values["product_weight_g"],
            values["product_length_cm"],
            values["product_height_cm"],
            values["product_width_cm"],
            volume,
            values["product_name_lenght"],
            values["product_description_lenght"],
            values["product_photos_qty"],
            defects["product_weight_g"],
            defects["product_length_cm"],
            defects["product_height_cm"],
            defects["product_width_cm"],
        )
    )

clean_sellers = []
seller_state_normalized = 0
seller_state_invalid = 0

for row in seller_rows:
    state = normalize_text(row["seller_state"], upper=True)

    if state != row["seller_state"]:
        seller_state_normalized += 1

    if state is not None and state not in VALID_BRAZIL_STATE_CODES:
        seller_state_invalid += 1

    clean_sellers.append(
        (
            row["seller_id"],
            row["seller_zip_code_prefix"],
            normalize_text(row["seller_city"]),
            row["seller_state"],
            state,
            1 if state in VALID_BRAZIL_STATE_CODES else 0,
        )
    )

known_products = {row[0] for row in clean_products}
known_sellers = {row[0] for row in clean_sellers}

referenced_products = {row["product_id"] for row in item_rows}
referenced_sellers = {row["seller_id"] for row in item_rows}

with sqlite3.connect(CLEAN_DB) as clean_conn:
    clean_conn.execute(
        """
        CREATE TABLE products_clean (
            product_id TEXT PRIMARY KEY,
            product_category_name_raw TEXT,
            product_category_name TEXT,
            product_category_name_english TEXT,
            product_weight_g_raw REAL,
            product_length_cm_raw REAL,
            product_height_cm_raw REAL,
            product_width_cm_raw REAL,
            product_weight_g REAL,
            product_length_cm REAL,
            product_height_cm REAL,
            product_width_cm REAL,
            product_volume_cm3 REAL,
            product_name_lenght REAL,
            product_description_lenght REAL,
            product_photos_qty REAL,
            product_weight_g_defect TEXT,
            product_length_cm_defect TEXT,
            product_height_cm_defect TEXT,
            product_width_cm_defect TEXT
        )
        """
    )

    clean_conn.executemany(
        """
        INSERT INTO products_clean VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        clean_products,
    )

    clean_conn.execute(
        """
        CREATE TABLE sellers_clean (
            seller_id TEXT PRIMARY KEY,
            seller_zip_code_prefix TEXT,
            seller_city TEXT,
            seller_state_raw TEXT,
            seller_state TEXT,
            seller_state_valid INTEGER NOT NULL
        )
        """
    )

    clean_conn.executemany(
        "INSERT INTO sellers_clean VALUES (?, ?, ?, ?, ?, ?)",
        clean_sellers,
    )

    clean_conn.commit()

with open(SUMMARY_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["table", "column", "defect", "rows", "share_of_rows", "repaired"])

    for column in PRODUCT_NUMERIC_COLUMNS:
        for defect in DEFECT_FAMILIES:
            count = defect_counts[column][defect]

            writer.writerow(
                [
                    "products",
                    column,
                    defect,
                    count,
                    round(count / len(clean_products), 6),
                    "yes" if defect in REPAIRABLE_DEFECTS else "no",
                ]
            )

    writer.writerow(["products", "all", "rows_total", len(clean_products), 1.0, ""])
    writer.writerow(
        [
            "products",
            "all",
            "rows_with_no_physical_measurements",
            incomplete_measurement_rows,
            round(incomplete_measurement_rows / len(clean_products), 6),
            "no",
        ]
    )
    writer.writerow(
        [
            "products",
            "all",
            "rows_with_no_description_attributes",
            incomplete_description_rows,
            round(incomplete_description_rows / len(clean_products), 6),
            "no",
        ]
    )
    writer.writerow(["sellers", "seller_state", "normalized", seller_state_normalized, "", "yes"])
    writer.writerow(["sellers", "seller_state", "not_a_valid_state_code", seller_state_invalid, "", "no"])
    writer.writerow(["sellers", "all", "rows_total", len(clean_sellers), 1.0, ""])

with open(REPAIRS_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["table", "record_id", "column", "defect", "original_value", "repaired_value"])
    writer.writerows(repair_records)

with open(COVERAGE_OUT, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["metric", "value"])
    writer.writerow(["product_rows", len(clean_products)])
    writer.writerow(["seller_rows", len(clean_sellers)])
    writer.writerow(["translation_rows", len(translation)])
    writer.writerow(["products_referenced_by_items", len(referenced_products)])
    writer.writerow(["products_referenced_but_absent", len(referenced_products - known_products)])
    writer.writerow(["sellers_referenced_by_items", len(referenced_sellers)])
    writer.writerow(["sellers_referenced_but_absent", len(referenced_sellers - known_sellers)])
    writer.writerow(["distinct_categories_in_products", len({row[2] for row in clean_products if row[2]})])
    writer.writerow(["distinct_categories_untranslated", len(untranslated_categories)])
    writer.writerow(["products_without_category", sum(1 for row in clean_products if row[2] is None)])
    writer.writerow(["products_with_untranslated_category", sum(1 for row in clean_products if row[2] and row[3] is None)])

for row in clean_products:
    repaired = {
        "product_weight_g": row[8],
        "product_length_cm": row[9],
        "product_height_cm": row[10],
        "product_width_cm": row[11],
    }

    for column, value in repaired.items():
        if value is None:
            continue

        if value < 0:
            raise SystemExit(
                f"Repair left a negative {column} on product {row[0]}."
            )

        if value >= SCALED_COLUMNS[column]:
            raise SystemExit(
                f"Repair left {column} at or above its scale threshold on product {row[0]}."
            )

for record in repair_records:
    table, record_id, column, defect, original, repaired_value = record

    if defect == "scaled" and repaired_value * SCALE_FACTOR != original:
        raise SystemExit(
            f"Scaled repair is not reversible for {column} on {record_id}."
        )

    if defect == "negated" and repaired_value != -original:
        raise SystemExit(
            f"Negated repair is not reversible for {column} on {record_id}."
        )

print("=== Task 2 catalogue repair ===")
print(f"product_rows={len(clean_products)}")
print(f"seller_rows={len(clean_sellers)}")

for column in PRODUCT_NUMERIC_COLUMNS:
    for defect in DEFECT_FAMILIES:
        count = defect_counts[column][defect]

        if count:
            print(f"{column}_{defect}={count}")

print(f"rows_with_no_physical_measurements={incomplete_measurement_rows}")
print(f"rows_with_no_description_attributes={incomplete_description_rows}")
print(f"repairs_applied={len(repair_records)}")
print(f"seller_state_normalized={seller_state_normalized}")
print(f"seller_state_not_a_valid_code={seller_state_invalid}")
print(f"products_referenced_but_absent={len(referenced_products - known_products)}")
print(f"sellers_referenced_but_absent={len(referenced_sellers - known_sellers)}")
print(f"distinct_categories_untranslated={len(untranslated_categories)}")

print(f"\nclean_database={CLEAN_DB}")
print(f"summary_file={SUMMARY_OUT}")
print(f"repairs_file={REPAIRS_OUT}")
print(f"coverage_file={COVERAGE_OUT}")