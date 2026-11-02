# PCI Review

Batch extraction and preliminary labor-rate checks for ACME and BrandSafway change-request PDFs. Uses `ocr_ingestion` for extraction and adds support for BrandSafway Trade/Hrs/Rate/Cost tables.

## Setup

From the project root on macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

On Windows, create the environment with `py -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1` in PowerShell.

Scanned printed tables require Tesseract. On macOS with Homebrew:

```bash
brew install tesseract
```

Native PDF text can be processed without Tesseract. Handwritten content requires manual review.

## Inputs

| Path | Contents |
| --- | --- |
| `data/pci_rate_test/inputs/` | Change-request PDFs |
| `data/pci_rate_test/reference_tracker.csv` | Cleaned labor-rate tracker |

The tracker must contain contractor, position, effective start/end dates, regular/OT/DT rates, and approval status. Both the full cleaned tracker and the condensed `labor_rates_fa.csv` schema are supported.

Keep client documents, reference data, review confirmations, and generated results under the ignored `data/` directory. Submitted requests remain separate from approved reference data.

## Run

Read embedded PDF text:

```bash
python -m pci_review.batch --inputs data/pci_rate_test/inputs --reference data/pci_rate_test/reference_tracker.csv --output data/pci_rate_test/run_native
```

Enable OCR for scanned printed tables:

```bash
python -m pci_review.batch --inputs data/pci_rate_test/inputs --reference data/pci_rate_test/reference_tracker.csv --output data/pci_rate_test/run_with_ocr --ocr
```

Use a fresh output folder for each run. Nonempty output folders are rejected. The batch writes candidates and findings separately from the app's saved `document_line_items.csv` and leaves the reference tracker unchanged.

## Outputs

| File | Contents |
| --- | --- |
| `document_inventory.csv` | Input files, contractor routing, coverage, row counts, and errors |
| `extracted_labor.csv` | Candidate labor records in the existing 36-column schema |
| `findings.csv` | Checks, outcomes, explanations, and reference links |
| `review_worksheet.csv` | Rows needing date, billing, or extraction confirmation |
| `page_inventory.csv`, `table_inventory.csv` | Page and table extraction details |
| `extraction_issues.json`, `*-evidence.json` | Extraction issues and source evidence |
| `run_summary.json` | Processing and finding counts |

Each finding represents one check, so a labor record can have several findings. `numeric_comparison` reports the calculation result; `status` also accounts for pending extraction review. For `description_hours`, the expected value comes from worker count times hours in the description, not from confirmed timesheets.

A processed document or numeric match does not establish approval. Zero extracted rows can indicate an unsupported layout. Check the page inventory and extraction issues for incomplete coverage. Source details, summaries, and revisions may overlap financially; do not sum every extracted row as an independent charge.

## Checks and limitations

The checker compares explicit billed rates with a unique Approved schedule covering the actual work period. It also checks hours times rates, explicit labor amounts, extension plus markup, description-based hours, and negative values.

Role qualifiers are preserved. Abbreviations, generic rates, premium descriptions, mixed-contractor packages, overlapping schedules, and missing work dates remain unresolved unless supported by reviewed evidence. Request dates and rate-expiry labels are not substituted for work dates.

Rate comparisons use exact decimal values. Arithmetic comparisons allow a two-cent rounding difference; that tolerance is an implementation setting, not a contractual allowance.

Results are preliminary. Full contract compliance, rental validation, request-total reconciliation, and approval recommendations are outside the current scope. Accuracy requires comparison with confirmed reviewer findings.

### Reviewed confirmations

The default [configuration](pci_review/review_config.example.json) is empty. A private config can be supplied with:

```bash
--config data/pci_rate_test/reviewed_config.json
```

Append that option to the batch command. Editing `review_worksheet.csv` alone does not apply confirmations.

- `record_confirmations`: keyed by full record ID. Requires `reviewed: true` and `evidence`. Optional fields are `extraction_confirmed`, `work_start`, `work_end`, and `billing_category` (`reg`, `ot`, `dt`, `premium_ot`, or `premium_dt`). Confirmed dates fill missing dates only. Premium comparisons require an explicit reference premium.
- `role_confirmations`: keyed by `Canonical contractor|Exact extracted role`. Requires `reference_position`, `reviewed: true`, and `evidence`. The target classification must include the applicable qualifiers.

## Tests

```bash
python -m pytest -q
```

The suite uses synthetic records, PDFs, and images. All 85 tests passed in the development environment. On Python 3.13.1 on macOS, 73 passed and 12 OCR tests were skipped without Tesseract. Passing tests do not measure accuracy on client requests.

## UI integration

```python
from pci_review import check_records, load_reference
from pci_review.extraction import extract_for_review

result, routing = extract_for_review(pdf_path, use_ocr=True)
reference = load_reference(reference_csv_path)
review_ids = {
    record_id
    for table in result.tables if table.requires_review
    for record_id in table.record_ids
}
findings = check_records(result.records, reference, review_required_ids=review_ids)
```

If extraction already runs in the interface, pass its records to `check_records()` directly. Display findings separately from source values and retain the table-review requirements. The new functions are not connected to the existing Streamlit app yet.

The additions are `pci_review/`, `tests/test_pci_review.py`, and this guide. They depend on `ocr_ingestion`; coordinate that branch dependency before submitting a pull request. Keep client data and generated outputs out of the commit.
