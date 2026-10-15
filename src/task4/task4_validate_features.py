# Task 4 - Validate the final feature table

import math
import os
import sqlite3

import numpy as np
import pandas as pd

SOURCE_DB = "outputs/intermediate/order_level_clean.sqlite"

FEATURES_IN = "outputs/final/task4_features.csv"
ORDER_IDS_IN = "outputs/final/task4_order_ids.csv"
LABELS_IN = "outputs/final/task4_labels.csv"
FEATURE_DICTIONARY_IN = "outputs/evidence/task4_feature_dictionary.csv"

VALIDATION_OUT = "outputs/evidence/task4_feature_validation.csv"

VALID_BRAZIL_STATE_CODES = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF",
    "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS",
    "RO", "RR", "SC", "SP", "SE", "TO",
]

FORBIDDEN_FEATURE_NAMES = {
    "order_id",
    "customer_id",
    "customer_unique_id",
    "order_status",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "payment_row_count",
    "payment_type_count",
    "total_payment_value",
    "max_payment_installments",
    "review_count",
    "avg_review_score",
    "min_review_score",
    "max_review_score",
    "delivered_after_estimate",
    "delivery_label_eligible",
    "delivery_label_exclusion_reasons",
    "total_item_price_raw",
    "total_freight_value_raw",
    "items_repaired",
    "customer_city",
    "customer_zip_code_prefix",
    "max_product_weight_g",
    "max_product_volume_cm3",
    "primary_product_category",
    "primary_product_category_english",
    "primary_seller_state",
    "distinct_seller_state_count",
    "items_from_customer_state",
    "items_with_known_seller_state",
    "items_with_missing_product_reference",
    "items_with_missing_seller_reference",
    "items_with_missing_weight",
    "items_with_missing_volume",
    "approval_year",
}

MONETARY_FEATURES = {
    "total_item_price": "items_with_missing_price",
    "total_freight_value": "items_with_missing_freight",
}

MONETARY_MISSING_FILL_VALUE = 0.0

CATALOGUE_FEATURES = {
    "total_product_weight_g": "items_with_missing_weight",
    "total_product_volume_cm3": "items_with_missing_volume",
    "avg_product_photos_qty": None,
}

CATALOGUE_MISSING_FILL_VALUE = 0.0

CATEGORY_MINIMUM_SUPPORT = 250


def load_source():
    with sqlite3.connect(SOURCE_DB) as conn:
        source = pd.read_sql_query(
            """
            SELECT *
            FROM order_level_clean
            WHERE delivery_label_eligible = 1
            ORDER BY order_id
            """,
            conn,
        )

    for column in [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_estimated_delivery_date",
    ]:
        source[column] = pd.to_datetime(
            source[column],
            errors="raise",
        )

    return source


def cyclical_sin(values, period):
    return np.sin(
        2 * np.pi * values / period
    )


def cyclical_cos(values, period):
    return np.cos(
        2 * np.pi * values / period
    )


def add_check(rows, check, failures):
    rows.append(
        {
            "check": check,
            "failures": int(failures),
            "passed": int(failures == 0),
        }
    )


