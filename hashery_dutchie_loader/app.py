import base64
import os
from datetime import datetime

import pandas as pd
import requests
from flask import Flask, jsonify
from google.cloud import bigquery, secretmanager

app = Flask(__name__)

# ---- CONFIG ----
PROJECT_ID = "hasherynj-data-warehouse"
DUTCHIE_BASE_URL = "https://api.pos.dutchie.com"

# BigQuery raw tables
INVENTORY_TABLE_ID = f"{PROJECT_ID}.raw.current_inventory"
PRODUCTS_TABLE_ID = f"{PROJECT_ID}.raw.product_catalog"


# ---- AUTH / SECRETS ----
def get_dutchie_api_key() -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/dutchie-api-key/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


def get_auth_header() -> dict:
    api_key = get_dutchie_api_key()
    auth_token = base64.b64encode(f"{api_key}:".encode()).decode()
    return {
        "Authorization": f"Basic {auth_token}",
        "Accept": "application/json",
    }


def sanitize_columns_for_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    # 1) Replace dots explicitly, then
    # 2) Replace any non-alphanumeric/underscore chars with underscore,
    # 3) Collapse repeated underscores, 4) Strip leading/trailing underscores
    df.columns = (
        df.columns.str.replace(".", "_", regex=False)
        .str.replace(r"[^0-9a-zA-Z_]", "_", regex=True)
        .str.replace("__+", "_", regex=True)
        .str.strip("_")
    )
    return df


# ---- INVENTORY LOADER ----
def fetch_inventory() -> pd.DataFrame:
    headers = get_auth_header()
    url = f"{DUTCHIE_BASE_URL}/reporting/inventory"
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        return pd.DataFrame()

    df = pd.json_normalize(data)
    df = sanitize_columns_for_bigquery(df)
    df["api_load_ts"] = datetime.utcnow()
    return df


def load_inventory_to_bigquery(df: pd.DataFrame) -> int:
    client = bigquery.Client(project=PROJECT_ID)
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )

    job = client.load_table_from_dataframe(
        df,
        INVENTORY_TABLE_ID,
        job_config=job_config,
    )
    job.result()
    return len(df)


@app.route("/load_inventory", methods=["POST", "GET"])
def load_inventory():
    try:
        df = fetch_inventory()
        if df.empty:
            return jsonify(
                {"status": "ok", "rows": 0, "message": "No data returned"}
            ), 200

        rows = load_inventory_to_bigquery(df)
        return jsonify({"status": "ok", "rows": rows}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---- PRODUCTS / CATALOG LOADER ----
def fetch_products() -> pd.DataFrame:
    headers = get_auth_header()
    url = f"{DUTCHIE_BASE_URL}/products"
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        return pd.DataFrame()

    df = pd.json_normalize(data)
    df = sanitize_columns_for_bigquery(df)
    df["api_load_ts"] = datetime.utcnow()
    return df


def load_products_to_bigquery(df: pd.DataFrame) -> int:
    client = bigquery.Client(project=PROJECT_ID)
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )

    job = client.load_table_from_dataframe(
        df,
        PRODUCTS_TABLE_ID,
        job_config=job_config,
    )
    job.result()
    return len(df)


@app.route("/load_products", methods=["POST", "GET"])
def load_products():
    try:
        df = fetch_products()
        if df.empty:
            return jsonify(
                {"status": "ok", "rows": 0, "message": "No data returned"}
            ), 200

        rows = load_products_to_bigquery(df)
        return jsonify({"status": "ok", "rows": rows}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---- HEALTHCHECK ----
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
