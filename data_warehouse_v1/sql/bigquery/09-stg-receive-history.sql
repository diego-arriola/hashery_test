CREATE OR REPLACE VIEW `hasherynj-data-warehouse.staging.stg_receive_history` AS WITH base AS (
        SELECT Title AS title_raw,
            `PO #` AS po_number_raw,
            `PO Name` AS po_name_raw,
            `Transaction ID` AS transaction_id,
            Vendor AS vendor_name_raw,
            `Vendor license #` AS vendor_license_raw,
            UPPER(TRIM(Vendor)) AS vendor_name_key_raw,
            UPPER(TRIM(`Vendor license #`)) AS vendor_license_key_raw,
            `Delivered on` AS delivered_on_raw,
            Status AS status_raw,
            Paid AS paid_raw,
            `Products` AS products_raw,
            `Order total` AS order_total_raw,
            `VCCB transfer ID` AS vccb_transfer_id,
            `VCCB transfer date` AS vccb_transfer_date_raw,
            `Received by` AS received_by,
            `Delivered by` AS delivered_by
        FROM `hasherynj-data-warehouse.raw.receive_history`
    ),
    -- 1) license -> vendor name map (rows that have both)
    license_to_name AS (
        SELECT UPPER(TRIM(`Vendor license #`)) AS vendor_license_key,
            ANY_VALUE(Vendor) AS vendor_name_fallback
        FROM `hasherynj-data-warehouse.raw.receive_history`
        WHERE `Vendor license #` IS NOT NULL
            AND `Vendor license #` != ''
            AND Vendor IS NOT NULL
            AND Vendor != ''
        GROUP BY vendor_license_key
    ),
    -- 2) name -> license map (rows that have both)
    name_to_license AS (
        SELECT UPPER(TRIM(Vendor)) AS vendor_name_key,
            ANY_VALUE(`Vendor license #`) AS vendor_license_fallback
        FROM `hasherynj-data-warehouse.raw.receive_history`
        WHERE Vendor IS NOT NULL
            AND Vendor != ''
            AND `Vendor license #` IS NOT NULL
            AND `Vendor license #` != ''
        GROUP BY vendor_name_key
    ),
    imputed AS (
        SELECT b.*,
            -- Step A: clean license key (raw or from name_to_license)
            COALESCE(
                b.vendor_license_key_raw,
                UPPER(TRIM(name_to_license.vendor_license_fallback))
            ) AS vendor_license_key_stage,
            -- Step B: clean name key (raw or from license_to_name)
            COALESCE(
                b.vendor_name_key_raw,
                UPPER(TRIM(license_to_name.vendor_name_fallback))
            ) AS vendor_name_key_stage,
            -- flags: did we fill anything from maps?
            b.vendor_license_raw IS NULL
            AND name_to_license.vendor_license_fallback IS NOT NULL AS vendor_license_imputed_flag_map,
            b.vendor_name_raw IS NULL
            AND license_to_name.vendor_name_fallback IS NOT NULL AS vendor_name_imputed_flag_map
        FROM base b
            LEFT JOIN name_to_license ON b.vendor_name_key_raw = name_to_license.vendor_name_key
            LEFT JOIN license_to_name ON b.vendor_license_key_raw = license_to_name.vendor_license_key
    ),
    -- Optional: parse vendor name from title when still null
    with_title AS (
        SELECT i.*,
            CASE
                WHEN vendor_name_key_stage IS NULL
                AND title_raw LIKE '% - % - %' -- pattern: "MM/DD/YYYY - Vendor Name - 0001234567"
                THEN UPPER(TRIM(SPLIT(title_raw, ' - ') [OFFSET(1)]))
                ELSE vendor_name_key_stage
            END AS vendor_name_key_final
        FROM imputed i
    )
SELECT -- identifiers
    title_raw,
    po_number_raw,
    po_name_raw,
    transaction_id,
    -- final vendor fields
    vendor_name_raw,
    vendor_license_raw,
    vendor_name_key_final AS vendor_name_key,
    vendor_license_key_stage AS vendor_license_key,
    -- imputation flags
    vendor_license_imputed_flag_map AS vendor_license_imputed_flag,
    vendor_name_imputed_flag_map
    OR (
        vendor_name_key_stage IS NULL
        AND vendor_name_key_final IS NOT NULL
    ) AS vendor_name_imputed_flag,
    -- timestamps
    delivered_on_raw,
    PARSE_TIMESTAMP(
        '%m/%d/%Y %I:%M %p',
        delivered_on_raw,
        'America/New_York'
    ) AS delivered_on_utc,
    PARSE_DATETIME('%m/%d/%Y %I:%M %p', delivered_on_raw) AS delivered_on_et,
    DATE(
        PARSE_TIMESTAMP(
            '%m/%d/%Y %I:%M %p',
            delivered_on_raw,
            'America/New_York'
        )
    ) AS delivered_date,
    -- metrics
    SAFE_CAST(order_total_raw AS NUMERIC) AS order_total,
    SAFE_CAST(products_raw AS INT64) AS products_count,
    -- status / payment
    status_raw,
    CASE
        WHEN UPPER(TRIM(status_raw)) = 'RECEIVED' THEN 'RECEIVED'
        WHEN UPPER(TRIM(status_raw)) = 'PENDING' THEN 'PENDING'
        ELSE 'OTHER'
    END AS status_clean,
    paid_raw,
    CAST(paid_raw AS BOOL) AS paid_bool,
    -- users / VCCB
    received_by,
    delivered_by,
    vccb_transfer_id,
    vccb_transfer_date_raw
FROM with_title;
