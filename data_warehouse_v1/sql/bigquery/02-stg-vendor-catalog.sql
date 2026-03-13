CREATE OR REPLACE VIEW `hasherynj-data-warehouse.staging.stg_vendor_catalog` AS
SELECT vendor_id,
    UPPER(TRIM(vendor_name)) AS vendor_name_key,
    UPPER(TRIM(vendor_code)) AS vendor_code_key,
    UPPER(TRIM(vendor_abbrev)) AS vendor_abbrev_key,
    vendor_city,
    contact_name,
    contact_email,
    vendor_type_id,
    load_ts
FROM `hasherynj-data-warehouse.raw.vendors_clean`;
