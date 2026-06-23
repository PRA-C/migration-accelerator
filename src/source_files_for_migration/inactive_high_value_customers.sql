-- TERADATA: High-value customers with no recent orders (re-engagement target list)
-- Tables: customers, orders (from input_schema)

WITH customer_spend AS (
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        c.email,
        c.phone,
        c.city,
        c.country,
        c.signup_date,
        COUNT(o.order_id) AS lifetime_orders,
        SUM(o.amount) AS lifetime_spend,
        MAX(o.order_date) AS last_order_date,
        AVG(o.amount) AS avg_order_value
    FROM customers c
    LEFT JOIN orders o
        ON c.customer_id = o.customer_id
        AND o.status IN ('COMPLETED', 'SHIPPED', 'DELIVERED')
    GROUP BY
        c.customer_id, c.first_name, c.last_name, c.email, c.phone,
        c.city, c.country, c.signup_date
),
ranked AS (
    SELECT
        customer_id,
        first_name,
        last_name,
        email,
        phone,
        city,
        country,
        signup_date,
        lifetime_orders,
        lifetime_spend,
        last_order_date,
        avg_order_value,
        CASE
            WHEN last_order_date IS NULL THEN NULL
            ELSE (CURRENT_DATE - last_order_date)
        END AS days_since_last_order,
        RANK() OVER (PARTITION BY country ORDER BY lifetime_spend DESC) AS country_spend_rank
    FROM customer_spend
    WHERE lifetime_spend >= 1000
        AND lifetime_orders >= 3
)
SELECT
    customer_id,
    first_name || ' ' || last_name AS full_name,
    email,
    phone,
    city,
    country,
    signup_date,
    lifetime_orders,
    lifetime_spend,
    avg_order_value,
    last_order_date,
    days_since_last_order,
    country_spend_rank
FROM ranked
WHERE (days_since_last_order > 90 OR last_order_date IS NULL)
    AND country_spend_rank <= 25
ORDER BY lifetime_spend DESC, days_since_last_order DESC;
