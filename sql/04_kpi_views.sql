-- KPI views. Each KPI is defined once here and reused by the dashboard,
-- the anomaly detector and the AI assistant.
--
-- KPI definitions (all grouped by the date the order was PLACED):
--   orders              all orders placed
--   delivered_orders    orders with status 'delivered'
--   revenue             sum of (price + freight) for DELIVERED orders only.
--                       Canceled or undelivered orders are not earned money.
--   aov                 revenue / delivered_orders
--   cancellation_rate   % of orders with status canceled or unavailable
--   late_delivery_rate  % of delivered orders that arrived after the estimated date
--   avg_delivery_days   average days from purchase to delivery
--   avg_review_score    average review score (1 to 5)
--
-- NULLIF(x, 0) is used in every division so a day with zero orders gives
-- NULL instead of a "division by zero" error.


-- =====================================================================
-- kpi_daily
-- Business question: how did each KPI move day by day?
-- Starts from dim_date with a LEFT JOIN so days with no orders still
-- appear (with zeros). Rolling averages smooth out the weekday pattern.
-- =====================================================================
CREATE OR REPLACE VIEW mart.kpi_daily AS
WITH daily AS (
    SELECT
        d.date_key,
        d.day_name,
        d.is_complete_data,
        COUNT(f.order_id)                                         AS orders,
        COUNT(f.order_id) FILTER (WHERE f.is_delivered)           AS delivered_orders,
        COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0) AS revenue,
        COUNT(f.order_id) FILTER (WHERE f.is_canceled)            AS canceled_orders,
        COUNT(f.order_id) FILTER (WHERE f.is_late)                AS late_orders,
        COUNT(f.is_late)                                          AS orders_with_delivery_date,
        AVG(f.delivery_days)                                      AS avg_delivery_days,
        AVG(f.review_score)                                       AS avg_review_score
    FROM mart.dim_date AS d
    LEFT JOIN mart.fact_orders AS f ON f.order_date = d.date_key
    WHERE d.in_analysis_window
    GROUP BY d.date_key, d.day_name, d.is_complete_data
)
SELECT
    date_key,
    day_name,
    is_complete_data,
    orders,
    delivered_orders,
    revenue,
    ROUND(revenue / NULLIF(delivered_orders, 0), 2)                    AS aov,
    ROUND(100.0 * canceled_orders / NULLIF(orders, 0), 2)              AS cancellation_rate,
    ROUND(100.0 * late_orders / NULLIF(orders_with_delivery_date, 0), 2) AS late_delivery_rate,
    ROUND(avg_delivery_days, 2)                                        AS avg_delivery_days,
    ROUND(avg_review_score, 2)                                         AS avg_review_score,
    -- average of this day and the 6 days before it
    ROUND(AVG(revenue) OVER (ORDER BY date_key ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2)  AS revenue_7d_avg,
    -- average of this day and the 27 days before it
    ROUND(AVG(revenue) OVER (ORDER BY date_key ROWS BETWEEN 27 PRECEDING AND CURRENT ROW), 2) AS revenue_28d_avg,
    ROUND(AVG(orders)  OVER (ORDER BY date_key ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2)  AS orders_7d_avg
FROM daily;


-- =====================================================================
-- kpi_weekly
-- Business question: how did each KPI move week by week (Monday start)?
-- days_in_week shows weeks that are cut short at the edges of the data.
-- =====================================================================
CREATE OR REPLACE VIEW mart.kpi_weekly AS
WITH weekly AS (
    SELECT
        d.week_start,
        COUNT(DISTINCT d.date_key)                                AS days_in_week,
        BOOL_AND(d.is_complete_data)                              AS is_complete_data,
        COUNT(f.order_id)                                         AS orders,
        COUNT(f.order_id) FILTER (WHERE f.is_delivered)           AS delivered_orders,
        COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0) AS revenue,
        COUNT(f.order_id) FILTER (WHERE f.is_canceled)            AS canceled_orders,
        COUNT(f.order_id) FILTER (WHERE f.is_late)                AS late_orders,
        COUNT(f.is_late)                                          AS orders_with_delivery_date,
        AVG(f.delivery_days)                                      AS avg_delivery_days,
        AVG(f.review_score)                                       AS avg_review_score
    FROM mart.dim_date AS d
    LEFT JOIN mart.fact_orders AS f ON f.order_date = d.date_key
    WHERE d.in_analysis_window
    GROUP BY d.week_start
)
SELECT
    week_start,
    days_in_week,
    is_complete_data,
    orders,
    delivered_orders,
    revenue,
    ROUND(revenue / NULLIF(delivered_orders, 0), 2)                    AS aov,
    ROUND(100.0 * canceled_orders / NULLIF(orders, 0), 2)              AS cancellation_rate,
    ROUND(100.0 * late_orders / NULLIF(orders_with_delivery_date, 0), 2) AS late_delivery_rate,
    ROUND(avg_delivery_days, 2)                                        AS avg_delivery_days,
    ROUND(avg_review_score, 2)                                         AS avg_review_score,
    -- week-over-week revenue growth: this week compared with the week before
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY week_start))
          / NULLIF(LAG(revenue) OVER (ORDER BY week_start), 0), 2)     AS revenue_wow_growth_pct
