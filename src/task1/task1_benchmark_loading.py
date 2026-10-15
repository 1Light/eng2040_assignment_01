# Task 1 - Benchmark suitable loading approaches

import csv
import json
import os
import resource
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

SOURCE_DB = "marketplace.sqlite"
ITEMS_DB = "outputs/intermediate/items_clean.sqlite"
CATALOGUE_DB = "outputs/intermediate/catalogue_clean.sqlite"
BUILD_SQL = "sql/task1_build_order_level.sql"
SQL_RUNNER = "src/common/run_sql_script.py"
EVIDENCE_OUT = "outputs/evidence/task1_loading_benchmark.csv"
RUNS = 5
MIB = 1024 ** 2


def peak_rss_bytes(usage):
    if sys.platform == "darwin":
        return int(usage.ru_maxrss)
    return int(usage.ru_maxrss * 1024)


def sqlite_worker(output_db):
    with tempfile.TemporaryDirectory() as temp_dir:
        intermediate_dir = os.path.join(temp_dir, "outputs", "intermediate")
        os.makedirs(intermediate_dir)

        source_link = os.path.join(temp_dir, "marketplace.sqlite")
        sql_dir = os.path.join(temp_dir, "sql")
        os.makedirs(sql_dir)

        os.symlink(os.path.abspath(SOURCE_DB), source_link)
        os.symlink(
            os.path.abspath(ITEMS_DB),
            os.path.join(intermediate_dir, "items_clean.sqlite"),
        )
        os.symlink(
            os.path.abspath(CATALOGUE_DB),
            os.path.join(intermediate_dir, "catalogue_clean.sqlite"),
        )
        os.symlink(
            os.path.abspath(BUILD_SQL),
            os.path.join(sql_dir, "task1_build_order_level.sql"),
        )

        start = time.perf_counter()

        result = subprocess.run(
            [
                sys.executable,
                os.path.abspath(SQL_RUNNER),
                source_link,
                os.path.abspath(BUILD_SQL),
            ],
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        runtime = time.perf_counter() - start

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        generated_db = os.path.join(
            temp_dir,
            "outputs",
            "intermediate",
            "order_level.sqlite",
        )

        with sqlite3.connect(generated_db) as conn:
            rows = conn.execute(
                "SELECT COUNT(*) FROM order_level"
            ).fetchone()[0]

        output_size = os.path.getsize(generated_db)

        with open(generated_db, "rb") as src, open(output_db, "wb") as dst:
            dst.write(src.read())

    usage = resource.getrusage(resource.RUSAGE_CHILDREN)

    return {
        "approach": "sqlite",
        "runtime_seconds": runtime,
        "peak_memory_bytes": peak_rss_bytes(usage),
        "output_rows": rows,
        "output_size_bytes": output_size,
    }


def pandas_worker(output_db):
    import pandas as pd

    start = time.perf_counter()

    with sqlite3.connect(SOURCE_DB) as conn:
        orders = pd.read_sql_query("SELECT * FROM orders", conn)
        customers = pd.read_sql_query("SELECT * FROM customers", conn)
        payments = pd.read_sql_query("SELECT * FROM order_payments", conn)
        reviews = pd.read_sql_query("SELECT * FROM order_reviews", conn)

    with sqlite3.connect(ITEMS_DB) as conn:
        items = pd.read_sql_query("SELECT * FROM order_items_clean", conn)

    with sqlite3.connect(CATALOGUE_DB) as conn:
        products = pd.read_sql_query("SELECT * FROM products_clean", conn)
        sellers = pd.read_sql_query("SELECT * FROM sellers_clean", conn)

    products = products.assign(product_matched=1)
    sellers = sellers.assign(seller_matched=1)

    items = items.merge(
        products[
            [
                "product_id",
                "product_matched",
                "product_weight_g",
                "product_volume_cm3",
                "product_photos_qty",
                "product_category_name",
                "product_category_name_english",
            ]
        ],
        on="product_id",
        how="left",
        validate="many_to_one",
    )

    items = items.merge(
        sellers[
            [
                "seller_id",
                "seller_matched",
                "seller_state",
                "seller_state_valid",
            ]
        ],
        on="seller_id",
        how="left",
        validate="many_to_one",
    )

    items = items.merge(
        orders[["order_id", "customer_id"]].merge(
            customers[["customer_id", "customer_state"]],
            on="customer_id",
            how="left",
            validate="many_to_one",
        )[["order_id", "customer_state"]],
        on="order_id",
        how="left",
        validate="many_to_one",
    )

    items["weight_missing"] = items["product_weight_g"].isna().astype(int)
    items["volume_missing"] = items["product_volume_cm3"].isna().astype(int)
    items["product_unmatched"] = items["product_matched"].isna().astype(int)
    items["seller_unmatched"] = items["seller_matched"].isna().astype(int)
    items["valid_seller_state"] = items["seller_state"].where(
        items["seller_state_valid"] == 1
    )
    items["known_seller_state"] = (items["seller_state_valid"] == 1).astype(int)
    items["from_customer_state"] = (
        (items["seller_state_valid"] == 1)
        & (items["seller_state"] == items["customer_state"])
    ).astype(int)

    items["price_missing"] = items["price"].isna().astype(int)
    items["freight_missing"] = items["freight_value"].isna().astype(int)

    items["repaired"] = (
        items["price_defect"].isin(["scaled", "negated"]).astype(int)
        + items["freight_value_defect"].isin(["scaled", "negated"]).astype(int)
    )

    item_agg = (
        items.groupby("order_id", as_index=False)
        .agg(
            item_count=("order_item_id", "size"),
            distinct_product_count=("product_id", "nunique"),
            distinct_seller_count=("seller_id", "nunique"),
            total_item_price=("price", "sum"),
            total_freight_value=("freight_value", "sum"),
            total_item_price_raw=("price_raw", "sum"),
            total_freight_value_raw=("freight_value_raw", "sum"),
            price_raw_present=("price_raw", "count"),
            freight_value_raw_present=("freight_value_raw", "count"),
            items_with_missing_price=("price_missing", "sum"),
            items_with_missing_freight=("freight_missing", "sum"),
            items_repaired=("repaired", "sum"),
            total_product_weight_g=("product_weight_g", "sum"),
            max_product_weight_g=("product_weight_g", "max"),
            total_product_volume_cm3=("product_volume_cm3", "sum"),
            max_product_volume_cm3=("product_volume_cm3", "max"),
            avg_product_photos_qty=("product_photos_qty", "mean"),
            items_with_missing_weight=("weight_missing", "sum"),
            items_with_missing_volume=("volume_missing", "sum"),
            items_with_missing_product_reference=("product_unmatched", "sum"),
            items_with_missing_seller_reference=("seller_unmatched", "sum"),
            distinct_category_count=("product_category_name", "nunique"),
            distinct_seller_state_count=("valid_seller_state", "nunique"),
            items_with_known_seller_state=("known_seller_state", "sum"),
            items_from_customer_state=("from_customer_state", "sum"),
        )
    )

    primary_item = (
        items.sort_values(["order_id", "order_item_id"])
        .drop_duplicates("order_id", keep="first")[
            [
                "order_id",
                "product_category_name",
                "product_category_name_english",
                "seller_state",
            ]
        ]
        .rename(
            columns={
                "product_category_name": "primary_product_category",
                "product_category_name_english": (
                    "primary_product_category_english"
                ),
                "seller_state": "primary_seller_state",
            }
        )
    )

    item_agg = item_agg.merge(
        primary_item,
        on="order_id",
        how="left",
        validate="one_to_one",
    )

    item_agg.loc[
        item_agg["price_raw_present"] == 0,
        "total_item_price_raw",
    ] = None

    item_agg.loc[
        item_agg["freight_value_raw_present"] == 0,
        "total_freight_value_raw",
    ] = None

    item_agg = item_agg.drop(
        columns=[
            "price_raw_present",
            "freight_value_raw_present",
        ]
    )

    item_agg.loc[
        item_agg["items_with_missing_weight"] > 0,
        "total_product_weight_g",
    ] = None

    item_agg.loc[
        item_agg["items_with_missing_volume"] > 0,
        "total_product_volume_cm3",
    ] = None

    item_agg.loc[
        item_agg["items_with_missing_price"] > 0,
        "total_item_price",
    ] = None

    item_agg.loc[
        item_agg["items_with_missing_freight"] > 0,
        "total_freight_value",
    ] = None

    payment_agg = (
        payments.groupby("order_id", as_index=False)
        .agg(
            payment_row_count=("payment_sequential", "size"),
            payment_type_count=("payment_type", "nunique"),
            total_payment_value=("payment_value", "sum"),
            payment_value_present=("payment_value", "count"),
            max_payment_installments=("payment_installments", "max"),
        )
    )

    payment_agg.loc[
        payment_agg["payment_value_present"] == 0,
        "total_payment_value",
    ] = None

    payment_agg = payment_agg.drop(
        columns=["payment_value_present"]
    )

    review_agg = (
        reviews.groupby("order_id", as_index=False)
        .agg(
            review_count=("review_id", "size"),
            avg_review_score=("review_score", "mean"),
            min_review_score=("review_score", "min"),
            max_review_score=("review_score", "max"),
        )
    )

    result = (
        orders
        .merge(customers, on="customer_id", how="left", validate="many_to_one")
        .merge(item_agg, on="order_id", how="left", validate="one_to_one")
        .merge(payment_agg, on="order_id", how="left", validate="one_to_one")
        .merge(review_agg, on="order_id", how="left", validate="one_to_one")
    )

    count_columns = [
        "item_count",
        "distinct_product_count",
        "distinct_seller_count",
        "payment_row_count",
        "payment_type_count",
        "review_count",
        "items_with_missing_price",
        "items_with_missing_freight",
        "items_repaired",
        "items_with_missing_weight",
        "items_with_missing_volume",
        "items_with_missing_product_reference",
        "items_with_missing_seller_reference",
        "distinct_category_count",
        "distinct_seller_state_count",
        "items_with_known_seller_state",
        "items_from_customer_state",
    ]

    result[count_columns] = result[count_columns].fillna(0).astype(int)

    with sqlite3.connect(output_db) as conn:
        result.to_sql(
            "order_level",
            conn,
            if_exists="replace",
            index=False,
        )

    runtime = time.perf_counter() - start
    usage = resource.getrusage(resource.RUSAGE_SELF)

    return {
        "approach": "pandas",
        "runtime_seconds": runtime,
        "peak_memory_bytes": peak_rss_bytes(usage),
        "output_rows": len(result),
        "output_size_bytes": os.path.getsize(output_db),
    }


def run_worker(approach):
    with tempfile.NamedTemporaryFile(
        suffix=".sqlite",
        delete=False,
    ) as temp_file:
        output_db = temp_file.name

    try:
        result = subprocess.run(
            [
                sys.executable,
                __file__,
                "--worker",
                approach,
                output_db,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        return json.loads(result.stdout)
    finally:
        if os.path.exists(output_db):
            os.remove(output_db)


def summarize(results):
    rows = []

    for approach in ["sqlite", "pandas"]:
        subset = [r for r in results if r["approach"] == approach]

        median_runtime = statistics.median(
            r["runtime_seconds"] for r in subset
        )

        median_memory = statistics.median(
            r["peak_memory_bytes"] for r in subset
        )

        median_size = statistics.median(
            r["output_size_bytes"] for r in subset
        )

        rows.append(
            {
                "approach": approach,
                "runs": len(subset),
                "median_runtime_seconds": median_runtime,
                "median_runtime_seconds_reported": round(median_runtime, 4),
                "median_peak_memory_bytes": median_memory,
                "median_peak_memory_mib_reported": round(median_memory / MIB, 2),
                "output_rows": subset[0]["output_rows"],
                "median_output_size_bytes": median_size,
                "median_output_size_mib_reported": round(median_size / MIB, 2),
            }
        )

    return rows


def main():
    os.makedirs("outputs/evidence", exist_ok=True)

    results = []

    for approach in ["sqlite", "pandas"]:
        for run_number in range(1, RUNS + 1):
            result = run_worker(approach)
            result["run"] = run_number
            results.append(result)

            print(
                f"{approach} run {run_number}: "
                f"{result['runtime_seconds']:.4f}s, "
                f"{result['peak_memory_bytes'] / (1024 ** 2):.2f} MiB"
            )

    summary = summarize(results)

    with open(EVIDENCE_OUT, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "approach",
                "runs",
                "median_runtime_seconds",
                "median_runtime_seconds_reported",
                "median_peak_memory_bytes",
                "median_peak_memory_mib_reported",
                "output_rows",
                "median_output_size_bytes",
                "median_output_size_mib_reported",
            ],
        )
        writer.writeheader()
        writer.writerows(summary)

    print("\nSummary")

    for row in summary:
        print(
            f"{row['approach']}: "
            f"median runtime={row['median_runtime_seconds']:.4f}s, "
            f"median peak memory="
            f"{row['median_peak_memory_bytes'] / (1024 ** 2):.2f} MiB, "
            f"rows={row['output_rows']}, "
            f"output size="
            f"{row['median_output_size_bytes'] / (1024 ** 2):.2f} MiB"
        )

    print(f"\nevidence_file={EVIDENCE_OUT}")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        approach = sys.argv[2]
        output_db = sys.argv[3]

        if approach == "sqlite":
            result = sqlite_worker(output_db)
        elif approach == "pandas":
            result = pandas_worker(output_db)
        else:
            raise ValueError(f"Unknown approach: {approach}")

        print(json.dumps(result))
    else:
        main()