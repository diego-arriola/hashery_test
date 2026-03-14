CREATE OR REPLACE TABLE `hasherynj-data-warehouse.analytics.fact_receive_history` AS
SELECT -- keys
    transaction_id,
    po_number_raw,
    po_name_raw,
    vendor_name_key,
    vendor_license_key,
    -- descriptive
    title_raw,
    vendor_name_raw,
    vendor_license_raw,
    vendor_name_imputed_flag,
    vendor_license_imputed_flag,
    -- dates / times
    delivered_on_utc,
    delivered_on_et,
    delivered_date,
    -- metrics
    order_total,
    products_count,
    -- status / payment
    status_raw,
    status_clean,
    paid_raw,
    paid_bool,
    -- users
    received_by,
    delivered_by,
    -- VCCB
    vccb_transfer_id,
    vccb_transfer_date_raw
FROM `hasherynj-data-warehouse.staging.stg_receive_history`;
