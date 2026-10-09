# Tables in the mart schema

## fact_orders
One row per order. Columns: order_id, customer_id, order_date (date placed), order_purchase_timestamp, order_status, is_delivered, is_canceled, in_analysis_window, item_count, items_value, freight_value, order_revenue (price + freight), payment_value, payment_installments, main_payment_type, delivery_days, is_late, review_score, has_review_comment. Join to dim_customer on customer_id and to dim_date on order_date = date_key.

## fact_order_items
One row per item in an order. Columns: order_id, order_item_id, product_id, seller_id, customer_id, order_date, is_delivered, in_analysis_window, price, freight_value, item_total (price + freight). Join to dim_product on product_id and dim_seller on seller_id. Use this table for category or seller questions.

## dim_date
One row per calendar day. Columns: date_key, year, quarter, month, month_name, year_month ('YYYY-MM'), month_start, week_start, day_of_week (1 = Monday, 7 = Sunday), day_name ('Mon'...'Sun'), is_weekend, in_analysis_window, is_complete_data.

## dim_customer
One row per customer_id. Columns: customer_id, customer_unique_id (the real person), customer_city, customer_state.

## dim_product
One row per product. Columns: product_id, category.

## dim_seller
One row per seller. Columns: seller_id, seller_city, seller_state.

## kpi_daily
One row per day in the analysis window. Columns: date_key, day_name, is_complete_data, orders, delivered_orders, revenue, aov, cancellation_rate, late_delivery_rate, avg_delivery_days, avg_review_score, revenue_7d_avg, revenue_28d_avg, orders_7d_avg. Use it for questions about a specific day or daily trends.

## kpi_weekly
One row per week (week_start is a Monday). Columns: week_start, days_in_week, is_complete_data, orders, delivered_orders, revenue, aov, cancellation_rate, late_delivery_rate, avg_delivery_days, avg_review_score, revenue_wow_growth_pct.

## kpi_monthly
One row per month. Columns: month_start, year_month, orders, delivered_orders, revenue, aov, cancellation_rate, late_delivery_rate, avg_delivery_days, avg_review_score, previous_month_revenue, revenue_mom_growth_pct, orders_mom_growth_pct, revenue_running_total. Prefer this view for any monthly KPI question.

## kpi_monthly_by_category
One row per month and category (delivered orders only). Columns: month_start, category, orders, items_sold, revenue, revenue_share_pct, revenue_rank (1 = top category of that month), revenue_mom_growth_pct.

## kpi_monthly_by_state
One row per month and customer state. Columns: month_start, customer_state, orders, delivered_orders, revenue, aov, late_delivery_rate, avg_delivery_days, avg_review_score, revenue_share_pct, revenue_rank.

## kpi_monthly_by_payment_type
One row per month and payment type. Columns: month_start, main_payment_type, orders, revenue, avg_installments, orders_share_pct.

## cohort_retention
Columns: cohort_month (month of first purchase), months_since_first (0 = first month), active_customers, cohort_size, retention_pct.

## repeat_customer_summary
A single row. Columns: customers, repeat_customers, repeat_customer_pct.

## anomalies
One row per unusual day and KPI. Columns: anomaly_date, kpi, value, expected, deviation_pct, z_score, direction, flag_zscore, flag_iqr, flag_isolation_forest, methods_agreeing, severity.

## anomaly_drivers
Top 5 drivers per anomaly and dimension. Columns: anomaly_date, kpi, dimension, segment, actual, baseline, change, contribution_pct, driver_rank.

## review_themes
Sample of LLM-labelled reviews. Columns: order_id, order_date, review_score, theme, sentiment, english_summary, is_late, delivery_days, customer_state.
