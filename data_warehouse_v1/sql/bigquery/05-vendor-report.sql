SELECT v.vendor_name,
    COUNT(*) AS receive_count,
    SUM(f.order_total) AS total_spend,
    AVG(f.order_total) AS avg_order
FROM `hasherynj-data-warehouse.analytics.fact_receiving` f
    JOIN `hasherynj-data-warehouse.analytics.dim_vendor` v ON f.vendor_license_key = v.vendor_code_key
WHERE f.delivered_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY v.vendor_name
ORDER BY total_spend DESC;
