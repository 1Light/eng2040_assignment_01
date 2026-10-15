-- Task 1 - Assemble one row per order from repaired item, catalogue, payment and review data

.bail on

ATTACH DATABASE 'outputs/intermediate/items_clean.sqlite' AS items;
ATTACH DATABASE 'outputs/intermediate/catalogue_clean.sqlite' AS catalogue;
ATTACH DATABASE 'outputs/intermediate/order_level.sqlite' AS derived;

BEGIN TRANSACTION;

DROP TABLE IF EXISTS derived.order_level;

CREATE TABLE derived.order_level (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_status TEXT,
    order_purchase_timestamp TEXT,
    order_approved_at TEXT,
    order_delivered_carrier_date TEXT,
    order_delivered_customer_date TEXT,
    order_estimated_delivery_date TEXT,

    customer_unique_id TEXT,
    customer_zip_code_prefix TEXT,
    customer_city TEXT,
    customer_state TEXT,

    item_count INTEGER NOT NULL,
    distinct_product_count INTEGER NOT NULL,
    distinct_seller_count INTEGER NOT NULL,
    total_item_price REAL,
    total_freight_value REAL,
    total_item_price_raw REAL,
    total_freight_value_raw REAL,
    items_with_missing_price INTEGER NOT NULL,
    items_with_missing_freight INTEGER NOT NULL,
    items_repaired INTEGER NOT NULL,

    total_product_weight_g REAL,
    max_product_weight_g REAL,
    total_product_volume_cm3 REAL,
    max_product_volume_cm3 REAL,
    avg_product_photos_qty REAL,
    items_with_missing_product_reference INTEGER NOT NULL,
    items_with_missing_weight INTEGER NOT NULL,
    items_with_missing_volume INTEGER NOT NULL,
    distinct_category_count INTEGER NOT NULL,
    primary_product_category TEXT,
    primary_product_category_english TEXT,

    items_with_missing_seller_reference INTEGER NOT NULL,
    distinct_seller_state_count INTEGER NOT NULL,
    primary_seller_state TEXT,
    items_from_customer_state INTEGER NOT NULL,
    items_with_known_seller_state INTEGER NOT NULL,

    payment_row_count INTEGER NOT NULL,
    payment_type_count INTEGER NOT NULL,
    total_payment_value INTEGER,
    max_payment_installments INTEGER,

    review_count INTEGER NOT NULL,
    avg_review_score REAL,
    min_review_score INTEGER,
    max_review_score INTEGER
);

