-- Mart layer: a star schema built from the clean layer.
--
-- Fact tables hold the numbers we measure (orders, revenue).
-- Dimension tables hold the things we slice by (date, customer, product, seller).
-- This shape is what Power BI and the KPI views read from.
--
-- Re-running this file drops and rebuilds the whole mart schema.

DROP SCHEMA IF EXISTS mart CASCADE;
CREATE SCHEMA mart;


-- ---------------------------------------------------------------------
-- dim_date: one row per calendar day, from the first order to the last.
-- generate_series creates every day, including days with no orders,
-- so charts and rolling averages have no gaps.
--
-- in_analysis_window : Jan 2017 to Aug 2018.
-- is_complete_data   : false after 22 Aug 2018. Daily orders fall from
--                      about 250 to almost zero in the last days of the
--                      file, which looks like the export being cut off,
--                      not real business. Those days are excluded from
--                      anomaly detection.
-- ---------------------------------------------------------------------
CREATE TABLE mart.dim_date AS
SELECT
    d::date                              AS date_key,
    EXTRACT(YEAR FROM d)::int            AS year,
    EXTRACT(QUARTER FROM d)::int         AS quarter,
    EXTRACT(MONTH FROM d)::int           AS month,
    TO_CHAR(d, 'Mon')                    AS month_name,
    TO_CHAR(d, 'YYYY-MM')                AS year_month,
    DATE_TRUNC('month', d)::date         AS month_start,
    DATE_TRUNC('week', d)::date          AS week_start,      -- Monday of that week
    EXTRACT(ISODOW FROM d)::int          AS day_of_week,     -- 1 = Monday ... 7 = Sunday
    TO_CHAR(d, 'Dy')                     AS day_name,
    EXTRACT(ISODOW FROM d) IN (6, 7)     AS is_weekend,
    (d >= DATE '2017-01-01' AND d < DATE '2018-09-01') AS in_analysis_window,
    (d <= DATE '2018-08-22')             AS is_complete_data
FROM generate_series(
    (SELECT MIN(order_purchase_date) FROM clean.orders),
    (SELECT MAX(order_purchase_date) FROM clean.orders),
    INTERVAL '1 day'
) AS g(d);

ALTER TABLE mart.dim_date ADD PRIMARY KEY (date_key);


-- ---------------------------------------------------------------------
-- dim_customer, dim_product, dim_seller
-- ---------------------------------------------------------------------
CREATE TABLE mart.dim_customer AS
SELECT customer_id, customer_unique_id, customer_city, customer_state
FROM clean.customers;

ALTER TABLE mart.dim_customer ADD PRIMARY KEY (customer_id);
CREATE INDEX idx_dim_customer_unique_id ON mart.dim_customer (customer_unique_id);

CREATE TABLE mart.dim_product AS
SELECT product_id, category
FROM clean.products;

ALTER TABLE mart.dim_product ADD PRIMARY KEY (product_id);

CREATE TABLE mart.dim_seller AS
SELECT seller_id, seller_city, seller_state
FROM clean.sellers;

ALTER TABLE mart.dim_seller ADD PRIMARY KEY (seller_id);


