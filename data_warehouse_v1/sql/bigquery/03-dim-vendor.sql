CREATE OR REPLACE TABLE `hasherynj-data-warehouse.analytics.dim_vendor` AS
SELECT -- cleaned, consistent key based on vendor name text
    UPPER(TRIM(vendor)) AS vendor_key,
    UPPER(TRIM(vendor)) AS vendor_name,
    -- simple metrics
    COUNT(*) AS invoice_line_count,
    COUNT(DISTINCT invoice_id) AS distinct_invoices
FROM `hasherynj-data-warehouse.staging.stg_receiving_invoices`
WHERE vendor IS NOT NULL
GROUP BY UPPER(TRIM(vendor));
