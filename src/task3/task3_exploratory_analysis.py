# Task 3 - Exploratory analysis of delivery delays

import math
import os
import sqlite3

import matplotlib
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt

SOURCE_DB = "outputs/intermediate/order_level_clean.sqlite"

DELAY_SUMMARY_OUT = "outputs/tables/task3_delay_summary.csv"
LEAD_TIME_OUT = "outputs/tables/task3_lead_time_analysis.csv"
STATE_OUT = "outputs/tables/task3_state_analysis.csv"
STATE_QUALITY_OUT = "outputs/tables/task3_state_data_quality.csv"
WITHIN_STATE_OUT = "outputs/tables/task3_lead_time_within_state.csv"
CONFOUND_OUT = "outputs/tables/task3_lead_time_confound_summary.csv"
SENSITIVITY_OUT = "outputs/evidence/task3_sensitivity.csv"

DELAY_FIGURE_OUT = "outputs/figures/task3_delay_distribution.png"
LEAD_TIME_FIGURE_OUT = "outputs/figures/task3_lead_time_vs_late_rate.png"
STATE_FIGURE_OUT = "outputs/figures/task3_state_late_rates.png"
CONFOUND_FIGURE_OUT = "outputs/figures/task3_lead_time_confound.png"

WITHIN_STATE_MIN_ORDERS = 200
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

    proportion = successes / total
    denominator = 1 + z**2 / total

    centre = (
        proportion
        + z**2 / (2 * total)
    ) / denominator

    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
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

    return data


def add_analysis_columns(data):
    result = data.copy()

    result["delivery_date"] = (
        result[
            "order_delivered_customer_date"
        ].dt.normalize()
    )

    result["estimated_date"] = (
        result[
            "order_estimated_delivery_date"
        ].dt.normalize()
    )

    result["delay_days"] = (
        result["delivery_date"]
        - result["estimated_date"]
    ).dt.days

    result["approval_to_estimate_days"] = (
        result["order_estimated_delivery_date"]
        - result["order_approved_at"]
    ).dt.total_seconds() / 86400

    return result


def build_delay_summary(primary):
    labeled_orders = len(primary)

    late_orders = int(
        primary["delivered_after_estimate"].sum()
    )

    on_time_orders = labeled_orders - late_orders
    late_rate = late_orders / labeled_orders

    ci_low, ci_high = wilson_interval(
        late_orders,
        labeled_orders,
    )

    late_delays = primary.loc[
        primary["delivered_after_estimate"] == 1,
        "delay_days",
    ]

    summary = pd.DataFrame(
        [
            {
                "labeled_orders": labeled_orders,
                "late_orders": late_orders,
                "on_time_orders": on_time_orders,
                "late_rate": late_rate,
                "late_rate_ci95_low": ci_low,
                "late_rate_ci95_high": ci_high,
                "mean_late_delay_days": late_delays.mean(),
                "median_late_delay_days": late_delays.median(),
                "p25_late_delay_days": late_delays.quantile(0.25),
                "p75_late_delay_days": late_delays.quantile(0.75),
                "p90_late_delay_days": late_delays.quantile(0.90),
                "p95_late_delay_days": late_delays.quantile(0.95),
                "max_late_delay_days": late_delays.max(),
            }
        ]
    )

    summary.to_csv(
        DELAY_SUMMARY_OUT,
        index=False,
    )

    plt.figure(figsize=(9, 5))
    plt.hist(
        late_delays,
        bins=30,
        edgecolor="black",
    )
    plt.xlabel("Delay length in calendar days")
    plt.ylabel("Late orders")
    plt.title("Distribution of Late-Delivery Delay Lengths")
    plt.tight_layout()
    plt.savefig(
        DELAY_FIGURE_OUT,
        dpi=180,
    )
    plt.close()

    return summary


