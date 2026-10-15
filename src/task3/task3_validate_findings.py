# Task 3 - Validate robustness of exploratory findings

import math
import os
import sqlite3

import pandas as pd

SOURCE_DB = "outputs/intermediate/order_level_clean.sqlite"

LEAD_ROBUSTNESS_OUT = "outputs/evidence/task3_lead_time_robustness.csv"
STATE_VALIDITY_OUT = "outputs/evidence/task3_state_validity.csv"
STATE_PRIORITY_OUT = "outputs/tables/task3_state_priority.csv"
STATE_SENSITIVITY_OUT = "outputs/evidence/task3_state_sensitivity.csv"
WITHIN_STATE_ROBUSTNESS_OUT = (
    "outputs/evidence/task3_within_state_robustness.csv"
)

WITHIN_STATE_MIN_ORDER_THRESHOLDS = [100, 200, 400]
WITHIN_STATE_MIN_LATE_ORDERS = 10

VALID_BRAZIL_STATE_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF",
    "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS",
    "RO", "RR", "SC", "SP", "SE", "TO",
}


def wilson_interval(successes, total, z=1.96):
    if total == 0:
        return math.nan, math.nan

    p = successes / total
    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            p * (1 - p) / total
            + z**2 / (4 * total**2)
        )
        / denominator
    )

    return centre - margin, centre + margin


def load_data():
    with sqlite3.connect(SOURCE_DB) as conn:
        data = pd.read_sql_query(
            "SELECT * FROM order_level_clean",
            conn,
        )

    timestamp_columns = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]

    for column in timestamp_columns:
        data[column] = pd.to_datetime(
            data[column],
            errors="coerce",
        )

    data["delivery_date"] = (
        data["order_delivered_customer_date"].dt.normalize()
    )

    data["estimated_date"] = (
        data["order_estimated_delivery_date"].dt.normalize()
    )

    data["delay_days"] = (
        data["delivery_date"]
        - data["estimated_date"]
    ).dt.days

    data["approval_to_estimate_days"] = (
        data["order_estimated_delivery_date"]
        - data["order_approved_at"]
    ).dt.total_seconds() / 86400

    return data


def build_rule_subsets(data):
    delivered = data["order_status"].eq("delivered")

    minimal_mask = (
        delivered
        & data["order_delivered_customer_date"].notna()
        & data["order_estimated_delivery_date"].notna()
    )

    primary_mask = data["delivery_label_eligible"].eq(1)

    carrier_mask = (
        primary_mask
        & data["order_delivered_carrier_date"].notna()
        & (
            data["order_delivered_carrier_date"]
            >= data["order_approved_at"]
        )
        & (
            data["order_delivered_customer_date"]
            >= data["order_delivered_carrier_date"]
        )
    )

    masks = {
        "minimal_valid_delivery_and_estimate": minimal_mask,
        "primary_purchase_approval_chronology": primary_mask,
        "carrier_strict_chronology": carrier_mask,
    }

    subsets = {}

    for name, mask in masks.items():
        subset = data.loc[mask].copy()

        subset["analysis_label"] = (
            subset["delivery_date"]
            > subset["estimated_date"]
        ).astype(int)

        subsets[name] = subset

    return subsets


