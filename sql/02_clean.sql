-- Clean layer: fixes and flags on top of the raw layer.
--
-- Rule followed everywhere: NO ROW IS DELETED. Problem rows are kept and
-- flagged, so each KPI can decide what to include. The only table that
-- gets smaller is order_reviews, where repeated reviews of the same order
-- are reduced to the most recent one.
--
-- Re-running this file drops and rebuilds the whole clean schema.

DROP SCHEMA IF EXISTS clean CASCADE;
CREATE SCHEMA clean;


-- ---------------------------------------------------------------------
-- categories: Portuguese -> English names.
-- Two categories in the products file have no translation in the source
-- lookup, so they are added by hand here.
-- ---------------------------------------------------------------------
CREATE TABLE clean.categories AS
SELECT product_category_name, product_category_name_english
FROM raw.category_translation
UNION ALL
VALUES
    ('pc_gamer', 'pc_gamer'),
    ('portateis_cozinha_e_preparadores_de_alimentos', 'portable_kitchen_food_preparers');

ALTER TABLE clean.categories ADD PRIMARY KEY (product_category_name);


-- ---------------------------------------------------------------------
-- products: English category name; products with no category become
-- 'unknown'. The misspelled source columns ("lenght") are renamed.
-- LEFT JOIN keeps every product even when it has no category.
-- ---------------------------------------------------------------------
CREATE TABLE clean.products AS
SELECT
    p.product_id,
    COALESCE(c.product_category_name_english, 'unknown') AS category,
    p.product_name_lenght        AS product_name_length,
    p.product_description_lenght AS product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm
FROM raw.products AS p
LEFT JOIN clean.categories AS c
    ON c.product_category_name = p.product_category_name;

ALTER TABLE clean.products ADD PRIMARY KEY (product_id);


-- ---------------------------------------------------------------------
-- customers and sellers: city names in Title Case for display.
-- ---------------------------------------------------------------------
CREATE TABLE clean.customers AS
SELECT
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    INITCAP(customer_city) AS customer_city,
    customer_state
FROM raw.customers;

ALTER TABLE clean.customers ADD PRIMARY KEY (customer_id);
CREATE INDEX idx_customers_unique_id ON clean.customers (customer_unique_id);

CREATE TABLE clean.sellers AS
SELECT
    seller_id,
    seller_zip_code_prefix,
    INITCAP(seller_city) AS seller_city,
    seller_state
FROM raw.sellers;

ALTER TABLE clean.sellers ADD PRIMARY KEY (seller_id);


-- ---------------------------------------------------------------------
-- orders: derived columns and flags.
--
-- in_analysis_window : Jan 2017 to Aug 2018. Months outside this range
--                      have almost no orders and would distort trends.
-- delivery_days / is_late : filled only when the order status is
--                      'delivered' AND a delivery date exists. This drops
--                      delivered orders with no date, and ignores stray
--                      delivery dates on orders that were not delivered.
-- is_late            : compares calendar dates, so an order delivered any
--                      time on its estimated day counts as on time.
-- has_date_issue     : carrier or delivery timestamps out of order.
-- ---------------------------------------------------------------------
CREATE TABLE clean.orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_purchase_timestamp::date AS order_purchase_date,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    (o.order_status = 'delivered')                 AS is_delivered,
    (o.order_status IN ('canceled', 'unavailable')) AS is_canceled,

    EXISTS (
        SELECT 1 FROM raw.order_items AS i WHERE i.order_id = o.order_id
    ) AS has_items,

    (o.order_purchase_timestamp >= DATE '2017-01-01'
     AND o.order_purchase_timestamp < DATE '2018-09-01') AS in_analysis_window,

    CASE
        WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
        THEN ROUND(
            (EXTRACT(EPOCH FROM o.order_delivered_customer_date - o.order_purchase_timestamp) / 86400)::numeric,
            2
        )
    END AS delivery_days,

    CASE
        WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
        THEN o.order_delivered_customer_date::date > o.order_estimated_delivery_date::date
    END AS is_late,

    (COALESCE(o.order_delivered_carrier_date < o.order_purchase_timestamp, FALSE)
     OR COALESCE(o.order_delivered_customer_date < o.order_delivered_carrier_date, FALSE)) AS has_date_issue
FROM raw.orders AS o;

ALTER TABLE clean.orders ADD PRIMARY KEY (order_id);
CREATE INDEX idx_orders_purchase_date ON clean.orders (order_purchase_date);
CREATE INDEX idx_orders_customer_id   ON clean.orders (customer_id);


-- ---------------------------------------------------------------------
-- order_items: item_total = price + freight. This is the revenue amount.
-- ---------------------------------------------------------------------
CREATE TABLE clean.order_items AS
SELECT
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date,
    price,
    freight_value,
    price + freight_value AS item_total