def build_lead_time_analysis(primary):
    analysis = primary[
        primary[
            "approval_to_estimate_days"
        ].notna()
    ].copy()

    analysis["lead_time_group"] = pd.qcut(
        analysis["approval_to_estimate_days"],
        q=5,
        duplicates="drop",
    )

    rows = []

    for group, subset in analysis.groupby(
        "lead_time_group",
        observed=True,
        sort=True,
    ):
        labeled_orders = len(subset)

        late_orders = int(
            subset[
                "delivered_after_estimate"
            ].sum()
        )

        late_rate = late_orders / labeled_orders

        ci_low, ci_high = wilson_interval(
            late_orders,
            labeled_orders,
        )

        rows.append(
            {
                "lead_time_group": str(group),
                "min_lead_time_days": subset[
                    "approval_to_estimate_days"
                ].min(),
                "max_lead_time_days": subset[
                    "approval_to_estimate_days"
                ].max(),
                "median_lead_time_days": subset[
                    "approval_to_estimate_days"
                ].median(),
                "labeled_orders": labeled_orders,
                "late_orders": late_orders,
                "late_rate": late_rate,
                "late_rate_ci95_low": ci_low,
                "late_rate_ci95_high": ci_high,
            }
        )

    result = pd.DataFrame(rows)

    result.to_csv(
        LEAD_TIME_OUT,
        index=False,
    )

    x = range(len(result))
    y = result["late_rate"]

    lower_error = (
        y
        - result["late_rate_ci95_low"]
    )

    upper_error = (
        result["late_rate_ci95_high"]
        - y
    )

    labels = [
        f"Q{i + 1}\n"
        f"{row.min_lead_time_days:.1f}–"
        f"{row.max_lead_time_days:.1f} d\n"
        f"n={int(row.labeled_orders)}"
        for i, row in enumerate(
            result.itertuples()
        )
    ]

    plt.figure(figsize=(10, 5))
    plt.errorbar(
        x,
        y,
        yerr=[lower_error, upper_error],
        marker="o",
        capsize=4,
    )
    plt.xticks(
        list(x),
        labels,
    )
    plt.xlabel(
        "Approval-to-estimated-delivery lead-time quintile"
    )
    plt.ylabel("Late-delivery rate")
    plt.title(
        "Late-Delivery Rate by Approval-to-Estimate Lead Time"
    )
    plt.tight_layout()
    plt.savefig(
        LEAD_TIME_FIGURE_OUT,
        dpi=180,
    )
    plt.close()

    return result


def build_within_state_lead_time(primary, overall_late_rate):
    analysis = primary[
        primary["approval_to_estimate_days"].notna()
        & primary["customer_state"].isin(VALID_BRAZIL_STATE_CODES)
    ].copy()

    rows = []

    for state_code, subset in analysis.groupby(
        "customer_state",
        sort=True,
    ):
        late_orders = int(
            subset["delivered_after_estimate"].sum()
        )

        if (
            len(subset) < WITHIN_STATE_MIN_ORDERS
            or late_orders < WITHIN_STATE_MIN_LATE_ORDERS
        ):
            continue

        median_lead = subset[
            "approval_to_estimate_days"
        ].median()

        shorter = subset[
            subset["approval_to_estimate_days"] <= median_lead
        ]

        longer = subset[
            subset["approval_to_estimate_days"] > median_lead
        ]

        correlation = subset[
            "approval_to_estimate_days"
        ].corr(
            subset["delivered_after_estimate"]
        )

        rows.append(
            {
                "customer_state": state_code,
                "labeled_orders": len(subset),
                "late_orders": late_orders,
                "late_rate": late_orders / len(subset),
                "mean_lead_time_days": subset[
                    "approval_to_estimate_days"
                ].mean(),
                "median_lead_time_days": median_lead,
                "within_state_correlation": correlation,
                "shorter_lead_orders": len(shorter),
                "shorter_lead_late_rate": (
                    shorter["delivered_after_estimate"].mean()
                ),
                "longer_lead_orders": len(longer),
                "longer_lead_late_rate": (
                    longer["delivered_after_estimate"].mean()
                ),
            }
        )

    result = pd.DataFrame(rows)

    result["longer_minus_shorter_late_rate"] = (
        result["longer_lead_late_rate"]
        - result["shorter_lead_late_rate"]
    )

    result = result.sort_values(
        "mean_lead_time_days"
    ).reset_index(drop=True)

    result.to_csv(
        WITHIN_STATE_OUT,
        index=False,
    )

    pooled_correlation = analysis[
        "approval_to_estimate_days"
    ].corr(
        analysis["delivered_after_estimate"]
    )

    between_state_correlation = result[
        "mean_lead_time_days"
    ].corr(
        result["late_rate"]
    )

    confound = pd.DataFrame(
        [
            {
                "comparison": "pooled_across_all_orders",
                "unit": "order",
                "observations": len(analysis),
                "correlation": pooled_correlation,
            },
            {
                "comparison": "between_states",
                "unit": "state",
                "observations": len(result),
                "correlation": between_state_correlation,
            },
            {
                "comparison": "within_states_median",
                "unit": "state",
                "observations": len(result),
                "correlation": result[
                    "within_state_correlation"
                ].median(),
            },
            {
                "comparison": "states_with_negative_within_state_correlation",
                "unit": "state",
                "observations": len(result),
                "correlation": int(
                    (result["within_state_correlation"] < 0).sum()
                ),
            },
            {
                "comparison": "states_where_longer_lead_has_lower_late_rate",
                "unit": "state",
                "observations": len(result),
                "correlation": int(
                    (result["longer_minus_shorter_late_rate"] < 0).sum()
                ),
            },
        ]
    )

    confound.to_csv(
        CONFOUND_OUT,
        index=False,
    )

    figure, axes = plt.subplots(
        1,
        2,
        figsize=(13, 5.5),
    )

    axes[0].scatter(
        result["mean_lead_time_days"],
        result["late_rate"],
        s=result["labeled_orders"] / 10,
    )

    for row in result.itertuples():
        axes[0].annotate(
            row.customer_state,
            (
                row.mean_lead_time_days,
                row.late_rate,
            ),
            textcoords="offset points",
            xytext=(5, 4),
            fontsize=9,
        )

    axes[0].axhline(
        overall_late_rate,
        linestyle="--",
        linewidth=1,
    )

    axes[0].set_xlabel(
        "Mean approval-to-estimate lead time (days)"
    )
    axes[0].set_ylabel("Late-delivery rate")
    axes[0].set_title(
        "Between states: longer lead times, higher late rates\n"
        f"correlation = {between_state_correlation:.2f}"
    )

    positions = range(len(result))

    axes[1].plot(
        positions,
        result["shorter_lead_late_rate"],
        marker="o",
        label="Shorter lead than state median",
    )

    axes[1].plot(
        positions,
        result["longer_lead_late_rate"],
        marker="s",
        label="Longer lead than state median",
    )

    axes[1].set_xticks(list(positions))
    axes[1].set_xticklabels(
        result["customer_state"]
    )

    axes[1].set_xlabel(
        "Customer state, ordered by mean lead time"
    )
    axes[1].set_ylabel("Late-delivery rate")
    axes[1].set_title(
        "Within states: longer lead times, lower late rates"
    )
    axes[1].legend()

    figure.tight_layout()
    figure.savefig(
        CONFOUND_FIGURE_OUT,
        dpi=180,
    )
    plt.close(figure)

    return result, confound


