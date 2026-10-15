# Task 4 - Build the final numerical approval-time feature table

import math
import os
import sqlite3

import pandas as pd

SOURCE_DB = "outputs/intermediate/order_level_clean.sqlite"

FEATURES_OUT = "outputs/final/task4_features.csv"
ORDER_IDS_OUT = "outputs/final/task4_order_ids.csv"
LABELS_OUT = "outputs/final/task4_labels.csv"

FEATURE_DICTIONARY_OUT = "outputs/evidence/task4_feature_dictionary.csv"
BUILD_SUMMARY_OUT = "outputs/evidence/task4_feature_build_summary.csv"

MONETARY_FEATURES = [
    "total_item_price",
    "total_freight_value",
]

MONETARY_MISSING_FILL_VALUE = 0.0

CATALOGUE_FEATURES = [
    "total_product_weight_g",
    "total_product_volume_cm3",
    "avg_product_photos_qty",
]

CATALOGUE_MISSING_FILL_VALUE = 0.0

CATEGORY_MINIMUM_SUPPORT = 250

VALID_BRAZIL_STATE_CODES = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF",
    "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS",
    "RO", "RR", "SC", "SP", "SE", "TO",
]


def load_retained_orders():
    with sqlite3.connect(SOURCE_DB) as conn:
        data = pd.read_sql_query(
            """
            SELECT *
            FROM order_level_clean
            WHERE delivery_label_eligible = 1
            ORDER BY order_id
            """,
            conn,
        )

    timestamp_columns = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_estimated_delivery_date",
    ]

    for column in timestamp_columns:
        data[column] = pd.to_datetime(
            data[column],
            errors="raise",
        )

    return data


def cyclical_sin(values, period):
    return values.apply(
        lambda value: math.sin(
            2 * math.pi * value / period
        )
    )


def cyclical_cos(values, period):
    return values.apply(
        lambda value: math.cos(
            2 * math.pi * value / period
        )
    )


def retained_categories(data):
    counts = data["primary_product_category"].value_counts()

    kept = counts[counts >= CATEGORY_MINIMUM_SUPPORT]

    return sorted(kept.index)


def build_features(data, categories):
    features = pd.DataFrame(
        index=data.index,
    )

    features["item_count"] = (
        data["item_count"].astype(float)
    )

    features["distinct_product_count"] = (
        data[
            "distinct_product_count"
        ].astype(float)
    )

    features["distinct_seller_count"] = (
        data[
            "distinct_seller_count"
        ].astype(float)
    )

    for column in MONETARY_FEATURES:
        values = pd.to_numeric(
            data[column],
            errors="raise",
        )

        features[f"{column}_missing"] = (
            values.isna().astype(int)
        )

        features[column] = values.fillna(
            MONETARY_MISSING_FILL_VALUE
        ).astype(float)

    for column in CATALOGUE_FEATURES:
        values = pd.to_numeric(
            data[column],
            errors="raise",
        )

        features[f"{column}_missing"] = (
            values.isna().astype(int)
        )

        features[column] = values.fillna(
            CATALOGUE_MISSING_FILL_VALUE
        ).astype(float)

    features["distinct_category_count"] = (
        data["distinct_category_count"].astype(float)
    )

    category = data["primary_product_category"]

    for name in categories:
        features[f"product_category_{name}"] = (
            category.eq(name).astype(int)
        )

    features["product_category_other"] = (
        category.notna()
        & ~category.isin(categories)
    ).astype(int)

    features["product_category_unknown"] = (
        category.isna().astype(int)
    )

    known_seller_state = data[
        "items_with_known_seller_state"
    ].astype(int)

    from_customer_state = data[
        "items_from_customer_state"
    ].astype(int)

    features["shipped_from_customer_state"] = (
        (known_seller_state > 0)
        & (from_customer_state == known_seller_state)
    ).astype(int)

    features["seller_state_unknown"] = (
        known_seller_state == 0
    ).astype(int)

    features["purchase_to_approval_hours"] = (
        (
            data["order_approved_at"]
            - data["order_purchase_timestamp"]
        ).dt.total_seconds()
        / 3600
    )

    features["estimated_lead_days"] = (
        (
            data["order_estimated_delivery_date"]
            - data["order_approved_at"]
        ).dt.total_seconds()
        / 86400
    )

    approval_hour = (
        data["order_approved_at"].dt.hour
        + data["order_approved_at"].dt.minute / 60
        + data["order_approved_at"].dt.second / 3600
    )

    approval_weekday = (
        data["order_approved_at"].dt.dayofweek
    )

    approval_month_zero_based = (
        data["order_approved_at"].dt.month - 1
    )

    features["approval_hour_sin"] = cyclical_sin(
        approval_hour,
        24,
    )

    features["approval_hour_cos"] = cyclical_cos(
        approval_hour,
        24,
    )

    features["approval_weekday_sin"] = cyclical_sin(
        approval_weekday,
        7,
    )

    features["approval_weekday_cos"] = cyclical_cos(
        approval_weekday,
        7,
    )

    features["approval_month_sin"] = cyclical_sin(
        approval_month_zero_based,
        12,
    )

    features["approval_month_cos"] = cyclical_cos(
        approval_month_zero_based,
        12,
    )

    valid_state = data[
        "customer_state"
    ].isin(
        VALID_BRAZIL_STATE_CODES
    )

    for state in VALID_BRAZIL_STATE_CODES:
        features[
            f"customer_state_{state}"
        ] = (
            data["customer_state"]
            .eq(state)
            .astype(int)
        )

    features[
        "customer_state_unknown"
    ] = (
        ~valid_state
    ).astype(int)

    return features


