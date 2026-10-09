# KPI glossary

Business definitions used everywhere in this project. The AI assistant
retrieves these so that its SQL follows the same rules as the dashboard.

## Analysis window
All KPIs cover January 2017 to August 2018. Every query on fact_orders or fact_order_items must filter `in_analysis_window = TRUE` unless the question asks for a specific date inside that range. The KPI views (kpi_daily, kpi_weekly, kpi_monthly and the kpi_monthly_by_* views) are already limited to this window.

## Revenue
Revenue = SUM(order_revenue) from fact_orders for DELIVERED orders only: `WHERE is_delivered`. order_revenue is price plus freight of all items in the order. Canceled or undelivered orders are never counted as revenue. At item level use SUM(item_total) from fact_order_items with `WHERE is_delivered`.

## Orders
Orders = COUNT(*) of all orders placed, whatever their status. "Delivered orders" = orders with `is_delivered = TRUE`.

## Average order value (AOV)
AOV = revenue / number of delivered orders. Round to 2 decimals.

## Cancellation rate
Cancellation rate = percentage of orders with `is_canceled = TRUE` (status canceled or unavailable). Formula: 100.0 * COUNT(*) FILTER (WHERE is_canceled) / COUNT(*). Rates are always given as a percentage between 0 and 100, rounded to 2 decimals.

## Late delivery rate
An order is late when it was delivered after the estimated delivery date: `is_late = TRUE`. is_late is NULL when the order has no delivery date. Late delivery rate = 100.0 * COUNT(*) FILTER (WHERE is_late) / COUNT(is_late), as a percentage rounded to 2 decimals. COUNT(is_late) counts only orders that have delivery data.

## Delivery days
delivery_days = days from purchase to delivery to the customer. Average delivery days = AVG(delivery_days); NULL values (not delivered) are ignored automatically.

## Review score
review_score is 1 to 5, one review per order, NULL when the order has no review. Average review score = AVG(review_score). A "low" or "bad" review means review_score <= 2.

## Customers and repeat customers
customer_id is different for every order. The real person is `customer_unique_id` in dim_customer. To count customers, count DISTINCT customer_unique_id. A repeat customer has 2 or more delivered orders.

## Month-over-month growth
MoM growth % = 100 * (this month - previous month) / previous month. It is already calculated in kpi_monthly as revenue_mom_growth_pct and orders_mom_growth_pct.

## Dates and months
The order date is `order_date` (the day the order was placed). To group by month use DATE_TRUNC('month', order_date) or join dim_date and use year_month (text like '2018-03'). kpi_monthly has both month_start (date) and year_month (text).

## Product category
Category names are English snake_case text in dim_product.category, for example 'health_beauty', 'bed_bath_table', 'watches_gifts'. Products without a category have category = 'unknown'. Category analysis must use fact_order_items joined to dim_product, because one order can contain several categories.

## Customer state
customer_state in dim_customer is the 2-letter Brazilian state code, for example 'SP' (São Paulo), 'RJ' (Rio de Janeiro), 'MG' (Minas Gerais). Seller location is seller_state in dim_seller.

## Payment type
main_payment_type in fact_orders is the payment method that paid most of the order: credit_card, boleto, voucher, debit_card.

## Anomalies
mart.anomalies lists unusual days per KPI. kpi is one of: orders, revenue, aov, late_delivery_rate, avg_review_score. severity is 'high' or 'medium'. direction is 'spike' or 'drop'. Black Friday is 2017-11-24.

## Anomaly drivers
mart.anomaly_drivers explains high-severity revenue and orders anomalies. dimension is one of: category, customer_state, payment_type. segment is the value inside that dimension. contribution_pct is the share of the day's total change caused by that segment. driver_rank 1 is the biggest driver.

## Review themes
mart.review_themes holds a SAMPLE of reviews labelled by an LLM. theme is one of: late_delivery, not_received, wrong_or_missing_item, damaged_or_defective, poor_quality, seller_or_service, positive, other. Because it is a sample weighted towards low scores, use it for counts inside the sample, not for totals of the whole business.