def build_state_analysis(primary, overall_late_rate):
    state = primary["customer_state"]

    valid_state_mask = state.isin(
        VALID_BRAZIL_STATE_CODES
    )

    missing_state_mask = state.isna()

    invalid_state_mask = (
        state.notna()
        & ~valid_state_mask
    )

    valid = primary.loc[
        valid_state_mask
    ].copy()

    rows = []

    total_late_orders = int(
        primary[
            "delivered_after_estimate"
        ].sum()
    )

    for state_code, subset in valid.groupby(
        "customer_state",
        sort=True,
    ):
        labeled_orders = len(subset)

        late_orders = int(
            subset[
                "delivered_after_estimate"
            ].sum()
        )

        late_rate = late_orders / labeled_orders

        ci_low, ci_high = wilson_interval(
            late_orders,
            labeled_orders,
        )

        expected_late_orders = (
            labeled_orders
            * overall_late_rate
        )

        rows.append(
            {
                "customer_state": state_code,
                "labeled_orders": labeled_orders,
                "late_orders": late_orders,
                "late_rate": late_rate,
                "late_rate_ci95_low": ci_low,
                "late_rate_ci95_high": ci_high,
                "share_of_all_late_orders": (
                    late_orders
                    / total_late_orders
                ),
                "expected_late_orders_at_overall_rate": (
                    expected_late_orders
                ),
                "excess_late_orders_vs_overall": (
                    late_orders
                    - expected_late_orders
                ),
                "ci_entirely_above_overall_rate": int(
                    ci_low
                    > overall_late_rate
                ),
            }
        )

    result = pd.DataFrame(rows)

    result = result.sort_values(
        [
            "ci_entirely_above_overall_rate",
            "excess_late_orders_vs_overall",
        ],
        ascending=[False, False],
    ).reset_index(drop=True)

    result.to_csv(
        STATE_OUT,
        index=False,
    )

    state_quality = pd.DataFrame(
        [
            {
                "metric": "primary_labeled_orders",
                "value": len(primary),
            },
            {
                "metric": "orders_with_valid_state",
                "value": int(
                    valid_state_mask.sum()
                ),
            },
            {
                "metric": "orders_with_missing_state",
                "value": int(
                    missing_state_mask.sum()
                ),
            },
            {
                "metric": "orders_with_invalid_or_unknown_state",
                "value": int(
                    invalid_state_mask.sum()
                ),
            },
            {
                "metric": "orders_with_state_code_ZZ",
                "value": int(
                    state.eq("ZZ").sum()
                ),
            },
            {
                "metric": "valid_state_codes_analyzed",
                "value": int(
                    valid[
                        "customer_state"
                    ].nunique()
                ),
            },
        ]
    )

    state_quality.to_csv(
        STATE_QUALITY_OUT,
        index=False,
    )

    plot_data = result.sort_values(
        "late_rate",
        ascending=True,
    ).reset_index(drop=True)

    y = range(len(plot_data))
    rates = plot_data["late_rate"]

    lower_error = (
        rates
        - plot_data[
            "late_rate_ci95_low"
        ]
    )

    upper_error = (
        plot_data[
            "late_rate_ci95_high"
        ]
        - rates
    )

    plt.figure(
        figsize=(
            9,
            max(
                7,
                len(plot_data) * 0.3,
            ),
        )
    )

    plt.errorbar(
        rates,
        y,
        xerr=[
            lower_error,
            upper_error,
        ],
        fmt="o",
        capsize=3,
    )

    plt.yticks(
        list(y),
        plot_data["customer_state"],
    )

    plt.axvline(
        overall_late_rate,
        linestyle="--",
    )

    plt.xlabel("Late-delivery rate")
    plt.ylabel("Customer state")
    plt.title(
        "Late-Delivery Rates by Valid Customer State"
    )
    plt.tight_layout()
    plt.savefig(
        STATE_FIGURE_OUT,
        dpi=180,
    )
    plt.close()

    return result, state_quality


