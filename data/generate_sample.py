"""
Generate synthetic sales_data.csv with realistic data quality problems.

This dataset is purely synthetic — for demonstration and testing only.
Problems intentionally included:
  - Missing values (customer_age, revenue, country)
  - Duplicate rows
  - Inconsistent categories (country, acquisition_channel, customer_segment)
  - Outliers in revenue and quantity
  - Date strings in mixed formats
  - Negative quantities (invalid)
"""
import random
import math
import csv
import os

random.seed(42)

COUNTRIES = ["france", "France", "FRANCE", "germany", "Germany", "GERMANY",
             "spain", "Spain", "SPAIN", "italy", "Italy", None, "UK", "uk", "U.K."]
CHANNELS = ["organic", "Organic", "ORGANIC", "paid_search", "Paid Search",
            "social_media", "Social Media", "referral", "Referral", "email", "Email"]
PRODUCTS = ["Laptop Pro", "Smart Watch", "Wireless Earbuds", "Tablet X",
            "Mechanical Keyboard", "USB-C Hub", "Monitor 4K", "Webcam HD"]
SEGMENTS = ["premium", "Premium", "PREMIUM", "standard", "Standard",
            "STANDARD", "budget", "Budget", "enterprise", "Enterprise"]
DATE_FORMATS = [
    "2023-01-{:02d}", "2023/02/{:02d}", "{:02d}-03-2023",
    "2023-04-{:02d}", "April {}, 2023", "2023-05-{:02d}"
]


def random_date():
    fmt = random.choice(DATE_FORMATS)
    day = random.randint(1, 28)
    return fmt.format(day)


rows = []
for i in range(1, 1001):
    customer_id = f"CUST{i:05d}"

    # Missing age (~8%)
    age = random.randint(18, 75) if random.random() > 0.08 else None

    country = random.choice(COUNTRIES)

    channel = random.choice(CHANNELS)

    product = random.choice(PRODUCTS)

    # Revenue with outliers (~3%)
    if random.random() < 0.03:
        revenue = random.choice([0.01, 9999.99, 15000.0, -50.0])
    elif random.random() < 0.05:
        revenue = None  # ~5% missing
    else:
        revenue = round(random.uniform(20, 800), 2)

    # Quantity with some negatives (~2%)
    quantity = random.randint(1, 10)
    if random.random() < 0.02:
        quantity = -quantity

    discount = round(random.uniform(0, 0.40), 2)

    purchase_date = random_date()

    segment = random.choice(SEGMENTS)

    rows.append([customer_id, age, country, channel, product,
                 revenue, quantity, discount, purchase_date, segment])

# Add 50 exact duplicate rows
duplicates = random.choices(rows[:200], k=50)
rows.extend(duplicates)

random.shuffle(rows)

output_path = os.path.join(os.path.dirname(__file__), "sales_data.csv")
with open(output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "customer_id", "customer_age", "country", "acquisition_channel",
        "product", "revenue", "quantity", "discount", "purchase_date", "customer_segment"
    ])
    writer.writerows(rows)

print(f"Generated {len(rows)} rows → {output_path}")
