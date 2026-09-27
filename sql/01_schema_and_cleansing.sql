/* ============================================================
   MASTER DATA GOVERNANCE — CUSTOMER DOMAIN
   01_schema_and_cleansing.sql

   Purpose: load the raw intake file as-is, then produce a
   standardized/cleansed table ready for deduplication.

   Written for SQLite (portable, zero-setup demo). Postgres /
   SQL Server equivalents are noted in comments where syntax
   differs, so you can speak to either in an interview.
   ============================================================ */

-- 1. RAW TABLE — exact mirror of the intake file. Never edit this table;
--    it is your audit trail / "as received" snapshot.
DROP TABLE IF EXISTS customers_raw;
CREATE TABLE customers_raw (
    CustomerID     TEXT,
    FirstName      TEXT,
    LastName       TEXT,
    CompanyName    TEXT,
    Email          TEXT,
    Phone          TEXT,
    AddressLine1   TEXT,
    City           TEXT,
    State          TEXT,
    PostalCode     TEXT,
    Country        TEXT,
    CreatedDate    TEXT
);
-- Loaded via: .import --csv customer_master_raw.csv customers_raw  (sqlite3 CLI)
-- or pandas df.to_sql("customers_raw", conn, if_exists="replace")

-- 2. VALIDATION FLAGS — tag records with quality issues BEFORE fixing them.
--    This table is what your weekly defect-rate scorecard reads from.
DROP TABLE IF EXISTS customers_validation_log;
CREATE TABLE customers_validation_log AS
SELECT
    CustomerID,
    CASE WHEN TRIM(COALESCE(Email,''))    = '' THEN 1 ELSE 0 END AS missing_email,
    CASE WHEN TRIM(COALESCE(Phone,''))    = '' THEN 1 ELSE 0 END AS missing_phone,
    CASE WHEN TRIM(COALESCE(AddressLine1,'')) = '' THEN 1 ELSE 0 END AS missing_address,
    CASE WHEN TRIM(COALESCE(PostalCode,'')) = '' THEN 1 ELSE 0 END AS missing_postal,
    CASE WHEN Email NOT LIKE '%_@_%.__%' AND TRIM(COALESCE(Email,'')) != '' THEN 1 ELSE 0 END AS invalid_email_format
FROM customers_raw;

-- 3. CLEANSED / STANDARDIZED TABLE
--    - Trim whitespace on every text field
--    - Proper-case names, upper-case state/country codes
--    - Normalize country spelling variants to one value
--    - Strip phone numbers down to 10 digits, then re-format consistently
--    - Keep a normalized "match key" column used later for fuzzy blocking
DROP TABLE IF EXISTS customers_cleansed;
CREATE TABLE customers_cleansed AS
SELECT
    CustomerID,
    TRIM(FirstName)                                            AS FirstName,
    TRIM(LastName)                                             AS LastName,
    TRIM(CompanyName)                                          AS CompanyName,
    LOWER(TRIM(Email))                                         AS Email,
    -- Phone: strip everything except digits, keep last 10, re-format as (XXX) XXX-XXXX
    CASE
        WHEN LENGTH(
                REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                    TRIM(Phone),'(',''),')',''),'-',''),'.',''),' ',''),'+1','')
             ) >= 10
        THEN '(' || SUBSTR(
                REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                    TRIM(Phone),'(',''),')',''),'-',''),'.',''),' ',''),'+1',''),
                LENGTH(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                    TRIM(Phone),'(',''),')',''),'-',''),'.',''),' ',''),'+1','')) - 9, 3)
             || ') ' ||
             SUBSTR(
                REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                    TRIM(Phone),'(',''),')',''),'-',''),'.',''),' ',''),'+1',''),
                LENGTH(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                    TRIM(Phone),'(',''),')',''),'-',''),'.',''),' ',''),'+1','')) - 6, 3)
             || '-' ||
             SUBSTR(
                REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                    TRIM(Phone),'(',''),')',''),'-',''),'.',''),' ',''),'+1',''),
                LENGTH(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                    TRIM(Phone),'(',''),')',''),'-',''),'.',''),' ',''),'+1','')) - 3, 4)
        ELSE ''
    END                                                         AS Phone,
    TRIM(AddressLine1)                                          AS AddressLine1,
    TRIM(City)                                                  AS City,
    UPPER(TRIM(State))                                          AS State,
    TRIM(PostalCode)                                            AS PostalCode,
    -- Normalize country variants to one canonical value
    CASE
        WHEN UPPER(TRIM(Country)) IN ('USA','US','U.S.A.','UNITED STATES') THEN 'USA'
        ELSE UPPER(TRIM(Country))
    END                                                         AS Country,
    CreatedDate,
    -- Blocking key for fuzzy matching: first 3 letters of last name (upper)
    -- + first 3 digits of postal code. Cuts pairwise comparisons from
    -- O(n^2) down to comparisons only within the same block.
    UPPER(SUBSTR(TRIM(LastName), 1, 3)) || '-' || SUBSTR(TRIM(PostalCode), 1, 3) AS BlockKey
FROM customers_raw;

/* Postgres/SQL Server note: phone normalization above is written with
   nested REPLACE() for SQLite portability. In Postgres you'd write:
       REGEXP_REPLACE(phone, '[^0-9]', '', 'g')
   In SQL Server:
       dbo.fn_StripNonNumeric(phone)  -- via a scalar UDF, since T-SQL
       has no built-in REGEXP_REPLACE pre-2025.
*/

-- 4. QUICK COMPLETENESS METRIC (BEFORE dedup) — required fields populated
--    on ALL rows, duplicates included. This is your "before" baseline.
SELECT
    ROUND(100.0 * SUM(
        CASE WHEN Email != '' AND Phone != '' AND AddressLine1 != '' AND PostalCode != ''
             THEN 1 ELSE 0 END
    ) / COUNT(*), 1) AS pct_complete_before_dedup,
    COUNT(*) AS total_rows
FROM customers_cleansed;
