-- Task 1 - Validate record, count and total preservation in the order-level build

.bail on
.headers on
.mode column

ATTACH DATABASE 'outputs/intermediate/items_clean.sqlite' AS items;
ATTACH DATABASE 'outputs/intermediate/catalogue_clean.sqlite' AS catalogue;
ATTACH DATABASE 'outputs/intermediate/order_level.sqlite' AS derived;

SELECT
    'source_orders' AS check_name,
    COUNT(*) AS value
FROM orders

UNION ALL

SELECT
    'derived_order_level_rows',
    COUNT(*)
FROM derived.order_level

UNION ALL

SELECT
    'derived_distinct_order_ids',
    COUNT(DISTINCT order_id)
FROM derived.order_level;


SELECT
    COUNT(*) AS source_orders_missing_from_derived
FROM orders AS o
LEFT JOIN derived.order_level AS d
    ON d.order_id = o.order_id
WHERE d.order_id IS NULL;


SELECT
    COUNT(*) AS derived_orders_missing_from_source
FROM derived.order_level AS d
LEFT JOIN orders AS o
    ON o.order_id = d.order_id
WHERE o.order_id IS NULL;


SELECT
    COUNT(*) AS duplicate_order_ids
FROM (
    SELECT
        order_id
    FROM derived.order_level
    GROUP BY order_id
    HAVING COUNT(*) > 1
);


SELECT
    (SELECT COUNT(*) FROM order_items) AS source_item_rows,
    (SELECT COUNT(*) FROM items.order_items_clean) AS repaired_item_rows,
    (SELECT SUM(item_count) FROM derived.order_level) AS derived_item_rows;


SELECT
    (SELECT COUNT(DISTINCT order_id) FROM order_items) AS source_orders_with_items,
    (
        SELECT COUNT(*)
        FROM derived.order_level
        WHERE item_count > 0
    ) AS derived_orders_with_items;


SELECT
    COUNT(*) AS repaired_item_rows_missing_from_source
FROM items.order_items_clean AS i
LEFT JOIN order_items AS s
    ON s.order_id = i.order_id
   AND s.order_item_id = i.order_item_id
WHERE s.order_id IS NULL;


SELECT
    SUM(CASE WHEN i.price_raw IS NOT s.price THEN 1 ELSE 0 END)
        AS item_rows_with_altered_raw_price,
    SUM(CASE WHEN i.freight_value_raw IS NOT s.freight_value THEN 1 ELSE 0 END)
        AS item_rows_with_altered_raw_freight
FROM items.order_items_clean AS i
JOIN order_items AS s
    ON s.order_id = i.order_id
   AND s.order_item_id = i.order_item_id;


SELECT
    COUNT(*) AS unflagged_item_rows_with_changed_price
FROM items.order_items_clean
WHERE price_defect IS NULL
  AND price IS NOT price_raw;


SELECT
    COUNT(*) AS unflagged_item_rows_with_changed_freight
FROM items.order_items_clean
WHERE freight_value_defect IS NULL
  AND freight_value IS NOT freight_value_raw;


SELECT
    ROUND((SELECT SUM(price) FROM order_items), 2) AS source_item_price_total,
    ROUND((SELECT SUM(price_raw) FROM items.order_items_clean), 2) AS repaired_table_raw_price_total,
    ROUND((SELECT SUM(total_item_price_raw) FROM derived.order_level), 2) AS derived_raw_price_total;


SELECT
    ROUND((SELECT SUM(freight_value) FROM order_items), 2) AS source_freight_total,
    ROUND((SELECT SUM(freight_value_raw) FROM items.order_items_clean), 2) AS repaired_table_raw_freight_total,
    ROUND((SELECT SUM(total_freight_value_raw) FROM derived.order_level), 2) AS derived_raw_freight_total;


SELECT
    ROUND(
        (
            SELECT SUM(i.price)
            FROM items.order_items_clean AS i
            JOIN derived.order_level AS d
                ON d.order_id = i.order_id
            WHERE d.items_with_missing_price = 0
        ),
        2
    ) AS item_level_repaired_price_total,
    ROUND(
        (
            SELECT SUM(total_item_price)
            FROM derived.order_level
            WHERE items_with_missing_price = 0
        ),
        2
    ) AS order_level_repaired_price_total;


