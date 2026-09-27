/* ============================================================
   MASTER DATA GOVERNANCE — VENDOR & PRODUCT DOMAINS
   04_vendor_product_cleansing.sql

   Mirrors 01_schema_and_cleansing.sql's approach for Customer:
   raw table preserved as-is, a cleansed/standardized table built
   from it, and a blocking key prepared for the fuzzy-match step.

   Vendor and Product have different natural-key situations, which
   is worth calling out explicitly in an interview:
     - Vendor has TaxID, a strong natural key. Block on it FIRST,
       and treat name+state as a fallback for mis-keyed TaxIDs.
     - Product has NO reliable natural key across duplicates (a
       re-entered product gets a brand new SKU), so blocking must
       lean on Category + Vendor + a name fragment instead.
   ============================================================ */

-- Loaded via pandas: vdf.to_sql("vendor_raw", conn, if_exists="replace")
--                     pdf.to_sql("product_raw", conn, if_exists="replace")

DROP TABLE IF EXISTS vendor_cleansed;
CREATE TABLE vendor_cleansed AS
SELECT
    VendorID,
    TRIM(VendorName)                                            AS VendorName,
    TRIM(TaxID)                                                 AS TaxID,
    TRIM(ContactName)                                           AS ContactName,
    LOWER(TRIM(Email))                                          AS Email,
    TRIM(Phone)                                                 AS Phone,   -- re-formatted in Python (see pipeline script)
    TRIM(AddressLine1)                                          AS AddressLine1,
    TRIM(City)                                                  AS City,
    UPPER(TRIM(State))                                          AS State,
    TRIM(PostalCode)                                            AS PostalCode,
    CASE WHEN UPPER(TRIM(Country)) IN ('USA','US','U.S.A.','UNITED STATES') THEN 'USA'
         ELSE UPPER(TRIM(Country)) END                          AS Country,
    UPPER(TRIM(PaymentTerms))                                   AS PaymentTerms,
    TRIM(Status)                                                AS Status,
    -- Primary blocking key: TaxID is the strongest natural key for a vendor
    TRIM(TaxID)                                                 AS BlockKey_TaxID,
    -- Fallback blocking key: first 5 letters of the name (letters only) + state,
    -- used when TaxID itself was mis-keyed
    UPPER(SUBSTR(REPLACE(REPLACE(REPLACE(TRIM(VendorName),' ',''),'.',''),',',''), 1, 5))
        || '-' || UPPER(TRIM(State))                            AS BlockKey_Name
FROM vendor_raw;

DROP TABLE IF EXISTS product_cleansed;
CREATE TABLE product_cleansed AS
SELECT
    SKU,
    TRIM(ProductName)                                           AS ProductName,
    TRIM(Category)                                              AS Category,
    TRIM(VendorID)                                               AS VendorID,
    UPPER(TRIM(UnitOfMeasure))                                  AS UnitOfMeasure,
    TRIM(Status)                                                AS Status,
    -- No natural key survives a re-entry, so block on Category + Vendor +
    -- a short name fragment together — narrow enough to limit comparisons,
    -- broad enough to survive a typo in the fragment itself.
    UPPER(SUBSTR(TRIM(Category), 1, 4)) || '-' ||
    SUBSTR(TRIM(VendorID), -4) || '-' ||
    UPPER(SUBSTR(REPLACE(TRIM(ProductName), ' ', ''), 1, 4))    AS BlockKey
FROM product_raw;

-- Completeness baselines (before dedup) for the scorecard
SELECT 'Vendor' AS Domain,
    ROUND(100.0 * SUM(CASE WHEN Email!='' AND Phone!='' AND AddressLine1!='' AND TaxID!='' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_complete_before,
    COUNT(*) AS total_rows
FROM vendor_cleansed
UNION ALL
SELECT 'Product',
    ROUND(100.0 * SUM(CASE WHEN VendorID!='' AND UnitOfMeasure!='' THEN 1 ELSE 0 END) / COUNT(*), 1),
    COUNT(*)
FROM product_cleansed;
