# Task 4 - Audit feature eligibility at approval time

import os
import sqlite3

import pandas as pd

SOURCE_DB = "outputs/intermediate/order_level_clean.sqlite"
MARKETPLACE_DB = "marketplace.sqlite"
ELIGIBILITY_OUT = "outputs/evidence/task4_feature_eligibility.csv"
CANDIDATE_SUMMARY_OUT = "outputs/evidence/task4_candidate_feature_summary.csv"
SOURCE_COVERAGE_OUT = "outputs/evidence/task4_source_column_coverage.csv"


SOURCE_COLUMN_DISPOSITION = {
    ("orders", "order_id"): ("join_key", "Order grain and join key. Stored separately from the feature matrix."),
    ("orders", "customer_id"): ("join_key", "Join key to customers. Not a predictor."),
    ("orders", "order_status"): ("excluded", "Final or evolving order outcome creates leakage."),
    ("orders", "order_purchase_timestamp"): ("carried_to_order_level", "Available at approval. Supports elapsed-time features."),
    ("orders", "order_approved_at"): ("carried_to_order_level", "Defines the prediction cutoff."),
    ("orders", "order_delivered_carrier_date"): ("excluded", "Shipment event occurring after approval."),
    ("orders", "order_delivered_customer_date"): ("excluded", "Delivery outcome. Used only to construct the label."),
    ("orders", "order_estimated_delivery_date"): ("carried_to_order_level", "Available at approval. Supports estimated lead time."),

    ("customers", "customer_id"): ("join_key", "Join key from orders. Not a predictor."),
    ("customers", "customer_unique_id"): ("excluded", "Customer identifier. Excluded to avoid identity memorization."),
    ("customers", "customer_zip_code_prefix"): ("carried_to_order_level", "Customer location available at approval."),
    ("customers", "customer_city"): ("carried_to_order_level", "Customer location available at approval."),
    ("customers", "customer_state"): ("carried_to_order_level", "Customer location available at approval."),

    ("order_items", "order_id"): ("join_key", "Aggregation key to order grain."),
    ("order_items", "order_item_id"): ("aggregated", "Item sequence. Aggregated into item_count and used to define the primary item."),
    ("order_items", "product_id"): ("aggregated", "Aggregated into distinct_product_count and used to join catalogue attributes."),
    ("order_items", "seller_id"): ("aggregated", "Aggregated into distinct_seller_count and used to join seller attributes."),
    ("order_items", "shipping_limit_date"): ("excluded", "Explicitly prohibited as a predictor by the assignment."),
    ("order_items", "price"): ("aggregated", "Repaired then aggregated into total_item_price."),
    ("order_items", "freight_value"): ("aggregated", "Repaired then aggregated into total_freight_value."),

    ("order_payments", "order_id"): ("join_key", "Aggregation key to order grain."),
    ("order_payments", "payment_sequential"): ("excluded", "Payments are prohibited as predictors."),
    ("order_payments", "payment_type"): ("excluded", "Payments are prohibited as predictors."),
    ("order_payments", "payment_installments"): ("excluded", "Payments are prohibited as predictors."),
    ("order_payments", "payment_value"): ("excluded", "Payments are prohibited as predictors."),

    ("order_reviews", "review_id"): ("excluded", "Reviews are prohibited as predictors."),
    ("order_reviews", "order_id"): ("join_key", "Aggregation key to order grain."),
    ("order_reviews", "review_score"): ("excluded", "Reviews are prohibited as predictors."),
    ("order_reviews", "review_comment_title"): ("excluded", "Reviews are prohibited as predictors."),
    ("order_reviews", "review_comment_message"): ("excluded", "Reviews are prohibited as predictors."),
    ("order_reviews", "review_creation_date"): ("excluded", "Reviews are prohibited as predictors."),
    ("order_reviews", "review_answer_timestamp"): ("excluded", "Reviews are prohibited as predictors."),

    ("products", "product_id"): ("join_key", "Join key from order items."),
    ("products", "product_category_name"): ("aggregated", "Normalized then carried as primary_product_category."),
    ("products", "product_name_lenght"): ("excluded", "Listing copy length describes the catalogue entry rather than the shipment, and offers no defensible mechanism for delivery timing."),
    ("products", "product_description_lenght"): ("excluded", "Listing copy length describes the catalogue entry rather than the shipment, and offers no defensible mechanism for delivery timing."),
    ("products", "product_photos_qty"): ("aggregated", "Repaired then aggregated into avg_product_photos_qty."),
    ("products", "product_weight_g"): ("aggregated", "Repaired then aggregated into total_product_weight_g."),
    ("products", "product_length_cm"): ("aggregated", "Repaired then combined into product volume."),
    ("products", "product_height_cm"): ("aggregated", "Repaired then combined into product volume."),
    ("products", "product_width_cm"): ("aggregated", "Repaired then combined into product volume."),

    ("sellers", "seller_id"): ("join_key", "Join key from order items."),
    ("sellers", "seller_zip_code_prefix"): ("excluded", "Seller location is represented at state level. Zip prefix adds cardinality without a matching gain."),
    ("sellers", "seller_city"): ("excluded", "Seller location is represented at state level. City adds cardinality without a matching gain."),
    ("sellers", "seller_state"): ("aggregated", "Normalized then compared against customer state to derive shipment origin features."),

    ("category_translation", "product_category_name"): ("join_key", "Join key from products."),
    ("category_translation", "product_category_name_english"): ("carried_to_order_level", "English label for the product category. Carried for readability."),
}


