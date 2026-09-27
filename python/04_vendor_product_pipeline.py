"""
04_vendor_product_pipeline.py

Runs the same cleanse -> block -> fuzzy match -> golden record pattern used
for Customer (01/02) against the Vendor and Product domains. Kept as one
script since both domains are smaller and share the union-find helper.
"""
import sqlite3
import pandas as pd
from rapidfuzz import fuzz

DB = "master_data.db"
conn = sqlite3.connect(DB)

# ============================================================
# VENDOR DOMAIN
# ============================================================
vdf = pd.read_csv("vendor_master_raw.csv", dtype=str, keep_default_na=False)
vdf.to_sql("vendor_raw", conn, if_exists="replace", index=False)

for col in ["VendorName","ContactName","Email","Phone","AddressLine1","City","TaxID","PaymentTerms","Status"]:
    vdf[col] = vdf[col].astype(str).str.strip()
vdf["State"] = vdf["State"].str.upper()
vdf["Country"] = vdf["Country"].apply(lambda c: "USA" if c.strip().upper() in ("USA","US","U.S.A.","UNITED STATES") else c.strip().upper())
vdf["Email"] = vdf["Email"].str.lower()

def norm_phone(p):
    digits = "".join(ch for ch in str(p) if ch.isdigit())[-10:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return ""
vdf["Phone"] = vdf["Phone"].apply(norm_phone)

# Blocking keys: TaxID is the strongest natural key for vendors (should be
# unique per legal entity) — block primarily on that, then fall back to a
# name+state key for cases where TaxID was mis-keyed.
vdf["BlockKey_TaxID"] = vdf["TaxID"]
vdf["BlockKey_Name"] = vdf["VendorName"].str.upper().str.replace(r"[^A-Z]", "", regex=True).str[:5] + "-" + vdf["State"]

parent = {i: i for i in vdf.index}
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i
def union(i, j):
    ri, rj = find(i), find(j)
    if ri != rj:
        parent[rj] = ri

seen = set()
match_log = []
MATCH_THRESHOLD = 85

def run_pass(df, block_col, pass_name, compare_col, min_len=2):
    for key, group in df.groupby(block_col):
        if len(str(key).replace("-","")) < min_len or len(group) < 2:
            continue
        idxs = group.index.tolist()
        for a in range(len(idxs)):
            for b in range(a+1, len(idxs)):
                i, j = idxs[a], idxs[b]
                pair = tuple(sorted((i,j)))
                if pair in seen: continue
                score = fuzz.token_sort_ratio(str(df.at[i, compare_col]), str(df.at[j, compare_col]))
                if score >= MATCH_THRESHOLD:
                    seen.add(pair); union(i, j)
                    match_log.append({"Domain":"Vendor","A":df.at[i,"VendorID"],"B":df.at[j,"VendorID"],
                                       "Pass":pass_name,"Key":key,"Score":score,
                                       "NameA":df.at[i,"VendorName"],"NameB":df.at[j,"VendorName"]})

run_pass(vdf, "BlockKey_TaxID", "1_taxid", "VendorName", min_len=5)
run_pass(vdf, "BlockKey_Name", "2_name_state", "VendorName", min_len=3)
vdf["ClusterID"] = vdf.index.map(find)

VENDOR_REQUIRED = ["Email","Phone","AddressLine1","TaxID"]
def is_complete(row, fields):
    return all(str(row[f]).strip() != "" for f in fields)
pct_before_v = 100 * vdf.apply(lambda r: is_complete(r, VENDOR_REQUIRED), axis=1).mean()

def golden_vendor(group):
    g = {}
    g["VendorID"] = sorted(group["VendorID"])[0]
    g["SourceRecordCount"] = len(group)
    g["MergedVendorIDs"] = ", ".join(sorted(group["VendorID"]))
    non_blank = group[group["VendorName"].str.len() > 0]
    g["VendorName"] = non_blank.loc[non_blank["VendorName"].str.len().idxmax(), "VendorName"] if not non_blank.empty else ""
    for field in ["TaxID","ContactName","Email","Phone","AddressLine1","City","State","PostalCode","Country","PaymentTerms","Status"]:
        val = ""
        for _, row in group.iterrows():
            if str(row[field]).strip() != "":
                val = row[field]; break
        g[field] = val
    return g

golden_vendors = pd.DataFrame([golden_vendor(g) for _, g in vdf.groupby("ClusterID")])
pct_after_v = 100 * golden_vendors.apply(lambda r: is_complete(r, VENDOR_REQUIRED), axis=1).mean()

golden_vendors.to_csv("golden_vendors.csv", index=False)

vendor_summary = {
    "raw_record_count": len(vdf), "golden_record_count": len(golden_vendors),
    "duplicate_clusters_found": (golden_vendors["SourceRecordCount"] > 1).sum(),
    "records_merged_away": len(vdf) - len(golden_vendors),
    "pct_complete_before": round(pct_before_v, 1), "pct_complete_after": round(pct_after_v, 1),
}
print("VENDOR:", vendor_summary)

# ============================================================
# PRODUCT DOMAIN
# ============================================================
pdf_ = pd.read_csv("product_master_raw.csv", dtype=str, keep_default_na=False)
pdf_.to_sql("product_raw", conn, if_exists="replace", index=False)

for col in ["ProductName","Category","VendorID","UnitOfMeasure","Status"]:
    pdf_[col] = pdf_[col].astype(str).str.strip()

# Products have no reliable natural key across duplicates (new SKU each time),
# so blocking relies entirely on Category + Vendor + a name fragment.
pdf_["BlockKey"] = (
    pdf_["Category"].str.upper().str[:4] + "-" +
    pdf_["VendorID"].str[-4:] + "-" +
    pdf_["ProductName"].str.upper().str.replace(r"[^A-Z]", "", regex=True).str[:4]
)

parent2 = {i: i for i in pdf_.index}
def find2(i):
    while parent2[i] != i:
        parent2[i] = parent2[parent2[i]]
        i = parent2[i]
    return i
def union2(i, j):
    ri, rj = find2(i), find2(j)
    if ri != rj: parent2[rj] = ri

product_match_log = []
seen2 = set()
for key, group in pdf_.groupby("BlockKey"):
    if len(group) < 2 or len(str(key)) < 6:
        continue
    idxs = group.index.tolist()
    for a in range(len(idxs)):
        for b in range(a+1, len(idxs)):
            i, j = idxs[a], idxs[b]
            pair = tuple(sorted((i,j)))
            if pair in seen2: continue
            score = fuzz.token_sort_ratio(pdf_.at[i,"ProductName"], pdf_.at[j,"ProductName"])
            if score >= MATCH_THRESHOLD:
                seen2.add(pair); union2(i,j)
                product_match_log.append({"Domain":"Product","A":pdf_.at[i,"SKU"],"B":pdf_.at[j,"SKU"],
                                           "Pass":"1_category_vendor_name","Key":key,"Score":score,
                                           "NameA":pdf_.at[i,"ProductName"],"NameB":pdf_.at[j,"ProductName"]})
pdf_["ClusterID"] = pdf_.index.map(find2)

PRODUCT_REQUIRED = ["VendorID","UnitOfMeasure"]
pct_before_p = 100 * pdf_.apply(lambda r: is_complete(r, PRODUCT_REQUIRED), axis=1).mean()

def golden_product(group):
    g = {}
    g["SKU"] = sorted(group["SKU"])[0]
    g["SourceRecordCount"] = len(group)
    g["MergedSKUs"] = ", ".join(sorted(group["SKU"]))
    non_blank = group[group["ProductName"].str.len() > 0]
    g["ProductName"] = non_blank.loc[non_blank["ProductName"].str.len().idxmax(), "ProductName"] if not non_blank.empty else ""
    for field in ["Category","VendorID","UnitOfMeasure","Status"]:
        val = ""
        for _, row in group.iterrows():
            if str(row[field]).strip() != "":
                val = row[field]; break
        g[field] = val
    return g

golden_products = pd.DataFrame([golden_product(g) for _, g in pdf_.groupby("ClusterID")])
pct_after_p = 100 * golden_products.apply(lambda r: is_complete(r, PRODUCT_REQUIRED), axis=1).mean()
golden_products.to_csv("golden_products.csv", index=False)

product_summary = {
    "raw_record_count": len(pdf_), "golden_record_count": len(golden_products),
    "duplicate_clusters_found": (golden_products["SourceRecordCount"] > 1).sum(),
    "records_merged_away": len(pdf_) - len(golden_products),
    "pct_complete_before": round(pct_before_p, 1), "pct_complete_after": round(pct_after_p, 1),
}
print("PRODUCT:", product_summary)

pd.DataFrame(match_log + product_match_log).to_csv("vendor_product_match_audit_log.csv", index=False)
pd.DataFrame([{"Domain":"Vendor", **vendor_summary}, {"Domain":"Product", **product_summary}]).to_csv("vendor_product_summary_metrics.csv", index=False)

conn.close()
