# Automated Receiving Pipeline Implementation Guide

**Prepared for:** The Hashery Data & IT Teams
**Prepared by:** Diego Arriola, Data Analyst
**Date:** February 25, 2026
**Purpose:** Step-by-step technical implementation guide for GCP-based receiving automation

---

## Overview

This guide walks a new analyst or data engineer through implementing the GCP-based automated receiving pipeline in phased steps, matching the business plan timelines. Each step includes code samples, testing procedures, and success criteria.

**Timeline:** 12 weeks total across 5 phases
**Stack:** Google Cloud Platform (GCS, Cloud Vision, Cloud Run, Cloud Functions, BigQuery, Secret Manager)
**Prerequisites:** GCP project access, METRC NJ API key, Slack workspace admin access

---

## Phase 1: Pilot (Weeks 1–4)

### Objectives

- Validate OCR accuracy on sample invoices/manifests from top 3 vendors
- Build METRC enrichment service and test with real package IDs
- Create GCS folder structure and access controls
- Develop basic Slack notification (no approval workflow yet)

---

### Step 1: Create GCP Project and Cloud Storage Bucket

**Time:** 30 minutes

**Actions:**

1. In Google Cloud Console, create or select the project for this pipeline.
2. Navigate to **Cloud Storage → Buckets → Create**.
3. Configure bucket:
   - Name: `hashery-receiving`
   - Location type: Regional
   - Region: `us-east1` (closest to NJ)
   - Default storage class: Standard
   - Access control: Uniform
4. Create the bucket.

**Folder Structure:**

Create this folder hierarchy in GCS:

```text
hashery-receiving/
├── store-1/
│   └── 2026/
│       └── 02/
│           └── 25/
│               └── vendor-curaleaf/
│                   ├── invoice-12345.pdf
│                   ├── manifest-1A4000.pdf
│                   └── processed/
├── store-2/
│   └── [same structure]
├── store-3/
│   └── [same structure]
└── templates/
    ├── dutchie-bulk-upload-template.csv
    └── vendor-catalog-mappings.json
```

**Success Test:**

- Upload a test PDF to `store-1/2026/02/25/vendor-test/test.pdf`.
- Verify the file appears in GCS Browser console.
- Download the file to confirm upload/download permissions work.

**Screenshot to capture:** GCS bucket browser showing folder structure with test file uploaded.

---

### Step 2: Enable APIs and Create Service Account

**Time:** 20 minutes

**Actions:**

1. Navigate to **APIs & Services → Library**.
2. Enable the following APIs:
   - Cloud Vision API
   - Cloud Functions API
   - Cloud Run API
   - Secret Manager API
   - BigQuery API
3. Navigate to **IAM & Admin → Service Accounts → Create Service Account**.
4. Create service account:
   - Name: `receiving-pipeline-sa`
   - ID: `receiving-pipeline-sa`
   - Description: "Service account for automated receiving pipeline"
5. Grant roles to service account:
   - Storage Object Admin (on `hashery-receiving` bucket)
   - Cloud Vision API User
   - Secret Manager Secret Accessor
   - BigQuery Data Editor
   - Cloud Functions Invoker
6. Create and download JSON key for local testing.

**Success Test:**

From Cloud Shell or local terminal with gcloud CLI:

```bash
# Authenticate as service account
gcloud auth activate-service-account receiving-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com   --key-file=service-account-key.json

# List bucket contents
gcloud storage ls gs://hashery-receiving/

# Expected output: folders you created in Step 1
```

If command succeeds and lists folders, permissions are correctly configured.

**Screenshot to capture:** IAM service account page showing roles assigned to `receiving-pipeline-sa`.

---

### Step 3: Store METRC API Credentials in Secret Manager

**Time:** 10 minutes

**Actions:**

1. Navigate to **Security → Secret Manager → Create Secret**.
2. Configure secret:
   - Name: `metrc-nj-api-key`
   - Secret value: _paste your METRC NJ API key_
   - Leave other settings as default
3. Click **Create Secret**.
4. Grant access to service account:
   - On the secret detail page, click **Permissions**.
   - Add principal: `receiving-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com`
   - Role: Secret Manager Secret Accessor

**Success Test:**

From Cloud Shell:

```bash
# Retrieve secret value
gcloud secrets versions access latest --secret=metrc-nj-api-key

# Expected output: your METRC API key value
```

**Screenshot to capture:** Secret Manager showing `metrc-nj-api-key` secret with permissions tab displaying service account access.

---

### Step 4: Implement OCR Function (Cloud Functions)

**Time:** 4–6 hours (includes testing and debugging)

**Purpose:** Automatically extract text from uploaded invoice and manifest PDFs using Cloud Vision API.

Create a new directory for your function:

```bash
mkdir ocr-function
cd ocr-function
```

Create `main.py`:

