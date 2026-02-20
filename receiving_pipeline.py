"""
receiving_pipeline.py

End‑to‑end local pipeline to turn:
- Vendor invoice IMAGES (JPG/PNG)
- METRC / state manifest IMAGES (JPG/PNG)
- Vendor catalog CSV

into one normalized CSV with columns:
PackageID, catalogProduct, room, PricePerUnit, costPerUnit, quantity, expDate.

Folder layout (per vendor):

receiving_workdir/
    invoices/   -> invoice images (JPG/PNG) for ONE vendor
    manifests/  -> manifest images (JPG/PNG) for the same vendor
    catalog/    -> single CSV with a 'Product' column (vendor catalog)
    output/     -> final receiving_normalized.csv is written here

Core steps:
1. OCR invoice images to extract line items.
2. Compute PricePerUnit using your formula: (price / 0.8) * 2.
3. OCR manifest images to get packageID and expDate per item.
4. Match invoice product names to manifest item names.
5. Map invoice product names to catalog Product values (catalogProduct).
6. Emit final normalized CSV for import.
"""

import re
import uuid
from pathlib import Path
from typing import List

import pandas as pd
from PIL import Image
import pytesseract


###############################
# CONFIG
###############################

# Root folder for a single vendor run.
BASE_DIR = Path("./receiving_workdir")

# Input subfolders
INVOICE_DIR = BASE_DIR / "invoices"
MANIFEST_DIR = BASE_DIR / "manifests"
CATALOG_DIR = BASE_DIR / "catalog"

# Output folder
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


###############################
# REGEX PATTERNS
###############################
# NOTE: These are HEURISTICS and will likely need tuning based on
# the actual OCR output of your invoices/manifests.

# Example OCR'ed invoice line (approximate):
#   Black Mamba Distillate 1G   20   24.00   480.00
# Captures: product name, quantity, price, line total.
INVOICE_LINE_REGEX = re.compile(
    r"^(?P<name>.+?)\s{2,}(?P<qty>\d+)\s+(?P<price>[0-9.,]+)\s+(?P<total>[0-9.,]+)$"
)

# Example OCR'ed manifest line (approximate):
#   1A1234ABC  Black Mamba Distillate 1G   20   01/27/27
# Captures: package ID, item name, quantity, expiration date.
MANIFEST_LINE_REGEX = re.compile(
    r"^(?P<package_id>1A[A-Z0-9]+).*?(?P<item_name>.+?)\s{2,}(?P<qty>\d+)\s*(?P<exp_date>\d{1,2}/\d{1,2}/\d{2,4})?"
)


###############################
# UTILITY
###############################


def clean_number(x: str) -> float:
    """
    Convert a string like '2,640.00' to float 2640.0.
    Returns 0.0 for blank/empty values.
    """
    x = str(x).replace(",", "").strip()
    return float(x) if x else 0.0


###############################
# INVOICE OCR + PARSING
###############################


def ocr_image_to_text(img_path: Path) -> str:
    """
    Run OCR on an image file (JPG/PNG) and return raw text.
    """
    img = Image.open(str(img_path))
    text = pytesseract.image_to_string(img)
    return text or ""


def extract_invoice_lines_from_image(img_path: Path) -> pd.DataFrame:
    """
    OCR a single invoice image and extract line items.

    Returns a DataFrame with columns:
    - source_file: invoice file name
    - invoice_line_id: UUID per row
    - product_name: raw product description string
    - quantity: integer quantity
    - price: unit price from invoice
    - totalPrice: line total from invoice
    """
    rows = []
    text = ocr_image_to_text(img_path)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = INVOICE_LINE_REGEX.match(line)
        if not m:
            continue

        name = m.group("name").strip()
        qty = int(m.group("qty"))
        price = clean_number(m.group("price"))
        total = clean_number(m.group("total"))

        rows.append(
            {
                "source_file": img_path.name,
                "invoice_line_id": str(uuid.uuid4()),
                "product_name": name,
                "quantity": qty,
                "price": price,
                "totalPrice": total,
            }
        )

    return pd.DataFrame(rows)


def load_all_invoices() -> pd.DataFrame:
    """
    Load and concatenate all invoice image files from INVOICE_DIR
    into a single DataFrame of line items.
    """
    all_rows: List[pd.DataFrame] = []

    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        for f in INVOICE_DIR.glob(ext):
            df = extract_invoice_lines_from_image(f)
            all_rows.append(df)

    return pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()


###############################
# MANIFEST OCR + PARSING
###############################


def extract_manifest_lines_from_image(img_path: Path) -> pd.DataFrame:
    """
    OCR a single manifest image and extract package-level data.

    Returns a DataFrame with columns:
    - source_file: manifest file name
    - packageID: METRC package ID (1A...)
    - manifest_item_name: item name string (should align to invoice product_name)
    - manifest_qty: quantity shipped
    - expDate: expiration/production date string
    """
    rows = []
    text = ocr_image_to_text(img_path)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = MANIFEST_LINE_REGEX.match(line)
        if not m:
            continue

        package_id = m.group("package_id").strip()
        item_name = m.group("item_name").strip()
        qty = int(m.group("qty"))
        exp_date = (m.group("exp_date") or "").strip()

        rows.append(
            {
                "source_file": img_path.name,
                "packageID": package_id,
                "manifest_item_name": item_name,
                "manifest_qty": qty,
                "expDate": exp_date,
            }
        )

    return pd.DataFrame(rows)