def build_lead_time_robustness(primary):
    analysis = primary[
        primary["approval_to_estimate_days"].notna()
    ].copy()

    rows = []

    late = analysis[
        analysis["analysis_label"] == 1
    ]["approval_to_estimate_days"]

    on_time = analysis[
        analysis["analysis_label"] == 0
    ]["approval_to_estimate_days"]

    rows.append(
        {
            "analysis": "continuous_summary",
            "group": "late_orders",
            "orders": len(late),
            "min_lead_days": late.min(),
            "median_lead_days": late.median(),
            "mean_lead_days": late.mean(),
            "max_lead_days": late.max(),
            "late_orders": len(late),
            "late_rate": 1.0,
        }
    )

    rows.append(
        {
            "analysis": "continuous_summary",
            "group": "on_time_orders",
            "orders": len(on_time),
            "min_lead_days": on_time.min(),
            "median_lead_days": on_time.median(),
            "mean_lead_days": on_time.mean(),
            "max_lead_days": on_time.max(),
            "late_orders": 0,
            "late_rate": 0.0,
        }
    )

    correlation = analysis[
        [
            "approval_to_estimate_days",
            "analysis_label",
        ]
    ].corr().iloc[0, 1]

    rows.append(
        {
            "analysis": "continuous_association",
            "group": "pearson_correlation",
            "orders": len(analysis),
            "min_lead_days": analysis[
                "approval_to_estimate_days"
            ].min(),
            "median_lead_days": analysis[
                "approval_to_estimate_days"
            ].median(),
            "mean_lead_days": analysis[
                "approval_to_estimate_days"
            ].mean(),
            "max_lead_days": analysis[
                "approval_to_estimate_days"
            ].max(),
            "late_orders": int(
                analysis["analysis_label"].sum()
            ),
            "late_rate": correlation,
        }
    )

    for quantiles, analysis_name in [
        (5, "quintiles"),
        (10, "deciles"),
    ]:
        grouped = analysis.copy()

        grouped["lead_group"] = pd.qcut(
            grouped["approval_to_estimate_days"],
            q=quantiles,
            duplicates="drop",
        )

        for group, subset in grouped.groupby(
            "lead_group",
            observed=True,
            sort=True,
        ):
            rows.append(
                {
                    "analysis": analysis_name,
                    "group": str(group),
                    "orders": len(subset),
                    "min_lead_days": subset[
                        "approval_to_estimate_days"
                    ].min(),
                    "median_lead_days": subset[
                        "approval_to_estimate_days"
                    ].median(),
                    "mean_lead_days": subset[
                        "approval_to_estimate_days"
                    ].mean(),
                    "max_lead_days": subset[
                        "approval_to_estimate_days"
                    ].max(),
                    "late_orders": int(
                        subset["analysis_label"].sum()
                    ),
                    "late_rate": subset[
                        "analysis_label"
                    ].mean(),
                }
            )

    result = pd.DataFrame(rows)
    result.to_csv(LEAD_ROBUSTNESS_OUT, index=False)

    return result


def summarize_within_state(subset, minimum_orders):
    analysis = subset[
        subset["approval_to_estimate_days"].notna()
        & subset["customer_state"].isin(VALID_BRAZIL_STATE_CODES)
    ]

    states = []

    for state, group in analysis.groupby(
        "customer_state",
        sort=True,
    ):
        late_orders = int(group["analysis_label"].sum())

        if (
            len(group) < minimum_orders
            or late_orders < WITHIN_STATE_MIN_LATE_ORDERS
        ):
            continue

        median_lead = group["approval_to_estimate_days"].median()

        shorter = group[
            group["approval_to_estimate_days"] <= median_lead
        ]

        longer = group[
            group["approval_to_estimate_days"] > median_lead
        ]

        states.append(
            {
                "customer_state": state,
                "labeled_orders": len(group),
                "late_rate": group["analysis_label"].mean(),
                "mean_lead_time_days": group[
                    "approval_to_estimate_days"
                ].mean(),
                "within_state_correlation": group[
                    "approval_to_estimate_days"
                ].corr(group["analysis_label"]),
                "longer_minus_shorter_late_rate": (
                    longer["analysis_label"].mean()
                    - shorter["analysis_label"].mean()
                ),
            }
        )

    if not states:
        return None

    frame = pd.DataFrame(states)

    return {
        "qualifying_states": len(frame),
        "orders_covered": int(frame["labeled_orders"].sum()),
        "pooled_correlation": analysis[
            "approval_to_estimate_days"
        ].corr(analysis["analysis_label"]),
        "between_state_correlation": frame[
            "mean_lead_time_days"
        ].corr(frame["late_rate"]),
        "median_within_state_correlation": frame[
            "within_state_correlation"
        ].median(),
        "states_with_negative_within_state_correlation": int(
            (frame["within_state_correlation"] < 0).sum()
        ),
        "states_where_longer_lead_has_lower_late_rate": int(
            (frame["longer_minus_shorter_late_rate"] < 0).sum()
        ),
    }