-- ---------------------------------------------------------------------
-- fact_orders: one row per order.
--
-- Items, payments and reviews each have many rows per order, so each is
-- first summarised to one row per order in a CTE, then joined. Joining
-- them directly would multiply rows and double-count revenue.
--
-- order_revenue = sum of (price + freight) of the order's items.
-- main_payment_type = the payment type that paid the largest amount.
-- ---------------------------------------------------------------------
CREATE TABLE mart.fact_orders AS
WITH item_totals AS (
    SELECT
        order_id,
        COUNT(*)           AS item_count,
        SUM(price)         AS items_value,
        SUM(freight_value) AS freight_value,
        SUM(item_total)    AS order_revenue
    FROM clean.order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(payment_value)        AS payment_value,
        MAX(payment_installments) AS payment_installments
    FROM clean.order_payments
    GROUP BY order_id
),
payment_by_type AS (
    SELECT order_id, payment_type, SUM(payment_value) AS type_value
    FROM clean.order_payments
    GROUP BY order_id, payment_type
),
main_payment AS (
    SELECT order_id, payment_type
    FROM (
        SELECT
            order_id,
            payment_type,
            ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY type_value DESC, payment_type) AS type_rank
        FROM payment_by_type
    ) AS ranked
    WHERE type_rank = 1
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_purchase_date            AS order_date,
    o.order_purchase_timestamp,
    o.order_status,
    o.is_delivered,
    o.is_canceled,
    o.in_analysis_window,
    COALESCE(it.item_count, 0)       AS item_count,
    COALESCE(it.items_value, 0)      AS items_value,
    COALESCE(it.freight_value, 0)    AS freight_value,
    COALESCE(it.order_revenue, 0)    AS order_revenue,
    pt.payment_value,
    pt.payment_installments,
    COALESCE(mp.payment_type, 'unknown') AS main_payment_type,
    o.delivery_days,
    o.is_late,
    r.review_score,
    (r.review_comment_message IS NOT NULL) AS has_review_comment
FROM clean.orders AS o
LEFT JOIN item_totals    AS it ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt ON pt.order_id = o.order_id
LEFT JOIN main_payment   AS mp ON mp.order_id = o.order_id
LEFT JOIN clean.order_reviews AS r ON r.order_id = o.order_id;

ALTER TABLE mart.fact_orders ADD PRIMARY KEY (order_id);
ALTER TABLE mart.fact_orders ADD FOREIGN KEY (customer_id) REFERENCES mart.dim_customer (customer_id);
ALTER TABLE mart.fact_orders ADD FOREIGN KEY (order_date)  REFERENCES mart.dim_date (date_key);
CREATE INDEX idx_fact_orders_order_date  ON mart.fact_orders (order_date);
CREATE INDEX idx_fact_orders_customer_id ON mart.fact_orders (customer_id);


-- ---------------------------------------------------------------------
-- fact_order_items: one row per item in an order.
-- Used for product and seller analysis. The order's date and status are
-- copied onto each item so item-level queries do not need an extra join.
-- ---------------------------------------------------------------------
CREATE TABLE mart.fact_order_items AS
SELECT
    i.order_id,
    i.order_item_id,
    i.product_id,
    i.seller_id,
    o.customer_id,
    o.order_purchase_date AS order_date,
    o.is_delivered,
    o.in_analysis_window,
    i.price,
    i.freight_value,
    i.item_total
FROM clean.order_items AS i
JOIN clean.orders AS o ON o.order_id = i.order_id;

ALTER TABLE mart.fact_order_items ADD PRIMARY KEY (order_id, order_item_id);
ALTER TABLE mart.fact_order_items ADD FOREIGN KEY (order_id)    REFERENCES mart.fact_orders (order_id);
ALTER TABLE mart.fact_order_items ADD FOREIGN KEY (product_id)  REFERENCES mart.dim_product (product_id);
ALTER TABLE mart.fact_order_items ADD FOREIGN KEY (seller_id)   REFERENCES mart.dim_seller (seller_id);
ALTER TABLE mart.fact_order_items ADD FOREIGN KEY (customer_id) REFERENCES mart.dim_customer (customer_id);
ALTER TABLE mart.fact_order_items ADD FOREIGN KEY (order_date)  REFERENCES mart.dim_date (date_key);
CREATE INDEX idx_fact_items_order_date ON mart.fact_order_items (order_date);
CREATE INDEX idx_fact_items_product_id ON mart.fact_order_items (product_id);
CREATE INDEX idx_fact_items_seller_id  ON mart.fact_order_items (seller_id);


ANALYZE mart.dim_date;
ANALYZE mart.dim_customer;
ANALYZE mart.dim_product;
ANALYZE mart.dim_seller;
ANALYZE mart.fact_orders;
ANALYZE mart.fact_order_items;