def build_feature_dictionary(categories):
    rows = [
        {
            "feature": "item_count",
            "representation": "numerical",
            "meaning": "Number of order-item rows in the order.",
            "source": "item_count",
        },
        {
            "feature": "distinct_product_count",
            "representation": "numerical",
            "meaning": "Number of distinct products in the order.",
            "source": "distinct_product_count",
        },
        {
            "feature": "distinct_seller_count",
            "representation": "numerical",
            "meaning": "Number of distinct sellers contributing items to the order.",
            "source": "distinct_seller_count",
        },
        {
            "feature": "total_item_price_missing",
            "representation": "missing_indicator",
            "meaning": "1 when at least one item in the order has no recorded price, so no order total exists; otherwise 0.",
            "source": "items_with_missing_price",
        },
        {
            "feature": "total_item_price",
            "representation": "numerical",
            "meaning": "Sum of repaired item prices in the order, in Brazilian reais. Set to 0 when total_item_price_missing is 1, where the indicator rather than the value carries the information.",
            "source": "total_item_price",
        },
        {
            "feature": "total_freight_value_missing",
            "representation": "missing_indicator",
            "meaning": "1 when at least one item in the order has no recorded freight charge, so no order total exists; otherwise 0.",
            "source": "items_with_missing_freight",
        },
        {
            "feature": "total_freight_value",
            "representation": "numerical",
            "meaning": "Sum of repaired item freight charges in the order, in Brazilian reais. Set to 0 when total_freight_value_missing is 1, where the indicator rather than the value carries the information.",
            "source": "total_freight_value",
        },
        {
            "feature": "total_product_weight_g_missing",
            "representation": "missing_indicator",
            "meaning": "1 when at least one item in the order has no recorded product weight, so no order weight exists; otherwise 0.",
            "source": "items_with_missing_weight",
        },
        {
            "feature": "total_product_weight_g",
            "representation": "numerical",
            "meaning": "Sum of repaired product weights across the items in the order, in grams. Set to 0 when total_product_weight_g_missing is 1.",
            "source": "total_product_weight_g",
        },
        {
            "feature": "total_product_volume_cm3_missing",
            "representation": "missing_indicator",
            "meaning": "1 when at least one item in the order has no recorded product dimensions, so no order volume exists; otherwise 0.",
            "source": "items_with_missing_volume",
        },
        {
            "feature": "total_product_volume_cm3",
            "representation": "numerical",
            "meaning": "Sum of repaired product volumes across the items in the order, in cubic centimetres. Set to 0 when total_product_volume_cm3_missing is 1.",
            "source": "total_product_volume_cm3",
        },
        {
            "feature": "avg_product_photos_qty_missing",
            "representation": "missing_indicator",
            "meaning": "1 when no item in the order has a recorded listing photo count; otherwise 0.",
            "source": "avg_product_photos_qty",
        },
        {
            "feature": "avg_product_photos_qty",
            "representation": "numerical",
            "meaning": "Mean listing photo count across the items in the order. Set to 0 when avg_product_photos_qty_missing is 1.",
            "source": "avg_product_photos_qty",
        },
        {
            "feature": "distinct_category_count",
            "representation": "numerical",
            "meaning": "Number of distinct product categories in the order. 0 when no item has a known category.",
            "source": "distinct_category_count",
        },
        {
            "feature": "shipped_from_customer_state",
            "representation": "derived_indicator",
            "meaning": "1 when every item with a known seller state ships from the customer's own state; otherwise 0.",
            "source": "items_from_customer_state + items_with_known_seller_state",
        },
        {
            "feature": "seller_state_unknown",
            "representation": "derived_indicator",
            "meaning": "1 when no item in the order has a valid seller state, so shipment origin cannot be determined; otherwise 0.",
            "source": "items_with_known_seller_state",
        },
        {
            "feature": "purchase_to_approval_hours",
            "representation": "engineered_numerical",
            "meaning": "Elapsed hours from order purchase to approval.",
            "source": "order_purchase_timestamp + order_approved_at",
        },
        {
            "feature": "estimated_lead_days",
            "representation": "engineered_numerical",
            "meaning": "Days from approval to the estimated delivery timestamp.",
            "source": "order_approved_at + order_estimated_delivery_date",
        },
        {
            "feature": "approval_hour_sin",
            "representation": "cyclical_date_time",
            "meaning": "Sine encoding of approval time within the 24-hour daily cycle.",
            "source": "order_approved_at",
        },
        {
            "feature": "approval_hour_cos",
            "representation": "cyclical_date_time",
            "meaning": "Cosine encoding of approval time within the 24-hour daily cycle.",
            "source": "order_approved_at",
        },
        {
            "feature": "approval_weekday_sin",
            "representation": "cyclical_date_time",
            "meaning": "Sine encoding of approval weekday within the seven-day weekly cycle.",
            "source": "order_approved_at",
        },
        {
            "feature": "approval_weekday_cos",
            "representation": "cyclical_date_time",
            "meaning": "Cosine encoding of approval weekday within the seven-day weekly cycle.",
            "source": "order_approved_at",
        },
        {
            "feature": "approval_month_sin",
            "representation": "cyclical_date_time",
            "meaning": "Sine encoding of approval month within the annual cycle.",
            "source": "order_approved_at",
        },
        {
            "feature": "approval_month_cos",
            "representation": "cyclical_date_time",
            "meaning": "Cosine encoding of approval month within the annual cycle.",
            "source": "order_approved_at",
        },
    ]

    for name in categories:
        rows.append(
            {
                "feature": f"product_category_{name}",
                "representation": "one_hot_categorical",
                "meaning": (
                    f"1 when the first item in the order belongs to category {name}; otherwise 0. "
                    f"Retained because the category covers at least {CATEGORY_MINIMUM_SUPPORT} modelling rows."
                ),
                "source": "primary_product_category",
            }
        )

    rows.append(
        {
            "feature": "product_category_other",
            "representation": "one_hot_categorical",
            "meaning": (
                "1 when the first item has a known category that covers fewer than "
                f"{CATEGORY_MINIMUM_SUPPORT} modelling rows; otherwise 0."
            ),
            "source": "primary_product_category",
        }
    )

    rows.append(
        {
            "feature": "product_category_unknown",
            "representation": "one_hot_categorical",
            "meaning": "1 when the first item has no known product category; otherwise 0.",
            "source": "primary_product_category",
        }
    )

    for state in VALID_BRAZIL_STATE_CODES:
        rows.append(
            {
                "feature": f"customer_state_{state}",
                "representation": "one_hot_categorical",
                "meaning": f"1 when the customer state is {state}; otherwise 0.",
                "source": "customer_state",
            }
        )

    rows.append(
        {
            "feature": "customer_state_unknown",
            "representation": "one_hot_categorical",
            "meaning": "1 when customer state is missing or not a valid Brazilian state/Federal District code.",
            "source": "customer_state",
        }
    )

    return pd.DataFrame(rows)