def build_within_state_robustness(rule_subsets):
    rows = []

    for rule_name, subset in rule_subsets.items():
        for minimum_orders in WITHIN_STATE_MIN_ORDER_THRESHOLDS:
            summary = summarize_within_state(
                subset,
                minimum_orders,
            )

            if summary is None:
                continue

            rows.append(
                {
                    "rule": rule_name,
                    "minimum_state_orders": minimum_orders,
                    **summary,
                }
            )

    result = pd.DataFrame(rows)

    result.to_csv(
        WITHIN_STATE_ROBUSTNESS_OUT,
        index=False,
    )

    return result


def build_state_validity(primary):
    state = primary["customer_state"]

    result = pd.DataFrame(
        [
            {
                "state_category": "valid_brazil_state_code",
                "orders": int(
                    state.isin(
                        VALID_BRAZIL_STATE_CODES
                    ).sum()
                ),
            },
            {
                "state_category": "missing_state",
                "orders": int(state.isna().sum()),
            },
            {
                "state_category": "invalid_or_unknown_state_code",
                "orders": int(
                    (
                        state.notna()
                        & ~state.isin(
                            VALID_BRAZIL_STATE_CODES
                        )
                    ).sum()
                ),
            },
            {
                "state_category": "state_code_ZZ",
                "orders": int(
                    state.eq("ZZ").sum()
                ),
            },
        ]
    )

    result.to_csv(
        STATE_VALIDITY_OUT,
        index=False,
    )

    return result


def analyze_states(subset, rule_name):
    valid = subset[
        subset["customer_state"].isin(
            VALID_BRAZIL_STATE_CODES
        )
    ].copy()

    overall_rate = subset[
        "analysis_label"
    ].mean()

    rows = []

    for state, group in valid.groupby(
        "customer_state",
        sort=True,
    ):
        orders = len(group)
        late_orders = int(
            group["analysis_label"].sum()
        )
        late_rate = late_orders / orders

        ci_low, ci_high = wilson_interval(
            late_orders,
            orders,
        )

        expected_late = orders * overall_rate
        excess_late = late_orders - expected_late

        rows.append(
            {
                "rule": rule_name,
                "customer_state": state,
                "labeled_orders": orders,
                "late_orders": late_orders,
                "late_rate": late_rate,
                "late_rate_ci95_low": ci_low,
                "late_rate_ci95_high": ci_high,
                "overall_late_rate": overall_rate,
                "expected_late_orders_at_overall_rate": (
                    expected_late
                ),
                "excess_late_orders_vs_overall": (
                    excess_late
                ),
                "ci_entirely_above_overall_rate": int(
                    ci_low > overall_rate
                ),
            }
        )

    result = pd.DataFrame(rows)

    result["excess_rank"] = (
        result[
            "excess_late_orders_vs_overall"
        ]
        .rank(
            method="min",
            ascending=False,
        )
        .astype(int)
    )

    supported = result[
        result[
            "ci_entirely_above_overall_rate"
        ].eq(1)
    ].copy()

    supported["evidence_supported_priority_rank"] = (
        supported[
            "excess_late_orders_vs_overall"
        ]
        .rank(
            method="min",
            ascending=False,
        )
        .astype(int)
    )

    result = result.merge(
        supported[
            [
                "customer_state",
                "evidence_supported_priority_rank",
            ]
        ],
        on="customer_state",
        how="left",
    )

    return result


