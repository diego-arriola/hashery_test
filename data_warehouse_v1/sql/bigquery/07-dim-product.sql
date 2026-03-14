CREATE OR REPLACE TABLE `hasherynj-data-warehouse.analytics.dim_product` AS
SELECT -- stable key
    UPPER(TRIM(SKU)) AS product_key,
    -- identifiers / naming
    SKU AS sku,
    product_name AS product_name,
    -- core attributes (adjust to your actual column names)
    Category AS product_category,
    Brand AS brand_name,
    Strain AS strain_name,
    -- basic flags if present
    is_retired AS is_retired,
    is_available_online AS is_available_online,
    CURRENT_TIMESTAMP() AS rebuild_ts
FROM `hasherynj-data-warehouse.staging.stg_product_catalog`
WHERE SKU IS NOT NULL;