def make_rule_masks(data):
    delivered = (
        data["order_status"]
        == "delivered"
    )

    minimal = (
        delivered
        & data[
            "order_delivered_customer_date"
        ].notna()
        & data[
            "order_estimated_delivery_date"
        ].notna()
    )

    primary = (
        data[
            "delivery_label_eligible"
        ] == 1
    )

    carrier_strict = (
        primary
        & data[
            "order_delivered_carrier_date"
        ].notna()
        & (
            data[
                "order_delivered_carrier_date"
            ]
            >= data["order_approved_at"]
        )
        & (
            data[
                "order_delivered_customer_date"
            ]
            >= data[
                "order_delivered_carrier_date"
            ]
        )
    )

    return {
        "minimal_valid_delivery_and_estimate": minimal,
        "primary_purchase_approval_chronology": primary,
        "carrier_strict_chronology": carrier_strict,
    }


def build_sensitivity(data):
    rows = []

    for rule_name, mask in make_rule_masks(
        data
    ).items():
        subset = data.loc[
            mask
        ].copy()

        labels = (
            subset["delivery_date"]
            > subset["estimated_date"]
        ).astype(int)

        labeled_orders = len(subset)
        late_orders = int(labels.sum())
        late_rate = (
            late_orders
            / labeled_orders
        )

        ci_low, ci_high = wilson_interval(
            late_orders,
            labeled_orders,
        )

        late_delays = subset.loc[
            labels == 1,
            "delay_days",
        ]

        valid_state_orders = int(
            subset[
                "customer_state"
            ].isin(
                VALID_BRAZIL_STATE_CODES
            ).sum()
        )

        rows.append(
            {
                "rule": rule_name,
                "labeled_orders": labeled_orders,
                "late_orders": late_orders,
                "late_rate": late_rate,
                "late_rate_ci95_low": ci_low,
                "late_rate_ci95_high": ci_high,
                "median_late_delay_days": (
                    late_delays.median()
                ),
                "mean_late_delay_days": (
                    late_delays.mean()
                ),
                "median_approval_to_estimate_days": (
                    subset[
                        "approval_to_estimate_days"
                    ].median()
                ),
                "orders_with_valid_state": (
                    valid_state_orders
                ),
            }
        )

    result = pd.DataFrame(rows)

    primary = result.loc[
        result["rule"]
        == "primary_purchase_approval_chronology"
    ].iloc[0]

    result[
        "labeled_orders_difference_from_primary"
    ] = (
        result["labeled_orders"]
        - primary["labeled_orders"]
    )

    result[
        "late_rate_difference_from_primary"
    ] = (
        result["late_rate"]
        - primary["late_rate"]
    )

    result[
        "median_delay_difference_from_primary"
    ] = (
        result[
            "median_late_delay_days"
        ]
        - primary[
            "median_late_delay_days"
        ]
    )

    result.to_csv(
        SENSITIVITY_OUT,
        index=False,
    )

    return result