def build_state_analyses(rule_subsets):
    all_results = []

    for rule_name, subset in rule_subsets.items():
        all_results.append(
            analyze_states(
                subset,
                rule_name,
            )
        )

    sensitivity = pd.concat(
        all_results,
        ignore_index=True,
    )

    sensitivity.to_csv(
        STATE_SENSITIVITY_OUT,
        index=False,
    )

    primary = sensitivity[
        sensitivity["rule"].eq(
            "primary_purchase_approval_chronology"
        )
    ].copy()

    primary = primary.sort_values(
        [
            "ci_entirely_above_overall_rate",
            "excess_late_orders_vs_overall",
        ],
        ascending=[False, False],
    ).reset_index(drop=True)

    primary.to_csv(
        STATE_PRIORITY_OUT,
        index=False,
    )

    return primary, sensitivity


def main():
    os.makedirs(
        "outputs/evidence",
        exist_ok=True,
    )
    os.makedirs(
        "outputs/tables",
        exist_ok=True,
    )

    data = load_data()
    rule_subsets = build_rule_subsets(data)

    primary = rule_subsets[
        "primary_purchase_approval_chronology"
    ]

    lead_robustness = build_lead_time_robustness(
        primary
    )

    state_validity = build_state_validity(
        primary
    )

    within_state_robustness = (
        build_within_state_robustness(
            rule_subsets
        )
    )

    state_priority, state_sensitivity = (
        build_state_analyses(
            rule_subsets
        )
    )

    correlation_row = lead_robustness[
        lead_robustness["analysis"].eq(
            "continuous_association"
        )
    ].iloc[0]

    supported_states = state_priority[
        state_priority[
            "ci_entirely_above_overall_rate"
        ].eq(1)
    ]

    print("=== Task 3 robustness checks ===")

    print(
        "lead_time_label_correlation="
        f"{correlation_row['late_rate']:.6f}"
    )

    print(
        "within_state_robustness_configurations="
        f"{len(within_state_robustness)}"
    )

    print(
        "configurations_with_negative_within_state_median="
        f"{int((within_state_robustness['median_within_state_correlation'] < 0).sum())}"
        f"/{len(within_state_robustness)}"
    )

    print(
        "configurations_with_positive_between_state_correlation="
        f"{int((within_state_robustness['between_state_correlation'] > 0).sum())}"
        f"/{len(within_state_robustness)}"
    )

    print(
        "valid_state_orders="
        f"{int(state_validity.loc[state_validity['state_category'] == 'valid_brazil_state_code', 'orders'].iloc[0])}"
    )

    print(
        "missing_state_orders="
        f"{int(state_validity.loc[state_validity['state_category'] == 'missing_state', 'orders'].iloc[0])}"
    )

    print(
        "invalid_or_unknown_state_orders="
        f"{int(state_validity.loc[state_validity['state_category'] == 'invalid_or_unknown_state_code', 'orders'].iloc[0])}"
    )

    print(
        "evidence_supported_states_above_overall_rate="
        f"{len(supported_states)}"
    )

    if len(supported_states) > 0:
        first = supported_states.iloc[0]

        print(
            "primary_investigation_state="
            f"{first['customer_state']}"
        )

        print(
            "primary_investigation_state_orders="
            f"{int(first['labeled_orders'])}"
        )

        print(
            "primary_investigation_state_late_orders="
            f"{int(first['late_orders'])}"
        )

        print(
            "primary_investigation_state_late_rate="
            f"{first['late_rate']:.4%}"
        )

        print(
            "primary_investigation_state_excess_late_orders="
            f"{first['excess_late_orders_vs_overall']:.2f}"
        )

    print(
        f"lead_robustness={LEAD_ROBUSTNESS_OUT}"
    )
    print(
        f"state_validity={STATE_VALIDITY_OUT}"
    )
    print(
        f"state_priority={STATE_PRIORITY_OUT}"
    )
    print(
        f"state_sensitivity={STATE_SENSITIVITY_OUT}"
    )
    print(
        "within_state_robustness="
        f"{WITHIN_STATE_ROBUSTNESS_OUT}"
    )


if __name__ == "__main__":
    main()