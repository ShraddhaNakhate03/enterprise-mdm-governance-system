import random
from faker import Faker
import pandas as pd

fake = Faker()
Faker.seed(21)
random.seed(21)

N_CORE = 3000
DUP_RATE = 0.16
US_STATES = ["CA","NY","TX","FL","IL","WA","MA","GA","OH","PA","NC","MI","AZ","CO","NJ"]
PAYMENT_TERMS = ["NET15", "NET30", "NET45", "NET60"]
STATUSES = ["Active", "Active", "Active", "Inactive", "Under Review"]  # weighted toward Active

LEGAL_SUFFIXES = ["Inc.", "LLC", "Corp.", "Co.", "Ltd.", ""]

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

def random_tax_id():
    return f"{random.randint(10,99)}-{random.randint(1000000,9999999)}"

def make_core_record(i):
    company_base = fake.company().replace(" Inc","").replace(" LLC","").replace(",","")
    suffix = random.choice(LEGAL_SUFFIXES)
    vendor_name = f"{company_base} {suffix}".strip()
    return {
        "VendorID": f"VEND{2000+i}",
        "VendorName": vendor_name,
        "TaxID": random_tax_id(),
        "ContactName": fake.name(),
        "Email": f"ap.{fake.free_email_domain().split('.')[0]}{random.randint(1,99)}@{fake.free_email_domain()}",
        "Phone": random_phone(),
        "AddressLine1": fake.street_address(),
        "City": fake.city(),
        "State": random.choice(US_STATES),
        "PostalCode": fake.zipcode(),
        "Country": "USA",
        "PaymentTerms": random.choice(PAYMENT_TERMS),
        "Status": random.choice(STATUSES),
    }

def mess_up_text(text):
    choice = random.random()
    if choice < 0.3 and len(text) > 4:
        pos = random.randint(1, len(text)-2)
        return text[:pos] + text[pos+1:]
    elif choice < 0.55:
        return text.upper()
    elif choice < 0.75:
        return text.lower()
    else:
        return text + "  "  # trailing whitespace

def vary_legal_suffix(name):
    variants = [
        name.replace(" Inc.", " Incorporated"),
        name.replace(" LLC", " L.L.C."),
        name.replace(" Corp.", " Corporation"),
        name.replace(".", ""),
        name + " LLC",
        name.strip(),
    ]
    return random.choice(variants)

def make_duplicate(record):
    dup = record.copy()
    dup["VendorID"] = f"VEND{9000 + random.randint(0, 999999)}"
    dup["VendorName"] = vary_legal_suffix(mess_up_text(dup["VendorName"]))
    # TaxID sometimes re-keyed with a typo (common real-world data entry error)
    if random.random() < 0.2:
        tid = list(dup["TaxID"])
        pos = random.randint(3, len(tid)-1)
        tid[pos] = str(random.randint(0,9))
        dup["TaxID"] = "".join(tid)
    if random.random() < 0.4:
        dup["ContactName"] = fake.name()  # contact changed, same company
    digits = "".join(ch for ch in dup["Phone"] if ch.isdigit())[-10:]
    if len(digits) == 10:
        dup["Phone"] = random.choice(PHONE_FORMATS)(digits)
    for field in ["Email", "Phone", "AddressLine1", "PostalCode"]:
        if random.random() < 0.18:
            dup[field] = ""
    if random.random() < 0.25:
        dup["Country"] = random.choice(["USA", "US", "U.S.A.", "United States"])
    return dup

core_records = [make_core_record(i) for i in range(N_CORE)]
n_dupes = int(N_CORE * DUP_RATE)
duplicate_records = [make_duplicate(r) for r in random.sample(core_records, n_dupes)]

n_dirty = int(N_CORE * 0.05)
dirty_records = []
for i in range(n_dirty):
    r = make_core_record(N_CORE + i)
    for field in random.sample(["Email", "Phone", "AddressLine1", "TaxID"], k=random.randint(1,2)):
        r[field] = ""
    dirty_records.append(r)

all_records = core_records + duplicate_records + dirty_records
random.shuffle(all_records)
df = pd.DataFrame(all_records, columns=[
    "VendorID","VendorName","TaxID","ContactName","Email","Phone",
    "AddressLine1","City","State","PostalCode","Country","PaymentTerms","Status"
])
df.to_csv("/home/claude/vendor_master_raw.csv", index=False)

print(f"Total records: {len(df)}  |  Core: {N_CORE}  |  Duplicates: {n_dupes}  |  Dirty: {n_dirty}")
print(df.head(6).to_string())
