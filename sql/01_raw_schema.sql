-- Raw layer: one table per Olist CSV file, loaded exactly as downloaded.
-- Nothing is cleaned here. Cleaning happens in 02_clean.sql.
-- Re-running this file drops and rebuilds the whole raw schema.

DROP SCHEMA IF EXISTS raw CASCADE;
CREATE SCHEMA raw;

-- One row per customer_id. Note: customer_id is created per ORDER;
-- customer_unique_id identifies the actual person across orders.
CREATE TABLE raw.customers (
    customer_id              VARCHAR(32) PRIMARY KEY,
    customer_unique_id       VARCHAR(32) NOT NULL,
    customer_zip_code_prefix VARCHAR(5),
    customer_city            TEXT,
    customer_state           CHAR(2)
);

CREATE TABLE raw.sellers (
    seller_id              VARCHAR(32) PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(5),
    seller_city            TEXT,
    seller_state           CHAR(2)
);

-- Portuguese category name -> English category name.
CREATE TABLE raw.category_translation (
    product_category_name         TEXT PRIMARY KEY,
    product_category_name_english TEXT NOT NULL
);

-- Column names "lenght" are misspelled in the source file; kept as-is in raw.
CREATE TABLE raw.products (
    product_id                 VARCHAR(32) PRIMARY KEY,
    product_category_name      TEXT,
    product_name_lenght        INTEGER,
    product_description_lenght INTEGER,
    product_photos_qty         INTEGER,
    product_weight_g           NUMERIC(10, 2),
    product_length_cm          NUMERIC(10, 2),
    product_height_cm          NUMERIC(10, 2),
    product_width_cm           NUMERIC(10, 2)
);

-- One row per order.
CREATE TABLE raw.orders (
    order_id                      VARCHAR(32) PRIMARY KEY,
    customer_id                   VARCHAR(32) NOT NULL REFERENCES raw.customers (customer_id),
    order_status                  TEXT NOT NULL,
    order_purchase_timestamp      TIMESTAMP NOT NULL,
    order_approved_at             TIMESTAMP,
    order_delivered_carrier_date  TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
);

-- One row per item inside an order. An order can have many items,
-- so the primary key needs both columns.
CREATE TABLE raw.order_items (
    order_id            VARCHAR(32) NOT NULL REFERENCES raw.orders (order_id),
    order_item_id       INTEGER NOT NULL,
    product_id          VARCHAR(32) NOT NULL REFERENCES raw.products (product_id),
    seller_id           VARCHAR(32) NOT NULL REFERENCES raw.sellers (seller_id),
    shipping_limit_date TIMESTAMP,
    price               NUMERIC(10, 2),
    freight_value       NUMERIC(10, 2),
    PRIMARY KEY (order_id, order_item_id)
);

-- One row per payment. An order can be paid in several parts
-- (for example voucher + credit card), numbered by payment_sequential.
CREATE TABLE raw.order_payments (
    order_id             VARCHAR(32) NOT NULL REFERENCES raw.orders (order_id),
    payment_sequential   INTEGER NOT NULL,
    payment_type         TEXT,
    payment_installments INTEGER,
    payment_value        NUMERIC(10, 2),
    PRIMARY KEY (order_id, payment_sequential)
);

-- One row per review of an order. review_id alone is NOT unique in the
-- source data, so the primary key is (review_id, order_id).
CREATE TABLE raw.order_reviews (
    review_id               VARCHAR(32) NOT NULL,
    order_id                VARCHAR(32) NOT NULL REFERENCES raw.orders (order_id),
    review_score            INTEGER,
    review_comment_title    TEXT,
    review_comment_message  TEXT,
    review_creation_date    TIMESTAMP,
    review_answer_timestamp TIMESTAMP,
    PRIMARY KEY (review_id, order_id)
);