ALLOWED_CANDIDATES = {
    "order_purchase_timestamp": {
        "category": "date_time",
        "reason": "Known before approval and suitable for elapsed-time and calendar features.",
    },
    "order_approved_at": {
        "category": "date_time",
        "reason": "Defines the prediction-time cutoff and supports approval-time calendar features.",
    },
    "order_estimated_delivery_date": {
        "category": "date_time",
        "reason": "Delivery estimate is available by approval and can support estimated lead-time features.",
    },
    "customer_zip_code_prefix": {
        "category": "categorical",
        "reason": "Customer location is known before approval.",
        "retained": "no",
        "retention_reason": "7,343 distinct values across 15,843 modelling rows. One-hot encoding would add more columns than rows support, and customer_state already carries the geographic signal.",
    },
    "customer_city": {
        "category": "categorical",
        "reason": "Customer location is known before approval.",
        "retained": "no",
        "retention_reason": "2,287 distinct values. Same cardinality objection as zip prefix, with customer_state retained in its place.",
    },
    "customer_state": {
        "category": "categorical",
        "reason": "Customer location is known before approval.",
        "retained": "yes",
        "retention_reason": "Low cardinality geographic signal, one-hot encoded with an explicit unknown category.",
    },
    "item_count": {
        "category": "numerical",
        "reason": "Order contents are known by approval.",
    },
    "distinct_product_count": {
        "category": "numerical",
        "reason": "Order contents are known by approval.",
    },
    "distinct_seller_count": {
        "category": "numerical",
        "reason": "Sellers participating in the order are known by approval.",
    },
    "total_item_price": {
        "category": "numerical",
        "reason": "Order item prices are known as part of the order before approval. Scaled and negated item values are repaired before aggregation and the total is null when any item price is missing.",
    },
    "total_freight_value": {
        "category": "numerical",
        "reason": "Order freight charges are known as part of the order before approval. Scaled and negated item values are repaired before aggregation and the total is null when any item freight is missing.",
    },
    "items_with_missing_price": {
        "category": "numerical",
        "reason": "Counts items whose price is absent at approval. Missingness is a condition of the order that is observable at prediction time, so it is represented rather than discarded.",
    },
    "items_with_missing_freight": {
        "category": "numerical",
        "reason": "Counts items whose freight charge is absent at approval. Missingness is a condition of the order that is observable at prediction time, so it is represented rather than discarded.",
    },
    "total_product_weight_g": {
        "category": "numerical",
        "reason": "Catalogue attribute of the ordered products, known at approval. Scaled and negated source values are repaired before aggregation.",
    },
    "max_product_weight_g": {
        "category": "numerical",
        "reason": "Heaviest single item in the order, known at approval.",
        "retained": "no",
        "retention_reason": "90.2% of modelling rows contain a single item, where this duplicates total_product_weight_g exactly.",
    },
    "total_product_volume_cm3": {
        "category": "numerical",
        "reason": "Derived from repaired product dimensions, known at approval.",
    },
    "max_product_volume_cm3": {
        "category": "numerical",
        "reason": "Largest single item volume in the order, known at approval.",
        "retained": "no",
        "retention_reason": "90.2% of modelling rows contain a single item, where this duplicates total_product_volume_cm3 exactly.",
    },
    "avg_product_photos_qty": {
        "category": "numerical",
        "reason": "Mean listing photo count across the ordered products, known at approval.",
    },
    "distinct_category_count": {
        "category": "numerical",
        "reason": "Number of distinct product categories in the order, known at approval.",
    },
    "primary_product_category": {
        "category": "categorical",
        "reason": "Category of the first item in the order, known at approval.",
    },
    "primary_product_category_english": {
        "category": "categorical",
        "reason": "English label for the primary product category.",
        "retained": "no",
        "retention_reason": "Encodes the same field as primary_product_category under a different label. Retaining both would duplicate the feature.",
    },
    "primary_seller_state": {
        "category": "categorical",
        "reason": "State of the seller supplying the first item, known at approval.",
        "retained": "no",
        "retention_reason": "Its predictive content is captured by the shipment-origin features, which compare seller state against customer state. One-hot encoding it separately would add 23 columns for a weaker signal.",
    },
    "distinct_seller_state_count": {
        "category": "numerical",
        "reason": "Number of distinct valid seller states supplying the order, known at approval.",
        "retained": "no",
        "retention_reason": "Near constant: 17,925 of 20,000 orders take the value 1, and only 93 exceed it.",
    },
    "items_from_customer_state": {
        "category": "numerical",
        "reason": "Items shipped from the customer's own state, known at approval. Combined with items_with_known_seller_state to derive shipment origin.",
    },
    "items_with_known_seller_state": {
        "category": "numerical",
        "reason": "Items whose seller state is a valid code, known at approval. Denominator for the shipment-origin derivation.",
    },
    "items_with_missing_product_reference": {
        "category": "numerical",
        "reason": "Counts items whose product is absent from the catalogue. Observable at approval and represented rather than discarded.",
    },
    "items_with_missing_seller_reference": {
        "category": "numerical",
        "reason": "Counts items whose seller is absent from the seller table. Observable at approval and represented rather than discarded.",
    },
    "items_with_missing_weight": {
        "category": "numerical",
        "reason": "Counts items with no recorded weight. Observable at approval and represented rather than discarded.",
    },
    "items_with_missing_volume": {
        "category": "numerical",
        "reason": "Counts items with no recorded dimensions. Observable at approval and represented rather than discarded.",
    },
}