def validate_build(data, features, categories):
    order_ids = data[
        ["order_id"]
    ].copy()

    labels = data[
        ["delivered_after_estimate"]
    ].copy()

    labels[
        "delivered_after_estimate"
    ] = labels[
        "delivered_after_estimate"
    ].astype(int)

    duplicate_order_ids = int(
        order_ids["order_id"].duplicated().sum()
    )

    feature_missing_values = int(
        features.isna().sum().sum()
    )

    numeric_feature_count = int(
        features.select_dtypes(
            include="number"
        ).shape[1]
    )

    non_numeric_feature_count = (
        features.shape[1]
        - numeric_feature_count
    )

    label_values = sorted(
        labels[
            "delivered_after_estimate"
        ].unique().tolist()
    )

    state_feature_columns = [
        column
        for column in features.columns
        if column.startswith(
            "customer_state_"
        )
    ]

    state_encoding_failures = int(
        (
            features[
                state_feature_columns
            ].sum(axis=1)
            != 1
        ).sum()
    )

    category_feature_columns = [
        column
        for column in features.columns
        if column.startswith("product_category_")
    ]

    category_encoding_failures = int(
        (
            features[
                category_feature_columns
            ].sum(axis=1)
            != 1
        ).sum()
    )

    origin_conflict_failures = int(
        (
            (features["shipped_from_customer_state"] == 1)
            & (features["seller_state_unknown"] == 1)
        ).sum()
    )

    summary = pd.DataFrame(
        [
            {
                "metric": "retained_orders",
                "value": len(data),
            },
            {
                "metric": "feature_rows",
                "value": len(features),
            },
            {
                "metric": "feature_columns",
                "value": features.shape[1],
            },
            {
                "metric": "numeric_feature_columns",
                "value": numeric_feature_count,
            },
            {
                "metric": "non_numeric_feature_columns",
                "value": non_numeric_feature_count,
            },
            {
                "metric": "duplicate_order_ids",
                "value": duplicate_order_ids,
            },
            {
                "metric": "feature_missing_values",
                "value": feature_missing_values,
            },
            {
                "metric": "state_encoding_failures",
                "value": state_encoding_failures,
            },
            {
                "metric": "total_item_price_filled",
                "value": int(
                    features[
                        "total_item_price_missing"
                    ].sum()
                ),
            },
            {
                "metric": "total_freight_value_filled",
                "value": int(
                    features[
                        "total_freight_value_missing"
                    ].sum()
                ),
            },
            {
                "metric": "retained_category_columns",
                "value": len(categories),
            },
            {
                "metric": "category_minimum_support",
                "value": CATEGORY_MINIMUM_SUPPORT,
            },
            {
                "metric": "category_encoding_failures",
                "value": category_encoding_failures,
            },
            {
                "metric": "orders_in_retained_categories",
                "value": int(
                    features[
                        [f"product_category_{name}" for name in categories]
                    ].sum(axis=1).sum()
                ),
            },
            {
                "metric": "orders_in_other_category",
                "value": int(features["product_category_other"].sum()),
            },
            {
                "metric": "orders_without_category",
                "value": int(features["product_category_unknown"].sum()),
            },
            {
                "metric": "orders_shipped_from_customer_state",
                "value": int(features["shipped_from_customer_state"].sum()),
            },
            {
                "metric": "orders_with_unknown_seller_state",
                "value": int(features["seller_state_unknown"].sum()),
            },
            {
                "metric": "origin_conflict_failures",
                "value": origin_conflict_failures,
            },
            {
                "metric": "late_labels",
                "value": int(
                    labels[
                        "delivered_after_estimate"
                    ].sum()
                ),
            },
            {
                "metric": "on_time_labels",
                "value": int(
                    (
                        labels[
                            "delivered_after_estimate"
                        ]
                        == 0
                    ).sum()
                ),
            },
        ]
    )

    if len(data) != len(features):
        raise ValueError(
            "Feature row count does not match retained orders."
        )

    if len(order_ids) != len(labels):
        raise ValueError(
            "Order ID and label row counts do not match."
        )

    if duplicate_order_ids != 0:
        raise ValueError(
            "Duplicate order IDs found."
        )

    if feature_missing_values != 0:
        raise ValueError(
            "Final feature table contains missing values."
        )

    if non_numeric_feature_count != 0:
        raise ValueError(
            "Final feature table contains non-numeric columns."
        )

    if label_values != [0, 1]:
        raise ValueError(
            f"Unexpected label values: {label_values}"
        )

    if state_encoding_failures != 0:
        raise ValueError(
            "Customer-state one-hot encoding is invalid."
        )

    if category_encoding_failures != 0:
        raise ValueError(
            "Product-category one-hot encoding is invalid."
        )

    if origin_conflict_failures != 0:
        raise ValueError(
            "An order is marked both same-state and unknown-origin."
        )

    return order_ids, labels, summary