FROM weekly;


-- =====================================================================
-- kpi_monthly
-- Business question: how is the business growing month over month?
-- LAG() looks at the previous row (the previous month).
-- SUM() OVER (ORDER BY ...) gives a running total.
-- =====================================================================
CREATE OR REPLACE VIEW mart.kpi_monthly AS
WITH monthly AS (
    SELECT
        d.month_start,
        d.year_month,
        COUNT(f.order_id)                                         AS orders,
        COUNT(f.order_id) FILTER (WHERE f.is_delivered)           AS delivered_orders,
        COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0) AS revenue,
        COUNT(f.order_id) FILTER (WHERE f.is_canceled)            AS canceled_orders,
        COUNT(f.order_id) FILTER (WHERE f.is_late)                AS late_orders,
        COUNT(f.is_late)                                          AS orders_with_delivery_date,
        AVG(f.delivery_days)                                      AS avg_delivery_days,
        AVG(f.review_score)                                       AS avg_review_score
    FROM mart.dim_date AS d
    LEFT JOIN mart.fact_orders AS f ON f.order_date = d.date_key
    WHERE d.in_analysis_window
    GROUP BY d.month_start, d.year_month
)
SELECT
    month_start,
    year_month,
    orders,
    delivered_orders,
    revenue,
    ROUND(revenue / NULLIF(delivered_orders, 0), 2)                    AS aov,
    ROUND(100.0 * canceled_orders / NULLIF(orders, 0), 2)              AS cancellation_rate,
    ROUND(100.0 * late_orders / NULLIF(orders_with_delivery_date, 0), 2) AS late_delivery_rate,
    ROUND(avg_delivery_days, 2)                                        AS avg_delivery_days,
    ROUND(avg_review_score, 2)                                         AS avg_review_score,
    LAG(revenue) OVER (ORDER BY month_start)                           AS previous_month_revenue,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month_start))
          / NULLIF(LAG(revenue) OVER (ORDER BY month_start), 0), 2)    AS revenue_mom_growth_pct,
    ROUND(100.0 * (orders - LAG(orders) OVER (ORDER BY month_start))
          / NULLIF(LAG(orders) OVER (ORDER BY month_start), 0), 2)     AS orders_mom_growth_pct,
    SUM(revenue) OVER (ORDER BY month_start)                           AS revenue_running_total
FROM monthly;