def main():
    os.makedirs(
        "outputs/tables",
        exist_ok=True,
    )

    os.makedirs(
        "outputs/figures",
        exist_ok=True,
    )

    os.makedirs(
        "outputs/evidence",
        exist_ok=True,
    )

    data = add_analysis_columns(
        load_data()
    )

    primary = data.loc[
        data[
            "delivery_label_eligible"
        ] == 1
    ].copy()

    primary[
        "delivered_after_estimate"
    ] = (
        primary[
            "delivered_after_estimate"
        ].astype(int)
    )

    delay_summary = build_delay_summary(
        primary
    )

    lead_time_analysis = (
        build_lead_time_analysis(
            primary
        )
    )

    overall_late_rate = float(
        delay_summary.iloc[0][
            "late_rate"
        ]
    )

    state_analysis, state_quality = (
        build_state_analysis(
            primary,
            overall_late_rate,
        )
    )

    within_state, confound = (
        build_within_state_lead_time(
            primary,
            overall_late_rate,
        )
    )

    sensitivity = build_sensitivity(
        data
    )

    first_priority = (
        state_analysis.iloc[0]
    )

    print("=== Task 3 outputs ===")

    print(
        f"primary_labeled_orders="
        f"{len(primary)}"
    )

    print(
        f"late_orders="
        f"{int(primary['delivered_after_estimate'].sum())}"
    )

    print(
        f"late_rate="
        f"{overall_late_rate:.4%}"
    )

    print(
        "median_late_delay_days="
        f"{delay_summary.iloc[0]['median_late_delay_days']:.2f}"
    )

    print(
        f"lead_time_groups="
        f"{len(lead_time_analysis)}"
    )

    print(
        f"within_state_lead_time_states="
        f"{len(within_state)}"
    )

    for row in confound.itertuples():
        print(
            f"{row.comparison}="
            f"{row.correlation:.4f}"
        )

    print(
        f"valid_state_codes_analyzed="
        f"{len(state_analysis)}"
    )

    print(
        "missing_state_orders="
        f"{int(state_quality.loc[state_quality['metric'] == 'orders_with_missing_state', 'value'].iloc[0])}"
    )

    print(
        "invalid_or_unknown_state_orders="
        f"{int(state_quality.loc[state_quality['metric'] == 'orders_with_invalid_or_unknown_state', 'value'].iloc[0])}"
    )

    print(
        "first_investigation_state="
        f"{first_priority['customer_state']}"
    )

    print(
        "first_investigation_state_late_rate="
        f"{first_priority['late_rate']:.4%}"
    )

    print(
        "first_investigation_state_excess_late_orders="
        f"{first_priority['excess_late_orders_vs_overall']:.2f}"
    )

    print(
        f"sensitivity_rules="
        f"{len(sensitivity)}"
    )

    print(
        f"delay_summary="
        f"{DELAY_SUMMARY_OUT}"
    )

    print(
        f"lead_time_analysis="
        f"{LEAD_TIME_OUT}"
    )

    print(
        f"state_analysis="
        f"{STATE_OUT}"
    )

    print(
        f"state_quality="
        f"{STATE_QUALITY_OUT}"
    )

    print(
        f"within_state_lead_time="
        f"{WITHIN_STATE_OUT}"
    )

    print(
        f"lead_time_confound_summary="
        f"{CONFOUND_OUT}"
    )

    print(
        f"sensitivity="
        f"{SENSITIVITY_OUT}"
    )

    print(
        f"delay_figure="
        f"{DELAY_FIGURE_OUT}"
    )

    print(
        f"lead_time_figure="
        f"{LEAD_TIME_FIGURE_OUT}"
    )

    print(
        f"state_figure="
        f"{STATE_FIGURE_OUT}"
    )

    print(
        f"lead_time_confound_figure="
        f"{CONFOUND_FIGURE_OUT}"
    )


if __name__ == "__main__":
    main()