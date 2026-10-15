# Decisions

This document explains the pipeline decisions that could reasonably have been made differently. For each decision, it gives the supporting evidence, explains why that option was chosen, and states the rule followed by the code.

Decisions required by the assignment are not covered here. These include using `orders` as the base table, aggregating one-to-many tables before joining them, keeping order IDs separate from model features, and excluding payments and reviews.

All findings are based on the supplied modified extract. An observed association does not prove that one factor causes another.

| | Decision |
|---|---|
| 1 | [Build the order-level table in SQLite rather than pandas](#1-build-the-order-level-table-in-sqlite-rather-than-pandas) |
| 2 | [Repair item prices and freight before aggregation](#2-repair-item-prices-and-freight-before-aggregation) |
| 3 | [Repair the catalogue, separating three defect mechanisms](#3-repair-the-catalogue-separating-three-defect-mechanisms) |
| 4 | [Keep every order, label only the ones that can be trusted](#4-keep-every-order-label-only-the-ones-that-can-be-trusted) |
| 5 | [Require four timestamps and a possible chronology](#5-require-four-timestamps-and-a-possible-chronology) |
| 6 | [Compare calendar dates, not times of day](#6-compare-calendar-dates-not-times-of-day) |
| 7 | [Record why each order was excluded, and diagnose the seven-day shift](#7-record-why-each-order-was-excluded-and-diagnose-the-seven-day-shift) |
| 8 | [Decompose lead time by state instead of reporting the pooled figure](#8-decompose-lead-time-by-state-instead-of-reporting-the-pooled-figure) |
| 9 | [Prioritise states by excess late orders, not by rate](#9-prioritise-states-by-excess-late-orders-not-by-rate) |
| 10 | [Test every finding against all three label rules](#10-test-every-finding-against-all-three-label-rules) |
| 11 | [Use approval as the cutoff, and audit eligibility at two levels](#11-use-approval-as-the-cutoff-and-audit-eligibility-at-two-levels) |
| 12 | [Encode hour, weekday and month as sine and cosine pairs](#12-encode-hour-weekday-and-month-as-sine-and-cosine-pairs) |
| 13 | [Exclude calendar year](#13-exclude-calendar-year) |
| 14 | [Keep customer state, drop city and ZIP prefix](#14-keep-customer-state-drop-city-and-zip-prefix) |
| 15 | [Represent missing values with an indicator instead of imputing](#15-represent-missing-values-with-an-indicator-instead-of-imputing) |
| 16 | [Include catalogue measurements, with separate indicators per cause](#16-include-catalogue-measurements-with-separate-indicators-per-cause) |
| 17 | [Encode product category by minimum support](#17-encode-product-category-by-minimum-support) |
| 18 | [Derive shipment origin at item level](#18-derive-shipment-origin-at-item-level) |
| 19 | [Remove every external binary dependency](#19-remove-every-external-binary-dependency) |
| 20 | [Measure resources with two independent passes](#20-measure-resources-with-two-independent-passes) |

---

## 1. Build the order-level table in SQLite rather than pandas

**Evidence.** Both approaches were benchmarked five times. Each ran in a separate Python process, so both measurements include the same interpreter startup cost. The outputs also match across all 46 columns. The benchmark therefore compares the loading methods, not differences in the work they perform.

| Approach | Runtime | Peak memory | Output size |
|---|---:|---:|---:|
| SQLite-first | 0.2526 s | 48.28 MiB | 7.45 MiB |
| pandas-first | 0.3522 s | 202.19 MiB | 6.59 MiB |

Before the catalogue tables were joined, the memory gap was 110 MiB. After joining the product and seller tables, it grew to 140 MiB.

**Reasoning.** SQLite performs filtering, grouping and joins inside the database engine, which processes the data without holding every joined table in Python memory. The pandas approach keeps the joined tables in memory, so its working set grows as more tables are added. This explains why the memory gap gets wider with each additional join, and it is the main reason to prefer SQLite.

SQLite was 1.39 times faster. The larger and more consistent advantage is its lower memory use.

The benchmark does not show a storage advantage: the pandas output file is smaller.

One detail matters when comparing these results with earlier runs. The original pandas version used a `min_count` lambda to match SQL's handling of null values. That forced pandas to use a Python operation for each group instead of its vectorised aggregation path. The lambda took 1.32 s, compared with 0.016 s for an equivalent plain aggregation, making the pandas version appear about four times slower. Replacing it with a plain sum and a non-null count produces the same values without that avoidable overhead. A fair benchmark should not make one approach slower through an unnecessary implementation choice.

**Rule.** Build the order-level table using SQL inside SQLite. Before comparing performance, verify that both approaches produce identical outputs.

**Evidence file.** `outputs/evidence/task1_loading_benchmark.csv`

---

## 2. Repair item prices and freight before aggregation

**Evidence.** The `price` and `freight_value` columns each contain three types of defects. These types do not overlap: none of the 22,662 item rows has more than one defect flag.

| Column | Defect | Item rows | Repairable |
|---|---|---:|---|
| price | scaled | 412 | yes |
| price | negated | 408 | yes |
| price | missing | 439 | no |
| freight_value | scaled | 473 | yes |
| freight_value | negated | 458 | yes |
| freight_value | missing | 427 | no |

Scaled values are 1,000 times larger than they should be. For a product that has both a suspect value and clean values on other rows, the factor can be checked against the median of the product's clean rows. Dividing the suspect value by that median gives the following results:

| Column | Exactly 1,000 | Close to 1,000 | No clean reference |
|---|---:|---:|---:|
| price | 184 | 92 | 136 |
| freight_value | 76 | 237 | 160 |

Freight values vary legitimately by destination, even for the same product. As a result, the product's median freight value is a less precise reference than its median price.

A value is classified as scaled only when it passes two tests. The first checks the value's exactness: genuine amounts have two decimal places, so multiplying by 1,000 produces a whole number of cents divisible by 1,000. Some clean values pass this test by coincidence—5.13% of prices and 0.13% of freight values—so it is not enough by itself. A second test checks the value's size. The thresholds differ by column:

- **Freight, 1,000.** Genuine freight values do not exceed 314.40, leaving a wide gap between the largest genuine value and the smallest defective one.
- **Price, 10,000.** Genuine prices reach 9,990.00. Round retail prices such as 1,200.00 also pass the exactness test by design. Of the 47 rows flagged between 1,000 and 5,000, only 2 have a clean reference for the same product, and one of those has a ratio of 2 rather than 1,000.

For the 136 prices and 160 freight values without a clean reference, the coincidence rates would predict roughly seven and zero accidental passes, respectively. Instead, every one of these values passed both tests, which is not the pattern seen in genuine values.

Negated values have had their signs reversed. Taking the absolute value brings 95.69% of negative prices to within 20% of the clean median for the same product, among the 255 rows with a clean reference. For freight, the comparison uses a positive item from the same order, which shares the destination. Among the 90 rows with such a comparison, 87.78% are within 5% of that reference.

In total, 2,617 item rows are flagged—11.55% of the table—across 2,561 orders. A total of 1,751 values can be repaired; the other 866 are missing and remain missing. Of the affected orders, 486 contain more than one item.

| Column | Original total | Repaired total | Recorded corrections |
|---|---:|---:|---:|
| price | 54,446,205.77 | 2,749,872.09 | -51,696,333.68 |
| freight_value | 10,515,059.68 | 447,027.82 | -10,068,031.86 |

**Reasoning.** Inspection shows that these values are not all unusable. The three defect types can be distinguished, each has a testable explanation, and two can be repaired without guessing.

The repairs must happen before grouping items into orders. Grouping adds the item values together, and 486 affected orders contain both clean and defective items. After aggregation, it would be difficult to distinguish a total inflated by one defective item from a genuinely high total. This is why the repair runs before the Task 1 build, even though it belongs to Task 2.

Missing values are left as missing. The data does not tell us what those values should be, so filling them with plausible numbers would make unknown amounts look as though they had been observed.

The original values and defect types are retained for every row. This allows the values before repair to be recovered and the changes to be checked against the source.

**Rule.** Classify every `price` and `freight_value` as `scaled`, `negated`, `missing` or clean. Divide `scaled` values by 1,000, take the absolute value of `negated` values, and leave `missing` values as null. Keep `price_raw`, `freight_value_raw`, `price_defect` and `freight_value_defect`. Stop the pipeline if a row has more than one defect flag or if the repaired totals do not match the recorded corrections. Run this step before the Task 1 build.

**Evidence files.** `outputs/evidence/task2_item_repair_summary.csv`, `task2_item_repair_verification.csv`, `task2_item_repair_reconciliation.csv`

---

## 3. Repair the catalogue, separating three defect mechanisms

**Evidence.** The `products` table contains three types of defects. The values themselves determine which type applies.

| Column | Scaled | Negated | Sentinel `-1` | Missing |
|---|---:|---:|---:|---:|
| product_weight_g | 89 | 72 | 0 | 221 |
| product_length_cm | 94 | 102 | 0 | 207 |
| product_height_cm | 92 | 103 | 0 | 208 |
| product_width_cm | 84 | 95 | 0 | 213 |
| product_photos_qty | 0 | 0 | 146 | 436 |
| product_name_lenght | 0 | 0 | 112 | 172 |
| product_description_lenght | 0 | 0 | 136 | 173 |

Every negative value in the three count columns is exactly `-1`; there are no other negative values in those columns. The four measurement columns contain no `-1` values. Their negative values range from -50 to -30,000 for weight and from -16 to -80 for length, matching the corresponding positive distributions.

Scaled catalogue values follow the same 1,000-times-larger pattern as the item values, but the thresholds are set separately for each measurement. For dimensions, the threshold is 1,000: no genuine dimension exceeds 118 cm, and there are no values between 200 and 1,000. For weight, the threshold is 50,000. Genuine weights reach 40 kg, and the values from 10,000 to 50,000 have a mixed divisibility rate of 13.7%, consistent with some genuine round-number weights. Above 50,000, the rate rises to 100%, compared with a baseline of 3.2%.

After division by 1,000, the flagged dimensions fall within the clean-value distributions. The median suspect dimensions are 25.5, 16.0 and 21.0 cm, compared with clean medians of 25, 13 and 20 cm.

`seller_state` must be normalised before it is used. In 2,029 of 2,071 rows, the value differed from its trimmed, uppercase form; examples include `' CE  '` and `'sp'`. After normalisation, 114 sellers have the invalid state code `ZZ`, and 42 have no state recorded.

Category names also need normalisation before translation. The 121 original spellings reduce to 73, of which 70 match `category_translation`. Formatting differences explain most of the apparent translation gap.

There are 910 item rows whose `product_id` is absent from `products`, and 893 whose seller is absent from the seller table.

**Reasoning.** The key distinction is between a `-1` used as a missing-value marker and a negative measurement whose sign has been reversed. A photo count of `-1` means the count is missing; taking its absolute value would incorrectly turn it into a real count of one. The measurement columns show a different pattern, so each type is handled according to its own evidence rather than by applying one rule to every column.

Missing measurements are not filled in, for the same reason as missing prices and freight values.

Rows with unmatched product or seller references are kept. Their orders can still have a known delivery outcome, so dropping them would remove labelled orders because of a separate catalogue problem.

**Rule.** Normalise `product_category_name` and `seller_state` before joining tables or comparing values. Classify each measurement as `scaled`, `negated`, `sentinel_missing`, `missing` or clean. Divide `scaled` values by 1,000, take the absolute value of `negated` values, and convert both `sentinel_missing` and `missing` values to null. Stop the pipeline if a repair cannot be reversed exactly, or if a repaired measurement remains negative or above its threshold. Run this step before the Task 1 build.

**Evidence files.** `outputs/evidence/task2_catalogue_repair_summary.csv`, `task2_catalogue_repairs.csv`, `task2_catalogue_coverage.csv`

---

## 4. Keep every order, label only the ones that can be trusted

**Evidence.** The cleaned table contains 20,000 rows and 20,000 distinct order IDs, with no rows lost or added. Of these orders, 15,843 have a delivery label: 1,060 were late and 14,783 were on time. The remaining 4,157 have no label, and each has a recorded reason.

Even among orders with labels, optional information is often missing, including customer records, catalogue measurements and reviews.

**Reasoning.** Keeping an order and trusting its delivery label are two separate decisions. An order can have no matching catalogue entry and still have a delivery date and estimated date, which are enough to determine its outcome.

The assignment explicitly says that a missing optional catalogue field does not, by itself, make an order unusable.

Deleting orders without labels would also remove the record of what happened to them. Keeping all orders, with a null label and a reason where the outcome is unreliable, accounts for every one of the 20,000 orders.

**Rule.** Keep all 20,000 orders. If an order has no reliable outcome, leave its label null and record the exclusion reason. Missing optional fields alone must never invalidate a label.

**Evidence files.** `outputs/evidence/task2_cleaning_summary.csv`, `task2_clean_validation.txt`

---

## 5. Require four timestamps and a possible chronology

**Evidence.** Three possible label rules were compared for delivered orders:

| Rule | Labelled | Late | Late rate |
|---|---:|---:|---:|
| Valid delivery and estimate only | 17,273 | 1,107 | 6.4088% |
| Purchase and approval chronology | 15,843 | 1,060 | 6.6907% |
| Carrier-strict chronology | 15,335 | 1,041 | 6.7884% |

Requiring the carrier handoff timestamp removes another 508 orders and changes the late rate by about a tenth of a percentage point.

**Reasoning.** The simplest rule checks only whether the delivery and estimate dates are valid. It does not check whether the dates make sense together, so an order delivered before approval could still receive a label. That would make the outcome unreliable.

The carrier handoff records when the seller passes the parcel to the courier. It does not determine whether the customer received the order after the estimated date. Requiring that timestamp would therefore discard 508 otherwise labelled orders without helping answer the question the label is meant to capture.

The purchase and approval timestamps provide the minimum checks needed for a credible timeline, so the main rule uses those checks without requiring the carrier timestamp.

**Rule.** An order is eligible if its status is `delivered`, its purchase, approval, delivery and estimated-delivery timestamps all parse as valid dates, and all five chronology conditions hold: approval is not before purchase; delivery is not before purchase or approval; and the estimate is not before purchase or approval. The carrier timestamp is not required.

**Evidence files.** `outputs/evidence/task2_label_reliability.csv`, `task2_label_sensitivity.csv`

---

## 6. Compare calendar dates, not times of day

**Evidence.** There are 222 orders whose delivery date is exactly the estimated date. Comparing full timestamps would classify some of these as late simply because they arrived later in the day.

**Reasoning.** The assignment defines a late delivery as one that arrives after the estimated date. An order delivered at 18:00 on its estimated date still arrived on that date, so it counts as on time.

**Rule.** Set `delivered_after_estimate` to 1 when the delivery calendar date is later than the estimated calendar date, and to 0 when it is the same date or earlier. Use null when the order cannot be labelled reliably.

---

## 7. Record why each order was excluded, and diagnose the seven-day shift

**Evidence.** There are 4,157 unlabelled orders, each with one or more recorded exclusion reasons. Validation confirms that every eligible order has no exclusion reason and every ineligible order has at least one.

One reason points to a specific injected defect rather than scattered data errors. For 812 orders, the delivery timestamp is earlier than the approval timestamp. Of those, 803 are exactly seven days earlier, down to the second:

```text
order_delivered_customer_date = order_approved_at - 7 days
```

The other 9 differ by 0.14, 0.15, 0.19, 0.28, 0.75, 1.20, 1.22, 2.22 and 3.25 days. These look like ordinary timestamp noise. There are no cases between 3.25 and 7 days.

Of the 803 orders shifted back by exactly seven days, 782 have status `delivered` and are excluded by the chronology checks. The other 21 already fail the status check, so they never reach the chronology checks. This explains why 803 orders show the shift but only 791 are recorded under `delivery_before_approval`.

Moving a delivery timestamp backwards can only make an order appear earlier. All 782 affected delivered orders would therefore have been labelled on time if they had been kept. Including them would lower the late rate from 6.69% to 6.38%.

**Reasoning.** An exclusion reason such as `delivery_before_approval` records what a check found, not why the timestamps look that way. Measuring the gap reveals a clear seven-day pattern in 791 recorded failures, while separating the 9 other cases from it.

The direction of the effect matters: excluding these orders protects the late-rate estimate from being pushed down. In this case, dropping the affected records does not inflate the measured rate; it prevents an underestimate.

The diagnosis is recorded separately, without changing the exclusion rules. The 791 recorded `delivery_before_approval` cases consist of 782 orders shifted back by seven days and 9 with other timestamp gaps. The existing chronology checks already exclude these orders for a valid reason. Adding a more specific exclusion label would change counts used by other decisions and checks without making the outcome more reliable.

**Rule.** Record every applicable reason in `delivery_label_exclusion_reasons`. When a chronology violation follows a measurable pattern, record its offset in `delivery_before_approval_offset_days` and the diagnosis in `delivery_shift_pattern`, rather than adding the pattern to the exclusion reason.

**Evidence file.** `outputs/evidence/task2_label_exclusions.csv`

---

## 8. Decompose lead time by state instead of reporting the pooled figure

**Evidence.** Across all 15,843 labelled orders, lead time appears to have almost no relationship with lateness. The pooled correlation is -0.030, and late rates across lead-time quintiles range from 4.99% to 7.54% without a clear trend.

That pooled result hides two relationships that point in opposite directions:

| Comparison | Unit | Correlation |
|---|---|---:|
| Pooled across all orders | order | -0.030 |
| Between states, mean lead time against late rate | state | +0.750 |
| Within states, median of the 11 | state | -0.076 |

All 11 states that meet the inclusion criteria have a negative within-state correlation. When orders in each state are split at that state's median lead time, 10 of the 11 have a lower late rate for orders with longer lead times:

| State | Mean lead (days) | Shorter-lead late rate | Longer-lead late rate |
|---|---:|---:|---:|
| SP | 18.6 | 5.71% | 3.23% |
| MG | 24.1 | 5.62% | 3.71% |
| SC | 25.2 | 6.34% | 6.72% |
| RJ | 25.9 | 14.64% | 8.36% |
| GO | 26.6 | 9.79% | 2.80% |
| BA | 28.8 | 15.77% | 8.71% |
| PE | 30.9 | 23.42% | 8.11% |

SC is the exception, but the difference is only 0.4 percentage points, which is small.

The result is consistent across nine configurations: the three label rules combined with minimum state sizes of 100, 200 and 400. The between-state correlation is positive in all nine, ranging from 0.65 to 0.76. The median within-state correlation is negative in all nine, ranging from -0.067 to -0.089.

**Reasoning.** Reporting only the pooled result would suggest that lead time provides almost no information. Separating the analysis by state shows that this conclusion comes from combining groups with different delivery conditions.

The two comparisons answer different questions. Between states, a longer estimate tends to indicate a more difficult destination, and those states also have higher late rates. Within the same state, where the destination is more comparable, orders with longer estimates tend to be late less often. That is the intended role of a delivery estimate.

The practical interpretation follows from the within-state result: longer estimates are not shown to cause late delivery. Instead, estimates are already longer in places where delivery is harder.

These are still observational results. The business sets the lead time rather than assigning it randomly, so the analysis does not measure what would happen if the business lengthened an estimate.

**Rule.** Report the pooled relationship alongside the between-state and within-state results; do not report the pooled correlation alone. Calculate within-state comparisons only for states with at least 200 labelled orders and 10 late orders, and report sensitivity to that minimum. Do not make causal claims.

**Evidence files.** `outputs/tables/task3_lead_time_confound_summary.csv`, `outputs/evidence/task3_within_state_robustness.csv`

---

## 9. Prioritise states by excess late orders, not by rate

**Evidence.** The highest late rates occur in states with very small samples. In Roraima, 2 of 9 orders were late, giving a rate of 22.22%. Rio de Janeiro had a lower rate of 11.50%, but it came from 1,843 orders.

Flagging a state only when the lower bound of its 95% Wilson interval is above the overall late rate identifies eight states: RJ, BA, PE, CE, MA, AL, PI and PA.

RJ has the largest burden among these states. At the overall rate, its 1,843 orders would be expected to include about 123 late deliveries. It had 212, or roughly 89 more than expected at that rate.

Among labelled orders, 14,211 have a valid state code, 967 have no state, and 665 have the code `ZZ`.

**Reasoning.** A percentage based on very few orders can be misleading. The Wilson interval gives a more reliable range than a normal approximation for proportions near zero, which matters for states with only a handful of orders.

Requiring the lower end of a state's 95% interval to remain above the overall late rate means that even its more favourable estimate is still worse than average.

Ranking the flagged states by their excess number of late orders shows where the largest operational burden lies. This is more useful for prioritisation than ranking states by rate alone.

Orders with missing or invalid state codes remain part of the overall analysis. Their locations cannot be mapped, but their delivery outcomes are still known.

**Rule.** Flag a state when the lower bound of its 95% Wilson interval exceeds the overall late rate. Rank flagged states by the number of late orders above what the overall rate would suggest. Report missing and invalid state counts alongside any geographic conclusion.

**Evidence files.** `outputs/tables/task3_state_priority.csv`, `task3_state_data_quality.csv`

---

## 10. Test every finding against all three label rules

**Evidence.** The three label rules produce late rates of 6.4088%, 6.6907% and 6.7884%. The median late delay is 7 days under all three. The same eight states are flagged by each rule, with RJ ranked first.

**Reasoning.** The label rule involves a judgement call. If a finding changes depending on which reasonable rule is used, it may reflect the rule rather than a genuine pattern in deliveries.

Repeating the analysis under all three rules makes that sensitivity measurable instead of leaving it as an assumption.

**Rule.** Report results using the main label rule and record how each conclusion changes under the alternatives.

**Evidence files.** `outputs/evidence/task3_sensitivity.csv`, `task3_state_sensitivity.csv`, `task3_lead_time_robustness.csv`

---

## 11. Use approval as the cutoff, and audit eligibility at two levels

**Evidence.** The feature-eligibility audit runs at two levels. Against the cleaned order-level table, it identifies 29 candidate columns available by approval time; 27 are excluded, and none is left unclassified.

The second audit reads the source schema directly from `marketplace.sqlite` and assigns a disposition to all 47 columns across all 8 tables:

| Disposition | Columns |
|---|---:|
| excluded | 19 |
| aggregated | 12 |
| join_key | 9 |
| carried_to_order_level | 7 |

Every source column is classified, and the audit fails if one is not. Of the 29 candidate columns, 22 are retained and 7 are excluded, with a recorded reason for each decision.

**Reasoning.** Any information that becomes available only after approval would reveal something from the future, so `order_approved_at` is the cutoff for model features.

Auditing only the derived table would not be enough. A source table removed earlier in the pipeline could never appear as unclassified because its columns would no longer be present. Reading the original schema directly makes the coverage check meaningful: if a source table or column is silently dropped, the audit can detect it rather than overlook it.

A candidate can be eligible for use but still be deliberately excluded. Recording the decision and its reason makes that choice explicit rather than leaving it looking like an omission.

**Rule.** Every predictor must use only information available at or before `order_approved_at`. Assign an explicit disposition to every column in every source table, and record whether each candidate is retained and why.

**Evidence files.** `outputs/evidence/task4_feature_eligibility.csv`, `task4_source_column_coverage.csv`

---

## 12. Encode hour, weekday and month as sine and cosine pairs

**Evidence.** Approval hour, weekday and month are cyclical: after the last value, the sequence returns to the first. Validation recalculates all six encoded columns from the source data and finds no mismatches.

**Reasoning.** As ordinary numbers, 23:00 and 00:00 appear 23 units apart even though they are one hour apart. December and January appear 11 units apart even though they are consecutive months. A model that reads these numbers as ordinary distances could learn the wrong relationship at the boundary.

Encoding each field with a sine and cosine pair places values around a circle, so values near the boundary remain close together. Three cyclical fields therefore produce six columns.

**Rule.** Encode each cyclical time field as a sine and cosine pair. Do not also include the original integer value.

---

## 13. Exclude calendar year

**Evidence.** The approval timestamps cover only 2016, 2017 and 2018. The feature table is intended for a model that will score later orders, so the scoring period is outside the years represented in the training data.

**Reasoning.** The year is known at approval, so excluding it is not a way to prevent leakage. It is a choice about whether the feature will generalise to future data.

Using `approval_year` as a number tells the model that 2018 is greater than 2016 along a scale that continues beyond the training period. Because it sees only three years, the model may extrapolate to later years based on a pattern that is just an accident of the available data.

One-hot encoding does not fully solve the problem. An order from 2019 would activate none of the three year columns, creating an input pattern the model did not see during training.

The year is not needed to retain the useful time information. The cyclical month encoding captures seasonal patterns, while the order's other features describe its own characteristics. The year would mainly identify the particular period covered by the training data, which does not transfer to a later scoring period.

**Rule.** Do not include calendar year or any encoding of it in the feature matrix. Validation must fail if a year feature appears. Keep the year in the cleaned data for analysis.

---

## 14. Keep customer state, drop city and ZIP prefix

**Evidence.** `customer_city` has 2,287 distinct values and `customer_zip_code_prefix` has 7,343, compared with 15,843 rows in the modelling data. `customer_state` has 27 valid values plus an unknown category.

The `customer_state_unknown` category is active for 1,632 rows, or 10.3% of the data.

**Reasoning.** One-hot encoding the ZIP prefixes would create almost half as many columns as there are rows. State captures the broader geographic differences using only 28 categories.

City and ZIP prefix remain in `order_level_clean`, so they are still available if another approach to encoding is needed. The eligibility audit records why they are excluded from this feature table instead of silently dropping them.

The unknown state category is important. If those orders were dropped, roughly one in ten modelling rows would disappear, including potentially late orders from a positive class of only 1,060 orders.

All 28 state categories are kept. The columns in this block therefore sum to one for every row and are collinear with an intercept. The 21 product-category columns have the same property. This is intentional: regularised and tree-based models can handle it, and keeping each category makes every column directly interpretable as a named state or category instead of a comparison with an arbitrary reference. An unregularised logistic regression would need one level removed, but that decision belongs to the modelling step rather than the feature-table build.

**Rule.** Keep `customer_state` as a one-hot encoded feature, with an explicit unknown category. Exclude city and ZIP prefix because of their high numbers of distinct values, and record the reasons. Keep all levels of each categorical feature block; remove a reference level at modelling time if the chosen method requires it.

---

## 15. Represent missing values with an indicator instead of imputing

**Evidence.** After repair, `total_item_price` ranges from 0.85 to 9,900.00 and `total_freight_value` from 0.00 to 479.28; neither contains negative values. Before repair, 288 order totals were negative. The 99th percentiles fell from 99,900.00 and 18,230.00 to 998.93 and 102.72 after repair.

Of the 15,843 retained orders, 15,474 have a usable item-price total and 15,529 have a usable freight total. The missing totals affect 369 and 314 orders, respectively, because at least one contributing item value is missing.

The missing values show little difference in late rates:

| Group | Orders | Late rate |
|---|---:|---:|
| `total_item_price` present | 15,474 | 6.69% |
| `total_item_price` missing | 369 | 6.78% |
| `total_freight_value` present | 15,529 | 6.70% |
| `total_freight_value` missing | 314 | 7.01% |

There are 50 retained orders with a genuine freight total of zero.

**Reasoning.** Once an imputed value is placed in the feature matrix, it can look just like a value that was actually observed. A missing-value indicator preserves the distinction. For example, a genuinely free shipment has a freight value of 0 and an indicator of 0; an unknown freight value is filled with 0 but has an indicator of 1. The 50 genuine zero-freight orders show why this distinction matters in practice.

Dropping orders with missing totals would instead remove labelled examples from a dataset with only 1,060 late orders.

The indicators are included to represent the data accurately, not because missingness has been shown to predict lateness. The late-rate differences are less than one percentage point, so no predictive claim is made about the missing values.

**Rule.** Include `total_item_price` and `total_freight_value`, each with a matching `_missing` indicator. Set the value to 0 where the indicator is 1. Exclude the pre-repair columns and `items_repaired`: the first two are audit fields, while the third describes the cleaning process rather than the order and would not be available in the same form when scoring a new order.

**Evidence file.** `outputs/evidence/task4_numeric_quality_summary.csv`

---

## 16. Include catalogue measurements, with separate indicators per cause

**Evidence.** The repaired catalogue aggregates have values for most of the modelling population:

| Feature | Orders with a value | Of 15,843 |
|---|---:|---:|
| total_product_weight_g | 14,724 | 92.9% |
| total_product_volume_cm3 | 14,510 | 91.6% |
| avg_product_photos_qty | 14,505 | 91.6% |

Weight has a steady relationship with late delivery across quintiles:

| Weight quintile | Orders | Late rate |
|---|---:|---:|
| up to 250 g | 3,089 | 5.54% |
| 250 to 517 g | 2,806 | 6.41% |
| 517 to 1,150 g | 2,984 | 6.64% |
| 1,150 to 2,850 g | 2,919 | 7.02% |
| above 2,850 g | 2,926 | 7.96% |

Missing catalogue values have two separate causes. In 740 orders, at least one product is absent from the catalogue. In other orders, the product is present but its measurements are missing: 379 orders have no weight, 593 have no dimensions, and 748 have no photo count.

A total of 90.2% of modelling rows contain only one item.

**Reasoning.** Weight shows the strongest steadily increasing numeric relationship with lateness in the dataset. There is also a plausible operational explanation: heavier shipments may be handled differently and take longer to move.

Each measurement needs its own missing-value indicator because the causes of missingness are not the same. One shared indicator based only on unmatched products would incorrectly mark orders where the product exists but one or more measurements are absent.

Maximum weight and maximum volume are not included. Because 90.2% of orders contain one item, these maximum values are usually identical to the corresponding totals and add little new information.

**Rule.** Include `total_product_weight_g`, `total_product_volume_cm3` and `avg_product_photos_qty`, each with its own missing-value indicator and a zero fill. Include `distinct_category_count`, which is 0 when none of the items has a known category and does not need an indicator. Exclude maximum weight and maximum volume because they largely duplicate the totals.

---

## 17. Encode product category by minimum support

**Evidence.** After cleaning, there are 73 distinct product categories in the modelling data, and 1,280 orders have no known category. Many categories are rare: 41 appear in fewer than 50 orders each.

A minimum of 250 orders retains 19 categories, which cover 79.7% of the rows. This cutoff falls on a stable boundary: thresholds of 200 and 250 both retain the same 19 categories.

Among the retained categories, late rates range from 5.42% to 9.68%, compared with the overall rate of 6.69%.

**Reasoning.** There are 1,060 late orders in the positive class. Encoding all 73 categories would leave roughly 8 positive examples per predictor, below the conventional guideline of about 10. Retaining 19 categories gives roughly 15 positive examples per category feature.

A minimum-support rule is clearer than simply taking the top N categories. It specifies how much data a category must have to earn its own column, and it remains meaningful if the dataset changes. The pipeline applies the rule when it builds the feature table instead of hard-coding today's list of categories.

Target encoding was rejected because it replaces each category with its observed late rate, using the label to construct a predictor. With only 1,060 late orders spread across 73 categories, that would create a substantial risk of leakage.

Low-support categories are not dropped. They share an explicit `other` column, while orders with no known category use an `unknown` column. This keeps every order represented and ensures the category block sums to one.

**Rule.** At build time, create a one-hot column for each category with at least 250 orders. Add `product_category_other` for known categories below the threshold and `product_category_unknown` for orders without a known category. The columns in this block must sum to exactly 1 for every row, and each retained category must meet the minimum count in the output.

---

## 18. Derive shipment origin at item level

**Evidence.** Comparing each seller's state with the customer's state gives three groups:

| Shipment origin | Orders | Late rate |
|---|---:|---:|
| All items from the customer's own state | 4,428 | 4.74% |
| At least one item from another state | 9,933 | 7.60% |
| No item with a known seller state | 1,482 | 6.41% |

The difference is not explained only by the mix of customer states. Within the individual customer states, cross-state orders have a higher late rate in 4 of the 5 states with enough data in both groups. The median difference is 2.2 percentage points. In RJ, the rates are 4.32% for same-state shipping and 12.05% for cross-state shipping.

There are 27 orders with items from both the customer's state and other states.

**Reasoning.** This is the largest single difference in the dataset, larger than the differences between states in Task 3. Shipping distance is one plausible explanation.

The feature must be calculated before items are grouped into orders. An order can contain items from sellers in several states, so once the item-level information has been aggregated, it is no longer possible to reliably determine whether all items came from the customer's state.

Two columns represent the three groups without adding a redundant feature: same-state shipping is `(1, 0)`, cross-state shipping is `(0, 0)`, and unknown origin is `(0, 1)`. Adding a third indicator would make the block redundant with an intercept.

The 27 mixed-origin orders are grouped with cross-state shipping. There are too few to estimate them separately, and each order includes at least one shipment from outside the customer's state.

`seller_state_unknown` is included so those orders can be represented correctly, not because unknown origin has been shown to predict lateness. Its late rate of 6.41% is close to the overall rate of 6.69%. The indicator keeps 1,482 orders in the dataset without treating them as cross-state shipments by default.

**Rule.** Include `shipped_from_customer_state`, set to 1 when at least one item's seller state is known and every known seller state matches the customer's state. Include `seller_state_unknown`, set to 1 when no item's seller state is known. An order must never have both indicators set to 1.

---

## 19. Remove every external binary dependency

**Evidence.** An earlier version depended on two command-line programs that are not Python packages: `sqlite3`, which executed every SQL script, and `/usr/bin/time`, which measured peak memory for each stage.

Neither program could be installed through `requirements.txt`. On a machine without `sqlite3`, twelve consecutive pipeline stages failed because Task 1 uses it to build the data that every later stage depends on.

Both dependencies have now been replaced with Python's standard library:

- `src/common/run_sql_script.py` executes SQL through Python's `sqlite3` module. It handles the `.bail`, `.headers` and `.mode` directives used in the scripts, splits statements with `sqlite3.complete_statement` instead of splitting on semicolons, and reproduces the command-line tool's column-aligned output. Its output was compared byte for byte with the evidence files generated by the original command-line tool; all three scripts match exactly.
- Peak memory is measured with `os.wait4`, which returns resource usage for a specific child process. This also removes two platform-specific regular expressions that previously parsed the output of `time -l` and `time -v`.

The full pipeline has now run successfully on a machine without either external program: all 21 stages passed. `task5_environment.csv` records `external_binaries_required = none` as a value generated by the pipeline, rather than relying on a statement in the documentation.

**Reasoning.** The assignment asks whether another person can reproduce the pipeline with one command. Requiring a program that cannot be installed through `requirements.txt` creates a direct obstacle to reproducing the work. Its absence had already stopped the pipeline at Task 1 and caused later stages to fail as well.

Both dependencies were avoidable. Python already includes the SQLite engine, and its standard library can report resource usage for a child process. The external programs duplicated functionality available in Python.

One platform limitation remains: `os.wait4` and the `resource` module are POSIX interfaces, so the pipeline assumes a Unix-like operating system.

**Rule.** Depend only on Python, a POSIX operating system and the packages pinned in `requirements.txt`. Execute SQL through `run_sql_script.py`, not an external SQL client, and use the standard library to measure process resources instead of an external timing program.

**Evidence file.** `outputs/evidence/task5_environment.csv`

---

## 20. Measure resources with two independent passes

**Evidence.** The profiler runs the data-building stages twice, using separate temporary copies of the repository. The first pass provides the estimate and the second provides the measurement. The comparison records runtime, peak memory, temporary storage, saved storage and intermediate storage for each stage.

The temporary copies exclude `marketplace.sqlite`, `outputs/`, `.git/` and Python cache files. This keeps the canonical inputs and outputs untouched. Only the comparison CSV is written back to the main repository.

**Reasoning.** The assignment asks how estimated and measured resource needs compare at each stage. A theoretical estimate would not meet the evidence standard used elsewhere in the pipeline. Instead, one clean empirical run serves as the estimate for a second run on the same machine.

Profiling requires clean rebuilds. Running them in the main repository would overwrite or delete the outputs already produced by the pipeline, so each pass runs in its own temporary workspace.

The five resource measures are reported separately because each represents a different constraint. Combining them into one number would hide important differences. For example, temporary storage is zero for every stage except the benchmark.

Temporary storage is sampled every 5 milliseconds rather than monitored continuously. A file created and deleted between samples could be missed, so the recorded peak is the highest value observed during sampling.

**Rule.** Use two separate clean passes. Run profiling in temporary copies and never modify the canonical outputs. Report each resource measure separately, and describe temporary storage as a sampled peak.

**Evidence file.** `outputs/evidence/task5_pipeline_resource_comparison.csv`

---

## What the pipeline guarantees

The pipeline checks each item below on every run and stops if a check fails.

- All 20,000 source orders appear exactly once in the order-level table, with no duplicates or extra orders.
- Item, payment and review row counts match the source.
- The original monetary totals match the source exactly: 54,446,205.77 for item prices and 10,515,059.68 for freight.
- Repaired totals reconcile with the recorded corrections, and no unflagged row has changed.
- Every ineligible order has at least one exclusion reason, and no eligible order has one.
- The feature table has 15,843 rows and 73 numerical columns, contains no missing values, and aligns row by row with the ID and label files.
- All 107 feature checks pass; each engineered feature is recalculated from the source data.
- No forbidden column appears in the feature matrix.