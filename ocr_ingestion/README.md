# Local printed labor-table ingestion

Upload individual PDFs or images, inspect the original printed labor rates, and append selected records to a local CSV. Processing runs on your machine. No ZIP, API key, or cloud document service is needed. The ingestion package preserves submitted values. The separate reviewer application compares them against approved reference schedules and leaves final decisions to a human reviewer.

## Start

From the repository root:

```bash
source warren_towers/bin/activate
python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m reviewer
```

Open **http://127.0.0.1:8000**. The server binds to loopback; this is a local application without accounts or shared hosting. Node.js 22+ is recommended to build the frontend. See the [reviewer guide](../reviewer/README.md) for development commands and the labor checker.

Tesseract is a separate system dependency for scanned printed tables:

```bash
# macOS
brew install tesseract
# Ubuntu / Debian
sudo apt-get install tesseract-ocr
```

Document reading is automatic: selectable PDF text is extracted directly and scanned pages use local OCR when needed. The interface has no OCR checkbox or configuration section. The app reports missing Tesseract when OCR is needed. Supported inputs are PDF, PNG, JPEG, and multipage TIFF, up to 200 MB each. Password-protected PDFs must be unlocked before uploading.

## Review and add rows

1. Upload a file. Enter the required contractor as printed on the source and project name. The program does not derive the contractor or actual project name from a filename or rate match. The filename prefix before the first `-` appears separately as **Project ID (filename)**, a display label rather than a verified project number.
2. Click **Extract labor rates**. Changing metadata afterwards requires extracting again.
3. Review detected labor tables and source pages. Only rows with an explicit hourly rate and a printed description, classification, or worker name are offered for saving. Totals, summaries, and supporting-cost tables are excluded.
4. For unfamiliar labor tables, map the printed columns, including a rate and a source label. Description/total-only tables and rows without usable rates are ignored. Mapping does not imply that the data has been validated. Blank optional cells remain unknown. Source classifications and descriptions are preserved.
5. Explicitly confirm tables that used OCR, manual mapping, unresolved cells, or overlay filtering. Compare them against the original printed cells and exclude handwriting or reviewer corrections.
6. Select individual rows and click **Save selected rows**. Already-saved record IDs are skipped; you can add more rows from the same document later.

The app does not extract handwritten tickets or use handwritten dates. Scanned pages must have separated column headings and aligned labor-rate data rows to produce a review table. Notes, empty headers, totals-only pages, and scattered keywords do not qualify. Known scanned layouts use their normal parser; an unfamiliar layout is offered for mapping only when it contains a usable rate and source label. Ruled headings can use an additional sparse-text OCR pass to recover section labels. Local OCR is not proof that every detected word is printed; obscured or unparseable rates are omitted rather than invented.

For ACME Waterproofing documents, only usable rate rows within printed **LABOR** sections are extracted. Pages without a LABOR section and tables outside those sections are skipped, including material, trucking, cover, and summary tables. They do not appear for mapping or require review. ACME is identified from the contractor input or printed company name; provide the contractor for fully scanned documents. OCR and unfamiliar labor tables still require review. Generic HRS/RATE values remain separate from explicit ST/OT/DT rates. Existing saved rows are not reclassified automatically; extract the document again to replace an older preview.

Native PDF annotations are omitted from previews. Flattened annotations are page content and can still appear in the source image. The native extractor excludes check glyphs and colored spans in fonts different from the source's black text; it preserves colored source text in the normal source fonts. This is a conservative heuristic tested on the supplied examples, not a universal annotation separator. Tables with filtered spans require explicit review. When the original value is obscured, do not accept a guessed or corrected value.

## View saved data

Click **Saved data** to browse usable labor-rate rows from `data/document_line_items.csv` inside the local interface, even without uploading a document. Search across columns or click **Refresh workspace** to reload changes saved by another session. This read-only view preserves original values and hides legacy non-labor or unusable rows without deleting them. Extraction previews are not included until you click **Save selected rows**.

The default client view uses readable column labels, hides empty layout-specific columns, and shortens record IDs to 12 characters (extended if prefixes collide). **Show technical columns and full IDs** restores the complete raw view. Full identifiers remain unchanged in storage and drive duplicate protection. Descriptions appear when provided by the printed table; worker-detail tables may instead contain classification and worker-name columns. Project names are required for new extractions; older rows are not backfilled or rewritten.

Known-layout table IDs combine page, rounded header Y coordinate, and table kind (for example `p3-y240-labor_detail`). Fallback grid IDs use page and the zero-based detected grid index (for example `p3-grid0`). These IDs are scoped to the document, not globally unique. Record identity combines the document content hash, table ID, and source row position. Identical file reuploads, even renamed, do not add saved rows again. Matching values at different source locations remain separate; modified files are distinct versions, not automatically deduplicated against originals.

## Schema and local artifacts

