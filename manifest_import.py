import logging
import re
from pathlib import Path

import ocrmypdf
import pandas as pd
import pdfplumber

logging.getLogger("pdfminer").setLevel(logging.ERROR)

# ---------- Auto-detect newest *manifest* PDF in this folder ----------
script_dir = Path(__file__).resolve().parent

pdf_files = [p for p in script_dir.glob("*.pdf") if "manifest" in p.name.lower()]

if not pdf_files:
    raise FileNotFoundError(
        "No manifest PDFs (name contains 'manifest') found in script folder."
    )

PDF_PATH = max(pdf_files, key=lambda p: p.stat().st_mtime)
OCR_PATH = script_dir / (PDF_PATH.stem + "-ocr.pdf")

print(f"Using manifest: {PDF_PATH.name}")

# ---------- OCR step (idempotent) ----------
if not OCR_PATH.exists():
    print(f"OCR output not found, creating: {OCR_PATH.name}")
    ocrmypdf.ocr(
        str(PDF_PATH),
        str(OCR_PATH),
        language="eng",
        force_ocr=True,
        progress_bar=False,
    )
else:
    print(f"OCR file already exists: {OCR_PATH.name}")

# ---------- Regexes & helpers ----------
pkg_id_re = re.compile(r"(1A[0-9A-Z]+)")
date_re = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2})")
# Examples: "Shp: 1 ea 1", "Shp: 420 g 125 DK", "Shp: 336 g 96 DK"
qty_re = re.compile(r"Shp:\s*\S+\s+\S+\s+(\d+)(?:\s+\S+)?", re.IGNORECASE)


def normalize_date(raw: str) -> str:
    if not raw:
        return ""
    m = date_re.search(raw)
    if not m:
        return ""
    mm, dd, yy = m.groups()
    return f"{int(mm):02d}/{int(dd):02d}/{yy}"


rows = []

# ---------- Parse OCR'ed PDF line-by-line ----------
with pdfplumber.open(str(OCR_PATH)) as pdf:
    for page in pdf.pages:
        text = page.extract_text() or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        for ln in lines:
            # Skip obvious non-package detail lines
            if "Source Package" in ln or "Source Harvest" in ln or "Item Details" in ln:
                continue

            # Pull every 1A... ID on this line
            pkg_ids = [m.group(1) for m in pkg_id_re.finditer(ln)]
            if not pkg_ids:
                continue

            # Quantity & expiration date live on the same “row” in NJ manifests
            qty_match = qty_re.search(ln)
            qty_val = int(qty_match.group(1)) if qty_match else ""

            exp_date = normalize_date(ln)

            # Product: try pipe split first, then pattern, then fallback
            parts = [p.strip() for p in ln.split("|")]
            product = ""
            if len(parts) >= 3:
                # NJ layout: [0]=pkg+lab, [1]=date, [2]=item name, [3]=quantity
                product = parts[2]
            else:
                # Try to capture “Something - SB - ... (Bud/Flower - Packaged)”
                m_prod = re.search(
                    r"([A-Z][A-Za-z0-9\s\-()/]+\(Bud/Flower\s*-\s*Packaged\))", ln
                )
                if m_prod:
                    product = m_prod.group(1)
                else:
                    # As a last resort, keep the whole line
                    product = ln

            for pkg_id in pkg_ids:
                rows.append(
                    {
                        "LineNo.": "",
                        "PackageID": pkg_id,
                        "Product": product,
                        "Quantity": qty_val,
                        "Expiration Date": exp_date,
                    }
                )

# ---------- Build dataframe & save ----------
df_out = pd.DataFrame(rows)

if not df_out.empty:
    # Keep only rows that look like real packages:
    # have PackageID and Product and Quantity or Date
    df_out = df_out[df_out["PackageID"].notna() & (df_out["PackageID"] != "")]
    df_out = df_out.drop_duplicates(subset=["PackageID"])

    # Sort by PackageID
    df_out = df_out.sort_values("PackageID", kind="mergesort")

    # Assign LineNo. sequentially
    df_out["LineNo."] = range(1, len(df_out) + 1)

    # Enforce column order
    df_out = df_out[["LineNo.", "PackageID", "Product", "Quantity", "Expiration Date"]]

    out_csv = script_dir / "manifest_packages.csv"
    out_xlsx = script_dir / "manifest_packages.xlsx"
    df_out.to_csv(out_csv, index=False)
    df_out.to_excel(out_xlsx, index=False)

    print(f"Extracted {len(df_out)} package rows from OCR'ed PDF.")
    print(f"Wrote: {out_csv.name} and {out_xlsx.name}")
else:
    print(f"No package rows found in OCR'ed file: {OCR_PATH.name}")
