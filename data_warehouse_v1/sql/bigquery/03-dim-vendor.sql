CREATE OR REPLACE TABLE `hasherynj-data-warehouse.analytics.dim_vendor` AS WITH dedup AS (
        SELECT vendor_id,
            vendor_name,
            vendor_code,
            vendor_abbrev,
            vendor_city,
            contact_name,
            contact_email,
            vendor_type_id,
            ROW_NUMBER() OVER (
                PARTITION BY COALESCE(
                    vendor_code_key,
                    vendor_abbrev_key,
                    vendor_name_key
                )
                ORDER BY load_ts DESC
            ) AS rn
        FROM `hasherynj-data-warehouse.staging.stg_vendor_catalog`
    )
SELECT *
FROM dedup
WHERE rn = 1;
