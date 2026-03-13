# Hashery Cloud Data Stack v1 – Dutchie + METRC

## 1. Purpose of this setup

Goal: give Hashery a simple, maintainable cloud data stack so you can analyze sales and inventory across **Dutchie + METRC** in one place, and later add more sources.

Primary uses in v1:
- Daily/weekly reporting (store performance, product performance).
- Inventory and compliance reconciliation between Dutchie and METRC.
- A foundation for dashboards and more advanced analytics later.


## 2. v1 scope

**In scope:**
- Data sources: Dutchie ERP, METRC (compliance).
- Platform: Google Cloud Platform (GCP).
- Storage + warehouse: Cloud Storage (GCS) + BigQuery.
- Ingestion: CSV exports (manual or semi-automated) into GCS, then loaded to BigQuery.
- Modeling: Raw → Staging → Analytics layers in BigQuery.

**Out of scope for v1 (future):**
- Real-time / streaming ingestion.
- Complex orchestration (Composer, full dbt project, etc.).
- Additional systems (accounting, marketing, etc.).


## 3. Core GCP architecture

**Project level:**
- Use a dedicated GCP project for analytics, e.g. `hashery-analytics`.

**Storage:**
- Create a Cloud Storage bucket, e.g. `gs://hashery-analytics-raw`.
- Organize folders by source and entity, for example:
  - `raw/dutchie/orders/`
  - `raw/dutchie/products/`
  - `raw/dutchie/inventory/`
  - `raw/metrc/packages/`
  - `raw/metrc/transfers/`

**Warehouse (BigQuery):**
- Create datasets to separate layers, e.g.:
  - `hashery_raw`
  - `hashery_staging`
  - `hashery_analytics`


## 4. Data sources and how they land

### 4.1 Dutchie (ERP / POS)

**Typical entities to bring in v1:**
- Orders / sales (line-level or order-level exports).
- Product catalog (SKUs, strain, category, brand).
- Inventory / stock levels.

**Ingestion pattern (v1):**
- Export CSVs from Dutchie reports on a regular cadence (start daily or weekly).
- Drop them into the appropriate GCS folders (e.g., `raw/dutchie/orders/2026/03/05/…`).
- Create corresponding BigQuery tables in `hashery_raw`, for example:
  - `raw_dutchie_orders`
  - `raw_dutchie_products`
  - `raw_dutchie_inventory`
- Define schemas to match the exported CSV fields.


### 4.2 METRC (compliance)

**What METRC tracks that matters for analytics:**
- Packages / inventory: package tags, item type, quantity, status.
- Transfers: inbound/outbound manifests, dates, source/destination.
- Recorded sales (if your market and setup use METRC for this).

**Ingestion pattern (v1):**
- Use METRC UI CSV exports for:
  - Packages list (active/archived).
  - Transfers (recent inbound/outbound).
  - Optionally sales, if available/exported.
- Save/export these CSVs into GCS under `raw/metrc/...`.
- Create `hashery_raw` tables:
  - `raw_metrc_packages`
  - `raw_metrc_transfers`
  - optionally `raw_metrc_sales`


## 5. Data modeling in BigQuery

Use a simple **three-layer** approach:

1. **Raw layer (`hashery_raw`)** – tables mirror source files.
   - Examples: `raw_dutchie_orders`, `raw_dutchie_products`, `raw_dutchie_inventory`, `raw_metrc_packages`, `raw_metrc_transfers`.
   - Changes allowed: basic type casting and ingestion metadata (e.g., `load_timestamp`).

2. **Staging layer (`hashery_staging`)** – cleaned and normalized tables.
   - Examples:
     - `stg_dutchie_orders`
     - `stg_dutchie_products`
     - `stg_dutchie_inventory`
     - `stg_metrc_packages`
     - `stg_metrc_transfers`
   - Typical tasks:
     - Cast fields to correct types (dates, numbers).
     - Standardize time zones.
     - Normalize text (case, trimming, canonical names).
     - Add derived helper columns (e.g., `order_date`, `is_medical` flags).

3. **Analytics layer (`hashery_analytics`)** – business-friendly facts and dimensions.
   - Examples:
     - Dimensions:
       - `dim_store` – one row per store/license (with Dutchie store ID + METRC license ID).
       - `dim_product` – one row per product/SKU (Dutchie IDs plus mapped METRC item/category if available).
       - `dim_metrc_package` – one row per package (tag, item, batch/harvest, current status).
     - Facts:
       - `fact_daily_sales` – daily sales per store/product (from Dutchie, optionally enriched with METRC IDs).
       - `fact_inventory_snapshot` – inventory levels per store/product (Dutchie) with METRC package counts joined in for reconciliation.


## 6. Join logic: Dutchie + METRC

To make the two systems talk to each other:

- **Store mapping:**
  - Create a small mapping table `map_store` (can live in `hashery_staging`):
    - Columns like `dutchie_store_id`, `metrc_license_number`, `store_name`, etc.

- **Product mapping:**
  - Create a `map_product` table to connect Dutchie products/variants to METRC items:
    - Columns like `dutchie_product_id`, `dutchie_sku`, `metrc_item_name`, `metrc_item_category`, `notes`.
  - Start by mapping your highest-volume SKUs; expand over time.