EXCLUDED_CANDIDATES = {
    "order_id": {
        "reason": "Identifier only. It must be stored separately from model features.",
    },
    "customer_id": {
        "reason": "Identifier with high memorization risk and no defensible general predictive meaning.",
    },
    "customer_unique_id": {
        "reason": "Customer identifier. Excluded to avoid identity memorization.",
    },
    "order_status": {
        "reason": "Final or evolving order outcome information creates leakage.",
    },
    "order_purchase_timestamp_raw": {
        "reason": "Raw duplicate of the cleaned purchase timestamp and not needed as a separate predictor.",
    },
    "order_approved_at_raw": {
        "reason": "Raw duplicate of the cleaned approval timestamp and not needed as a separate predictor.",
    },
    "order_delivered_carrier_date_raw": {
        "reason": "Post-approval delivery event and therefore leakage.",
    },
    "order_delivered_customer_date_raw": {
        "reason": "Actual delivery outcome and therefore direct target leakage.",
    },
    "order_estimated_delivery_date_raw": {
        "reason": "Raw duplicate of the cleaned estimated delivery timestamp.",
    },
    "order_delivered_carrier_date": {
        "reason": "Occurs after approval and is post-prediction information.",
    },
    "order_delivered_customer_date": {
        "reason": "Actual delivery occurs after approval and directly leaks the target.",
    },
    "payment_row_count": {
        "reason": "Payment records have no timestamp proving that this information is available by approval.",
    },
    "payment_type_count": {
        "reason": "Payment records have no timestamp proving that this information is available by approval.",
    },
    "total_payment_value": {
        "reason": "Payment records have no timestamp proving that this information is available by approval.",
    },
    "max_payment_installments": {
        "reason": "Payment records have no timestamp proving that this information is available by approval.",
    },
    "review_count": {
        "reason": "Reviews are post-order information and may occur after delivery.",
    },
    "avg_review_score": {
        "reason": "Review outcome information is not available at approval.",
    },
    "min_review_score": {
        "reason": "Review outcome information is not available at approval.",
    },
    "max_review_score": {
        "reason": "Review outcome information is not available at approval.",
    },
    "delivered_after_estimate": {
        "reason": "Prediction label. It must never appear in the feature matrix.",
    },
    "delivery_label_eligible": {
        "reason": "Label-construction metadata, not a predictor.",
    },
    "delivery_label_exclusion_reasons": {
        "reason": "Post-hoc label and data-quality metadata, not a predictor.",
    },
    "total_item_price_raw": {
        "reason": "Pre-repair duplicate of the cleaned item price total, retained only as a preservation audit trail.",
    },
    "total_freight_value_raw": {
        "reason": "Pre-repair duplicate of the cleaned freight total, retained only as a preservation audit trail.",
    },
    "items_repaired": {
        "reason": "Records how many item values this pipeline corrected. It describes the cleaning process rather than the order, and no equivalent would exist when scoring a new order, so it is not a predictor.",
    },
    "delivery_before_approval_offset_days": {
        "reason": "Diagnostic column recording how far a delivery timestamp precedes approval. It exists only to identify a data defect and is populated only for orders the label already excludes.",
    },
    "delivery_shift_pattern": {
        "reason": "Diagnostic label naming the chronology defect found in an order. Label-construction metadata, not a predictor.",
    },
}