def load_all_manifests() -> pd.DataFrame:
    """
    Load and concatenate all manifest image files from MANIFEST_DIR
    into a single DataFrame.
    """
    all_rows: List[pd.DataFrame] = []

    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        for f in MANIFEST_DIR.glob(ext):
            df = extract_manifest_lines_from_image(f)
            all_rows.append(df)

    return pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()


###############################
# CATALOG LOADING
###############################


def load_catalog() -> pd.DataFrame:
    """
    Load the single vendor catalog CSV from CATALOG_DIR.

    Requirements:
    - Exactly one CSV file present.
    - Must contain a 'Product' column.

    Adds:
    - Product_norm: lowercased, stripped version of Product
      used for fuzzy matching.
    """
    csv_files = list(CATALOG_DIR.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError("No catalog CSV found in catalog/ folder")
    if len(csv_files) > 1:
        raise RuntimeError("Multiple catalog CSVs found; keep only one per vendor.")

    df = pd.read_csv(csv_files[0])
    if "Product" not in df.columns:
        raise KeyError("Catalog CSV must have a 'Product' column")

    df["Product_norm"] = df["Product"].str.lower().str.strip()
    return df


def fuzzy_match_catalog_product(product_name: str, catalog_df: pd.DataFrame) -> str:
    """
    Map a raw invoice product_name to a catalog Product value.

    Simple strategy:
    - Normalize product_name to lowercase.
    - Try a substring match on the first ~15 characters against Product_norm.
    - Fallback to exact normalized match.
    - Return empty string if no match is found.

    You can replace this with a more advanced fuzzy matcher if needed.
    """
    name_norm = product_name.lower().strip()
    if not name_norm:
        return ""

    # Substring match on the first 15 chars
    prefix = name_norm[:15]

    matches = catalog_df[catalog_df["Product_norm"].str.contains(prefix, na=False)]
    if not matches.empty:
        return matches.iloc[0]["Product"]

    # Exact normalized match fallback
    exact = catalog_df[catalog_df["Product_norm"] == name_norm]
    if not exact.empty:
        return exact.iloc[0]["Product"]

    return ""


###############################
# FINAL TABLE CONSTRUCTION
###############################


def build_final_table() -> pd.DataFrame:
    """
    Orchestrate the full workflow:

    1) Load invoice line items from images and compute PricePerUnit:
       PricePerUnit = (price / 0.8) * 2

    2) Load manifests from images and, if present, join them to invoices
       using normalized product names (product_name vs manifest_item_name)
       to bring in packageID and expDate.

    3) Load catalog and map each invoice product_name to
       a catalogProduct value.

    4) Construct the final DataFrame with standardized columns:
       packageID, catalogProduct, room, PricePerUnit,
       costPerUnit, quantity, expDate
    """
    invoices_df = load_all_invoices()
    manifests_df = load_all_manifests()
    catalog_df = load_catalog()

    if invoices_df.empty:
        raise RuntimeError(
            "No invoice line items extracted. "
            "Check that invoice images exist and regex matches OCR text."
        )

    # Step 1: compute PricePerUnit using your formula
    invoices_df["PricePerUnit"] = (invoices_df["price"] / 0.8) * 2

    # Step 2: join manifests to invoices via name match
    if not manifests_df.empty:
        manifests_df["manifest_item_norm"] = (
            manifests_df["manifest_item_name"].str.lower().str.strip()
        )
        invoices_df["product_norm"] = (
            invoices_df["product_name"].str.lower().str.strip()
        )

        merged = pd.merge(
            invoices_df,
            manifests_df,
            left_on="product_norm",
            right_on="manifest_item_norm",
            how="left",
        )
    else:
        merged = invoices_df.copy()
        merged["packageID"] = ""
        merged["expDate"] = ""

    # Step 3: map invoice product_name to catalog Product -> catalogProduct
    merged["catalogProduct"] = merged["product_name"].apply(
        lambda s: fuzzy_match_catalog_product(s, catalog_df)
    )

    # Step 4: assemble final normalized columns
    merged["room"] = "Receiving Room"  # static room per your workflow
    merged["costPerUnit"] = merged["price"]  # rename price -> costPerUnit
    merged["quantity"] = merged["quantity"].astype(int)

    final_cols = [
        "packageID",
        "catalogProduct",
        "room",
        "PricePerUnit",
        "costPerUnit",
        "quantity",
        "expDate",
    ]

    final_df = merged[final_cols].copy()
    return final_df


###############################
# ENTRY POINT
###############################


def main():
    """
    Entry point for CLI usage.

    Example:
        $ python3 receiving_pipeline.py

    Expects:
    - ./receiving_workdir/invoices/*.jpg|*.jpeg|*.png
    - ./receiving_workdir/manifests/*.jpg|*.jpeg|*.png
    - ./receiving_workdir/catalog/vendor_catalog.csv

    Writes:
    - ./receiving_workdir/output/receiving_normalized.csv
    """
    final_df = build_final_table()
    out_file = OUTPUT_DIR / "receiving_normalized.csv"
    final_df.to_csv(out_file, index=False)
    print(f"Wrote {len(final_df)} rows to {out_file}")


if __name__ == "__main__":
    main()
