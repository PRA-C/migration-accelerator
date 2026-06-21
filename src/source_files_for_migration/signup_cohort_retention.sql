-- DUCKDB: Signup cohort retention and repeat purchase analysis
-- Tables: customers, orders (from input_schema)

WITH cohort_base AS (
    SELECT
        c.customer_id,
        date_trunc('month', c.signup_date) AS signup_cohort,
        c.country,
        MIN(o.order_date) AS first_purchase_date,
        MAX(o.order_date) AS last_purchase_date,
        COUNT(o.order_id) AS order_count,
        SUM(o.amount) AS total_spend
    FROM customers c
    LEFT JOIN orders o
        ON c.customer_id = o.customer_id
        AND o.status IN ('COMPLETED', 'SHIPPED', 'DELIVERED')
    WHERE c.signup_date >= current_date - INTERVAL '36 months'
    GROUP BY 1, 2, 3
),
cohort_summary AS (
    SELECT
        signup_cohort,
        country,
        COUNT(*) AS cohort_size,
        SUM(CASE WHEN order_count > 0 THEN 1 ELSE 0 END) AS converted_customers,
        SUM(CASE WHEN order_count >= 2 THEN 1 ELSE 0 END) AS repeat_customers,
        AVG(total_spend) AS avg_cohort_spend,
        AVG(
            CASE
                WHEN first_purchase_date IS NOT NULL
                THEN first_purchase_date - signup_cohort
            END
        ) AS avg_days_to_first_order
    FROM cohort_base
    GROUP BY 1, 2
)
SELECT
    signup_cohort,
    country,
    cohort_size,
    converted_customers,
    repeat_customers,
    CAST(converted_customers AS DECIMAL(18,4)) / NULLIF(cohort_size, 0) * 100 AS conversion_rate_pct,
    CAST(repeat_customers AS DECIMAL(18,4)) / NULLIF(converted_customers, 0) * 100 AS repeat_rate_pct,
    avg_cohort_spend,
    avg_days_to_first_order,
    RANK() OVER (
        PARTITION BY signup_cohort
        ORDER BY converted_customers DESC
    ) AS country_rank_in_cohort
FROM cohort_summary
WHERE cohort_size >= 5
ORDER BY signup_cohort DESC, conversion_rate_pct DESC;
