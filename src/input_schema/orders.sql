CREATE MULTISET TABLE orders (
    order_id INTEGER NOT NULL,
    customer_id INTEGER,
    order_date DATE,
    amount DECIMAL(10,2),
    company VARCHAR(100),
    status VARCHAR(20)
);
