# Warren labor reviewer

A local browser application for reviewing printed labor rates and identifying differences against applicable approved schedules. React replaces the previous Streamlit interface; the extraction engine and accepted CSV schema remain compatible.

## Setup and launch

From the repository root:

```bash
source warren_towers/bin/activate
python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m reviewer
```

Open **http://127.0.0.1:8000**. Build the frontend again after changing it. The backend serves the compiled interface and API from the same address. Node.js 22+ is recommended for builds; running the built application requires Python only. Tesseract is required for scans (`brew install tesseract` on macOS); native text PDFs can be processed without it.

For frontend development, keep the Python server running and run `npm --prefix frontend run dev` in another terminal. Vite serves at http://127.0.0.1:5173 and proxies `/api` to the local backend.

## Review workflow

1. **Upload & review:** Choose **Upload document**, add a PDF, PNG, JPEG, or TIFF, enter the project and contractor, and extract labor rates. Processing opens **Documents in review**. You can switch back to Upload document while processing continues. Documents are limited to 200 MB.
2. **Saved data:** Search and filter accepted labor records. Select records for a check. Open a record to inspect its original values and source page. Short displayed IDs extend when prefixes collide; full identifiers remain in storage and exports. Project ID (filename) is a display label derived from the filename, not a verified business identifier.
3. **Labor checks:** Activate a reference schedule and check selected records or the full saved dataset. Review matches, differences, and unresolved checks independently. Open each result for source and tracker evidence. A row containing explicit ST, OT, and DT rates produces three comparisons.
4. **Differences:** Review and export flagged rate differences, including rates absent from the applicable approved set. For 100 comparisons with 8 differences, this tab and export contain exactly 8 findings. Unresolved checks are counted separately.

**Upload document** and **Documents in review** are separate views. Opening a new upload retains the active document. Switching back retains its source page, selected rows and confirmations; switching between documents also keeps each document's page and row selection while the app is open. The last view and active document are restored after a reload, and confirmed source reviews are saved on the server. Unsaved file drafts and row-selection drafts remain in memory only.

The three process steps are clickable. **Upload document** opens the form; **Review extracted rates** opens the review view; **Save & check** takes you to the selected document's save actions. Step navigation never saves rows or runs checks automatically. Use the explicit save/check buttons for those actions. The review list refreshes processing statuses while it is open, and background completion does not interrupt an upload draft.

The **Documents to review** queue is in Documents in review, with pending table reviews, unreadable pages, failed extractions, and documents with no usable rates first. Use its attention filter to focus on outstanding work. Each document shows its status, including whether it needs review, is ready to save, or is saved.

Within a document, the **Review checklist** lists required reviews and column mapping first. A newly opened document starts on its first pending page; returning to a document resumes your place. Click a checklist item or **Next table to review** to open the source page and focus a specific table. Confirm source checks, select rows and save them explicitly. Confirmations survive reloads and server restarts; remapping invalidates confirmations whose values changed. Saved source rows do not trigger repeat review. Unreadable pages link to their source so you can inspect them or retry a clearer upload.

Existing saved records are not rewritten. If a contractor, classification, or date is missing or needs reconciliation, use **Set comparison details**. A reviewer can select multiple saved rows and apply shared details in one operation. Blank fields in a bulk edit leave existing overrides alone; blank fields in an individual edit restore the original printed value. Comparison details are stored separately, and each check run preserves the details it used. Rerun after changing them.

The source page omits native PDF annotations. Flattened handwriting can remain visible. Unknown or obscured printed values require human review; extraction does not guarantee perfect recognition for arbitrary documents.

Document reading is automatic. PDFs with selectable text use direct extraction; scans use local OCR when needed. There is no OCR switch or configuration section in the interface, and legacy saved preferences cannot disable document reading. Tesseract is required for scanned documents. Extracted values that require source review still need explicit confirmation.

## Crossed-out and replacement rates

The current ingestion policy preserves original printed rates and excludes reviewer corrections. A PDF may therefore show an original rate crossed out with a green replacement while the checker still evaluates the original submission. A flagged original rate does not establish whether a later correction is correct.

Correction-aware extraction is a separate extension, not implemented by the code cleanup. It should retain both original and proposed replacement values, link each to the same source row and visual evidence, distinguish typed PDF corrections from handwriting/raster images, and require confirmation when the replacement or its target is uncertain. Color alone cannot identify a correction: green checkmarks, classification labels and totals also occur. Replacement rates must not be guessed from the approved tracker or silently substituted into the original dataset.

## Reference schedule and comparison rules

The initial reference is imported from `data/labor_rates_fa.csv` when needed; this original file is never changed. **Reference schedule / Manage schedule** accepts a UTF-8 replacement CSV up to 10 MB. Required columns:

```text
source_csv_row_number,subcontractor,position,effective_time_period_start,effective_time_period_finish,reg_rate,ot_rate,dt_rate,status,bu_approval_received
```

Use unique source row identifiers, YYYY-MM-DD dates, and numeric rates or blank unknown values. Missing columns, duplicate identifiers, malformed dates/rates, or malformed CSV rows prevent import. Incomplete schedules and reversed date ranges are shown as issues and cannot produce successful checks. Preview the schedule and explicitly activate it. Reference versions and their original uploaded CSVs are retained immutably and identified by file content hash; prior findings retain their original version.

Matching rules:

- Resolve the contractor first, using exact names, punctuation/legal-suffix normalization, or an unambiguous short company name. Parenthetical mentions of another company do not turn that company into the contractor. A missing contractor must be supplied once for the document; matching never searches other contractors for a convenient rate.
- Select classifications within that contractor using a saved equivalent title, normalized title (including foreman/foreperson and journeyman/journey person), or trade family. For example Masons → Masonry → Bricklayer classifications; Laborers → Laborer classifications. Stated seniority, apprentice percentages, groups, shifts, and specialties are preserved. Where the tracker uses only generic role names, compare within those contractor roles. If the printed classification is absent/unrecognized, a contractor-only rate check is labeled explicitly in the finding.
- Only schedules marked **Approved** that cover the entire work period supply comparison rates. BU approval receipt remains evidence. Pending/withdrawn schedules cannot shadow applicable approved rates. Conflicting overlapping approved rates for the same classification still need review, as do missing dates, unknown/ambiguous contractors, invalid reference information and work periods spanning rate changes.
- Compare the submitted rate with the approved rates in that contractor/trade/role scope. A matching value is a rate match; preserve all supporting classification and row evidence. A broad title is not silently rewritten to a specific grade. If there is one applicable rate, calculate the signed difference. If several grades have different approved rates and none equals the submission, flag **Not in approved rates**, list the possible rates/classifications, and leave the single expected rate and per-hour difference blank. Never choose the nearest price or cross a stated role/grade to make a rate match. A rate match from a broad description establishes membership in the eligible schedule, not independent verification of a worker's exact grade.
- Regular, OT, and DT are compared separately using exact Python Decimal values, with no tolerance. A single printed Rate is always treated as regular (REG) and compared directly against the tracker’s `reg_rate`; no rate-type selection is required. Explicit ST columns also map to regular/`reg_rate`, while explicitly labeled OT/DT columns retain their separate comparisons. Normal UI tables show the single Rate under Regular rate. Raw extraction fields and original source values remain intact in storage and the technical view. Historical rate-type overrides are ignored. Check runs from earlier comparison rules are marked outdated and must be rerun to use this rule.
- Both higher and lower submitted rates are differences. The signed difference per hour is submitted minus approved. The checker does not calculate total financial impact, decide contractual compliance beyond these rules, or approve/reject requests.

The CSV export contains one finding per differing source row/rate type, with finding/run/record/document IDs, project, contractor, classification, work period, source location, submitted/approved rates, signed difference, reference_rate_field (reg_rate for regular), reference version and tracker row, approval evidence, comparison details, matching method/explanation, possible classifications, approved rate set, and all supporting reference rows. Spreadsheet formula prefixes in textual source labels are escaped. All differences in the selected run are exported; search filters affect the screen only. Outdated runs are labeled in the interface and download filename.

## Classification map

Open **Classification map** in Labor checks or Differences. The active tracker generates a local hierarchy: contractor → trade family → actual tracker classification → source schedule/rate. It covers every known nonblank classification in that reference, with unfamiliar titles under Other classifications. Family labels and spelling aliases organize known data; this is not a claim to know every construction occupation or every possible synonym.

Reviewers can save a contractor-specific equivalent job title targeting an actual classification in the active tracker, then rerun checks. Relationships are editable by saving the same source title again and removable from the map. They cannot target another contractor or an invented classification, and they never overwrite source wording. The check snapshot retains its selected classifications, matching method/explanation, approved rate set and reference rows. Relationship changes make prior runs outdated. All graph data and saved relationships stay local; no external model is called.

## Storage and operation

Accepted rows remain in `data/document_line_items.csv` with the existing lock, append recovery, duplicate protection, and `document_line_items_private/` evidence. Equal-looking source rows remain distinct. Exact reuploads and renamed copies skip already-saved IDs; modified/rescanned documents remain separate versions.

New originals are stored in `data/reviewer/uploads/`. `data/reviewer/reviewer.sqlite3` stores extraction sessions, immutable reference versions, active-reference selection, current comparison details, contractor-specific classification relationships, and immutable check-run snapshots. All are ignored by Git and stay local. Browser storage contains only tab/session/run identifiers. Refreshing or restarting preserves completed extraction and checks; interrupted jobs are marked failed and can be retried through reupload. A single extraction worker processes queued documents and exposes page progress.

`WARREN_DATA_DIR` can point to another local data directory, useful for isolated demos/tests. It must contain any intended reference and accepted dataset; the default is the repository's `data/`. The server runs on 127.0.0.1:8000. No cloud APIs, external fonts, accounts, or public hosting are used. Original documents, extracted worker information, evidence, and exported findings are sensitive local artifacts.

## Verification

```bash
python -m pytest -q
npm --prefix frontend run build
npm --prefix frontend run format:check
npm --prefix frontend test
python -m ruff check reviewer tests --select E4,E7,E9,F,I
python -m ruff format --check reviewer tests
```

Browser tests use installed Google Chrome (`channel: chrome`) and start their own loopback server on port 8000. Stop the normal reviewer before running them. They use disposable synthetic documents and a temporary data directory; they never open the real dataset. Screenshots and traces are written under ignored `frontend/test-results/`. The browser tests cover the 100-comparison/8-difference workflow, source evidence, CSV download, review resolution, outdated results, reference activation, reload, and desktop/mobile widths.

API routes are documented at **http://127.0.0.1:8000/docs**. Extraction, mapping and save requests enforce source review on the backend; UI controls alone are not the enforcement boundary. Review sessions use revision checks, and required table confirmations are tied to current extracted values. Comparison-detail bulk writes validate every selected row before committing atomically.

## Code layout

`reviewer/api.py` connects request handling to the extraction, comparison, matching and persistence modules. Request validation is in `schemas.py`, upload/preview helpers in `documents.py`, and shared state fingerprints in `state.py`. These boundaries preserve the accepted CSV schema and review tokens.

The frontend workspace coordinates state and navigation in `App.tsx`. Dedicated components render the reference schedule, source findings, comparison details, classification map, and review checklist. TypeScript checks reject unused locals/parameters; Prettier and Ruff provide repeatable formatting and Python lint checks. The extraction notebooks remain untouched.
