.bail on
.headers on
.mode column

ATTACH DATABASE 'outputs/intermediate/order_level_clean.sqlite' AS clean;

SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT order_id) AS distinct_orders
FROM clean.order_level_clean;


SELECT
    COUNT(*) AS duplicate_order_ids
FROM (
    SELECT order_id
    FROM clean.order_level_clean
    GROUP BY order_id
    HAVING COUNT(*) > 1
);


SELECT
    COUNT(*) AS source_orders_missing_from_clean
FROM orders AS o
LEFT JOIN clean.order_level_clean AS c
    ON c.order_id = o.order_id
WHERE c.order_id IS NULL;


SELECT
    COUNT(*) AS clean_orders_missing_from_source
FROM clean.order_level_clean AS c
LEFT JOIN orders AS o
    ON o.order_id = c.order_id
WHERE o.order_id IS NULL;


SELECT
    COUNT(*) AS invalid_normalized_status_values
FROM clean.order_level_clean
WHERE order_status IS NOT NULL
  AND (
      order_status != LOWER(order_status)
      OR order_status != TRIM(order_status)
  );


SELECT
    COUNT(*) AS invalid_normalized_state_values
FROM clean.order_level_clean
WHERE customer_state IS NOT NULL
  AND (
      customer_state != UPPER(customer_state)
      OR customer_state != TRIM(customer_state)
  );


SELECT
    COUNT(*) AS eligible_rows_with_invalid_label
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND delivered_after_estimate NOT IN (0, 1);


SELECT
    COUNT(*) AS eligible_rows_with_null_label
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND delivered_after_estimate IS NULL;


SELECT
    COUNT(*) AS ineligible_rows_with_non_null_label
FROM clean.order_level_clean
WHERE delivery_label_eligible = 0
  AND delivered_after_estimate IS NOT NULL;


SELECT
    COUNT(*) AS ineligible_rows_without_reason
FROM clean.order_level_clean
WHERE delivery_label_eligible = 0
  AND (
      delivery_label_exclusion_reasons IS NULL
      OR TRIM(delivery_label_exclusion_reasons) = ''
  );


SELECT
    COUNT(*) AS eligible_rows_with_exclusion_reason
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND delivery_label_exclusion_reasons IS NOT NULL;


SELECT
    COUNT(*) AS eligible_rows_not_delivered
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND order_status != 'delivered';


SELECT
    COUNT(*) AS eligible_rows_missing_required_timestamp
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND (
      order_purchase_timestamp IS NULL
      OR order_approved_at IS NULL
      OR order_delivered_customer_date IS NULL
      OR order_estimated_delivery_date IS NULL
  );


SELECT
    COUNT(*) AS eligible_rows_with_invalid_chronology
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND (
      order_approved_at < order_purchase_timestamp
      OR order_delivered_customer_date < order_purchase_timestamp
      OR order_delivered_customer_date < order_approved_at
      OR order_estimated_delivery_date < order_purchase_timestamp
      OR order_estimated_delivery_date < order_approved_at
  );


SELECT
    COUNT(*) AS label_mismatches
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND delivered_after_estimate !=
      CASE
          WHEN DATE(order_delivered_customer_date)
               > DATE(order_estimated_delivery_date)
          THEN 1
          ELSE 0
      END;


SELECT
    COUNT(*) AS eligible_orders_with_missing_optional_customer_state
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND customer_state IS NULL;


SELECT
    COUNT(*) AS eligible_orders_with_missing_review_score
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND avg_review_score IS NULL;


SELECT
    COUNT(*) AS eligible_orders_with_missing_item_total
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND total_item_price IS NULL;


SELECT
    COUNT(*) AS eligible_orders_with_missing_payment_total
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
  AND total_payment_value IS NULL;


SELECT
    delivery_label_eligible,
    COUNT(*) AS order_count
FROM clean.order_level_clean
GROUP BY delivery_label_eligible
ORDER BY delivery_label_eligible DESC;


SELECT
    delivered_after_estimate,
    COUNT(*) AS order_count
FROM clean.order_level_clean
WHERE delivery_label_eligible = 1
GROUP BY delivered_after_estimate
ORDER BY delivered_after_estimate;


DETACH DATABASE clean;