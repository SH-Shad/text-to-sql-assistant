import sqlite3
import random
from datetime import date, timedelta
import os

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH     = os.path.join(os.path.dirname(__file__), "analytics.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
SEED        = 42          # reproducible randomness
random.seed(SEED)

# ── Helpers ───────────────────────────────────────────────────────────────────
def random_date(start: date, end: date) -> str:
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0, delta))).isoformat()

# ── Seed data definitions ─────────────────────────────────────────────────────
REGIONS    = ["North", "South", "East", "West"]
STATUSES   = ["completed", "completed", "completed", "returned", "pending"]  # weighted

FIRST_NAMES = ["Alice", "Bob", "Carol", "David", "Eva", "Frank", "Grace",
                "Henry", "Iris", "James", "Karen", "Leo", "Mia", "Noah",
                "Olivia", "Paul", "Quinn", "Rachel", "Sam", "Tina"]
LAST_NAMES  = ["Smith", "Johnson", "Lee", "Brown", "Davis", "Wilson",
                "Moore", "Taylor", "Anderson", "Thomas"]

PRODUCTS = [
    ("Wireless Headphones",  "Electronics", 79.99),
    ("Mechanical Keyboard",  "Electronics", 129.99),
    ("USB-C Hub",            "Electronics", 49.99),
    ("Webcam HD",            "Electronics", 89.99),
    ("Running Shoes",        "Sports",      119.99),
    ("Yoga Mat",             "Sports",      34.99),
    ("Dumbbells Set",        "Sports",      89.99),
    ("Resistance Bands",     "Sports",      24.99),
    ("Cotton T-Shirt",       "Clothing",    19.99),
    ("Denim Jacket",         "Clothing",    69.99),
    ("Wool Sweater",         "Clothing",    49.99),
    ("Running Shorts",       "Clothing",    29.99),
    ("Desk Lamp",            "Home",        39.99),
    ("Coffee Maker",         "Home",        89.99),
    ("Air Purifier",         "Home",        149.99),
    ("Throw Pillow Set",     "Home",        44.99),
]

# ── Main seeding function ─────────────────────────────────────────────────────
def seed():
    # Wipe and recreate
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Apply schema
    with open(SCHEMA_PATH, "r") as f:
        cur.executescript(f.read())

    # 1. Products
    cur.executemany(
        "INSERT INTO products (name, category, unit_price) VALUES (?, ?, ?)",
        PRODUCTS
    )

    # 2. Customers (100 unique customers)
    customers = []
    used_emails = set()
    for i in range(1, 101):
        first = random.choice(FIRST_NAMES)
        last  = random.choice(LAST_NAMES)
        email = f"{first.lower()}.{last.lower()}{i}@example.com"
        region     = random.choice(REGIONS)
        signup     = random_date(date(2022, 1, 1), date(2023, 6, 30))
        customers.append((first + " " + last, email, region, signup))

    cur.executemany(
        "INSERT INTO customers (name, email, region, signup_date) VALUES (?, ?, ?, ?)",
        customers
    )

    # 3. Orders + Order Items (≈500 orders over 2 years)
    order_start = date(2023, 1, 1)
    order_end   = date(2024, 12, 31)

    order_id = 1
    item_id  = 1
    orders_rows = []
    items_rows  = []

    for _ in range(500):
        customer_id = random.randint(1, 100)
        order_date  = random_date(order_start, order_end)
        status      = random.choice(STATUSES)
        orders_rows.append((order_id, customer_id, order_date, status))

        # Each order has 1–4 line items
        n_items = random.randint(1, 4)
        chosen_products = random.sample(range(1, len(PRODUCTS) + 1), n_items)
        for pid in chosen_products:
            price    = PRODUCTS[pid - 1][2]
            quantity = random.randint(1, 3)
            # Slight historical price variance (±10%)
            hist_price = round(price * random.uniform(0.90, 1.10), 2)
            items_rows.append((item_id, order_id, pid, quantity, hist_price))
            item_id += 1

        order_id += 1

    cur.executemany(
        "INSERT INTO orders (order_id, customer_id, order_date, status) VALUES (?, ?, ?, ?)",
        orders_rows
    )
    cur.executemany(
        "INSERT INTO order_items (item_id, order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
        items_rows
    )

    conn.commit()
    conn.close()

    print(f"✅ Database seeded at: {DB_PATH}")
    print(f"   {len(PRODUCTS)} products")
    print(f"   100 customers")
    print(f"   {len(orders_rows)} orders")
    print(f"   {len(items_rows)} order items")

if __name__ == "__main__":
    seed()