def main():
    os.makedirs(
        "outputs/final",
        exist_ok=True,
    )

    os.makedirs(
        "outputs/evidence",
        exist_ok=True,
    )

    data = load_retained_orders()

    categories = retained_categories(data)

    features = build_features(
        data,
        categories,
    )

    feature_dictionary = (
        build_feature_dictionary(categories)
    )

    order_ids, labels, summary = (
        validate_build(
            data,
            features,
            categories,
        )
    )

    features.to_csv(
        FEATURES_OUT,
        index=False,
    )

    order_ids.to_csv(
        ORDER_IDS_OUT,
        index=False,
    )

    labels.to_csv(
        LABELS_OUT,
        index=False,
    )

    feature_dictionary.to_csv(
        FEATURE_DICTIONARY_OUT,
        index=False,
    )

    summary.to_csv(
        BUILD_SUMMARY_OUT,
        index=False,
    )

    print("=== Task 4 feature build ===")
    print(f"retained_orders={len(data)}")
    print(
        f"feature_columns={features.shape[1]}"
    )
    print(
        f"retained_category_columns={len(categories)}"
    )
    print(
        "feature_missing_values="
        f"{int(features.isna().sum().sum())}"
    )
    print(
        "duplicate_order_ids="
        f"{int(order_ids['order_id'].duplicated().sum())}"
    )
    print(
        "late_labels="
        f"{int(labels['delivered_after_estimate'].sum())}"
    )
    print(
        "on_time_labels="
        f"{int((labels['delivered_after_estimate'] == 0).sum())}"
    )
    print(
        f"features={FEATURES_OUT}"
    )
    print(
        f"order_ids={ORDER_IDS_OUT}"
    )
    print(
        f"labels={LABELS_OUT}"
    )
    print(
        "feature_dictionary="
        f"{FEATURE_DICTIONARY_OUT}"
    )
    print(
        f"build_summary={BUILD_SUMMARY_OUT}"
    )


if __name__ == "__main__":
    main()