SELECT
    ROUND(
        (
            SELECT SUM(i.freight_value)
            FROM items.order_items_clean AS i
            JOIN derived.order_level AS d
                ON d.order_id = i.order_id
            WHERE d.items_with_missing_freight = 0
        ),
        2
    ) AS item_level_repaired_freight_total,
    ROUND(
        (
            SELECT SUM(total_freight_value)
            FROM derived.order_level
            WHERE items_with_missing_freight = 0
        ),
        2
    ) AS order_level_repaired_freight_total;


SELECT
    (
        SELECT COUNT(*)
        FROM items.order_items_clean
        WHERE price_defect IN ('scaled', 'negated')
           OR freight_value_defect IN ('scaled', 'negated')
    ) AS item_level_repairs,
    (SELECT SUM(items_repaired) FROM derived.order_level) AS derived_repairs;


SELECT
    (
        SELECT COUNT(*)
        FROM items.order_items_clean
        WHERE price_defect = 'missing'
    ) AS item_level_missing_price_rows,
    (SELECT SUM(items_with_missing_price) FROM derived.order_level) AS derived_missing_price_rows,
    (
        SELECT COUNT(*)
        FROM items.order_items_clean
        WHERE freight_value_defect = 'missing'
    ) AS item_level_missing_freight_rows,
    (SELECT SUM(items_with_missing_freight) FROM derived.order_level) AS derived_missing_freight_rows;


SELECT
    COUNT(*) AS orders_with_inconsistent_price_total_nullability
FROM derived.order_level
WHERE (items_with_missing_price > 0 AND total_item_price IS NOT NULL)
   OR (items_with_missing_price = 0 AND item_count > 0 AND total_item_price IS NULL);


SELECT
    COUNT(*) AS orders_with_inconsistent_freight_total_nullability
FROM derived.order_level
WHERE (items_with_missing_freight > 0 AND total_freight_value IS NOT NULL)
   OR (items_with_missing_freight = 0 AND item_count > 0 AND total_freight_value IS NULL);


SELECT
    COUNT(*) AS orders_with_negative_repaired_totals
FROM derived.order_level
WHERE total_item_price < 0
   OR total_freight_value < 0;


SELECT
    (SELECT COUNT(*) FROM products) AS source_product_rows,
    (SELECT COUNT(*) FROM catalogue.products_clean) AS cleaned_product_rows,
    (SELECT COUNT(*) FROM sellers) AS source_seller_rows,
    (SELECT COUNT(*) FROM catalogue.sellers_clean) AS cleaned_seller_rows;


SELECT
    SUM(CASE WHEN p.product_weight_g_raw IS NOT s.product_weight_g THEN 1 ELSE 0 END)
        AS product_rows_with_altered_raw_weight,
    SUM(CASE WHEN p.product_length_cm_raw IS NOT s.product_length_cm THEN 1 ELSE 0 END)
        AS product_rows_with_altered_raw_length,
    SUM(CASE WHEN p.product_category_name_raw IS NOT s.product_category_name THEN 1 ELSE 0 END)
        AS product_rows_with_altered_raw_category
FROM catalogue.products_clean AS p
JOIN products AS s
    ON s.product_id = p.product_id;


SELECT
    COUNT(*) AS unflagged_product_rows_with_changed_weight
FROM catalogue.products_clean
WHERE product_weight_g_defect IS NULL
  AND product_weight_g IS NOT product_weight_g_raw;


SELECT
    COUNT(*) AS products_with_negative_repaired_measurements
FROM catalogue.products_clean
WHERE product_weight_g < 0
   OR product_length_cm < 0
   OR product_height_cm < 0
   OR product_width_cm < 0;


SELECT
    COUNT(*) AS products_with_surviving_missing_sentinel
FROM catalogue.products_clean
WHERE product_name_lenght = -1
   OR product_description_lenght = -1
   OR product_photos_qty = -1;


SELECT
    COUNT(*) AS sellers_with_unnormalized_state
FROM catalogue.sellers_clean
WHERE seller_state IS NOT NULL
  AND seller_state <> TRIM(UPPER(seller_state));


