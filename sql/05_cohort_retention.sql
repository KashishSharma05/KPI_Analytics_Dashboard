-- Cohort retention.
-- Business question: of the customers who bought for the first time in a
-- given month, what percentage came back and bought again in later months?
--
-- A "cohort" is the group of customers whose FIRST purchase was in the
-- same month. A customer is identified by customer_unique_id, because
-- customer_id changes with every order.
--
-- Read a row like this: cohort 2017-03, months_since_first = 2 means
-- "customers who first bought in March 2017 and bought again in May 2017".

CREATE OR REPLACE VIEW mart.cohort_retention AS
WITH customer_months AS (
    -- every month in which each customer placed a delivered order
    SELECT DISTINCT
        c.customer_unique_id,
        DATE_TRUNC('month', f.order_date)::date AS order_month
    FROM mart.fact_orders AS f
    JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
    WHERE f.is_delivered AND f.in_analysis_window
),
first_purchase AS (
    -- the cohort of each customer = the month of their first order
    SELECT customer_unique_id, MIN(order_month) AS cohort_month
    FROM customer_months
    GROUP BY customer_unique_id
),
cohort_activity AS (
    -- how many customers of each cohort were active N months later
    SELECT
        fp.cohort_month,
        (EXTRACT(YEAR FROM cm.order_month) - EXTRACT(YEAR FROM fp.cohort_month)) * 12
            + (EXTRACT(MONTH FROM cm.order_month) - EXTRACT(MONTH FROM fp.cohort_month)) AS months_since_first,
        COUNT(*) AS active_customers
    FROM customer_months AS cm
    JOIN first_purchase AS fp ON fp.customer_unique_id = cm.customer_unique_id
    GROUP BY 1, 2
)
SELECT
    cohort_month,
    months_since_first::int AS months_since_first,
    active_customers,
    -- month 0 is the cohort itself, so its count is the cohort size
    FIRST_VALUE(active_customers) OVER (PARTITION BY cohort_month ORDER BY months_since_first) AS cohort_size,
    ROUND(100.0 * active_customers
          / FIRST_VALUE(active_customers) OVER (PARTITION BY cohort_month ORDER BY months_since_first), 2) AS retention_pct
FROM cohort_activity;


-- Business question: overall, how many customers ever bought more than once?
CREATE OR REPLACE VIEW mart.repeat_customer_summary AS
WITH orders_per_customer AS (
    SELECT c.customer_unique_id, COUNT(*) AS delivered_orders
    FROM mart.fact_orders AS f
    JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
    WHERE f.is_delivered AND f.in_analysis_window
    GROUP BY c.customer_unique_id
)
SELECT
    COUNT(*)                                       AS customers,
    COUNT(*) FILTER (WHERE delivered_orders >= 2)  AS repeat_customers,
    ROUND(100.0 * COUNT(*) FILTER (WHERE delivered_orders >= 2) / COUNT(*), 2) AS repeat_customer_pct
FROM orders_per_customer;
