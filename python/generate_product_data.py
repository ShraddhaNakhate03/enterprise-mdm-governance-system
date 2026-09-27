import random
from faker import Faker
import pandas as pd

fake = Faker()
Faker.seed(33)
random.seed(33)

N_CORE = 3500
DUP_RATE = 0.14
CATEGORIES = ["Electronics","Office Supplies","Furniture","Industrial","Packaging","Apparel","Hardware","Software"]
UOM_OPTIONS = ["EA", "CS", "PK", "LB", "BX"]
STATUSES = ["Active", "Active", "Active", "Discontinued", "Pending"]

def make_core_record(i, category):
    return {
        "SKU": f"SKU-{20000+i}",
        "ProductName": fake.catch_phrase(),
        "Category": category,
        "VendorID": f"VEND{random.randint(2000,4999)}",
        "UnitOfMeasure": random.choice(UOM_OPTIONS),
        "Status": random.choice(STATUSES),
    }

def mess_up_name(name):
    choice = random.random()
    if choice < 0.3:
        return name.upper()
    elif choice < 0.5:
        return name.lower()
    elif choice < 0.7 and len(name) > 6:
        # abbreviate: drop a word
        words = name.split(" ")
        if len(words) > 2:
            words.pop(random.randint(0, len(words)-1))
        return " ".join(words)
    elif choice < 0.85:
        return name.replace("-", " ")
    else:
        return name + " "

def make_duplicate(record):
    dup = record.copy()
    # duplicate PRODUCT gets a NEW SKU — this is the "same product entered twice"
    # problem (different SKU, same real-world item), which is the hardest kind
    # of product dedup because the natural key (SKU) is different by definition.
    dup["SKU"] = f"SKU-{90000 + random.randint(0, 999999)}"
    dup["ProductName"] = mess_up_name(dup["ProductName"])
    if random.random() < 0.15:
        dup["UnitOfMeasure"] = random.choice(UOM_OPTIONS)  # inconsistent UOM entry
    if random.random() < 0.1:
        dup["VendorID"] = f"VEND{random.randint(2000,4999)}"  # re-sourced from a different vendor
    return dup

records = []
for i in range(N_CORE):
    category = random.choice(CATEGORIES)
    records.append(make_core_record(i, category))

n_dupes = int(N_CORE * DUP_RATE)
duplicate_records = [make_duplicate(r) for r in random.sample(records, n_dupes)]

n_dirty = int(N_CORE * 0.04)
dirty_records = []
for i in range(n_dirty):
    r = make_core_record(N_CORE + i, random.choice(CATEGORIES))
    if random.random() < 0.5:
        r["UnitOfMeasure"] = ""
    else:
        r["VendorID"] = ""
    dirty_records.append(r)

all_records = records + duplicate_records + dirty_records
random.shuffle(all_records)
df = pd.DataFrame(all_records, columns=["SKU","ProductName","Category","VendorID","UnitOfMeasure","Status"])
df.to_csv("/home/claude/product_master_raw.csv", index=False)

print(f"Total records: {len(df)}  |  Core: {N_CORE}  |  Duplicates: {n_dupes}  |  Dirty: {n_dirty}")
print(df.head(6).to_string())
