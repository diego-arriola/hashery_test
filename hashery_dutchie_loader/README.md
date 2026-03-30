# hashery_dutchie_loader

A Flask-based microservice deployed on **Google Cloud Run** that pulls data from the **Dutchie POS API** and loads it into **BigQuery** raw tables. It powers the Hashery data warehouse by keeping inventory and product catalog data fresh.

---

## What Was Built

### Overview
This service exposes HTTP endpoints that, when triggered (e.g., by Cloud Scheduler), fetch live data from Dutchie and do a full `WRITE_TRUNCATE` load into BigQuery raw tables.

### Architecture
```
Cloud Scheduler
      │
      ▼
  Cloud Run (this service)
      │
      ├── GET /load_inventory  ──▶  Dutchie API (/reporting/inventory)
      │                                   └──▶  BigQuery: raw.current_inventory
      │
      └── GET /load_products   ──▶  Dutchie API (/products)
                                          └──▶  BigQuery: raw.product_catalog
```

### Key Details
| Item | Value |
|---|---|
| GCP Project | `hasherynj-data-warehouse` |
| BigQuery Dataset | `raw` |
| Inventory Table | `raw.current_inventory` |
| Products Table | `raw.product_catalog` |
| Secret | `dutchie-api-key` (via Secret Manager) |
| Port | `8080` |
| Base Image | `python:3.12-slim` |

### Endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/load_inventory` | GET / POST | Fetches inventory from Dutchie and truncates+loads into BigQuery |
| `/load_products` | GET / POST | Fetches product catalog from Dutchie and truncates+loads into BigQuery |
| `/health` | GET | Healthcheck — returns `{"status": "ok"}` |

### Authentication
The Dutchie API uses **HTTP Basic Auth**. The API key is stored in **GCP Secret Manager** under the secret name `dutchie-api-key`. The app retrieves it at runtime via the `google-cloud-secret-manager` library and base64-encodes it as `key:` (no password).

### Column Sanitization
BigQuery doesn't allow special characters in column names. The `sanitize_columns_for_bigquery()` function:
1. Replaces dots (`.`) with underscores
2. Replaces any remaining non-alphanumeric/underscore characters
3. Collapses repeated underscores
4. Strips leading/trailing underscores

---

## Files
```
hashery_dutchie_loader/
├── app.py            # Main Flask app — all endpoints and BQ load logic
├── Dockerfile        # Container build config (python:3.12-slim)
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

---

## Adding a New Store

If Hashery opens a new location and you need to ingest its Dutchie data separately, follow these steps:

### 1. Get the New Store's Dutchie API Key
- Obtain the API key from the Dutchie dashboard for the new store.
- Store it in **GCP Secret Manager** with a new secret name, e.g., `dutchie-api-key-store2`.

### 2. Add New BigQuery Tables
In BigQuery under the `hasherynj-data-warehouse` project, create the new raw tables for the store:
```sql
CREATE TABLE IF NOT EXISTS `hasherynj-data-warehouse.raw.current_inventory_store2` AS
SELECT * FROM `hasherynj-data-warehouse.raw.current_inventory` WHERE FALSE;

CREATE TABLE IF NOT EXISTS `hasherynj-data-warehouse.raw.product_catalog_store2` AS
SELECT * FROM `hasherynj-data-warehouse.raw.product_catalog` WHERE FALSE;
```

### 3. Update `app.py`
Add a new secret retrieval function and new load routes for the store. Follow the existing pattern:

```python
# New secret retrieval
def get_dutchie_api_key_store2() -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/dutchie-api-key-store2/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")

# New table IDs
INVENTORY_TABLE_STORE2 = f"{PROJECT_ID}.raw.current_inventory_store2"
PRODUCTS_TABLE_STORE2  = f"{PROJECT_ID}.raw.product_catalog_store2"

# New endpoints
@app.route("/load_inventory_store2", methods=["POST", "GET"])
def load_inventory_store2():
    ...

@app.route("/load_products_store2", methods=["POST", "GET"])
def load_products_store2():
    ...
```

### 4. Grant Secret Manager Access
Make sure the Cloud Run service account has `secretmanager.secretAccessor` on the new secret:
```bash
gcloud secrets add-iam-policy-binding dutchie-api-key-store2 \
  --member="serviceAccount:<YOUR_CLOUD_RUN_SA>@hasherynj-data-warehouse.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 5. Redeploy the Cloud Run Service
After updating `app.py`, rebuild and redeploy:
```bash
gcloud builds submit --tag gcr.io/hasherynj-data-warehouse/hashery-dutchie-loader
gcloud run deploy hashery-dutchie-loader \
  --image gcr.io/hasherynj-data-warehouse/hashery-dutchie-loader \
  --region us-east1 \
  --platform managed
```

### 6. Add Cloud Scheduler Jobs
Create new Scheduler jobs targeting the new endpoints:
```bash
gcloud scheduler jobs create http load-inventory-store2 \
  --schedule="0 * * * *" \
  --uri="https://<CLOUD_RUN_URL>/load_inventory_store2" \
  --http-method=GET \
  --location=us-east1

gcloud scheduler jobs create http load-products-store2 \
  --schedule="0 6 * * *" \
  --uri="<CLOUD_RUN_URL>/load_products_store2" \
  --http-method=GET \
  --location=us-east1
```

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set up Application Default Credentials (for Secret Manager + BigQuery access)
gcloud auth application-default login

# Run locally
python app.py
# Server starts on http://localhost:8080
```
