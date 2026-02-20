# Invoice + Manifest + Catalog Processing – User Instructions

## Goal

Turn three data sources:

- Vendor **invoices**
- State/manufacturing **manifests** (e.g., METRC)
- A vendor **catalog CSV**

into one clean CSV with standardized columns:

`PackageID, catalogProduct, room, PricePerUnit, costPerUnit, quantity, expDate`

---

## What You Need

For **one vendor at a time**, gather:

1. **Invoices**
   - PDF or image files from the vendor
   - Show line items, quantities, and prices

2. **Manifests**
   - State or METRC transportation/manufacturing manifests
   - Contain package IDs (often starting with `1A`) and production/expiration dates

3. **Catalog**
   - A CSV file for the same vendor
   - Must include a **`Product`** column (official product names)

---

## High-Level Flow

1. Start a **new chat** with the AI tool.
2. Paste the **general processing prompt** (stored in a separate `.txt` file).
3. Upload files in **three clearly labeled batches**:
   - Batch 1 – Invoices
   - Batch 2 – Manifests
   - Batch 3 – Catalog
4. Receive **one final CSV** and save it.

---

## Step-by-Step Instructions

### 1. Start a New Chat

- Open a **fresh conversation** so there’s no previous context.
- This keeps the run isolated to a single vendor.

### 2. Paste the Main Processing Prompt

1. Open the file, for example:
   `general_processing_prompt.txt`
2. Copy **all** of the text in that file.
3. Paste it into the chat as **one message** and send it.
4. Do **not** upload any files yet.

---

### 3. Upload Batch 1 – Invoices

In the chat:

1. Type and send:

   ```text
   Batch 1 starts now – INVOICES for [Vendor Name].
   ```

2. Attach **all invoice PDFs/images** for this vendor and send them with that message.
3. When done uploading, type and send:

   ```text
   Batch 1 done.
   ```

---

### 4. Upload Batch 2 – Manifests

In the chat:

1. Type and send:

   ```text
   Batch 2 starts now – MANIFESTS (METRC/state) for [Vendor Name].
   ```

2. Attach **all manifest PDFs/images** for this vendor and send them.
3. When done uploading, type and send:

   ```text
   Batch 2 done.
   ```

---

### 5. Upload Batch 3 – Catalog

In the chat:

1. Type and send:

   ```text
   Batch 3 starts now – CATALOG CSV for [Vendor Name].
   ```

2. Attach the vendor’s **catalog CSV** (with a `Product` column) and send it.
3. Then type and send:

   ```text
   Batch 3 done. Please run the full process and return the final CSV only.
   ```

---

### 6. Save the Result

- The AI should respond with **CSV text only** (no explanations).
- Copy the entire response into a text editor (e.g., Notepad).
- Save as:

  ```text
  [VendorName]-[Date]-Processed.csv
  ```

- Open that file in Excel or import it into your inventory system.

---

## What the AI Is Expected To Do (Summary)

You don’t perform these steps manually; the **prompt** instructs the AI to do them.

### From Invoices

- Extract:
  - `packageID` (if present)
  - `product name`
  - `quantity` (in units, not cases)
  - `totalPrice` (line total before tax)
- Compute:
  - `price = totalPrice / quantity`

### From Manifests

- Extract:
  - `manifestPackageID` (e.g., `1A...`)
  - `manifestProductName`
  - `expirationDate` (or production/expiration date, depending on what’s available)

### Join Invoices + Manifests

- Match rows using product/strain/size/format.
- Create:
  - `PackageID` (final package ID from manifest)
  - `expDate` (from manifest date)

### From Catalog

- Use the `Product` column to map each invoice line to:
  - `catalogProduct` (the exact `Product` text)

### Pricing

- Use `price` from invoices to compute:

  ```text
  PricePerUnit = (price / 0.8) * 2
  ```

### Final Columns (Order Matters)

The final CSV must have **exactly** these columns:

1. `PackageID`
2. `catalogProduct`
3. `room` – set to `Receiving Room` for every row
4. `PricePerUnit`
5. `costPerUnit` – the `price` from invoices
6. `quantity`
7. `expDate`

---

## Tips & Notes

- Always process **one vendor at a time**.
- Make sure the **catalog** matches that vendor.
- If you get an **empty/blank CSV**:
  - Confirm the main prompt was sent **before** any files.
  - Confirm the **Batch 1/2/3** labels and `done` messages were used exactly.
- You can reuse this `.md` file for any vendor; just change the vendor name and the set of files when you follow the steps.
