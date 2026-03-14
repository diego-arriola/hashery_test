CREATE OR REPLACE TABLE `hasherynj-data-warehouse.analytics.fact_receiving` AS
SELECT -- business keys
    CAST(invoice_id AS STRING) AS invoice_id,
    CAST(store_id AS STRING) AS store_id,
    CAST(sku AS STRING) AS sku,
    -- dimension keys
    UPPER(TRIM(vendor)) AS vendor_key,
    UPPER(TRIM(sku)) AS product_key,
    -- descriptive
    vendor,
    -- dates
    invoice_date_clean AS invoice_date,
    -- metrics (cleaned)
    qty_clean AS qty,
    unit_price_clean AS unit_price,
    extended_clean AS extended,
    -- derived metric
    CASE
        WHEN qty_clean IS NOT NULL
        AND qty_clean != 0 THEN extended_clean / qty_clean
        ELSE NULL
    END AS effective_unit_price
FROM `hasherynj-data-warehouse.staging.stg_receiving_invoices`;
