/* ============================================================
   MASTER DATA GOVERNANCE — PRICING DOMAIN
   03_pricing_exception_audit.sql

   Purpose: isolate every category of pricing risk BEFORE the file
   is ingested into the downstream billing/ERP system — catching
   these here prevents invoice discrepancies later.

   Written for SQLite. Window functions (ROW_NUMBER, COUNT OVER)
   are ANSI-standard and run unchanged on Postgres / SQL Server.
   ============================================================ */

DROP TABLE IF EXISTS pricing_raw;
CREATE TABLE pricing_raw (
    SKU             TEXT,
    ProductName     TEXT,
    Category        TEXT,
    VendorID        TEXT,
    ListPrice       TEXT,   -- kept as TEXT on load so blanks/negatives surface, cast in queries
    DiscountPct     TEXT,
    NetPrice        TEXT,
    EffectiveDate   TEXT,
    PriceListSource TEXT
);
-- Loaded via pandas df.to_sql("pricing_raw", conn, if_exists="replace")

-- Policy reference table: authorized max discount % per category.
-- In production this would come from a pricing-governance system;
-- here it's the control your audit checks every row against.
DROP TABLE IF EXISTS discount_policy;
CREATE TABLE discount_policy (Category TEXT, MaxAuthorizedDiscount REAL);
INSERT INTO discount_policy (Category, MaxAuthorizedDiscount) VALUES
    ('Electronics', 0.20), ('Office Supplies', 0.15), ('Furniture', 0.25),
    ('Industrial', 0.10), ('Packaging', 0.15), ('Apparel', 0.30),
    ('Hardware', 0.20), ('Software', 0.35);

/* ------------------------------------------------------------
   EXCEPTION 1: Duplicate SKU with conflicting price
   A SKU should have exactly one active list price. Multiple
   distinct prices for the same SKU means two source systems (or
   two data-entry events) disagree — a direct invoice-mismatch risk.
   ------------------------------------------------------------ */
DROP TABLE IF EXISTS exception_duplicate_sku_pricing;
CREATE TABLE exception_duplicate_sku_pricing AS
SELECT
    SKU,
    COUNT(DISTINCT ROUND(CAST(ListPrice AS REAL), 2)) AS distinct_prices_found,
    GROUP_CONCAT(DISTINCT ROUND(CAST(ListPrice AS REAL), 2)) AS conflicting_prices,
    GROUP_CONCAT(DISTINCT PriceListSource) AS sources_involved,
    COUNT(*) AS row_count
FROM pricing_raw
WHERE ListPrice NOT IN ('', '0') AND CAST(ListPrice AS REAL) > 0
GROUP BY SKU
HAVING COUNT(DISTINCT ROUND(CAST(ListPrice AS REAL), 2)) > 1;

/* ------------------------------------------------------------
   EXCEPTION 2: Unauthorized discount (exceeds category policy)
   ------------------------------------------------------------ */
DROP TABLE IF EXISTS exception_unauthorized_discount;
CREATE TABLE exception_unauthorized_discount AS
SELECT
    p.SKU, p.ProductName, p.Category, p.VendorID,
    CAST(p.DiscountPct AS REAL)         AS discount_applied,
    d.MaxAuthorizedDiscount             AS discount_authorized,
    ROUND(CAST(p.DiscountPct AS REAL) - d.MaxAuthorizedDiscount, 3) AS discount_overage
FROM pricing_raw p
JOIN discount_policy d ON p.Category = d.Category
WHERE CAST(p.DiscountPct AS REAL) > d.MaxAuthorizedDiscount
ORDER BY discount_overage DESC;

/* ------------------------------------------------------------
   EXCEPTION 3: Zero, negative, or missing price
   ------------------------------------------------------------ */
DROP TABLE IF EXISTS exception_invalid_price;
CREATE TABLE exception_invalid_price AS
SELECT SKU, ProductName, Category, VendorID, ListPrice, PriceListSource
FROM pricing_raw
WHERE ListPrice = '' OR CAST(ListPrice AS REAL) <= 0;

/* ------------------------------------------------------------
   EXCEPTION 4: NetPrice does not equal ListPrice x (1 - Discount)
   Catches formula/calc errors introduced during manual entry or
   a broken ETL step, independent of whether the discount itself
   is authorized.
   ------------------------------------------------------------ */
DROP TABLE IF EXISTS exception_netprice_mismatch;
CREATE TABLE exception_netprice_mismatch AS
SELECT
    SKU, ProductName, Category,
    CAST(ListPrice AS REAL)     AS list_price,
    CAST(DiscountPct AS REAL)   AS discount_pct,
    CAST(NetPrice AS REAL)      AS net_price_reported,
    ROUND(CAST(ListPrice AS REAL) * (1 - CAST(DiscountPct AS REAL)), 2) AS net_price_expected,
    ROUND(CAST(NetPrice AS REAL) - (CAST(ListPrice AS REAL) * (1 - CAST(DiscountPct AS REAL))), 2) AS variance
FROM pricing_raw
WHERE ListPrice NOT IN ('', '0') AND NetPrice != ''
  AND ABS(CAST(NetPrice AS REAL) - (CAST(ListPrice AS REAL) * (1 - CAST(DiscountPct AS REAL)))) > 0.5;

/* ------------------------------------------------------------
   SUMMARY: exception counts for the scorecard
   ------------------------------------------------------------ */
SELECT 'Duplicate SKU pricing'   AS exception_type, COUNT(*) AS row_count FROM exception_duplicate_sku_pricing
UNION ALL
SELECT 'Unauthorized discount',   COUNT(*) FROM exception_unauthorized_discount
UNION ALL
SELECT 'Invalid price (<=0/null)', COUNT(*) FROM exception_invalid_price
UNION ALL
SELECT 'NetPrice calc mismatch', COUNT(*) FROM exception_netprice_mismatch;
