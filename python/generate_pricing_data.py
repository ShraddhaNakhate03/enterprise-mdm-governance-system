import random
from faker import Faker
import pandas as pd

fake = Faker()
Faker.seed(7)
random.seed(7)

N_SKUS = 4000                  # unique products
CATEGORIES = ["Electronics","Office Supplies","Furniture","Industrial","Packaging","Apparel","Hardware","Software"]
AUTHORIZED_MAX_DISCOUNT = {    # policy ceiling per category — the audit checks against this
    "Electronics": 0.20, "Office Supplies": 0.15, "Furniture": 0.25,
    "Industrial": 0.10, "Packaging": 0.15, "Apparel": 0.30,
    "Hardware": 0.20, "Software": 0.35,
}

def make_sku_record(i, category):
    base_price = round(random.uniform(5, 2500), 2)
    discount = round(random.uniform(0, AUTHORIZED_MAX_DISCOUNT[category] * 0.8), 3)  # normally within policy
    return {
        "SKU": f"SKU-{10000+i}",
        "ProductName": fake.catch_phrase(),
        "Category": category,
        "VendorID": f"VEND{random.randint(1000,1999)}",
        "ListPrice": base_price,
        "DiscountPct": discount,
        "NetPrice": round(base_price * (1 - discount), 2),
        "EffectiveDate": fake.date_between(start_date="-2y", end_date="-1M").isoformat(),
        "PriceListSource": random.choice(["ERP_Feed", "Vendor_Catalog", "Manual_Entry", "Contract_Pricing"]),
    }

records = []
for i in range(N_SKUS):
    category = random.choice(CATEGORIES)
    records.append(make_sku_record(i, category))

# --- Inject anomaly type 1: duplicate SKU at a different price (rate mismatch) ---
n_dupe_sku = int(N_SKUS * 0.07)
dupe_targets = random.sample(records, n_dupe_sku)
for r in dupe_targets:
    dup = r.copy()
    # same SKU, but a conflicting price from a different source/date
    dup["ListPrice"] = round(r["ListPrice"] * random.uniform(0.85, 1.25), 2)
    dup["NetPrice"] = round(dup["ListPrice"] * (1 - dup["DiscountPct"]), 2)
    dup["EffectiveDate"] = fake.date_between(start_date="-11M", end_date="today").isoformat()
    dup["PriceListSource"] = random.choice(["ERP_Feed", "Vendor_Catalog", "Manual_Entry", "Contract_Pricing"])
    records.append(dup)

# --- Inject anomaly type 2: unauthorized discount (exceeds category policy ceiling) ---
n_bad_discount = int(N_SKUS * 0.04)
for r in random.sample(records, n_bad_discount):
    over_by = random.uniform(1.3, 2.5)
    r["DiscountPct"] = round(min(AUTHORIZED_MAX_DISCOUNT[r["Category"]] * over_by, 0.85), 3)
    r["NetPrice"] = round(r["ListPrice"] * (1 - r["DiscountPct"]), 2)

# --- Inject anomaly type 3: zero / negative / null price errors ---
n_bad_price = int(N_SKUS * 0.015)
for r in random.sample(records, n_bad_price):
    choice = random.random()
    if choice < 0.4:
        r["ListPrice"] = 0
    elif choice < 0.7:
        r["ListPrice"] = round(-abs(r["ListPrice"]), 2)
    else:
        r["ListPrice"] = ""
    r["NetPrice"] = ""

# --- Inject anomaly type 4: NetPrice doesn't match ListPrice x (1-Discount) — calc error ---
n_calc_error = int(N_SKUS * 0.02)
for r in random.sample([x for x in records if x["ListPrice"] not in ("", 0) and not (isinstance(r["ListPrice"], (int,float)) and r["ListPrice"] < 0)], n_calc_error):
    r["NetPrice"] = round(r["NetPrice"] * random.uniform(1.1, 1.4), 2)

random.shuffle(records)
df = pd.DataFrame(records)
df.to_csv("/home/claude/pricing_master_raw.csv", index=False)

print(f"Total price list rows: {len(df)}")
print(f"Unique SKUs: {df['SKU'].nunique()}")
print(f"Injected duplicate-SKU price conflicts: {n_dupe_sku}")
print(f"Injected unauthorized-discount rows: {n_bad_discount}")
print(f"Injected zero/negative/null price rows: {n_bad_price}")
print(f"Injected NetPrice calc-mismatch rows: {n_calc_error}")
print(df.head(8).to_string())