SELECT
    (
        SELECT COUNT(*)
        FROM items.order_items_clean AS i
        LEFT JOIN catalogue.products_clean AS p
            ON p.product_id = i.product_id
        WHERE p.product_id IS NULL
    ) AS item_level_orphan_product_rows,
    (SELECT SUM(items_with_missing_product_reference) FROM derived.order_level)
        AS derived_orphan_product_rows,
    (
        SELECT COUNT(*)
        FROM items.order_items_clean AS i
        LEFT JOIN catalogue.sellers_clean AS s
            ON s.seller_id = i.seller_id
        WHERE s.seller_id IS NULL
    ) AS item_level_orphan_seller_rows,
    (SELECT SUM(items_with_missing_seller_reference) FROM derived.order_level)
        AS derived_orphan_seller_rows;


SELECT
    COUNT(*) AS orders_with_inconsistent_weight_total_nullability
FROM derived.order_level
WHERE (items_with_missing_weight > 0 AND total_product_weight_g IS NOT NULL)
   OR (items_with_missing_weight = 0 AND item_count > 0 AND total_product_weight_g IS NULL);


SELECT
    COUNT(*) AS orders_with_inconsistent_volume_total_nullability
FROM derived.order_level
WHERE (items_with_missing_volume > 0 AND total_product_volume_cm3 IS NOT NULL)
   OR (items_with_missing_volume = 0 AND item_count > 0 AND total_product_volume_cm3 IS NULL);


SELECT
    COUNT(*) AS orders_with_negative_catalogue_aggregates
FROM derived.order_level
WHERE total_product_weight_g < 0
   OR total_product_volume_cm3 < 0
   OR max_product_weight_g < 0
   OR max_product_volume_cm3 < 0;


SELECT
    COUNT(*) AS orders_with_impossible_seller_state_counts
FROM derived.order_level
WHERE items_from_customer_state > items_with_known_seller_state
   OR items_with_known_seller_state > item_count
   OR items_with_missing_product_reference > item_count
   OR items_with_missing_seller_reference > item_count;


SELECT
    COUNT(*) AS orders_with_impossible_category_counts
FROM derived.order_level
WHERE distinct_category_count > item_count
   OR distinct_seller_state_count > item_count;


SELECT
    COUNT(*) AS orders_with_primary_catalogue_values_but_no_items
FROM derived.order_level
WHERE item_count = 0
  AND (primary_product_category IS NOT NULL OR primary_seller_state IS NOT NULL);


SELECT
    COUNT(*) AS orders_claiming_same_state_without_customer_state
FROM derived.order_level
WHERE items_from_customer_state > 0
  AND customer_state IS NULL;


SELECT
    (SELECT COUNT(*) FROM order_payments) AS source_payment_rows,
    (SELECT SUM(payment_row_count) FROM derived.order_level) AS derived_payment_rows;


SELECT
    (SELECT COUNT(DISTINCT order_id) FROM order_payments) AS source_orders_with_payments,
    (
        SELECT COUNT(*)
        FROM derived.order_level
        WHERE payment_row_count > 0
    ) AS derived_orders_with_payments;


SELECT
    ROUND((SELECT SUM(payment_value) FROM order_payments), 2) AS source_payment_total,
    ROUND((SELECT SUM(total_payment_value) FROM derived.order_level), 2) AS derived_payment_total;


SELECT
    (SELECT COUNT(*) FROM order_reviews) AS source_review_rows,
    (SELECT SUM(review_count) FROM derived.order_level) AS derived_review_rows;


SELECT
    (SELECT COUNT(DISTINCT order_id) FROM order_reviews) AS source_orders_with_reviews,
    (
        SELECT COUNT(*)
        FROM derived.order_level
        WHERE review_count > 0
    ) AS derived_orders_with_reviews;


SELECT
    COUNT(*) AS source_orders_with_missing_customer_reference
FROM orders AS o
LEFT JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;


SELECT
    COUNT(*) AS derived_orders_with_missing_customer_attributes
FROM derived.order_level
WHERE customer_unique_id IS NULL
  AND customer_zip_code_prefix IS NULL
  AND customer_city IS NULL
  AND customer_state IS NULL;


SELECT
    COUNT(*) AS orders_with_zero_items
FROM derived.order_level
WHERE item_count = 0;


SELECT
    COUNT(*) AS orders_with_zero_payments
FROM derived.order_level
WHERE payment_row_count = 0;


SELECT
    COUNT(*) AS orders_with_zero_reviews
FROM derived.order_level
WHERE review_count = 0;


DETACH DATABASE derived;
DETACH DATABASE catalogue;
DETACH DATABASE items;