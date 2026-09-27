import random
from faker import Faker
import pandas as pd

fake = Faker()
Faker.seed(42)
random.seed(42)

N_CORE = 5000          # unique "clean" customers
DUP_RATE = 0.18        # % of core records that get a messy duplicate

US_STATES = ["CA","NY","TX","FL","IL","WA","MA","GA","OH","PA","NC","MI","AZ","CO","NJ"]

PHONE_FORMATS = [
    lambda n: f"({n[:3]}) {n[3:6]}-{n[6:]}",
    lambda n: f"{n[:3]}-{n[3:6]}-{n[6:]}",
    lambda n: f"{n[:3]}.{n[3:6]}.{n[6:]}",
    lambda n: f"+1{n}",
    lambda n: n,
]

def random_phone():
    digits = "".join(str(random.randint(0,9)) for _ in range(10))
    return random.choice(PHONE_FORMATS)(digits)

def make_core_record(i):
    first = fake.first_name()
    last = fake.last_name()
    company = fake.company() if random.random() < 0.35 else ""
    return {
        "CustomerID": f"CUST{100000+i}",
        "FirstName": first,
        "LastName": last,
        "CompanyName": company,
        "Email": f"{first.lower()}.{last.lower()}{random.randint(1,99)}@{fake.free_email_domain()}",
        "Phone": random_phone(),
        "AddressLine1": fake.street_address(),
        "City": fake.city(),
        "State": random.choice(US_STATES),
        "PostalCode": fake.zipcode(),
        "Country": "USA",
        "CreatedDate": fake.date_between(start_date="-3y", end_date="-1M").isoformat(),
    }

def mess_up_name(name):
    """Introduce a typo / variation into a string."""
    choice = random.random()
    if choice < 0.25 and len(name) > 3:
        pos = random.randint(1, len(name)-2)
        return name[:pos] + name[pos+1:]          # dropped letter
    elif choice < 0.5:
        return name.upper()                        # case variation
    elif choice < 0.7:
        return name.lower()
    elif choice < 0.85 and len(name) > 3:
        pos = random.randint(1, len(name)-2)
        letters = list(name)
        letters[pos], letters[pos+1] = letters[pos+1], letters[pos]
        return "".join(letters)                     # swapped letters
    else:
        return name + " "                           # trailing whitespace

def make_duplicate(record):
    """Create a near-duplicate of a core record with realistic messiness."""
    dup = record.copy()
    dup["CustomerID"] = f"CUST{900000 + random.randint(0, 999999)}"

    # vary the name (this is the fuzzy-match challenge)
    dup["FirstName"] = mess_up_name(dup["FirstName"])
    if random.random() < 0.5:
        dup["LastName"] = mess_up_name(dup["LastName"])

    # sometimes convert to "Last, First" style or add a suffix
    if random.random() < 0.15:
        dup["FirstName"], dup["LastName"] = dup["LastName"], dup["FirstName"]

    # inconsistent company formatting
    if dup["CompanyName"]:
        variants = [
            dup["CompanyName"].replace("Inc.", "Incorporated"),
            dup["CompanyName"].replace(",", ""),
            dup["CompanyName"].upper(),
            dup["CompanyName"] + " LLC",
        ]
        dup["CompanyName"] = random.choice(variants)

    # re-format phone differently than the original
    digits = "".join(ch for ch in dup["Phone"] if ch.isdigit())[-10:]
    if len(digits) == 10:
        dup["Phone"] = random.choice(PHONE_FORMATS)(digits)

    # randomly blank out fields (completeness problem)
    for field in ["Email", "Phone", "AddressLine1", "PostalCode"]:
        if random.random() < 0.20:
            dup[field] = ""

    # inconsistent city/state casing
    if random.random() < 0.3:
        dup["City"] = dup["City"].upper()
    if random.random() < 0.2:
        dup["Country"] = random.choice(["USA", "US", "U.S.A.", "United States", "usa"])

    # slightly later created date (as if re-entered)
    dup["CreatedDate"] = fake.date_between(start_date="-11M", end_date="today").isoformat()

    return dup

# --- Build core records ---
core_records = [make_core_record(i) for i in range(N_CORE)]

# --- Inject messy duplicates ---
n_dupes = int(N_CORE * DUP_RATE)
dupe_sources = random.sample(core_records, n_dupes)
duplicate_records = [make_duplicate(r) for r in dupe_sources]

# --- Inject a few fully "dirty" standalone records (not duplicates, just messy) ---
n_dirty = int(N_CORE * 0.05)
dirty_records = []
for i in range(n_dirty):
    r = make_core_record(N_CORE + i)
    # random missing required fields
    for field in random.sample(["Email", "Phone", "AddressLine1", "PostalCode", "City"], k=random.randint(1,2)):
        r[field] = ""
    dirty_records.append(r)

all_records = core_records + duplicate_records + dirty_records
random.shuffle(all_records)

df = pd.DataFrame(all_records, columns=[
    "CustomerID","FirstName","LastName","CompanyName","Email","Phone",
    "AddressLine1","City","State","PostalCode","Country","CreatedDate"
])

# Save CSV (raw, exactly as "received")
df.to_csv("/home/claude/customer_master_raw.csv", index=False)

print(f"Total records: {len(df)}")
print(f"Core unique customers: {N_CORE}")
print(f"Injected messy duplicates: {n_dupes}")
print(f"Standalone dirty records: {n_dirty}")
print(df.head(10).to_string())