def load_data():
    with sqlite3.connect(SOURCE_DB) as conn:
        return pd.read_sql_query(
            "SELECT * FROM order_level_clean",
            conn,
        )


def classify_columns(data):
    rows = []

    for column in data.columns:
        if column in ALLOWED_CANDIDATES:
            info = ALLOWED_CANDIDATES[column]

            rows.append(
                {
                    "column": column,
                    "decision": "allowed_candidate",
                    "feature_type": info["category"],
                    "retained_in_matrix": info.get("retained", "yes"),
                    "retention_reason": info.get(
                        "retention_reason",
                        "Retained as an approval-time predictor.",
                    ),
                    "reason": info["reason"],
                }
            )

        elif column in EXCLUDED_CANDIDATES:
            info = EXCLUDED_CANDIDATES[column]

            rows.append(
                {
                    "column": column,
                    "decision": "excluded",
                    "feature_type": "",
                    "retained_in_matrix": "no",
                    "retention_reason": info["reason"],
                    "reason": info["reason"],
                }
            )

        else:
            rows.append(
                {
                    "column": column,
                    "decision": "unclassified",
                    "feature_type": "",
                    "retained_in_matrix": "no",
                    "retention_reason": "Column was not explicitly classified.",
                    "reason": "Column was not explicitly classified.",
                }
            )

    result = pd.DataFrame(rows)
    result.to_csv(ELIGIBILITY_OUT, index=False)

    return result


def audit_source_columns():
    with sqlite3.connect(MARKETPLACE_DB) as conn:
        tables = [
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]

        rows = []

        for table in tables:
            columns = [
                info[1]
                for info in conn.execute(f'PRAGMA table_info("{table}")')
            ]

            for column in columns:
                disposition, reason = SOURCE_COLUMN_DISPOSITION.get(
                    (table, column),
                    ("unclassified", "Source column was not explicitly classified."),
                )

                rows.append(
                    {
                        "source_table": table,
                        "source_column": column,
                        "disposition": disposition,
                        "reason": reason,
                    }
                )

    result = pd.DataFrame(rows)
    result.to_csv(SOURCE_COVERAGE_OUT, index=False)

    return result