```python
import json
import re
import os
from google.cloud import vision, storage

vision_client = vision.ImageAnnotatorClient()
storage_client = storage.Client()


def process_pdf(event, context):
    """Triggered by GCS object finalize event.
    Extracts text from PDF using Cloud Vision OCR.
    """
    bucket_name = event['bucket']
    file_name = event['name']

    # Only process PDF files
    if not file_name.lower().endswith('.pdf'):
        print(f"Skipping non-PDF file: {file_name}")
        return

    # Skip already-processed files
    if '/processed/' in file_name or '-parsed.json' in file_name:
        print(f"Skipping processed file: {file_name}")
        return

    print(f"Processing {file_name} from bucket {bucket_name}")

    bucket = storage_client.bucket(bucket_name)
    gcs_uri = f"gs://{bucket_name}/{file_name}"

    # Determine document type from filename
    doc_type = 'manifest' if 'manifest' in file_name.lower() else 'invoice'

    # Call Cloud Vision API
    try:
        text = extract_text_from_pdf(gcs_uri)
        print(f"Extracted {len(text)} characters from {doc_type}")

        # Parse text into structured data
        if doc_type == 'invoice':
            line_items = parse_invoice(text)
        else:
            line_items = parse_manifest(text)

        # Save parsed JSON
        output_path = file_name.rsplit('.', 1)[0] + '-parsed.json'
        output_blob = bucket.blob(output_path)
        output_blob.upload_from_string(
            json.dumps(line_items, indent=2),
            content_type='application/json'
        )
        print(f"Saved parsed data to {output_path}")

    except Exception as e:
        print(f"Error processing {file_name}: {str(e)}")
        raise


def extract_text_from_pdf(gcs_uri):
    """Extract text from PDF using Cloud Vision API."""
    mime_type = 'application/pdf'
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
    gcs_source = vision.GcsSource(uri=gcs_uri)
    input_config = vision.InputConfig(gcs_source=gcs_source, mime_type=mime_type)

    # For single-page or small PDFs, use synchronous API
    request = vision.AnnotateFileRequest(
        input_config=input_config,
        features=[feature],
        pages=[1, 2, 3]  # Process first 3 pages
    )

    response = vision_client.annotate_file(request=request)

    # Concatenate text from all pages
    full_text = ""
    for page_response in response.responses:
        if page_response.full_text_annotation:
            full_text += page_response.full_text_annotation.text + "
"

    return full_text


def parse_invoice(text):
    """Parse invoice text into structured line items.
    TODO: Customize regex patterns for your specific vendors.
    """
    line_items = []

    # Example pattern for line items (customize for your vendors)
    # Looking for: Product Name | Quantity | Unit Price
    pattern = r'([A-Za-z0-9\s\-]+)\s+(\d+)\s+\$?([\d.]+)'

    for match in re.finditer(pattern, text):
        product_name = match.group(1).strip()
        quantity = int(match.group(2))
        unit_cost = float(match.group(3))

        line_items.append({
            "product_name": product_name,
            "quantity": quantity,
            "cost_per_unit": unit_cost,
            "price_per_unit": None,  # Will be filled from catalog or manual entry
            "source": "invoice"
        })

    # Extract invoice metadata
    invoice_num_match = re.search(r'Invoice\s*#?\s*:?\s*(\w+)', text, re.IGNORECASE)
    invoice_number = invoice_num_match.group(1) if invoice_num_match else "UNKNOWN"

    return {
        "invoice_number": invoice_number,
        "line_items": line_items
    }


def parse_manifest(text):
    """Parse METRC manifest text into structured data.
    TODO: Customize for NJ METRC manifest format.
    """
    line_items = []

    # Example pattern for METRC package IDs (1A4000...)
    package_pattern = r'(1A[A-Z0-9]{20,})'

    # Extract package IDs
    package_ids = re.findall(package_pattern, text)

    # Extract quantities (adjacent to package IDs typically)
    # This is highly dependent on manifest format - adjust as needed
    qty_pattern = r'(\d+)\s*(?:units?|ea|each)'
    quantities = re.findall(qty_pattern, text, re.IGNORECASE)

    # Pair package IDs with quantities
    for i, pkg_id in enumerate(package_ids):
        qty = int(quantities[i]) if i < len(quantities) else 1

        line_items.append({
            "package_id": pkg_id,
            "quantity": qty,
            "source": "manifest"
        })

    return {
        "manifest_type": "metrc",
        "line_items": line_items
    }
```

Create `requirements.txt`:

```text
google-cloud-vision==3.4.5
google-cloud-storage==2.14.0
```

**Deploy Function:**

```bash
gcloud functions deploy process-receiving-pdf   --gen2   --runtime=python311   --region=us-east1   --source=.   --entry-point=process_pdf   --trigger-event-filters="type=google.cloud.storage.object.v1.finalized"   --trigger-event-filters="bucket=hashery-receiving"   --service-account=receiving-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com   --timeout=300s   --memory=512MB
```

**Success Test:**

1. Upload a sample invoice PDF to GCS: `store-1/2026/02/25/vendor-test/invoice-001.pdf`.
2. Wait 10–30 seconds for function to trigger.
3. Check Cloud Functions logs:
   - Navigate to **Cloud Functions → process-receiving-pdf → Logs**.
   - Look for "Processing invoice-001.pdf" and "Saved parsed data" messages.
4. Download the generated JSON file: `invoice-001-parsed.json`.
5. Verify JSON structure contains extracted line items.

**Expected JSON output:**

```json
{
  "invoice_number": "001",
  "line_items": [
    {
      "product_name": "Blue Dream 3.5g",
      "quantity": 24,
      "cost_per_unit": 15.50,
      "price_per_unit": null,
      "source": "invoice"
    }
  ]
}
```

**Screenshot to capture:** Cloud Functions logs showing successful OCR processing with extracted line items count.

---

### Step 5: Build METRC Enrichment Service (Cloud Run)

**Time:** 3–4 hours

**Purpose:** Microservice that accepts package IDs and returns enriched data from METRC NJ API.

Create new directory:

```bash
mkdir metrc-enrichment
cd metrc-enrichment
```

Create `main.py`:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
from google.cloud import secretmanager

app = FastAPI(title="METRC Enrichment Service")
sm_client = secretmanager.SecretManagerServiceClient()


class EnrichmentRequest(BaseModel):
    package_ids: list[str]


class PackageData(BaseModel):
    package_id: str
    expiration_date: str | None = None
    strain_name: str | None = None
    product_name: str | None = None
    quantity: float | None = None
    unit_of_measure: str | None = None
    error: str | None = None


def get_metrc_key():
    """Retrieve METRC API key from Secret Manager."""
    project_id = os.environ.get('GCP_PROJECT')
    name = f"projects/{project_id}/secrets/metrc-nj-api-key/versions/latest"
    response = sm_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/enrich-packages")
