.bail on
.headers on
.mode column

ATTACH DATABASE 'outputs/intermediate/order_level.sqlite' AS derived;

SELECT
    COUNT(*) AS total_orders,
    SUM(order_id IS NULL) AS missing_order_id,
    SUM(customer_id IS NULL) AS missing_customer_id,
    SUM(order_status IS NULL) AS missing_order_status,
    SUM(order_purchase_timestamp IS NULL) AS missing_purchase_timestamp,
    SUM(order_approved_at IS NULL) AS missing_approved_timestamp,
    SUM(order_delivered_carrier_date IS NULL) AS missing_carrier_timestamp,
    SUM(order_delivered_customer_date IS NULL) AS missing_customer_delivery_timestamp,
    SUM(order_estimated_delivery_date IS NULL) AS missing_estimated_delivery_timestamp,
    SUM(customer_unique_id IS NULL) AS missing_customer_unique_id,
    SUM(customer_state IS NULL) AS missing_customer_state,
    SUM(total_item_price IS NULL) AS missing_item_total,
    SUM(total_freight_value IS NULL) AS missing_freight_total,
    SUM(total_payment_value IS NULL) AS missing_payment_total,
    SUM(avg_review_score IS NULL) AS missing_review_score
FROM derived.order_level;


SELECT
    order_status AS raw_status,
    LOWER(TRIM(order_status)) AS normalized_status,
    COUNT(*) AS order_count
FROM derived.order_level
GROUP BY order_status
ORDER BY normalized_status, order_count DESC;


SELECT
    customer_state AS raw_state,
    UPPER(TRIM(customer_state)) AS normalized_state,
    COUNT(*) AS order_count
FROM derived.order_level
GROUP BY customer_state
ORDER BY normalized_state, order_count DESC;


SELECT
    SUM(
        CASE
            WHEN order_purchase_timestamp IS NOT NULL
             AND order_approved_at IS NOT NULL
             AND order_approved_at < order_purchase_timestamp
            THEN 1 ELSE 0
        END
    ) AS approval_before_purchase,

    SUM(
        CASE
            WHEN order_approved_at IS NOT NULL
             AND order_delivered_carrier_date IS NOT NULL
             AND order_delivered_carrier_date < order_approved_at
            THEN 1 ELSE 0
        END
    ) AS carrier_before_approval,

    SUM(
        CASE
            WHEN order_delivered_carrier_date IS NOT NULL
             AND order_delivered_customer_date IS NOT NULL
             AND order_delivered_customer_date < order_delivered_carrier_date
            THEN 1 ELSE 0
        END
    ) AS delivery_before_carrier,

    SUM(
        CASE
            WHEN order_purchase_timestamp IS NOT NULL
             AND order_delivered_customer_date IS NOT NULL
             AND order_delivered_customer_date < order_purchase_timestamp
            THEN 1 ELSE 0
        END
    ) AS delivery_before_purchase
FROM derived.order_level;


SELECT
    SUM(total_item_price < 0) AS negative_item_total,
    SUM(total_freight_value < 0) AS negative_freight_total,
    SUM(total_payment_value < 0) AS negative_payment_total,
    MIN(total_item_price) AS min_item_total,
    MAX(total_item_price) AS max_item_total,
    MIN(total_freight_value) AS min_freight_total,
    MAX(total_freight_value) AS max_freight_total,
    MIN(total_payment_value) AS min_payment_total,
    MAX(total_payment_value) AS max_payment_total
FROM derived.order_level;


SELECT
    SUM(item_count = 0) AS orders_without_items,
    SUM(payment_row_count = 0) AS orders_without_payments,
    SUM(review_count = 0) AS orders_without_reviews,
    SUM(
        customer_unique_id IS NULL
        AND customer_zip_code_prefix IS NULL
        AND customer_city IS NULL
        AND customer_state IS NULL
    ) AS orders_with_missing_customer_reference
FROM derived.order_level;


SELECT
    COUNT(*) AS item_rows,
    SUM(price IS NULL) AS missing_price,
    SUM(price < 0) AS negative_price,
    SUM(freight_value IS NULL) AS missing_freight,
    SUM(freight_value < 0) AS negative_freight
FROM order_items;


SELECT
    COUNT(*) AS payment_rows,
    SUM(payment_value IS NULL) AS missing_payment_value,
    SUM(payment_value < 0) AS negative_payment_value,
    SUM(payment_installments IS NULL) AS missing_installments,
    SUM(payment_installments < 0) AS negative_installments
FROM order_payments;


SELECT
    COUNT(*) AS review_rows,
    SUM(review_score IS NULL) AS missing_review_score,
    SUM(review_score < 1 OR review_score > 5) AS review_score_outside_1_to_5
FROM order_reviews;


SELECT
    COUNT(*) AS orders_with_items_but_no_usable_item_price
FROM (
    SELECT order_id
    FROM order_items
    GROUP BY order_id
    HAVING COUNT(price) = 0
);


SELECT
    COUNT(*) AS orders_with_payments_but_no_usable_payment_value
FROM (
    SELECT order_id
    FROM order_payments
    GROUP BY order_id
    HAVING COUNT(payment_value) = 0
);


SELECT
    COUNT(*) AS orders_with_reviews_but_no_usable_review_score
FROM (
    SELECT order_id
    FROM order_reviews
    GROUP BY order_id
    HAVING COUNT(review_score) = 0
);


SELECT
    LOWER(TRIM(order_status)) AS normalized_status,
    COUNT(*) AS order_count,
    SUM(order_delivered_customer_date IS NULL) AS missing_delivery_timestamp,
    SUM(order_estimated_delivery_date IS NULL) AS missing_estimated_timestamp
FROM derived.order_level
GROUP BY LOWER(TRIM(order_status))
ORDER BY order_count DESC;


DETACH DATABASE derived;