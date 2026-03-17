-- Customers dimension
CREATE TABLE IF NOT EXISTS customers (
    customer_id   INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL,
    email         TEXT    UNIQUE NOT NULL,
    region        TEXT    NOT NULL,   -- 'North', 'South', 'East', 'West'
    signup_date   TEXT    NOT NULL    -- ISO format: 'YYYY-MM-DD'
);

-- Products dimension
CREATE TABLE IF NOT EXISTS products (
    product_id    INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL,
    category      TEXT    NOT NULL,   -- 'Electronics', 'Clothing', 'Home', 'Sports'
    unit_price    REAL    NOT NULL
);

-- Orders fact table
CREATE TABLE IF NOT EXISTS orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date    TEXT    NOT NULL,
    status        TEXT    NOT NULL    -- 'completed', 'returned', 'pending'
);

-- Order line items (the most granular fact)
CREATE TABLE IF NOT EXISTS order_items (
    item_id       INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    REAL    NOT NULL    -- price at time of purchase (can differ from current)
);