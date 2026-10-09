-- Growth and customer-journey analysis.
-- Run after 03_star_schema.sql.


-- =====================================================================
-- order_funnel_monthly
-- Business question: of the orders placed, how many make it through each
-- step of the journey, and where do we lose them?
--
-- Each stage includes the condition of the stage before it, so the
-- numbers can only go down from one stage to the next.
-- =====================================================================
CREATE OR REPLACE VIEW mart.order_funnel_monthly AS
WITH stages AS (
    SELECT
        DATE_TRUNC('month', o.order_purchase_date)::date AS month_start,
        (o.order_approved_at IS NOT NULL)                AS approved,
        (o.order_delivered_carrier_date IS NOT NULL)     AS shipped,
        o.is_delivered                                   AS delivered,
        COALESCE(o.is_late = FALSE, FALSE)               AS on_time,
        COALESCE(r.review_score >= 4, FALSE)             AS happy
    FROM clean.orders AS o
    LEFT JOIN clean.order_reviews AS r ON r.order_id = o.order_id
    WHERE o.in_analysis_window
)
SELECT
    month_start,
    COUNT(*)                                                              AS placed,
    COUNT(*) FILTER (WHERE approved)                                      AS approved,
    COUNT(*) FILTER (WHERE approved AND shipped)                          AS shipped,
    COUNT(*) FILTER (WHERE approved AND shipped AND delivered)            AS delivered,
    COUNT(*) FILTER (WHERE approved AND shipped AND delivered AND on_time) AS delivered_on_time,
    COUNT(*) FILTER (WHERE approved AND shipped AND delivered AND on_time AND happy) AS on_time_and_happy
FROM stages
GROUP BY month_start;


-- =====================================================================
-- customer_summary: one row per real customer (customer_unique_id).
-- Business question: who are our customers, when did they first buy,
-- what did they buy first, and did they come back?
--
-- ROW_NUMBER() numbers each customer's delivered orders from oldest to
-- newest, so order 1 is the first purchase and order 2 the first repeat.
-- An order's "main category" is the category with the highest item value.
-- =====================================================================
DROP TABLE IF EXISTS mart.customer_summary CASCADE;

CREATE TABLE mart.customer_summary AS
WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        c.customer_state,
        f.order_id,
        f.order_date,
        f.order_revenue,
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY f.order_purchase_timestamp
        ) AS order_number
    FROM mart.fact_orders AS f
    JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
    WHERE f.is_delivered AND f.in_analysis_window
),
category_value AS (
    SELECT i.order_id, p.category, SUM(i.item_total) AS category_total
    FROM mart.fact_order_items AS i
    JOIN mart.dim_product AS p ON p.product_id = i.product_id
    GROUP BY i.order_id, p.category
),
main_category AS (
    SELECT order_id, category
    FROM (
        SELECT
            order_id,
            category,
            ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY category_total DESC, category) AS category_rank
        FROM category_value
    ) AS ranked
    WHERE category_rank = 1
)
SELECT
    o.customer_unique_id,
    MIN(o.order_date)                                         AS first_order_date,
    DATE_TRUNC('month', MIN(o.order_date))::date              AS first_order_month,
    MIN(o.order_date) FILTER (WHERE o.order_number = 2)       AS second_order_date,
    COUNT(*)                                                  AS delivered_orders,
    SUM(o.order_revenue)                                      AS revenue,
    MAX(o.customer_state) FILTER (WHERE o.order_number = 1)   AS first_state,
    MAX(m.category) FILTER (WHERE o.order_number = 1)         AS first_category
FROM customer_orders AS o
LEFT JOIN main_category AS m ON m.order_id = o.order_id
GROUP BY o.customer_unique_id;

ALTER TABLE mart.customer_summary ADD PRIMARY KEY (customer_unique_id);


-- =====================================================================
-- customer_monthly
-- Business question: each month, how much of the business comes from new
-- customers and how much from returning ones?
-- A customer is "new" in the month of their first delivered order.
-- =====================================================================
CREATE OR REPLACE VIEW mart.customer_monthly AS
SELECT
    DATE_TRUNC('month', f.order_date)::date AS month_start,
    COUNT(DISTINCT c.customer_unique_id)    AS active_customers,
    COUNT(DISTINCT c.customer_unique_id)
        FILTER (WHERE s.first_order_month = DATE_TRUNC('month', f.order_date)) AS new_customers,
    COUNT(DISTINCT c.customer_unique_id)
        FILTER (WHERE s.first_order_month < DATE_TRUNC('month', f.order_date)) AS returning_customers,
    COALESCE(SUM(f.order_revenue)
        FILTER (WHERE s.first_order_month = DATE_TRUNC('month', f.order_date)), 0) AS revenue_new,
    COALESCE(SUM(f.order_revenue)
        FILTER (WHERE s.first_order_month < DATE_TRUNC('month', f.order_date)), 0) AS revenue_returning
FROM mart.fact_orders AS f
JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
JOIN mart.customer_summary AS s ON s.customer_unique_id = c.customer_unique_id
WHERE f.is_delivered AND f.in_analysis_window
GROUP BY 1;


-- =====================================================================
-- repeat_by_first_category
-- Business question: which first purchases bring customers back?
-- Only categories with at least 500 first-time customers, so the rate is
-- not based on a handful of people.
-- =====================================================================
CREATE OR REPLACE VIEW mart.repeat_by_first_category AS
SELECT
    first_category,
    COUNT(*)                                          AS customers,
    COUNT(*) FILTER (WHERE delivered_orders >= 2)     AS repeat_customers,
    ROUND(100.0 * COUNT(*) FILTER (WHERE delivered_orders >= 2) / COUNT(*), 2) AS repeat_rate_pct,
    ROUND(AVG(revenue), 2)                            AS revenue_per_customer
FROM mart.customer_summary
WHERE first_category IS NOT NULL
GROUP BY first_category
HAVING COUNT(*) >= 500;

ANALYZE mart.customer_summary;