INSERT INTO derived.order_level
WITH item_catalogue AS (
    SELECT
        i.order_id,
        i.order_item_id,
        i.product_id,
        i.seller_id,
        i.price,
        i.freight_value,
        i.price_raw,
        i.freight_value_raw,
        i.price_defect,
        i.freight_value_defect,
        p.product_id AS matched_product_id,
        p.product_weight_g,
        p.product_volume_cm3,
        p.product_photos_qty,
        p.product_category_name,
        p.product_category_name_english,
        s.seller_id AS matched_seller_id,
        s.seller_state,
        s.seller_state_valid,
        cu.customer_state AS order_customer_state
    FROM items.order_items_clean AS i
    LEFT JOIN catalogue.products_clean AS p
        ON p.product_id = i.product_id
    LEFT JOIN catalogue.sellers_clean AS s
        ON s.seller_id = i.seller_id
    LEFT JOIN orders AS o
        ON o.order_id = i.order_id
    LEFT JOIN customers AS cu
        ON cu.customer_id = o.customer_id
),
primary_item AS (
    SELECT
        order_id,
        product_category_name,
        product_category_name_english,
        seller_state
    FROM (
        SELECT
            order_id,
            product_category_name,
            product_category_name_english,
            seller_state,
            ROW_NUMBER() OVER (
                PARTITION BY order_id
                ORDER BY order_item_id
            ) AS item_rank
        FROM item_catalogue
    )
    WHERE item_rank = 1
),
item_order_agg AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        COUNT(DISTINCT product_id) AS distinct_product_count,
        COUNT(DISTINCT seller_id) AS distinct_seller_count,
        SUM(CASE WHEN price IS NULL THEN 1 ELSE 0 END) AS items_with_missing_price,
        SUM(CASE WHEN freight_value IS NULL THEN 1 ELSE 0 END) AS items_with_missing_freight,
        SUM(
            CASE
                WHEN price_defect IN ('scaled', 'negated') THEN 1
                ELSE 0
            END
            +
            CASE
                WHEN freight_value_defect IN ('scaled', 'negated') THEN 1
                ELSE 0
            END
        ) AS items_repaired,
        CASE
            WHEN SUM(CASE WHEN price IS NULL THEN 1 ELSE 0 END) > 0 THEN NULL
            ELSE SUM(price)
        END AS total_item_price,
        CASE
            WHEN SUM(CASE WHEN freight_value IS NULL THEN 1 ELSE 0 END) > 0 THEN NULL
            ELSE SUM(freight_value)
        END AS total_freight_value,
        SUM(price_raw) AS total_item_price_raw,
        SUM(freight_value_raw) AS total_freight_value_raw,

        CASE
            WHEN SUM(CASE WHEN product_weight_g IS NULL THEN 1 ELSE 0 END) > 0 THEN NULL
            ELSE SUM(product_weight_g)
        END AS total_product_weight_g,
        MAX(product_weight_g) AS max_product_weight_g,
        CASE
            WHEN SUM(CASE WHEN product_volume_cm3 IS NULL THEN 1 ELSE 0 END) > 0 THEN NULL
            ELSE SUM(product_volume_cm3)
        END AS total_product_volume_cm3,
        MAX(product_volume_cm3) AS max_product_volume_cm3,
        AVG(product_photos_qty) AS avg_product_photos_qty,
        SUM(CASE WHEN matched_product_id IS NULL THEN 1 ELSE 0 END)
            AS items_with_missing_product_reference,
        SUM(CASE WHEN product_weight_g IS NULL THEN 1 ELSE 0 END)
            AS items_with_missing_weight,
        SUM(CASE WHEN product_volume_cm3 IS NULL THEN 1 ELSE 0 END)
            AS items_with_missing_volume,
        COUNT(DISTINCT product_category_name) AS distinct_category_count,

        SUM(CASE WHEN matched_seller_id IS NULL THEN 1 ELSE 0 END)
            AS items_with_missing_seller_reference,
        COUNT(DISTINCT CASE WHEN seller_state_valid = 1 THEN seller_state END)
            AS distinct_seller_state_count,
        SUM(
            CASE
                WHEN seller_state_valid = 1
                     AND seller_state = order_customer_state
                THEN 1
                ELSE 0
            END
        ) AS items_from_customer_state,
        SUM(CASE WHEN seller_state_valid = 1 THEN 1 ELSE 0 END)
            AS items_with_known_seller_state
    FROM item_catalogue
    GROUP BY order_id
),
payment_order_agg AS (
    SELECT
        order_id,
        COUNT(*) AS payment_row_count,
        COUNT(DISTINCT payment_type) AS payment_type_count,
        SUM(payment_value) AS total_payment_value,
        MAX(payment_installments) AS max_payment_installments
    FROM order_payments
    GROUP BY order_id
),
review_order_agg AS (
    SELECT
        order_id,
        COUNT(*) AS review_count,
        AVG(review_score) AS avg_review_score,
        MIN(review_score) AS min_review_score,
        MAX(review_score) AS max_review_score
    FROM order_reviews
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    c.customer_unique_id,
    c.customer_zip_code_prefix,
    c.customer_city,
    c.customer_state,

    COALESCE(i.item_count, 0),
    COALESCE(i.distinct_product_count, 0),
    COALESCE(i.distinct_seller_count, 0),
    i.total_item_price,
    i.total_freight_value,
    i.total_item_price_raw,
    i.total_freight_value_raw,
    COALESCE(i.items_with_missing_price, 0),
    COALESCE(i.items_with_missing_freight, 0),
    COALESCE(i.items_repaired, 0),

    i.total_product_weight_g,
    i.max_product_weight_g,
    i.total_product_volume_cm3,
    i.max_product_volume_cm3,
    i.avg_product_photos_qty,
    COALESCE(i.items_with_missing_product_reference, 0),
    COALESCE(i.items_with_missing_weight, 0),
    COALESCE(i.items_with_missing_volume, 0),
    COALESCE(i.distinct_category_count, 0),
    pi.product_category_name,
    pi.product_category_name_english,

    COALESCE(i.items_with_missing_seller_reference, 0),
    COALESCE(i.distinct_seller_state_count, 0),
    pi.seller_state,
    COALESCE(i.items_from_customer_state, 0),
    COALESCE(i.items_with_known_seller_state, 0),

    COALESCE(p.payment_row_count, 0),
    COALESCE(p.payment_type_count, 0),
    p.total_payment_value,
    p.max_payment_installments,

    COALESCE(r.review_count, 0),
    r.avg_review_score,
    r.min_review_score,
    r.max_review_score
FROM orders AS o
LEFT JOIN customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN item_order_agg AS i
    ON i.order_id = o.order_id
LEFT JOIN primary_item AS pi
    ON pi.order_id = o.order_id
LEFT JOIN payment_order_agg AS p
    ON p.order_id = o.order_id
LEFT JOIN review_order_agg AS r
    ON r.order_id = o.order_id;

COMMIT;

DETACH DATABASE derived;
DETACH DATABASE catalogue;
DETACH DATABASE items;