FROM raw.order_items;

ALTER TABLE clean.order_items ADD PRIMARY KEY (order_id, order_item_id);
CREATE INDEX idx_order_items_product_id ON clean.order_items (product_id);
CREATE INDEX idx_order_items_seller_id  ON clean.order_items (seller_id);


-- ---------------------------------------------------------------------
-- order_payments: kept as-is. Revenue is calculated from order items,
-- not from payments, so odd payment rows do not affect any revenue KPI.
-- ---------------------------------------------------------------------
CREATE TABLE clean.order_payments AS
SELECT order_id, payment_sequential, payment_type, payment_installments, payment_value
FROM raw.order_payments;

ALTER TABLE clean.order_payments ADD PRIMARY KEY (order_id, payment_sequential);


-- ---------------------------------------------------------------------
-- order_reviews: exactly one review per order.
-- Some orders were reviewed more than once. ROW_NUMBER() numbers each
-- order's reviews from newest to oldest, and only number 1 is kept.
-- Blank comments become NULL so "has a comment" is easy to test.
-- ---------------------------------------------------------------------
CREATE TABLE clean.order_reviews AS
WITH ranked AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY r.order_id
            ORDER BY r.review_answer_timestamp DESC, r.review_id
        ) AS review_rank
    FROM raw.order_reviews AS r
)
SELECT
    order_id,
    review_id,
    review_score,
    NULLIF(TRIM(review_comment_title), '')   AS review_comment_title,
    NULLIF(TRIM(review_comment_message), '') AS review_comment_message,
    review_creation_date,
    review_answer_timestamp
FROM ranked
WHERE review_rank = 1;

ALTER TABLE clean.order_reviews ADD PRIMARY KEY (order_id);


-- ---------------------------------------------------------------------
-- cleaning_log: how many rows each rule touched, and what was done.
-- These are the numbers quoted in the README.
-- ---------------------------------------------------------------------
CREATE TABLE clean.cleaning_log (
    rule_no       INTEGER PRIMARY KEY,
    rule          TEXT NOT NULL,
    rows_affected INTEGER NOT NULL,
    action        TEXT NOT NULL
);

INSERT INTO clean.cleaning_log
SELECT 1, 'Orders outside Jan 2017 - Aug 2018',
       COUNT(*) FILTER (WHERE NOT in_analysis_window),
       'Kept; flagged in_analysis_window = false'
FROM clean.orders
UNION ALL
SELECT 2, 'Orders with no items',
       COUNT(*) FILTER (WHERE NOT has_items),
       'Kept for cancellation rate; flagged has_items = false; no revenue'
FROM clean.orders
UNION ALL
SELECT 3, 'Extra reviews on orders reviewed more than once',
       (SELECT COUNT(*) FROM raw.order_reviews) - (SELECT COUNT(*) FROM clean.order_reviews),
       'Kept only the most recent review per order'
UNION ALL
SELECT 4, 'Products with no category',
       COUNT(*), 'Category set to unknown'
FROM raw.products WHERE product_category_name IS NULL
UNION ALL
SELECT 5, 'Products whose category had no English translation',
       COUNT(*), 'Translation added by hand (2 categories)'
FROM raw.products AS p
WHERE p.product_category_name IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM raw.category_translation AS t
      WHERE t.product_category_name = p.product_category_name
  )
UNION ALL
SELECT 6, 'Delivered orders with no delivery date',
       COUNT(*), 'Kept in revenue; delivery_days and is_late left NULL'
FROM raw.orders WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL
UNION ALL
SELECT 7, 'Non-delivered orders that have a delivery date',
       COUNT(*), 'Status trusted; delivery_days and is_late left NULL'
FROM raw.orders WHERE order_status <> 'delivered' AND order_delivered_customer_date IS NOT NULL
UNION ALL
SELECT 8, 'Orders with carrier/delivery timestamps out of order',
       COUNT(*) FILTER (WHERE has_date_issue),
       'Kept; flagged has_date_issue = true'
FROM clean.orders
UNION ALL
SELECT 9, 'Blank review comments',
       COUNT(*), 'Set to NULL'
FROM raw.order_reviews
WHERE review_comment_message IS NOT NULL AND TRIM(review_comment_message) = '';


-- Refresh table statistics so the query planner picks good plans.
ANALYZE clean.categories;
ANALYZE clean.products;
ANALYZE clean.customers;
ANALYZE clean.sellers;
ANALYZE clean.orders;
ANALYZE clean.order_items;
ANALYZE clean.order_payments;
ANALYZE clean.order_reviews;
