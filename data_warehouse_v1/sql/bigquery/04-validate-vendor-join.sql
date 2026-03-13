SELECT COUNT(*) AS total_receives,
    COUNTIF(v.vendor_name IS NOT NULL) AS matched,
    COUNTIF(vendor_code_key IS NOT NULL) AS code_matched
FROM `hasherynj-data-warehouse.analytics.fact_receiving` f
    LEFT JOIN `hasherynj-data-warehouse.analytics.dim_vendor` v ON f.vendor_license_key = v.vendor_code_key
    OR f.vendor_name_key = v.vendor_name_key;
