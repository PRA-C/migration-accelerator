-- DUCKDB: Customer lifetime value and order frequency
-- Tables: customers, orders (from input_schema)

WITH customer_orders AS (
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        c.email,
        c.city,
        c.country,
        c.signup_date,
        o.order_id,
        o.order_date,
        o.amount,
        o.status,
        o.company
    FROM customers c
    INNER JOIN orders o
        ON c.customer_id = o.customer_id
    WHERE o.status IN ('COMPLETED', 'SHIPPED', 'DELIVERED')
),
customer_metrics AS (
    SELECT
        customer_id,
        first_name,
        last_name,
        email,
        city,
        country,
        signup_date,
        COUNT(DISTINCT order_id) AS total_orders,
        SUM(amount) AS lifetime_spend,
        AVG(amount) AS avg_order_value,
        MIN(order_date) AS first_order_date,
        MAX(order_date) AS last_order_date,
        MAX(order_date) - MIN(order_date) AS customer_tenure_days
    FROM customer_orders
    GROUP BY 1, 2, 3, 4, 5, 6, 7
)
SELECT
    customer_id,
    first_name || ' ' || last_name AS full_name,
    email,
    city,
    country,
    signup_date,
    total_orders,
    lifetime_spend,
    avg_order_value,
    first_order_date,
    last_order_date,
    customer_tenure_days,
    RANK() OVER (PARTITION BY country ORDER BY lifetime_spend DESC) AS spend_rank_in_country,
    PERCENT_RANK() OVER (ORDER BY lifetime_spend) AS spend_percentile
FROM customer_metrics
QUALIFY spend_rank_in_country <= 10
ORDER BY country, spend_rank_in_country;