def validate():
    source = load_source()

    features = pd.read_csv(
        FEATURES_IN
    )

    order_ids = pd.read_csv(
        ORDER_IDS_IN,
        dtype={"order_id": str},
    )

    labels = pd.read_csv(
        LABELS_IN
    )

    dictionary = pd.read_csv(
        FEATURE_DICTIONARY_IN
    )

    rows = []

    add_check(
        rows,
        "feature_row_count_matches_source",
        abs(len(features) - len(source)),
    )

    add_check(
        rows,
        "order_id_row_count_matches_source",
        abs(len(order_ids) - len(source)),
    )

    add_check(
        rows,
        "label_row_count_matches_source",
        abs(len(labels) - len(source)),
    )

    add_check(
        rows,
        "duplicate_order_ids",
        order_ids["order_id"].duplicated().sum(),
    )

    source_ids = source[
        "order_id"
    ].astype(str).reset_index(drop=True)

    output_ids = order_ids[
        "order_id"
    ].astype(str).reset_index(drop=True)

    add_check(
        rows,
        "order_id_alignment_failures",
        (
            source_ids
            != output_ids
        ).sum(),
    )

    source_labels = source[
        "delivered_after_estimate"
    ].astype(int).reset_index(drop=True)

    output_labels = labels[
        "delivered_after_estimate"
    ].astype(int).reset_index(drop=True)

    add_check(
        rows,
        "label_alignment_failures",
        (
            source_labels
            != output_labels
        ).sum(),
    )

    add_check(
        rows,
        "feature_missing_values",
        features.isna().sum().sum(),
    )

    non_numeric_columns = (
        features.select_dtypes(
            exclude="number"
        ).columns
    )

    add_check(
        rows,
        "non_numeric_feature_columns",
        len(non_numeric_columns),
    )

    forbidden_present = (
        set(features.columns)
        & FORBIDDEN_FEATURE_NAMES
    )

    add_check(
        rows,
        "forbidden_feature_columns_present",
        len(forbidden_present),
    )

    dictionary_features = set(
        dictionary["feature"]
    )

    actual_features = set(
        features.columns
    )

    add_check(
        rows,
        "features_missing_from_dictionary",
        len(
            actual_features
            - dictionary_features
        ),
    )

    add_check(
        rows,
        "dictionary_entries_without_feature",
        len(
            dictionary_features
            - actual_features
        ),
    )

    expected_purchase_to_approval = (
        (
            source["order_approved_at"]
            - source["order_purchase_timestamp"]
        ).dt.total_seconds()
        / 3600
    )

    add_check(
        rows,
        "purchase_to_approval_value_failures",
        (
            ~np.isclose(
                features[
                    "purchase_to_approval_hours"
                ],
                expected_purchase_to_approval,
                rtol=1e-10,
                atol=1e-10,
            )
        ).sum(),
    )

    expected_lead = (
        (
            source[
                "order_estimated_delivery_date"
            ]
            - source["order_approved_at"]
        ).dt.total_seconds()
        / 86400
    )

    add_check(
        rows,
        "estimated_lead_value_failures",
        (
            ~np.isclose(
                features[
                    "estimated_lead_days"
                ],
                expected_lead,
                rtol=1e-10,
                atol=1e-10,
            )
        ).sum(),
    )

    add_check(
        rows,
        "negative_purchase_to_approval_hours",
        (
            features[
                "purchase_to_approval_hours"
            ]
            < 0
        ).sum(),
    )

    add_check(
        rows,
        "negative_estimated_lead_days",
        (
            features[
                "estimated_lead_days"
            ]
            < 0
        ).sum(),
    )

    approval_hour = (
        source["order_approved_at"].dt.hour
        + source[
            "order_approved_at"
        ].dt.minute / 60
        + source[
            "order_approved_at"
        ].dt.second / 3600
    )

    approval_weekday = (
        source[
            "order_approved_at"
        ].dt.dayofweek
    )

    approval_month = (
        source[
            "order_approved_at"
        ].dt.month
        - 1
    )

    expected_cyclical = {
        "approval_hour_sin": cyclical_sin(
            approval_hour,
            24,
        ),
        "approval_hour_cos": cyclical_cos(
            approval_hour,
            24,
        ),
        "approval_weekday_sin": cyclical_sin(
            approval_weekday,
            7,
        ),
        "approval_weekday_cos": cyclical_cos(
            approval_weekday,
            7,
        ),
        "approval_month_sin": cyclical_sin(
            approval_month,
            12,
        ),
        "approval_month_cos": cyclical_cos(
            approval_month,
            12,
        ),
    }

    for column, expected in expected_cyclical.items():
        add_check(
            rows,
            f"{column}_value_failures",
            (
                ~np.isclose(
                    features[column],
                    expected,
                    rtol=1e-10,
                    atol=1e-10,
                )
            ).sum(),
        )

    add_check(
        rows,
        "calendar_year_features_present",
        len(
            {"approval_year"}
            & set(features.columns)
        ),
    )

    state_columns = [
        f"customer_state_{state}"
        for state
        in VALID_BRAZIL_STATE_CODES
    ]

    state_columns.append(
        "customer_state_unknown"
    )

    add_check(
        rows,
        "missing_expected_state_columns",
        len(
            set(state_columns)
            - set(features.columns)
        ),
    )

    state_sum = features[
        state_columns
    ].sum(axis=1)

    add_check(
        rows,
        "state_one_hot_sum_failures",
        (
            state_sum != 1
        ).sum(),
    )

    for state in VALID_BRAZIL_STATE_CODES:
        expected = (
            source[
                "customer_state"
            ].eq(state)
            .astype(int)
        )

        actual = features[
            f"customer_state_{state}"
        ]

        add_check(
            rows,
            f"state_{state}_encoding_failures",
            (
                actual
                != expected
            ).sum(),
        )

    valid_state = source[
        "customer_state"
    ].isin(
        VALID_BRAZIL_STATE_CODES
    )

    expected_unknown = (
        ~valid_state
    ).astype(int)

    add_check(
        rows,
        "state_unknown_encoding_failures",
        (
            features[
                "customer_state_unknown"
            ]
            != expected_unknown
        ).sum(),
    )

    for column, missing_source in MONETARY_FEATURES.items():
        indicator = f"{column}_missing"

        source_values = pd.to_numeric(
            source[column],
            errors="raise",
        ).reset_index(drop=True)

        expected_indicator = (
            source_values.isna().astype(int)
        )

        expected_values = source_values.fillna(
            MONETARY_MISSING_FILL_VALUE
        ).astype(float)

        add_check(
            rows,
            f"{indicator}_value_failures",
            (
                features[indicator].astype(int)
                != expected_indicator
            ).sum(),
        )

        add_check(
            rows,
            f"{indicator}_matches_item_missing_counts",
            (
                features[indicator].astype(int)
                != (
                    source[missing_source]
                    .astype(int)
                    .gt(0)
                    .astype(int)
                    .reset_index(drop=True)
                )
            ).sum(),
        )

        add_check(
            rows,
            f"{column}_value_failures",
            (
                ~np.isclose(
                    features[column],
                    expected_values,
                    rtol=1e-10,
                    atol=1e-10,
                )
            ).sum(),
        )

        add_check(
            rows,
            f"{column}_negative_values",
            (features[column] < 0).sum(),
        )

        add_check(
            rows,
            f"{column}_filled_rows_not_zero",
            (
                features.loc[
                    features[indicator] == 1,
                    column,
                ]
                != MONETARY_MISSING_FILL_VALUE
            ).sum(),
        )

    for column, missing_source in CATALOGUE_FEATURES.items():
        indicator = f"{column}_missing"

        source_values = pd.to_numeric(
            source[column],
            errors="raise",
        ).reset_index(drop=True)

        expected_indicator = (
            source_values.isna().astype(int)
        )

        expected_values = source_values.fillna(
            CATALOGUE_MISSING_FILL_VALUE
        ).astype(float)

        add_check(
            rows,
            f"{indicator}_value_failures",
            (
                features[indicator].astype(int)
                != expected_indicator
            ).sum(),
        )

        if missing_source is not None:
            add_check(
                rows,
                f"{indicator}_matches_item_missing_counts",
                (
                    features[indicator].astype(int)
                    != (
                        source[missing_source]
                        .astype(int)
                        .gt(0)
                        .astype(int)
                        .reset_index(drop=True)
                    )
                ).sum(),
            )

        add_check(
            rows,
            f"{column}_value_failures",
            (
                ~np.isclose(
                    features[column],
                    expected_values,
                    rtol=1e-10,
                    atol=1e-10,
                )
            ).sum(),
        )

        add_check(
            rows,
            f"{column}_negative_values",
            (features[column] < 0).sum(),
        )

        add_check(
            rows,
            f"{column}_filled_rows_not_zero",
            (
                features.loc[
                    features[indicator] == 1,
                    column,
                ]
                != CATALOGUE_MISSING_FILL_VALUE
            ).sum(),
        )

    add_check(
        rows,
        "distinct_category_count_value_failures",
        (
            features["distinct_category_count"].astype(float)
            != source["distinct_category_count"].astype(float)
        ).sum(),
    )

    category_counts = source["primary_product_category"].value_counts()

    expected_categories = sorted(
        category_counts[
            category_counts >= CATEGORY_MINIMUM_SUPPORT
        ].index
    )

    expected_category_columns = [
        f"product_category_{name}"
        for name in expected_categories
    ]

    expected_category_columns.append("product_category_other")
    expected_category_columns.append("product_category_unknown")

    actual_category_columns = [
        column
        for column in features.columns
        if column.startswith("product_category_")
    ]

    add_check(
        rows,
        "category_column_set_failures",
        len(
            set(expected_category_columns)
            ^ set(actual_category_columns)
        ),
    )

    add_check(
        rows,
        "category_one_hot_sum_failures",
        (
            features[actual_category_columns].sum(axis=1) != 1
        ).sum(),
    )

    source_category = source["primary_product_category"].reset_index(drop=True)

    for name in expected_categories:
        add_check(
            rows,
            f"category_{name}_encoding_failures",
            (
                features[f"product_category_{name}"].astype(int)
                != source_category.eq(name).astype(int)
            ).sum(),
        )

    add_check(
        rows,
        "category_other_encoding_failures",
        (
            features["product_category_other"].astype(int)
            != (
                source_category.notna()
                & ~source_category.isin(expected_categories)
            ).astype(int)
        ).sum(),
    )

    add_check(
        rows,
        "category_unknown_encoding_failures",
        (
            features["product_category_unknown"].astype(int)
            != source_category.isna().astype(int)
        ).sum(),
    )

    add_check(
        rows,
        "retained_categories_below_minimum_support",
        sum(
            1
            for name in expected_categories
            if int(features[f"product_category_{name}"].sum())
            < CATEGORY_MINIMUM_SUPPORT
        ),
    )

    known_seller_state = (
        source["items_with_known_seller_state"]
        .astype(int)
        .reset_index(drop=True)
    )

    from_customer_state = (
        source["items_from_customer_state"]
        .astype(int)
        .reset_index(drop=True)
    )

    add_check(
        rows,
        "shipped_from_customer_state_value_failures",
        (
            features["shipped_from_customer_state"].astype(int)
            != (
                (known_seller_state > 0)
                & (from_customer_state == known_seller_state)
            ).astype(int)
        ).sum(),
    )

    add_check(
        rows,
        "seller_state_unknown_value_failures",
        (
            features["seller_state_unknown"].astype(int)
            != (known_seller_state == 0).astype(int)
        ).sum(),
    )

    add_check(
        rows,
        "shipment_origin_conflict_failures",
        (
            (features["shipped_from_customer_state"] == 1)
            & (features["seller_state_unknown"] == 1)
        ).sum(),
    )

    add_check(
        rows,
        "item_count_value_failures",
        (
            features[
                "item_count"
            ].astype(float)
            != source[
                "item_count"
            ].astype(float)
        ).sum(),
    )

    add_check(
        rows,
        "distinct_product_count_value_failures",
        (
            features[
                "distinct_product_count"
            ].astype(float)
            != source[
                "distinct_product_count"
            ].astype(float)
        ).sum(),
    )

    add_check(
        rows,
        "distinct_seller_count_value_failures",
        (
            features[
                "distinct_seller_count"
            ].astype(float)
            != source[
                "distinct_seller_count"
            ].astype(float)
        ).sum(),
    )

    result = pd.DataFrame(rows)

    result.to_csv(
        VALIDATION_OUT,
        index=False,
    )

    total_failures = int(
        result["failures"].sum()
    )

    failed_checks = int(
        (result["passed"] == 0).sum()
    )

    print(
        "=== Task 4 feature validation ==="
    )
    print(
        f"source_retained_orders="
        f"{len(source)}"
    )
    print(
        f"feature_rows="
        f"{len(features)}"
    )
    print(
        f"feature_columns="
        f"{features.shape[1]}"
    )
    print(
        f"validation_checks="
        f"{len(result)}"
    )
    print(
        f"failed_checks="
        f"{failed_checks}"
    )
    print(
        f"total_failures="
        f"{total_failures}"
    )
    print(
        f"validation="
        f"{VALIDATION_OUT}"
    )

    if total_failures != 0:
        print()
        print("Failed checks:")
        print(
            result.loc[
                result["passed"] == 0
            ].to_string(index=False)
        )

        raise ValueError(
            "Task 4 feature validation failed."
        )


def main():
    os.makedirs(
        "outputs/evidence",
        exist_ok=True,
    )

    validate()


if __name__ == "__main__":
    main()