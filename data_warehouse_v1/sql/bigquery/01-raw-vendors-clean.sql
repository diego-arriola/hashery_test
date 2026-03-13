CREATE OR REPLACE TABLE `hasherynj-data-warehouse.raw.vendors_clean` AS
SELECT CAST(`Vendor ID` AS STRING) AS vendor_id,
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