The main CSV is `data/document_line_items.csv`. All fields have stable names; unknown optional values are empty CSV fields. Exact decimal strings are used instead of binary floating-point rates. The CSV header remains compatible with existing saved data; the default interface focuses on labor-rate columns and hides amount/supporting-cost fields. The separate contract-reference tracker is not overwritten.

Blank BrandSafway template rows with preprinted rates but no submitted hours or amounts remain excluded. Legitimate repeated source rows remain distinct; the program does not collapse equal-looking business values.

| Fields | Meaning |
| --- | --- |
| `record_id`, `document_id` | Content hash plus source table/row identity; identical-looking rows at different source locations stay distinct. |
| `source_file`, `source_page`, `table_id`, `row_index`, `extraction_method` | Source evidence references. Page and row numbers start at 1. |
| `contractor`, `project`, `document_reference`, `ticket_id` | Explicit metadata and printed references. Per-row ticket IDs take precedence over page metadata. |
| `description`, `position_original`, `worker_name`, `rate_basis_raw` | Source wording without classification substitutions. For an ACME description explicitly stating `N [role] at ...`, the role substring is quoted verbatim alongside the full description; no tracker classification or seniority is inferred. |
| `work_start`, `work_end` | Explicit printed work dates; grouped labor dates carry forward only within their table. Unlabeled dates stay in `unlabeled_date_raw`. |
| `hours`, `rate` | Generic HRS/RATE values. A premium description does not imply a specific OT/DT classification. |
| `reg_hours`, `ot_hours`, `dt_hours`, `reg_rate`, `ot_rate`, `dt_rate` | Explicit ST/OT/DT columns. ST is named `reg` consistently with the tracker. These are submitted rates, not declarations of approval. |
| `reg_amount`, `ot_amount`, `dt_amount` | Separate printed ST/OT/DT extensions where present. A missing total is not filled by a calculated sum. |
| `quantity`, `unit`, `unit_rate` | Legacy schema fields retained for compatibility; supporting-cost tables are no longer ingested. |
| `extension_amount`, `overhead_profit_amount`, `total_amount` | Separate printed amounts; markup is not part of the labor hourly rate. |
| `row_type` | All labor records use `labor`. Worker-detail, tally, and generic-rate layouts remain in internal table metadata without changing source IDs. Legacy `labor_detail`/`labor_tally` values are accepted and shown as `labor` on read; new saves always use `labor`. Summaries and supporting-cost rows cannot be saved. |

Handwritten work dates and reference-derived premiums are intentionally absent from extraction. The rate-reference file `data/labor_rates_fa.csv` is never modified.

New UI uploads and persistent review sessions stay under `data/reviewer/`. Legacy uploads under `data/ocr_ingestion/uploads/` remain untouched. Saved source copies, evidence history, the manifest, and the recovery journal live under `data/document_line_items_private/`. File locking serializes writers. The CSV is physically appended; the recovery journal records its pre-append byte length. A write interrupted before the atomic manifest commit is rolled back on the next read/append. Existing incompatible CSV schemas are rejected. Changed documents have new hashes and remain separate versions.

All these data artifacts are private and ignored by Git. The downloaded JSON evidence contains client data and must also remain private.

## Reuse from Python

```python
from ocr_ingestion import extract_document, append_records

result = extract_document("path/to/document.pdf", contractor="Name printed on source")
# Inspect result.records, result.tables, result.issues, and result.pages before saving.
# Explicitly choose record IDs and confirm reviewed table IDs; never auto-approve OCR.
summary = append_records(
    result,
    "data/document_line_items.csv",
    selected_ids=[],
    reviewed_table_ids=[],
    source_path="path/to/document.pdf",
)
```

`extract_document` reads a document without updating the accumulated CSV. `append_records` is the explicit persistence operation; it rejects selected rows from tables requiring review unless their table IDs are confirmed. `map_table` in the extraction module supplies the manual-column-mapping API. `load_records` checks the schema and performs pending-append recovery under the same lock.

## Verification

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ocr_ingestion.evaluate \
  --reference 'data/brandsafway_combined_clean (1).csv' \
  --inputs brandsafway_data ACME_data
```

The evaluator writes private reports and per-document evidence to `data/ocr_ingestion/evaluation/`. It compares labor rows one-to-one, retaining repeated records. Numeric zero/dash equivalence and sums of explicit ST/OT/DT amounts are comparison conveniences only; they are not inserted into extracted records. It does not validate title aliases or assert that reviewer adjustments are contractual truth. Source PDFs remain authoritative for the original printed values.

This real-document evaluation disables OCR because the supplied labor tables have embedded printed text. Scanned printed-table extraction is tested separately with synthetic images and requires review in the app. Missing source documents and genuine mismatches are reported rather than silently ignored or fixed by copying reference values.

Contributor constraints are in [AGENTS.md](AGENTS.md). Private implementation handoffs remain local and are excluded from Git. Existing cleaning and teammate notebooks remain unchanged.