-- =====================================================================
-- kpi_monthly_by_category
-- Business question: which product categories drive revenue each month,
-- and how is each category growing?
-- An order can contain several categories, so this uses the item fact.
--   revenue_share_pct : category revenue / total revenue of that month
--   revenue_rank      : 1 = top category of the month
-- =====================================================================
CREATE OR REPLACE VIEW mart.kpi_monthly_by_category AS
WITH category_month AS (
    SELECT
        DATE_TRUNC('month', i.order_date)::date AS month_start,
        p.category,
        COUNT(DISTINCT i.order_id) AS orders,
        COUNT(*)                   AS items_sold,
        SUM(i.item_total)          AS revenue
    FROM mart.fact_order_items AS i
    JOIN mart.dim_product AS p ON p.product_id = i.product_id
    WHERE i.is_delivered AND i.in_analysis_window
    GROUP BY 1, 2
)
SELECT
    month_start,
    category,
    orders,
    items_sold,
    revenue,
    ROUND(100.0 * revenue / SUM(revenue) OVER (PARTITION BY month_start), 2) AS revenue_share_pct,
    RANK() OVER (PARTITION BY month_start ORDER BY revenue DESC)             AS revenue_rank,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (PARTITION BY category ORDER BY month_start))
          / NULLIF(LAG(revenue) OVER (PARTITION BY category ORDER BY month_start), 0), 2) AS revenue_mom_growth_pct
FROM category_month;


-- =====================================================================
-- kpi_monthly_by_state
-- Business question: which customer states buy the most, and where are
-- delivery and satisfaction worst?
-- =====================================================================
CREATE OR REPLACE VIEW mart.kpi_monthly_by_state AS
WITH state_month AS (
    SELECT
        DATE_TRUNC('month', f.order_date)::date AS month_start,
        c.customer_state,
        COUNT(*)                                          AS orders,
        COUNT(*) FILTER (WHERE f.is_delivered)            AS delivered_orders,
        COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0) AS revenue,
        COUNT(*) FILTER (WHERE f.is_late)                 AS late_orders,
        COUNT(f.is_late)                                  AS orders_with_delivery_date,
        AVG(f.delivery_days)                              AS avg_delivery_days,
        AVG(f.review_score)                               AS avg_review_score
    FROM mart.fact_orders AS f
    JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
    WHERE f.in_analysis_window
    GROUP BY 1, 2
)
SELECT
    month_start,
    customer_state,
    orders,
    delivered_orders,
    revenue,
    ROUND(revenue / NULLIF(delivered_orders, 0), 2)                      AS aov,
    ROUND(100.0 * late_orders / NULLIF(orders_with_delivery_date, 0), 2) AS late_delivery_rate,
    ROUND(avg_delivery_days, 2)                                          AS avg_delivery_days,
    ROUND(avg_review_score, 2)                                           AS avg_review_score,
    ROUND(100.0 * revenue / SUM(revenue) OVER (PARTITION BY month_start), 2) AS revenue_share_pct,
    RANK() OVER (PARTITION BY month_start ORDER BY revenue DESC)         AS revenue_rank
FROM state_month;


-- =====================================================================
-- kpi_monthly_by_payment_type
-- Business question: how do customers pay, and is the mix changing?
-- =====================================================================
CREATE OR REPLACE VIEW mart.kpi_monthly_by_payment_type AS
WITH payment_month AS (
    SELECT
        DATE_TRUNC('month', order_date)::date AS month_start,
        main_payment_type,
        COUNT(*)                                        AS orders,
        COALESCE(SUM(order_revenue) FILTER (WHERE is_delivered), 0) AS revenue,
        AVG(payment_installments)                       AS avg_installments
    FROM mart.fact_orders
    WHERE in_analysis_window
    GROUP BY 1, 2
)
SELECT
    month_start,
    main_payment_type,
    orders,
    revenue,
    ROUND(avg_installments, 2)                                              AS avg_installments,
    ROUND(100.0 * orders / SUM(orders) OVER (PARTITION BY month_start), 2)  AS orders_share_pct
FROM payment_month;
