"""
MASTER DATA GOVERNANCE — CUSTOMER DOMAIN
02_fuzzy_dedup_golden_record.py

Purpose:
  1. Load the cleansed customer table.
  2. Use blocking (BlockKey) to limit fuzzy comparisons to records that
     could plausibly be duplicates (same last-name prefix + postal prefix)
     instead of comparing every record to every other record (O(n^2)).
  3. Score candidate pairs with rapidfuzz (token-sort ratio on full name).
  4. Cluster matches above threshold into duplicate groups (union-find).
  5. Apply survivorship rules to build ONE golden record per cluster.
  6. Report completeness % before vs after, and write an audit log of
     every match decision (required for any real MDM project — you must
     be able to show WHY two records were merged).
"""

import sqlite3
import pandas as pd
from rapidfuzz import fuzz

DB = "master_data.db"
MATCH_THRESHOLD = 85          # similarity score (0-100) to treat as a duplicate
REQUIRED_FIELDS = ["Email", "Phone", "AddressLine1", "PostalCode"]

conn = sqlite3.connect(DB)
df = pd.read_sql("SELECT * FROM customers_cleansed", conn)
df["FullName"] = (df["FirstName"].fillna("") + " " + df["LastName"].fillna("")).str.strip()

# ---------- 1. MULTI-PASS BLOCKING ----------
# A single blocking key misses real duplicates whenever the value it's built
# from is itself dirty (blank postal code) or the typo/swap happens to land
# inside the key (e.g. first 3 letters of last name). Real MDM tools run
# several independent blocking passes and UNION the candidate pairs found,
# trading a bit more compute for much better recall. Three passes here:
#   Pass 1: last-name prefix + postal prefix   (catches most typo dupes)
#   Pass 2: first-name prefix + postal prefix  (catches first/last swaps)
#   Pass 3: email local-part                   (catches renamed/misspelled
#                                                names but same email root)
df["BlockKey2"] = (
    df["FirstName"].fillna("").str.upper().str[:3] + "-" + df["PostalCode"].fillna("").str[:3]
)
df["EmailKey"] = df["Email"].fillna("").str.split("@").str[0].str.replace(r"\d+$", "", regex=True)

# ---------- 2. UNION-FIND FOR CLUSTERING MATCHES ----------
parent = {idx: idx for idx in df.index}

def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i

def union(i, j):
    ri, rj = find(i), find(j)
    if ri != rj:
        parent[rj] = ri

match_log = []
seen_pairs = set()

def run_blocking_pass(block_col, pass_name, min_key_len=1):
    for block_key, group in df.groupby(block_col):
        if len(str(block_key).replace("-", "")) < min_key_len or len(group) < 2:
            continue
        idxs = group.index.tolist()
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                pair_key = tuple(sorted((i, j)))
                if pair_key in seen_pairs:
                    continue
                name_i, name_j = df.at[i, "FullName"], df.at[j, "FullName"]
                score = fuzz.token_sort_ratio(name_i, name_j)
                if score >= MATCH_THRESHOLD:
                    seen_pairs.add(pair_key)
                    union(i, j)
                    match_log.append({
                        "CustomerID_A": df.at[i, "CustomerID"],
                        "Name_A": name_i,
                        "CustomerID_B": df.at[j, "CustomerID"],
                        "Name_B": name_j,
                        "BlockingPass": pass_name,
                        "BlockKey": block_key,
                        "SimilarityScore": score,
                    })

run_blocking_pass("BlockKey", "1_lastname_postal", min_key_len=2)
run_blocking_pass("BlockKey2", "2_firstname_postal", min_key_len=2)
run_blocking_pass("EmailKey", "3_email_root", min_key_len=3)

df["ClusterID"] = df.index.map(find)

# ---------- 3. COMPLETENESS BEFORE DEDUP ----------
def is_complete(row):
    return all(str(row[f]).strip() != "" for f in REQUIRED_FIELDS)

pct_before = 100 * df.apply(is_complete, axis=1).mean()

# ---------- 4. SURVIVORSHIP RULES → GOLDEN RECORDS ----------
def build_golden_record(group: pd.DataFrame) -> dict:
    """
    Rules (documented so they can be defended in an interview / SOP):
      - Prefer the value from the MOST RECENTLY created record for each field.
      - If the most recent record's field is blank, fall back to any
        non-blank value elsewhere in the cluster.
      - For Name fields, prefer the LONGEST non-blank value (catches
        truncated / abbreviated duplicates).
      - CustomerID: keep the lowest-numbered ID (treated as the "original").
    """
    group = group.sort_values("CreatedDate", ascending=False)
    golden = {}
    golden["CustomerID"] = sorted(group["CustomerID"])[0]
    golden["SourceRecordCount"] = len(group)
    golden["MergedCustomerIDs"] = ", ".join(sorted(group["CustomerID"]))

    for field in ["FirstName", "LastName", "CompanyName"]:
        non_blank = group[group[field].astype(str).str.strip() != ""]
        golden[field] = (
            non_blank.loc[non_blank[field].astype(str).str.len().idxmax(), field]
            if not non_blank.empty else ""
        )

    for field in ["Email", "Phone", "AddressLine1", "City", "State", "PostalCode", "Country"]:
        val = ""
        for _, row in group.iterrows():          # already sorted most-recent first
            if str(row[field]).strip() != "":
                val = row[field]
                break
        golden[field] = val

    golden["CreatedDate"] = group["CreatedDate"].min()   # earliest = true original creation
    golden["LastMergedDate"] = group["CreatedDate"].max()
    return golden

golden_records = [build_golden_record(g) for _, g in df.groupby("ClusterID")]
golden_df = pd.DataFrame(golden_records)

# ---------- 5. COMPLETENESS AFTER DEDUP ----------
pct_after = 100 * golden_df.apply(is_complete, axis=1).mean()

# ---------- 6. OUTPUTS ----------
golden_df.to_csv("golden_customers.csv", index=False)
pd.DataFrame(match_log).to_csv("match_audit_log.csv", index=False)

summary = pd.DataFrame([{
    "raw_record_count": len(df),
    "golden_record_count": len(golden_df),
    "duplicate_clusters_found": (golden_df["SourceRecordCount"] > 1).sum(),
    "records_merged_away": len(df) - len(golden_df),
    "pct_complete_before": round(pct_before, 1),
    "pct_complete_after": round(pct_after, 1),
    "match_pairs_logged": len(match_log),
}])
summary.to_csv("dedup_summary_metrics.csv", index=False)

print(summary.to_string(index=False))
conn.close()