- **Package linkage (optional, as you refine):**
  - Where possible, associate Dutchie inventory / sales lines with specific METRC package tags.
  - Even if not 1:1 at first, having any linkage helps with reconciliation and audits.


## 7. First end‑to‑end use cases

Start with 1–2 concrete questions and build only what’s needed to answer them.

**Example Use Case A: Daily store & product performance**
- From Dutchie:
  - Aggregate orders into `fact_daily_sales` by date, store, product.
- In `dim_store` and `dim_product`, add attributes like region, product category, brand.
- Build a dashboard page showing:
  - Daily sales, units, discounts by store.
  - Top products by sales and units.

**Example Use Case B: Inventory & compliance reconciliation**
- From Dutchie:
  - Use `stg_dutchie_inventory` for on-hand quantities per product/store.
- From METRC:
  - Use `stg_metrc_packages` for quantities per package/license.
- In `fact_inventory_snapshot`:
  - Join Dutchie inventory to METRC packages via `map_store` and `map_product`.
  - Compare quantities to highlight mismatches.


## 8. How you’ll work with this day-to-day (v1)

1. Export CSVs from Dutchie and METRC to GCS folders.
2. Run BigQuery load jobs (or use UI) to append new data to raw tables.
3. Use SQL views or scheduled queries to refresh staging and analytics tables.
4. Connect a BI tool (e.g., Looker Studio / Looker) to `hashery_analytics` for dashboards.

As this stabilizes, replace manual exports with API-based ingestion and scheduled pipelines.


## 9. Future improvements (phase 2+)

Once v1 is stable and useful:

- **Automate ingestion:**
  - Use Cloud Scheduler + Cloud Functions / Workflows to pull or receive Dutchie and METRC data on a schedule into GCS, then trigger BigQuery loads.

- **Introduce dbt or similar:**
  - Manage transformations (`raw_` → `stg_` → `dim_`/`fact_`) as version-controlled models with tests and documentation.

- **More sources:**
  - Add accounting, marketing, e‑commerce, GA4, etc. into the same warehouse.

- **Governance & performance:**
  - Implement access controls by dataset.
  - Partition/cluster large tables by date to control cost and query speed.


## 10. Clarifying questions to answer next time

When you pick this back up, it will help to answer (even roughly) some of these:

1. **Business priorities**
   - Which matters more first: store performance reporting, product/assortment optimization, or compliance reconciliation?
   - Who will use the dashboards (owners, managers, budtenders)?

2. **Data freshness and cadence**
   - Is daily data load enough, or do you eventually want near-real-time (hourly) for some metrics?
   - On which days/times does it make sense to run loads (e.g., overnight)?

3. **Dutchie details**
   - Exactly which Dutchie reports/exports will you use (names, paths, fields)?
   - Do you get order lines (per product per order) or only summarized sales?

4. **METRC details**
   - Which METRC CSVs will you start with: packages, transfers, sales?
   - How are licenses/stores organized (one license per store, or more complex)?

5. **Reporting and tools**
   - Which BI tool will you use first (e.g., Looker Studio, Looker, others)?
   - Do you have any must-have reports from day one (e.g., weekly GM by category)?


## 11. Ready-made prompts for “future Diego”

When you come back to this, you can paste any of these directly to get specific help:

1. **Schema design for raw and staging**
   > "I’m ready to design the exact BigQuery schemas for `raw_dutchie_orders`, `raw_dutchie_products`, `raw_dutchie_inventory`, `raw_metrc_packages`, and `raw_metrc_transfers`. Assume the data comes from standard CSV exports. Help me propose column names, types, and keys, and show the CREATE TABLE statements."

2. **Designing the analytics layer**
   > "Help me design the `hashery_analytics` layer: `dim_store`, `dim_product`, `dim_metrc_package`, `fact_daily_sales`, and `fact_inventory_snapshot`. I want column lists, grain definitions, and example SQL to build them from the staging tables."

3. **Building the store and product mapping tables**
   > "Help me design `map_store` and `map_product` tables to link Dutchie stores/products to METRC licenses/items. I want suggested columns, key strategies, and workflows for keeping these mappings up to date."

4. **Reconciliation logic**
   > "Show me SQL examples in BigQuery for a `fact_inventory_reconciliation` table that compares Dutchie inventory to METRC package quantities by store/license and product. I want to flag and rank discrepancies."

5. **Automating ingestion later**
   > "I have v1 working with manual CSV drops to GCS. Help me design a phase‑2 ingestion pipeline using Cloud Scheduler + Cloud Functions or Workflows (and optionally dbt) to automatically pull data from Dutchie and METRC into GCS and then into BigQuery."

6. **Dashboard design**
   > "Using the `hashery_analytics` tables we discussed, help me outline the key pages and charts for an executive dashboard: store performance, product performance, and compliance reconciliation. Include the exact metrics and dimensions for each visual."

Use this doc as your anchor. Once you answer some of the clarifying questions and pick a first use case, you can feed that context back in along with one of the prompts above to get very concrete next steps.