def summarize_candidates(data):
    reliable = data.loc[
        data["delivery_label_eligible"] == 1
    ].copy()

    rows = []

    for column, metadata in ALLOWED_CANDIDATES.items():
        series = reliable[column]

        minimum = ""
        maximum = ""
        negative_count = ""

        if metadata["category"] == "numerical":
            numeric = pd.to_numeric(
                series,
                errors="coerce",
            )

            minimum = numeric.min()
            maximum = numeric.max()
            negative_count = int((numeric < 0).sum())

        elif metadata["category"] == "date_time":
            parsed = pd.to_datetime(
                series,
                errors="coerce",
            )

            minimum = parsed.min()
            maximum = parsed.max()

        rows.append(
            {
                "column": column,
                "feature_type": metadata["category"],
                "reliable_label_rows": len(reliable),
                "non_null_count": int(series.notna().sum()),
                "missing_count": int(series.isna().sum()),
                "distinct_count": int(series.nunique(dropna=True)),
                "minimum": minimum,
                "maximum": maximum,
                "negative_count": negative_count,
            }
        )

    result = pd.DataFrame(rows)

    result.to_csv(
        CANDIDATE_SUMMARY_OUT,
        index=False,
    )

    return result


def main():
    os.makedirs(
        "outputs/evidence",
        exist_ok=True,
    )

    data = load_data()

    eligibility = classify_columns(data)
    candidate_summary = summarize_candidates(data)
    source_coverage = audit_source_columns()

    unclassified = eligibility[
        eligibility["decision"] == "unclassified"
    ]

    unclassified_source = source_coverage[
        source_coverage["disposition"] == "unclassified"
    ]

    print("=== Task 4 feature eligibility audit ===")
    print(f"source_rows={len(data)}")
    print(
        "reliable_label_rows="
        f"{int((data['delivery_label_eligible'] == 1).sum())}"
    )
    print(
        "allowed_candidates="
        f"{int((eligibility['decision'] == 'allowed_candidate').sum())}"
    )
    print(
        "excluded_columns="
        f"{int((eligibility['decision'] == 'excluded').sum())}"
    )
    print(
        "unclassified_columns="
        f"{len(unclassified)}"
    )
    print(
        "retained_candidates="
        f"{int((eligibility['retained_in_matrix'] == 'yes').sum())}"
    )
    print(
        "source_tables_audited="
        f"{source_coverage['source_table'].nunique()}"
    )
    print(
        "source_columns_audited="
        f"{len(source_coverage)}"
    )
    print(
        "unclassified_source_columns="
        f"{len(unclassified_source)}"
    )

    print()
    print("Allowed candidates:")

    for column in eligibility.loc[
        eligibility["decision"] == "allowed_candidate",
        "column",
    ]:
        print(f"- {column}")

    print()
    print("Unclassified columns:")

    if len(unclassified) == 0:
        print("- none")
    else:
        for column in unclassified["column"]:
            print(f"- {column}")

    print()
    print("Approval-time candidates not retained in the matrix:")

    not_retained = eligibility[
        (eligibility["decision"] == "allowed_candidate")
        & (eligibility["retained_in_matrix"] == "no")
    ]

    if len(not_retained) == 0:
        print("- none")
    else:
        for column in not_retained["column"]:
            print(f"- {column}")

    print()
    print("Source-column disposition:")

    for disposition, count in (
        source_coverage["disposition"].value_counts().items()
    ):
        print(f"- {disposition}: {count}")

    if len(unclassified):
        raise SystemExit(
            "Order-level columns are unclassified: "
            + ", ".join(unclassified["column"])
        )

    if len(unclassified_source):
        raise SystemExit(
            "Source columns are unclassified: "
            + ", ".join(
                f"{row.source_table}.{row.source_column}"
                for row in unclassified_source.itertuples()
            )
        )

    print()
    print(f"eligibility={ELIGIBILITY_OUT}")
    print(f"candidate_summary={CANDIDATE_SUMMARY_OUT}")
    print(f"source_coverage={SOURCE_COVERAGE_OUT}")


if __name__ == "__main__":
    main()