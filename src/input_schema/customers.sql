CREATE MULTISET TABLE customers (
    customer_id INTEGER NOT NULL,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    email VARCHAR(100),
    phone VARCHAR(30),
    address VARCHAR(255),
    city VARCHAR(50),
    country VARCHAR(50),
    signup_date DATE,
    created_at TIMESTAMP(0)
);
