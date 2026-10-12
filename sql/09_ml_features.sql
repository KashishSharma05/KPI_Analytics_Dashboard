-- Features for the late-delivery prediction model.
-- Business question: at the moment an order is placed, can we tell
-- whether it will arrive after its estimated delivery date?
--
-- One row per delivered order (the ones where is_late is known).
--
-- RULE FOR EVERY COLUMN: it must be known at the moment of purchase.
-- The actual delivery date, the review and anything else that happens
-- later are NOT used. Using them would be "data leakage": the model
-- would look good here and be useless in real life.
--
-- The "history" columns (how late a seller or a state has been) are
-- built only from orders that had ALREADY BEEN DELIVERED before this
-- order was placed, because only then was their outcome known.
--
-- Run this after the clean schema is built.

-- The table lives in its own schema (ml), away from mart: the AI assistant
-- may query every mart table, and model features are not business KPIs.
CREATE SCHEMA IF NOT EXISTS ml;
DROP TABLE IF EXISTS ml.late_delivery_features;

-- ---------------------------------------------------------------------
-- Step 1. One row per delivered order, with everything known at purchase.
-- The "main" item is the most expensive one; its seller and category
-- describe the order. Kept as a temporary table with indexes, because
-- the history look-ups below read it many times.
-- ---------------------------------------------------------------------
CREATE TEMP TABLE order_base ON COMMIT DROP AS
WITH item_summary AS (
    SELECT
        i.order_id,
        COUNT(*)                                          AS item_count,
        COUNT(DISTINCT i.seller_id)                       AS seller_count,
        SUM(i.price)                                      AS items_value,
        SUM(i.freight_value)                              AS freight_value,
        COALESCE(SUM(p.product_weight_g), 0)              AS total_weight_g,
        COALESCE(SUM(p.product_length_cm * p.product_height_cm * p.product_width_cm), 0) AS total_volume_cm3
    FROM clean.order_items AS i
    JOIN clean.products AS p ON p.product_id = i.product_id
    GROUP BY i.order_id
),
main_item AS (
    SELECT DISTINCT ON (i.order_id)
        i.order_id, i.seller_id, p.category
    FROM clean.order_items AS i
    JOIN clean.products AS p ON p.product_id = i.product_id
    ORDER BY i.order_id, i.price DESC, i.order_item_id
)
SELECT
    o.order_id,
    o.order_purchase_timestamp                                      AS purchased_at,
    o.order_purchase_date                                           AS order_date,
    o.order_delivered_customer_date                                 AS delivered_at,
    o.order_delivered_customer_date::date                           AS delivered_date,
    o.is_late,
    (o.order_estimated_delivery_date::date - o.order_purchase_date) AS promised_days,
    EXTRACT(MONTH FROM o.order_purchase_timestamp)::int             AS purchase_month,
    EXTRACT(ISODOW FROM o.order_purchase_timestamp)::int            AS purchase_weekday,
    EXTRACT(HOUR FROM o.order_purchase_timestamp)::int              AS purchase_hour,
    c.customer_state,
    s.seller_state,
    m.seller_id,
    m.category,
    i.item_count, i.seller_count, i.items_value, i.freight_value, i.total_weight_g, i.total_volume_cm3
FROM clean.orders AS o
JOIN clean.customers AS c ON c.customer_id = o.customer_id
JOIN item_summary AS i    ON i.order_id = o.order_id
JOIN main_item AS m       ON m.order_id = o.order_id
JOIN clean.sellers AS s   ON s.seller_id = m.seller_id
WHERE o.in_analysis_window AND o.is_late IS NOT NULL;

CREATE INDEX ON order_base (seller_id, delivered_at);
ANALYZE order_base;


-- ---------------------------------------------------------------------
-- Step 2. Deliveries to each state in the 30 days before each day.
-- A calendar of every state and day is built first, so the window can
-- count back exactly 30 days even when a day had no deliveries.
-- "1 PRECEDING" stops at yesterday: today's deliveries are not known yet.
-- ---------------------------------------------------------------------
CREATE TEMP TABLE state_history ON COMMIT DROP AS
WITH delivered_per_day AS (
    SELECT customer_state, delivered_date, COUNT(*) AS delivered, SUM(is_late::int) AS late
    FROM order_base
    GROUP BY customer_state, delivered_date
),
calendar AS (
    SELECT st.customer_state, d.day::date AS day
    FROM (SELECT DISTINCT customer_state FROM order_base) AS st
    CROSS JOIN generate_series(DATE '2017-01-01', DATE '2018-08-31', INTERVAL '1 day') AS d(day)
)
SELECT
    cal.customer_state,
    cal.day,
    COALESCE(SUM(dp.delivered) OVER recent, 0) AS recent_orders,
    COALESCE(SUM(dp.late)      OVER recent, 0) AS recent_late
FROM calendar AS cal
LEFT JOIN delivered_per_day AS dp
       ON dp.customer_state = cal.customer_state AND dp.delivered_date = cal.day
WINDOW recent AS (PARTITION BY cal.customer_state ORDER BY cal.day ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING);


-- ---------------------------------------------------------------------
-- Step 3. The feature table.
-- ---------------------------------------------------------------------
CREATE TABLE ml.late_delivery_features AS
SELECT
    b.order_id,
    b.order_date,
    b.delivered_date,   -- NOT a feature: used only to keep unfinished orders out of the training data
    b.is_late,

    -- the promise made to the customer
    b.promised_days,

    -- when the order was placed
    b.purchase_month,
    b.purchase_weekday,
    b.purchase_hour,

    -- where it has to travel
    b.customer_state,
    b.seller_state,
    (b.customer_state = b.seller_state) AS same_state,

    -- what is in it
    b.category,
    b.item_count,
    b.seller_count,
    b.items_value,
    b.freight_value,
    ROUND(b.freight_value / NULLIF(b.items_value, 0), 4) AS freight_ratio,
    b.total_weight_g,
    b.total_volume_cm3,

    -- how this seller has done so far (orders already delivered before this purchase)
    sh.past_orders                                        AS seller_past_orders,
    sh.past_late_rate                                     AS seller_past_late_rate,

    -- how deliveries to this state went in the 30 days before the purchase day
    st.recent_orders                                      AS state_recent_orders,
    ROUND(st.recent_late::numeric / NULLIF(st.recent_orders, 0), 4) AS state_recent_late_rate
FROM order_base AS b
JOIN state_history AS st
  ON st.customer_state = b.customer_state AND st.day = b.order_date
-- LATERAL: for each order, look back at this seller's deliveries finished before it was placed.
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS past_orders, ROUND(AVG(d.is_late::int), 4) AS past_late_rate
    FROM order_base AS d
    WHERE d.seller_id = b.seller_id AND d.delivered_at < b.purchased_at
) AS sh ON TRUE;

ALTER TABLE ml.late_delivery_features ADD PRIMARY KEY (order_id);