def enrich_packages(req: EnrichmentRequest):
    """Enrich package IDs with data from METRC NJ API."""
    api_key = get_metrc_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base_url = "https://api-nj.metrc.com"

    results: list[PackageData] = []

    for pkg_id in req.package_ids:
        try:
            r = requests.get(
                f"{base_url}/packages/v1/{pkg_id}",
                headers=headers,
                timeout=10,
            )

            if r.status_code == 200:
                data = r.json()
                results.append(
                    PackageData(
                        package_id=pkg_id,
                        expiration_date=data.get("ExpirationDate"),
                        strain_name=data.get("StrainName"),
                        product_name=data.get("ProductName"),
                        quantity=data.get("Quantity"),
                        unit_of_measure=data.get("UnitOfMeasure"),
                        error=None,
                    )
                )
            elif r.status_code == 404:
                results.append(
                    PackageData(
                        package_id=pkg_id,
                        error="Package not found in METRC",
                    )
                )
            else:
                results.append(
                    PackageData(
                        package_id=pkg_id,
                        error=f"METRC API error: {r.status_code}",
                    )
                )
        except requests.RequestException as e:
            results.append(
                PackageData(
                    package_id=pkg_id,
                    error=f"Request failed: {str(e)}",
                )
            )

    return {"packages": [r.dict() for r in results]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
```

Create `requirements.txt`:

```text
fastapi==0.109.0
uvicorn[standard]==0.27.0
requests==2.31.0
google-cloud-secret-manager==2.18.0
pydantic==2.5.3
```

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Deploy to Cloud Run:**

```bash
# Build container
gcloud builds submit --tag gcr.io/PROJECT_ID/metrc-enrichment

# Deploy to Cloud Run
gcloud run deploy metrc-enrichment   --image gcr.io/PROJECT_ID/metrc-enrichment   --region us-east1   --platform managed   --service-account receiving-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com   --set-env-vars GCP_PROJECT=PROJECT_ID   --allow-unauthenticated   --timeout=60s   --memory=512Mi
```

**Success Test:**

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe metrc-enrichment --region us-east1 --format='value(status.url)')

# Test health endpoint
curl "$SERVICE_URL/health"

# Expected output: {"status":"healthy"}

# Test enrichment with real package ID
curl -X POST "$SERVICE_URL/enrich-packages"   -H "Content-Type: application/json"   -d '{"package_ids": ["1A4000000000001000012345"]}'

# Expected output: JSON with package data including expiration_date
```

**Screenshot to capture:** Cloud Run service page showing `metrc-enrichment` deployed and healthy, plus curl output with successful enrichment response.

---

### Step 6: Join Invoice + Manifest + METRC → Dutchie CSV

**Time:** 4–6 hours

**Purpose:** Combine parsed invoice, manifest, and METRC data into Dutchie-compatible CSV.

Create new Cloud Function directory:

```bash
mkdir csv-joiner
cd csv-joiner
```

Create `main.py`:

```python
import json
import csv
import os
import io
import requests
from datetime import datetime
from google.cloud import storage

storage_client = storage.Client()


def join_to_csv(event, context):
    """Triggered when *-parsed.json files are created.
    Joins invoice + manifest + METRC data into Dutchie CSV.
    """
    bucket_name = event['bucket']
    file_name = event['name']

    # Only process parsed JSON files
    if not file_name.endswith('-parsed.json'):
        return

    print(f"Processing {file_name}")

    # Determine folder path (vendor/date folder)
    folder_path = '/'.join(file_name.split('/')[:-1])

    bucket = storage_client.bucket(bucket_name)

    # Check if both invoice and manifest are processed
    invoice_json = None
    manifest_json = None

    # List all files in folder
    blobs = list(bucket.list_blobs(prefix=folder_path))

    for blob in blobs:
        if 'invoice' in blob.name and blob.name.endswith('-parsed.json'):
            invoice_json = json.loads(blob.download_as_text())
        elif 'manifest' in blob.name and blob.name.endswith('-parsed.json'):
            manifest_json = json.loads(blob.download_as_text())

    # Wait until both are available
    if not invoice_json or not manifest_json:
        print("Waiting for both invoice and manifest to be processed")
        return

    print("Both invoice and manifest ready, joining data")

    # Extract metadata
    vendor = folder_path.split('/')[-1].replace('vendor-', '')
    invoice_number = invoice_json.get('invoice_number', 'UNKNOWN')

    # Enrich with METRC data
    package_ids = [item['package_id'] for item in manifest_json['line_items']]
    metrc_data = call_metrc_enrichment(package_ids)

    # Create lookup dict
    metrc_lookup = {item['package_id']: item for item in metrc_data}

    # Join data
    csv_rows = []
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Match invoice items with manifest items (by position or product name matching)
    for i, inv_item in enumerate(invoice_json['line_items']):
        # Try to find corresponding manifest item
        man_item = manifest_json['line_items'][i] if i < len(manifest_json['line_items']) else {}
        pkg_id = man_item.get('package_id', '')

        # Get METRC enrichment
        metrc_info = metrc_lookup.get(pkg_id, {})

        csv_rows.append({
            "catalog_product": inv_item.get('product_name', ''),
            "package_id": pkg_id,
            "quantity": inv_item.get('quantity', 0),
            "expiration_date": metrc_info.get('expiration_date', ''),
            "cost_per_unit": inv_item.get('cost_per_unit', 0),
            "price_per_unit": inv_item.get('price_per_unit', 0),
            "room": "Receiving Room",
            "batch_number": "",
            "received_date": today,
            "vendor": vendor,
            "invoice_number": invoice_number
        })

    # Write CSV to processed folder
    csv_path = f"{folder_path}/processed/receiving-{invoice_number}.csv"
    write_csv_to_gcs(bucket, csv_path, csv_rows)

    print(f"Created CSV: {csv_path}")


def call_metrc_enrichment(package_ids):
    """Call METRC enrichment service."""
    service_url = os.environ.get('METRC_SERVICE_URL')

    if not service_url:
        print("METRC_SERVICE_URL not set, skipping enrichment")
        return []

    try:
        response = requests.post(
            f"{service_url}/enrich-packages",
            json={"package_ids": package_ids},
            timeout=30
        )
        response.raise_for_status()
        return response.json()['packages']
    except Exception as e:
        print(f"METRC enrichment failed: {str(e)}")
        return []


def write_csv_to_gcs(bucket, path, rows):
    """Write CSV data to GCS."""
    fieldnames = [
        "catalog_product", "package_id", "quantity", "expiration_date",
        "cost_per_unit", "price_per_unit", "room", "batch_number",
        "received_date", "vendor", "invoice_number"
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    blob = bucket.blob(path)
    blob.upload_from_string(output.getvalue(), content_type='text/csv')
```

Create `requirements.txt`:

```text
google-cloud-storage==2.14.0
requests==2.31.0
```

**Deploy Function:**

```bash
# Get METRC service URL
METRC_URL=$(gcloud run services describe metrc-enrichment --region us-east1 --format='value(status.url)')

#gcloud functions deploy join-receiving-csv #  --gen2 #  --runtime=python311 #  --region=us-east1 #  --source=. #  --entry-point=join_to_csv #  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" #  --trigger-event-filters="bucket=hashery-receiving" #  --service-account=receiving-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com #  --set-env-vars METRC_SERVICE_URL=$METRC_URL #  --timeout=300s #  --memory=512MB
```

**Success Test:**

1. Upload both an invoice and manifest PDF to the same vendor folder.
2. Wait for OCR function to create both `*-parsed.json` files.
3. Wait for CSV joiner to trigger.
4. Check for `processed/receiving-*.csv` file in the folder.
5. Download CSV and verify:
   - All 11 required columns present.
   - Expiration dates in `YYYY-MM-DD` format.
   - Package IDs populated (`1A4000...`).
   - Quantities and costs are numeric.
   - Room is `Receiving Room`.

**Sample expected CSV:**

```csv
catalog_product,package_id,quantity,expiration_date,cost_per_unit,price_per_unit,room,batch_number,received_date,vendor,invoice_number
Blue Dream 3.5g,1A4000000000001000012345,24,2026-12-31,15.50,45.00,Receiving Room,,2026-02-25,curaleaf,12345
```

**Screenshot to capture:** GCS folder showing invoice, manifest, parsed JSONs, and final CSV in `processed/` subfolder.

---

## Phase 2: Approval Workflow (Weeks 5–6)

### Objectives (Phase 2)

- Build Slack bot with approval detection
- Implement Firestore approval status tracking
- Add BigQuery audit logging
- Train product supervisor on new workflow

---

### Step 7: Create Slack App and Bot

**Time:** 30 minutes

**Actions:**

1. Go to `https://api.slack.com/apps` and click **Create New App**.
2. Choose **From scratch**.
3. App Name: `Receiving Bot`.
4. Workspace: Select your Hashery workspace.
5. Click **Create App**.
6. Configure **OAuth & Permissions**:
   - Scroll to **Bot Token Scopes**.
   - Add scopes: `chat:write`, `channels:history`, `channels:read`.
7. Install app to workspace:
   - Click **Install to Workspace**.
   - Authorize the app.
   - Copy the **Bot User OAuth Token** (starts with `xoxb-`).
8. Enable **Event Subscriptions**:
   - Toggle **Enable Events** to On.
   - Request URL: will be set after deploying bot in Step 8.
   - Subscribe to bot events: `message.channels`.
9. Copy **Signing Secret** from Basic Information page.

**Success Test:**

- Invite bot to `#hashery-nj-receiving` channel: `/invite @Receiving Bot`.
- Confirm bot appears in channel member list.

**Screenshot to capture:** Slack App OAuth & Permissions page showing bot token scopes and installed workspace.

---

### Step 8: Deploy Slack Bot on Cloud Run

**Time:** 3–4 hours

Create directory:

```bash
mkdir slack-bot
cd slack-bot
```

Create `main.py`:

```python
import os
import re
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
from google.cloud import firestore

# Initialize Slack app
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# Initialize Firestore
db = firestore.Client()


@app.message(re.compile("(approved|approve)", re.IGNORECASE))
def handle_approval(message, say, client):
    """Handle approval messages from supervisors."""
    user = message["user"]
    text = message["text"]
    channel = message["channel"]
    ts = message["ts"]
    thread_ts = message.get("thread_ts")

    # If this is a reply to a thread, mark that CSV as approved
    if thread_ts:
        # Find original message
        result = client.conversations_history(
            channel=channel,
            latest=thread_ts,
            limit=1,
            inclusive=True,
        )

        if result["messages"]:
            original = result["messages"][0]
            original_text = original.get("text", "")

            # Extract invoice number and vendor
            invoice_match = re.search(r"Invoice\s+(\S+)", original_text)
            vendor_match = re.search(r"(\w+)\s+Invoice", original_text)

            if invoice_match and vendor_match:
                invoice_num = invoice_match.group(1)
                vendor = vendor_match.group(1)

                # Update Firestore
                doc_ref = db.collection("approvals").document(f"{vendor}-{invoice_num}")
                doc_ref.set(
                    {
                        "vendor": vendor,
                        "invoice_number": invoice_num,
                        "approved_by": user,
                        "approved_at": firestore.SERVER_TIMESTAMP,
                        "status": "approved",
                        "channel": channel,
                        "thread_ts": thread_ts,
                    }
                )

                # Reply to thread
                say(
                    text=f"✅ Approval recorded from <@{user}> for {vendor} Invoice {invoice_num}",
                    thread_ts=thread_ts,
                )

                print(f"Approval recorded: {vendor} invoice {invoice_num} by {user}")


@app.event("app_mention")
def handle_mention(body, say):
    """Handle direct mentions."""
    say("Hi! I track receiving approvals. Reply 'Approved' to CSV notification threads.")


# Flask adapter for Cloud Run
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


@flask_app.route("/health", methods=["GET"])
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=8080)
```

Create `requirements.txt`:

```text
slack-bolt==1.18.0
flask==3.0.0
google-cloud-firestore==2.14.0
```

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["python", "main.py"]
```

**Store Slack credentials in Secret Manager (optional but recommended):**

```bash
# Store bot token
echo -n "xoxb-YOUR-BOT-TOKEN" | gcloud secrets create slack-bot-token --data-file=-

# Store signing secret
echo -n "YOUR-SIGNING-SECRET" | gcloud secrets create slack-signing-secret --data-file=-

# Grant access to service account
gcloud secrets add-iam-policy-binding slack-bot-token   --member="serviceAccount:receiving-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com"   --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding slack-signing-secret   --member="serviceAccount:receiving-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com"   --role="roles/secretmanager.secretAccessor"
```

**Deploy to Cloud Run:**

```bash
# Build and deploy
gcloud builds submit --tag gcr.io/PROJECT_ID/slack-bot

gcloud run deploy slack-bot   --image gcr.io/PROJECT_ID/slack-bot   --region us-east1   --platform managed   --service-account receiving-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com   --set-secrets SLACK_BOT_TOKEN=slack-bot-token:latest,SLACK_SIGNING_SECRET=slack-signing-secret:latest   --allow-unauthenticated   --timeout=60s   --memory=512Mi

# Get service URL
BOT_URL=$(gcloud run services describe slack-bot --region us-east1 --format='value(status.url)')
echo "Bot URL: $BOT_URL/slack/events"
```

Configure Slack Event Subscriptions:

1. Return to Slack App settings (`https://api.slack.com/apps`).
2. Go to **Event Subscriptions**.
3. Set Request URL to: `https://YOUR-BOT-URL/slack/events`.
4. Slack will verify the endpoint (should show "Verified" checkmark).
5. Save Changes.

**Success Test:**

1. In `#hashery-nj-receiving`, mention the bot: `@Receiving Bot hello`.
2. Bot should reply with help message.
3. Post a test message simulating CSV notification: `Curaleaf Invoice 123 processed`.
4. Reply to that message with `Approved`.
5. Bot should reply with confirmation and checkmark.
6. Check Firestore console for `approvals` collection and `Curaleaf-123` document.

**Screenshot to capture:** Slack thread showing CSV notification, approval reply, and bot confirmation; Firestore console showing approval document.

---

### Step 9: Connect CSV Completion → Slack Notification

**Time:** 2 hours

**Purpose:** Automatically post to Slack when CSV is ready, with signed URL for download.

Update the `join_to_csv` function from Step 6 to add Slack notification at the end.

Add to `csv-joiner/main.py`:

```python
import requests
from datetime import timedelta
```

Extend `join_to_csv` after CSV creation:

```python
    # Write CSV to processed folder
    csv_path = f"{folder_path}/processed/receiving-{invoice_number}.csv"
    write_csv_to_gcs(bucket, csv_path, csv_rows)

    print(f"Created CSV: {csv_path}")

    # Generate signed URL (24 hour expiry)
    csv_blob = bucket.blob(csv_path)
    signed_url = csv_blob.generate_signed_url(
        expiration=timedelta(hours=24),
        method="GET",
    )

    # Extract store name from path
    store_name = folder_path.split('/')[0]

    # Post to Slack
    post_to_slack(vendor, invoice_number, signed_url, store_name)
```

Add helper function:

```python
def post_to_slack(vendor, invoice_number, csv_url, store_name):
    """Post CSV notification to Slack."""
    slack_token = os.environ.get('SLACK_BOT_TOKEN')
    channel = os.environ.get('SLACK_CHANNEL', 'hashery-nj-receiving')

    if not slack_token:
        print("SLACK_BOT_TOKEN not set, skipping notification")
        return

    message = (
        f"📦 *{vendor} Invoice {invoice_number}* processed for {store_name}
"
        f"CSV ready for review: <{csv_url}|Download CSV>"
    )

    try:
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {slack_token}"},
            json={
                "channel": channel,
                "text": message,
                "unfurl_links": False,
            },
            timeout=10,
        )
        response.raise_for_status()
        print(f"Slack notification sent for {vendor} invoice {invoice_number}")
    except Exception as e:
        print(f"Failed to send Slack notification: {str(e)}")
```

**Redeploy function with Slack credentials:**

```bash
# Assume METRC_URL is already set from earlier

gcloud functions deploy join-receiving-csv   --gen2   --runtime=python311   --region=us-east1   --source=.   --entry-point=join_to_csv   --trigger-event-filters="type=google.cloud.storage.object.v1.finalized"   --trigger-event-filters="bucket=hashery-receiving"   --service-account=receiving-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com   --set-env-vars METRC_SERVICE_URL=$METRC_URL,SLACK_CHANNEL=hashery-nj-receiving   --set-secrets SLACK_BOT_TOKEN=slack-bot-token:latest   --timeout=300s   --memory=512MB
```

**Success Test:**

1. Upload invoice + manifest PDFs for a test vendor.
2. Wait for pipeline to complete (OCR → JSON → CSV).
3. Check `#hashery-nj-receiving` for notification message.
4. Click CSV download link in Slack message.
5. Verify CSV downloads correctly.
6. Reply `Approved` to the Slack thread.
7. Verify bot confirms approval and Firestore approval record exists.

**Screenshot to capture:** Slack channel showing automated CSV notification with download link and supervisor approval reply.

---

## Phase 3: Store 1 Production (Weeks 7–8)

### Objectives (Phase 3)

- Deploy to Store 1 for all vendors
- Run parallel with manual process for validation
- Collect accuracy metrics
- Refine catalog matching rules

---

### Step 10: Parallel Run and Validation

**Time:** Ongoing over 2 weeks

**Purpose:** Validate automated system accuracy against manual process before full cutover.

**Actions:**

1. Create validation tracking spreadsheet with columns:
   - Date
   - Vendor
   - Invoice Number
   - Line Items Count
   - Expiration Match %
   - Cost Match %
   - Quantity Match %
   - Package ID Match %
   - Notes
2. For each delivery in Week 7–8:
   - Store staff uploads PDFs to GCS.
   - Automated pipeline generates CSV.
   - Data analyst performs manual entry (current process).
   - Compare automated CSV vs manual entry.
3. Record discrepancies and patterns.

**Validation Script:**

Create `validation.py`:

```python
import pandas as pd
import sys


def validate_csv(automated_path, manual_path):
    """Compare automated CSV against manual entry."""
    auto_df = pd.read_csv(automated_path)
    manual_df = pd.read_csv(manual_path)

    # Merge on package_id
    merged = auto_df.merge(
        manual_df,
        on='package_id',
        suffixes=('_auto', '_manual'),
        how='outer',
    )

    total = len(merged)

    # Calculate match rates
    qty_match = (merged['quantity_auto'] == merged['quantity_manual']).sum()
    exp_match = (merged['expiration_date_auto'] == merged['expiration_date_manual']).sum()
    cost_match = (merged['cost_per_unit_auto'] == merged['cost_per_unit_manual']).sum()
    price_match = (merged['price_per_unit_auto'] == merged['price_per_unit_manual']).sum()

    print(f"Total line items: {total}")
    print(f"Quantity match: {qty_match}/{total} ({qty_match/total*100:.1f}%)")
    print(f"Expiration match: {exp_match}/{total} ({exp_match/total*100:.1f}%)")
    print(f"Cost match: {cost_match}/{total} ({cost_match/total*100:.1f}%)")
    print(f"Price match: {price_match}/{total} ({price_match/total*100:.1f}%)")

    # Show mismatches
    mismatches = merged[
        (merged['quantity_auto'] != merged['quantity_manual'])
        | (merged['expiration_date_auto'] != merged['expiration_date_manual'])
        | (merged['cost_per_unit_auto'] != merged['cost_per_unit_manual'])
    ]

    if len(mismatches) > 0:
        print("
Mismatched items:")
        print(
            mismatches[
                ['package_id', 'catalog_product_auto', 'quantity_auto', 'quantity_manual']
            ]
        )

    return {
        'total': total,
        'qty_match_pct': qty_match / total * 100,
        'exp_match_pct': exp_match / total * 100,
        'cost_match_pct': cost_match / total * 100,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python validation.py <automated.csv> <manual.csv>")
        sys.exit(1)

    results = validate_csv(sys.argv[1], sys.argv[2])

    # Success criteria: >98% match on all fields
    if all(
        v > 98
        for v in [
            results['qty_match_pct'],
            results['exp_match_pct'],
            results['cost_match_pct'],
        ]
    ):
        print("
✅ PASS: Accuracy meets threshold (>98%)")
        sys.exit(0)
    else:
        print("
❌ FAIL: Accuracy below threshold")
        sys.exit(1)
```

**Weekly Review Process:**

1. At end of each week, calculate aggregate metrics:
   - Average accuracy across all fields.
   - Most common error types.
   - Vendors with lowest accuracy.
2. Identify patterns:
   - Is one vendor's invoice format causing issues?
   - Are handwritten expiration dates harder to OCR?
   - Do certain product names fail catalog matching?
3. Adjust parsing logic and redeploy functions.
4. Document in runbook for future reference.

**Success Criteria for Phase 3 Completion:**

- Overall accuracy >98% for 2 consecutive weeks.
- Zero critical errors (wrong product, wrong expiration by >30 days).
- Store staff comfortable with upload process.
- Supervisor approval workflow functioning smoothly.
- Average processing time <15 minutes per delivery.

---

## Phase 4: Dutchie Integration (Weeks 9–12)

### Objectives (Phase 4)

- Request and obtain Dutchie API access
- Build direct API integration (bypass manual CSV upload)
- Implement automatic label printing trigger
- Expand OCR to support 10+ vendors

---

### Step 11: Manual Bulk Upload to Dutchie (Interim)

**Time:** 30 minutes

**Purpose:** Until Dutchie API is available, use manual bulk upload workflow.

**Actions:**

1. In Dutchie Backoffice, navigate to **Inventory → Receive Inventory**.
2. Select **Bulk Upload** option.
3. Download Dutchie's CSV template.
4. Compare template columns to your generated CSV.
5. Create mapping if needed (column reordering/renaming).
6. Upload approved CSV from GCS.
7. Map columns:
   - `catalog_product` → Product Name
   - `package_id` → Package ID
   - `quantity` → Quantity
   - `expiration_date` → Expiration Date
   - `cost_per_unit` → Cost
   - `price_per_unit` → Price
   - `room` → Room
8. Review preview and submit.
9. Print labels from Dutchie.

**Success Test:**

- Upload a small test CSV (2–3 items).
- Verify items appear in Dutchie inventory with correct:
  - Product names.
  - Quantities.
  - Expiration dates.
  - Cost and price values.
- Print labels and verify barcode/METRC ID is correct.

---

### Step 12: Request Dutchie API Access

**Time:** Variable (depends on Dutchie support response time)

**Actions:**

1. Contact Dutchie support via:
   - Support portal at `support.dutchie.com`.
   - Or email: `support@dutchie.com`.
2. Request API access for:
   - Inventory receiving endpoints.
   - Product catalog read access.
   - Purchase order creation (future enhancement).
3. Provide use case:
   - Automated receiving pipeline.
   - Integration with METRC.
   - Multi-store scaling.
4. Request documentation for:
   - Authentication (API keys, OAuth).
   - Receive inventory endpoint.
   - Product search/match endpoint.
   - Webhook notifications (if available).

**Once API access granted:**

- Store API credentials in Secret Manager.
- Review API documentation for endpoint structure.
- Identify rate limits and error handling requirements.

---

### Step 13: Build Dutchie API Integration (Future)

**Time:** 4–6 hours (once API access granted)

**Purpose:** Directly push receiving data to Dutchie via API instead of manual CSV upload.

Placeholder code structure:

```python
# dutchie-integration/main.py
import os
import requests
from google.cloud import firestore, storage, secretmanager

db = firestore.Client()
storage_client = storage.Client()
sm_client = secretmanager.SecretManagerServiceClient()


def receive_to_dutchie(data, context):
    """Cloud Function triggered by Firestore approval update.
    Pushes approved CSV data to Dutchie API.
    """
    # Get document that triggered function
    path_parts = context.resource.split('/documents/')[1].split('/')
    doc_id = path_parts[-1]

    # Read approval document
    doc = db.collection('approvals').document(doc_id).get()
    if not doc.exists:
        return

    approval_data = doc.to_dict()

    if approval_data.get('status') != 'approved':
        return

    vendor = approval_data['vendor']
    invoice_number = approval_data['invoice_number']

    print(f"Processing approved receive: {vendor} invoice {invoice_number}")

    # Find CSV in GCS (search logic based on vendor/invoice)
    # csv_data = ...

    # Get Dutchie API credentials
    dutchie_api_key = get_dutchie_key()

    headers = {
        "Authorization": f"Bearer {dutchie_api_key}",
        "Content-Type": "application/json",
    }

    # Example payload structure (adjust based on actual API)
    payload = {
        "vendor": vendor,
        "invoice_number": invoice_number,
        "items": [
            {
                "product_id": "...",  # from catalog match
                "package_id": "1A4000...",
                "quantity": 24,
                "expiration_date": "2026-12-31",
                "cost": 15.50,
                "price": 45.00,
            }
        ],
    }

    response = requests.post(
        "https://api.dutchie.com/v1/inventory/receive",  # example endpoint
        headers=headers,
        json=payload,
        timeout=30,
    )

    if response.status_code == 200:
        print(f"Successfully received {invoice_number} in Dutchie")
        # Update Firestore with Dutchie receive ID
        doc.reference.update(
            {
                "dutchie_receive_id": response.json().get('id'),
                "dutchie_status": "completed",
            }
        )
    else:
        print(f"Dutchie API error: {response.status_code} - {response.text}")
        doc.reference.update(
            {
                "dutchie_status": "error",
                "dutchie_error": response.text,
            }
        )


def get_dutchie_key():
    """Retrieve Dutchie API key from Secret Manager."""
    project_id = os.environ.get('GCP_PROJECT')
    name = f"projects/{project_id}/secrets/dutchie-api-key/versions/latest"
    response = sm_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
```

> Note: Actual implementation depends on Dutchie's API documentation.

---

## Phase 5: Multi-Store Rollout (Ongoing)

### Objectives (Phase 5)

- Deploy to Store 2 and Store 3 as they open
- Configure store-specific folder structures
- Train new store staff
- Monitor and optimize costs

---

### Step 14: Store 2/3 Deployment

**Time:** 2 hours per store

**Actions:**

1. Create store-specific folders in GCS:
   - `hashery-receiving/store-2/`
   - `hashery-receiving/store-3/`
2. Set up store-specific IAM permissions (if needed for access control).
3. Update Slack channel configuration:
   - Option 1: Use same channel with store tags.
   - Option 2: Create per-store channels (`#hashery-nj-store2-receiving`).
4. Train store staff on:
   - How to scan and name files correctly.
   - Where to upload in GCS (correct folder path).
   - How to confirm receipt in Slack.
5. Run parallel validation for 1 week per new store.
6. Monitor error rates and adjust parsing as needed.

**Success Test:**

- New store uploads first delivery.
- Pipeline processes without errors.
- CSV appears in correct processed folder.
- Slack notification sent to correct channel.
- Store staff can complete workflow independently.

---

## Testing Checklist Summary

Use this checklist to verify each phase is complete before moving to the next:

### Phase 1 Checklist

- [ ] GCS bucket created with correct folder structure.
- [ ] Service account created with all necessary roles.
- [ ] METRC API key stored in Secret Manager and accessible.
- [ ] OCR function deployed and processing PDFs successfully.
- [ ] METRC enrichment service deployed and returning package data.
- [ ] CSV joiner creating valid Dutchie-compatible CSVs.
- [ ] End-to-end test: upload PDFs → receive CSV with correct data.
- [ ] Accuracy validation on 3 test vendors >95%.

### Phase 2 Checklist

- [ ] Slack app created with correct scopes.
- [ ] Slack bot deployed on Cloud Run and responding to mentions.
- [ ] Firestore approvals collection storing approval data.
- [ ] CSV completion triggers Slack notification with signed URL.
- [ ] Supervisor can approve via Slack reply.
- [ ] Bot confirms approval and updates Firestore.
- [ ] End-to-end test: upload → CSV → Slack → approval → Firestore.

### Phase 3 Checklist

- [ ] Parallel run tracking spreadsheet set up.
- [ ] 2 weeks of validation data collected.
- [ ] Overall accuracy >98% for both weeks.
- [ ] Store staff trained and comfortable with workflow.
- [ ] Supervisor approval workflow running smoothly.
- [ ] Common error patterns documented and addressed.
- [ ] Manual process can be discontinued (or kept as backup).

### Phase 4 Checklist

- [ ] Dutchie bulk upload template obtained.
- [ ] CSV column mapping verified.
- [ ] Manual bulk upload tested successfully.
- [ ] Dutchie API access requested.
- [ ] API credentials stored in Secret Manager (when received).
- [ ] API integration function developed and tested (when access granted).
- [ ] Labels printing automatically after receive.

### Phase 5 Checklist

- [ ] Store 2 folder structure created.
- [ ] Store 2 staff trained.
- [ ] Store 2 first delivery processed successfully.
- [ ] Store 3 folder structure created.
- [ ] Store 3 staff trained.
- [ ] Store 3 first delivery processed successfully.
- [ ] Cost monitoring dashboard set up.
- [ ] Monthly cost within budget ($110–135).

---

## Troubleshooting Guide

### Common Issues and Solutions

| Issue | Solution |
| --- | --- |
| OCR function not triggering | Check Cloud Functions logs for errors; verify trigger configuration matches bucket name; confirm service account has Storage Object Admin role. |
| Vision API returns empty text | Check PDF is not encrypted or password-protected; verify PDF is text-based, not scanned images; try converting to higher DPI if scanned. |
| METRC enrichment returns 401 | Verify API key in Secret Manager is correct; check service account has Secret Accessor role; confirm METRC API key is not expired. |
| CSV missing package IDs | Check manifest parsing regex pattern; verify METRC package ID format (`1A4000...`); review manifest OCR output for accuracy. |
| Slack bot not responding | Check bot is invited to channel; verify Event Subscriptions URL is correct; check Cloud Run logs for errors; confirm bot token is valid. |
| Firestore approval not recorded | Check Firestore permissions for service account; verify Slack `thread_ts` is being captured; review bot logs for exceptions. |
| CSV signed URL expired | Increase expiration time in `generate_signed_url()` call; or regenerate URL when supervisor requests. |
| Dutchie bulk upload fails | Verify CSV column names match Dutchie template exactly; check for missing required fields; ensure date format is `YYYY-MM-DD`. |

### Debug Logging Commands

```bash
# View Cloud Function logs
gcloud functions logs read process-receiving-pdf --region=us-east1 --limit=50

# View Cloud Run logs
gcloud run services logs read metrc-enrichment --region=us-east1 --limit=50

# View specific log entries
gcloud logging read "resource.type=cloud_function AND resource.labels.function_name=process-receiving-pdf" --limit=20 --format=json

# Stream logs in real-time
gcloud functions logs read process-receiving-pdf --region=us-east1 --follow
```

---

## Cost Monitoring

### Setting Up Budget Alerts

1. Navigate to **Billing → Budgets & alerts**.
2. Click **Create Budget**.
3. Configure:
   - Budget name: `Receiving Pipeline Monthly`.
   - Projects: Select your project.
   - Services: All services.
   - Budget amount: $150/month (buffer above $135 estimate).
   - Threshold rules: 50%, 75%, 90%, 100%.
4. Add email notification recipients.
5. Create budget.

### Monthly Cost Review

Create a monthly checklist:

- [ ] Review GCP billing dashboard.
- [ ] Compare actual vs estimated costs.
- [ ] Identify top 3 cost drivers (usually Vision API, Cloud Run, Storage).
- [ ] Check for unexpected spikes.
- [ ] Optimize if over budget:
  - Reduce Vision API calls (batch processing).
  - Decrease Cloud Run instance count.
  - Archive old PDFs to Nearline storage.

---

## Security Best Practices

1. **Secrets Management:**
   - Never commit API keys or tokens to Git.
   - Always use Secret Manager for sensitive values.
   - Rotate secrets quarterly.
   - Audit secret access logs monthly.

2. **IAM Permissions:**
   - Follow principle of least privilege.
   - Use service accounts, not user accounts, for automation.
   - Review IAM permissions quarterly.
   - Remove unused service accounts.

3. **Data Protection:**
   - Enable versioning on GCS bucket.
   - Set up lifecycle policies for old PDFs (archive after 7 years).
   - Encrypt sensitive data at rest (GCP default).
   - Use signed URLs with short expiration (24 hours).

4. **Compliance:**
   - Log all METRC API calls for audit trail.
   - Retain all receiving documents for 7 years (NJ cannabis compliance).
   - Document all manual overrides or corrections.
   - Regular backup of Firestore approval records.

---

## Maintenance Schedule

### Daily

- Monitor Slack channel for processing errors.
- Review overnight deliveries processed correctly.
- Respond to any supervisor questions about CSVs.

### Weekly

- Review accuracy metrics from validation spreadsheet.
- Check Cloud Functions error rates in Logs Explorer.
- Verify all deliveries were processed (no stuck PDFs).
- Update vendor parsing patterns if new vendors added.

### Monthly

- Review GCP costs and optimize if needed.
- Audit IAM permissions and secret access.
- Update documentation with new vendor patterns.
- Train any new store staff on workflow.
- Review and archive old PDFs to Nearline storage.

### Quarterly

- Rotate API keys and secrets.
- Update dependencies (Python packages, Docker base images).
- Review and update parsing logic for accuracy improvements.
- Conduct disaster recovery test (restore from backup).
- Update business stakeholders on ROI and metrics.

---

## Success Metrics Dashboard

Create a simple BigQuery dashboard or Google Sheets tracker with these KPIs:

| Metric | Target | Actual |
| --- | --- | --- |
| Processing time per delivery | <15 min | [Track weekly avg] |
| Accuracy rate (all fields) | >98% | [Track weekly] |
| Deliveries automated | >95% | [Track monthly] |
| Manual interventions | <2 per week | [Track weekly] |
| GCP cost per delivery | <$3.00 | [Track monthly] |
| Supervisor approval time | <10 min | [Track weekly median] |
| System uptime | >99% | [Track monthly] |

---

## Conclusion

This implementation guide provides step-by-step instructions for building the automated receiving pipeline over 12 weeks. Each phase builds on the previous one, with clear success criteria and testing procedures.

**Key Takeaways:**

- Start small with 3 vendors in pilot phase.
- Validate accuracy through parallel runs before full cutover.
- Automate approval workflow through Slack to eliminate manual monitoring.
- Use GCP managed services to minimize operational overhead.
- Document all vendor-specific parsing patterns for future maintenance.
- Monitor costs and optimize regularly.
- Scale to multiple stores using same infrastructure.

**Next Steps:**

1. Get approval from supervisor and IT team.
2. Set up GCP project and billing.
3. Begin Phase 1 with 3 pilot vendors.
4. Iterate and improve based on validation results.
5. Roll out to production once accuracy targets are met.

For questions or issues during implementation, refer to the Troubleshooting Guide or contact the data team.

---

## Appendix: Quick Reference Commands

### GCP CLI Commands

```bash
# List all Cloud Functions
gcloud functions list --region=us-east1

# View function details
gcloud functions describe FUNCTION_NAME --region=us-east1

# Redeploy function with changes
gcloud functions deploy FUNCTION_NAME --source=. --region=us-east1

# List Cloud Run services
gcloud run services list --region=us-east1

# View service logs
gcloud run services logs read SERVICE_NAME --region=us-east1

# List GCS buckets
gcloud storage ls

# List files in bucket
gcloud storage ls gs://hashery-receiving/store-1/ --recursive

# Copy file from GCS
gcloud storage cp gs://hashery-receiving/path/to/file.pdf ./local-file.pdf

# View Secret Manager secrets
gcloud secrets list

# Access secret value
gcloud secrets versions access latest --secret=SECRET_NAME
```

### Python Testing Snippets

```python
# Test OCR locally
from google.cloud import vision
client = vision.ImageAnnotatorClient()

with open('test-invoice.pdf', 'rb') as f:
    content = f.read()

image = vision.Image(content=content)
response = client.document_text_detection(image=image)
print(response.full_text_annotation.text)
```

```python
# Test METRC enrichment service
import requests

response = requests.post(
    'https://YOUR-SERVICE-URL/enrich-packages',
    json={'package_ids': ['1A4000000000001000012345']}
)
print(response.json())
```

```python
# Test Slack message
from slack_sdk import WebClient
client = WebClient(token='xoxb-YOUR-TOKEN')

response = client.chat_postMessage(
    channel='hashery-nj-receiving',
    text='Test message from Python'
)
print(response['ok'])
```

---

## Document Revision History

| Date | Version | Changes |
| --- | --- | --- |
| 2026-02-25 | 1.0 | Initial implementation guide created |
