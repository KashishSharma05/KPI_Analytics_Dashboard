-- Root cause analysis for anomalies.
-- Business question: on a day when revenue or orders were unusual,
-- WHICH categories, states or payment types caused the change?
--
-- Method, for every high-severity revenue/orders anomaly:
--   1. Split the KPI by a dimension (category, customer state, payment type).
--   2. For each segment, compare the anomaly day ("actual") with that
--      segment's daily average over the previous 28 days ("baseline").
--   3. change = actual - baseline.
--      contribution_pct = this segment's change / total change of the day.
--   4. Keep the 5 segments with the biggest change for each dimension.
--
-- Only revenue and orders are analysed, because they add up across
-- segments. A rate (like late delivery %) does not add up that way.
--
-- Run this after src.detect_anomalies has filled mart.anomalies.

DROP TABLE IF EXISTS mart.anomaly_drivers;

CREATE TABLE mart.anomaly_drivers AS
WITH target_anomalies AS (
    SELECT anomaly_date, kpi
    FROM mart.anomalies
    WHERE severity = 'high' AND kpi IN ('revenue', 'orders')
),

-- Daily revenue and orders for every segment of every dimension.
-- Revenue counts delivered orders only; orders counts all orders
-- (the same definitions as the KPI views).
segment_daily AS (
    SELECT
        i.order_date,
        'category'                                        AS dimension,
        p.category                                        AS segment,
        COALESCE(SUM(i.item_total) FILTER (WHERE i.is_delivered), 0) AS revenue,
        COUNT(DISTINCT i.order_id)                        AS orders
    FROM mart.fact_order_items AS i
    JOIN mart.dim_product AS p ON p.product_id = i.product_id
    WHERE i.in_analysis_window
    GROUP BY i.order_date, p.category

    UNION ALL

    SELECT
        f.order_date,
        'customer_state',
        c.customer_state,
        COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0),
        COUNT(*)
    FROM mart.fact_orders AS f
    JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
    WHERE f.in_analysis_window
    GROUP BY f.order_date, c.customer_state

    UNION ALL

    SELECT
        f.order_date,
        'payment_type',
        f.main_payment_type,
        COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0),
        COUNT(*)
    FROM mart.fact_orders AS f
    WHERE f.in_analysis_window
    GROUP BY f.order_date, f.main_payment_type
),

-- Turn the two KPI columns into rows, so one query handles both KPIs.
segment_kpi AS (
    SELECT order_date, dimension, segment, 'revenue' AS kpi, revenue::numeric AS kpi_value FROM segment_daily
    UNION ALL
    SELECT order_date, dimension, segment, 'orders',         orders::numeric              FROM segment_daily
),

-- For each anomaly and segment: the value on the anomaly day, and the
-- daily average over the 28 days before it. Dividing by 28 (instead of
-- using AVG) counts days with no sales in that segment as zero.
actual_vs_baseline AS (
    SELECT
        a.anomaly_date,
        a.kpi,
        s.dimension,
        s.segment,
        COALESCE(SUM(s.kpi_value) FILTER (WHERE s.order_date = a.anomaly_date), 0)        AS actual,
        COALESCE(SUM(s.kpi_value) FILTER (WHERE s.order_date < a.anomaly_date), 0) / 28.0 AS baseline
    FROM target_anomalies AS a
    JOIN segment_kpi AS s
        ON  s.kpi = a.kpi
        AND s.order_date BETWEEN a.anomaly_date - 28 AND a.anomaly_date
    GROUP BY a.anomaly_date, a.kpi, s.dimension, s.segment
),

ranked AS (
    SELECT
        anomaly_date,
        kpi,
        dimension,
        segment,
        ROUND(actual, 2)            AS actual,
        ROUND(baseline, 2)          AS baseline,
        ROUND(actual - baseline, 2) AS change,
        ROUND(100.0 * (actual - baseline)
              / NULLIF(SUM(actual - baseline) OVER (PARTITION BY anomaly_date, kpi, dimension), 0), 2) AS contribution_pct,
        RANK() OVER (
            PARTITION BY anomaly_date, kpi, dimension
            ORDER BY ABS(actual - baseline) DESC
        ) AS driver_rank
    FROM actual_vs_baseline
)
SELECT *
FROM ranked
WHERE driver_rank <= 5;

ALTER TABLE mart.anomaly_drivers ADD PRIMARY KEY (anomaly_date, kpi, dimension, segment);
