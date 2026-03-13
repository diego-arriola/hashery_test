# Hashery Data Warehouse SQL Bundle

## Vendor Pipeline - March 13, 2026

### Save as separate .sql files in hashery_test/sql/bigquery/

## 01-raw-vendors-clean.sql

```sql
CREATE OR REPLACE TABLE `hasherynj-data-warehouse.raw.vendors_clean` AS
SELECT
  CAST(`Vendor ID` AS STRING) AS vendor_id,
  `Vendor name` AS vendor_name,
  `Vendor code` AS vendor_code,
  `City` AS vendor_city,
  CAST(`Country ID` AS STRING) AS country_id,
  `Contact name` AS contact_name,
  `Contact email` AS contact_email,
  `Abbreviation` AS vendor_abbrev,
  `Vendor type ID` AS vendor_type_id,
  `Notes` AS notes,
  CURRENT_TIMESTAMP() AS load_ts
FROM `hasherynj-data-warehouse.raw.vendor_catalog`;
```

## 02-stg-vendor-catalog.sql

```sql
CREATE OR REPLACE VIEW `hasherynj-data-warehouse.staging.stg_vendor_catalog` AS
SELECT
  vendor_id,
  UPPER(TRIM(vendor_name)) AS vendor_name_key,
  UPPER(TRIM(vendor_code)) AS vendor_code_key,
  UPPER(TRIM(vendor_abbrev)) AS vendor_abbrev_key,
  vendor_city,
  contact_name,
  contact_email,
  vendor_type_id,
  load_ts
FROM `hasherynj-data-warehouse.raw.vendors_clean`;
```

## 03-dim-vendor.sql

```sql
CREATE OR REPLACE TABLE `hasherynj-data-warehouse.analytics.dim_vendor` AS
WITH dedup AS (
  SELECT
    vendor_id,
    vendor_name,
    vendor_code,
    vendor_abbrev,
    vendor_city,
    contact_name,
    contact_email,
    vendor_type_id,
    ROW_NUMBER() OVER (
      PARTITION BY COALESCE(vendor_code_key, vendor_abbrev_key, vendor_name_key)
      ORDER BY load_ts DESC
    ) AS rn
  FROM `hasherynj-data-warehouse.staging.stg_vendor_catalog`
)
SELECT *
FROM dedup
WHERE rn = 1;
```

## 04-validate-vendor-join.sql

```sql
SELECT
  COUNT(*) AS total_receives,
  COUNTIF(v.vendor_name IS NOT NULL) AS matched,
  COUNTIF(vendor_code_key IS NOT NULL) AS code_matched
FROM `hasherynj-data-warehouse.analytics.fact_receiving` f
LEFT JOIN `hasherynj-data-warehouse.analytics.dim_vendor` v
  ON f.vendor_license_key = v.vendor_code_key
  OR f.vendor_name_key = v.vendor_name_key;
```

## 05-vendor-report.sql

```sql
SELECT
  v.vendor_name,
  COUNT(*) AS receive_count,
  SUM(f.order_total) AS total_spend,
  AVG(f.order_total) AS avg_order
FROM `hasherynj-data-warehouse.analytics.fact_receiving` f
JOIN `hasherynj-data-warehouse.analytics.dim_vendor` v ON f.vendor_license_key = v.vendor_code_key
WHERE f.delivered_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY v.vendor_name
ORDER BY total_spend DESC;
```

**Run order: 01 → 02 → 03 → 04 (validate) → 05 (report)**
**Update dates/columns as CSVs change.**
