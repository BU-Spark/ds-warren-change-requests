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

## Sign-in

Sign in with the shared project access code. The initial code is **1234**.
Set `WARREN_ACCESS_CODE` on the app service to change it to 4–128 letters/numbers
(case-sensitive), then redeploy. Code changes revoke existing code sessions.
The code is checked only on the server; sessions expire after one hour and
sign-out revokes them. Everyone with the code has access to the shared review
workspace, including document deletion; there is no individual identity or
account administration in this mode. Use a longer code for client access.

`WARREN_AUTH_MODE=code` is the default. Existing invite-only accounts are
preserved and can be used by setting `WARREN_AUTH_MODE=accounts`; see the
[account setup guide](AUTH_SETUP.md). `WARREN_PUBLIC_URL` is still required.
A disposable synthetic local demo may explicitly use
`WARREN_ALLOW_UNAUTHENTICATED=1` with no configured origin.

See [Railway deployment](RAILWAY.md) for hosted PostgreSQL, file storage, domain
configuration, and the first-admin command. Railway project permissions are
separate from the app's admin role.

## Review workflow

1. **Upload & review:** Choose **Upload document**, add a PDF, PNG, JPEG, or TIFF, enter the project and contractor, and extract labor rates. Processing opens **Documents in review**. You can switch back to Upload document while processing continues. Documents are limited to 200 MB.
2. **Saved documents:** Fully saved documents move here automatically and leave the review queue. Browse by filename/project/contractor, inspect the original source pages, open the document's saved rates, or check its accepted rows. Partially saved files also appear here with a Continue review action, while remaining in review until complete.
3. **Saved data:** Search and filter accepted labor records, including by source document. Select records for a check. Open a record to inspect its original values and source page. Short displayed IDs extend when prefixes collide; full identifiers remain in storage and exports. Project ID (filename) is a display label derived from the filename, not a verified business identifier.
4. **Labor checks:** Activate a reference schedule and check selected records or the full saved dataset. Review matches, differences, and unresolved checks independently. Open each result for source and tracker evidence. Only regular/ST rates are compared; a source row produces at most one regular-rate comparison. OT/DT-only rows are skipped.
5. **Differences:** Review and export flagged rate differences, including rates absent from the applicable approved set. For 100 comparisons with 8 differences, this tab and export contain exactly 8 findings. Unresolved checks are counted separately.

**Upload document** and **Documents in review** are separate views. Opening a new upload retains the active document. Switching back retains its source page, selected rows and confirmations; switching between documents also keeps each document's page and row selection while the app is open. The last view and active document are restored after a reload, and confirmed source reviews are saved on the server. Unsaved file drafts and row-selection drafts remain in memory only.

The three process steps are clickable. **Upload document** opens the form; **Review extracted rates** opens the review view; **Save & check** takes you to the selected document's save actions. Step navigation never saves rows or runs checks automatically. Use the explicit save/check buttons for those actions. The review list refreshes processing statuses while it is open, and background completion does not interrupt an upload draft.

The **Documents to review** queue is in Documents in review, with pending table reviews, unreadable pages, failed extractions, and documents with no usable rates first. Use its attention filter to focus on outstanding work. Fully saved documents are listed under Saved documents rather than in this queue. Partial saves and documents with unresolved pages/mapping remain in review.

Within a document, the **Review checklist** lists required reviews and column mapping first. A newly opened document starts on its first pending page; returning to a document resumes your place. Click a checklist item or **Next table to review** to open the source page and focus a specific table. Confirm source checks, select rows and save them explicitly. Confirmations survive reloads and server restarts; remapping invalidates confirmations whose values changed. Saved source rows do not trigger repeat review. Unreadable pages link to their source so you can inspect them or retry a clearer upload.

Existing saved records are not rewritten. If a contractor, classification, or date is missing or needs reconciliation, use **Set comparison details**. A reviewer can select multiple saved rows and apply shared details in one operation. Blank fields in a bulk edit leave existing overrides alone; blank fields in an individual edit restore the original printed value. Comparison details are stored separately, and each check run preserves the details it used. Rerun after changing them.

The Contractor column in review and Saved data shows the current comparison
contractor: a reviewer entry takes precedence over the original source/upload
value. **Contractor source** distinguishes **Reviewer entered**, **Upload/source**,
and **Missing — needs confirmation**. Searches, contractor filters and saved
document cards use that same confirmed name. Open a saved record to see both
the contractor used for comparisons and its original value. Clearing an
individual contractor override restores the original name, or leaves it
unconfirmed when the source was blank. Original records and source evidence
are never rewritten by these display changes.

The source page omits native PDF annotations. Flattened handwriting can remain visible. Unknown or obscured printed values require human review; extraction does not guarantee perfect recognition for arbitrary documents.

Document reading is automatic. PDFs with selectable text use direct extraction; scans use local OCR when needed. There is no OCR switch or configuration section in the interface, and legacy saved preferences cannot disable document reading. Tesseract is required for scanned documents. Extracted values that require source review still need explicit confirmation.

## Delete a document and restart

Use the trash action beside a document in the review queue or **Delete document**
in Saved documents. A confirmation lists saved rows, upload sessions, and check
history affected. Cancel leaves the workspace unchanged. Only the final
**Delete permanently** action performs deletion; if the document changes before
confirmation, review the confirmation again.

Deletion removes all upload/review sessions for the exact same file identity,
its saved CSV rows, source copies, extraction evidence, comparison details, and
check-history runs containing it. The confirmation explicitly identifies runs
that also include other documents; those entire historical snapshots are
removed, while other documents and their saved rows remain available to check
again. The approved reference schedule and classification relationships remain.
Same-named files with different content identities are separate documents.

Deletion is available to signed-in workspace reviewers and affects the shared
workspace. Failed, queued, and processing uploads may be deleted too. A deleted
worker cannot recreate its session or results when it finishes. Original files
outside the app's managed storage are not removed.

Upload the original file again to restart extraction and source review. Its
deleted row IDs no longer block saving. CSV replacement is locked and
recoverable; confirmed deletions interrupted during metadata/file cleanup are
finished on the next data request or server restart. The server does not modify
historical findings in place or leave deleted-document findings in analytics.

## Work dates: document, page, or selected rows

Upload has an optional **Work start / Work finish** range. Enter both dates to
fill extracted rows without work dates, or leave both blank and continue.
Printed work dates and earlier reviewer dates are kept by default. Use actual
work dates, rather than invoice, submission or approval dates. For one day,
enter the same date in both fields.

In document review, **Set document dates**, **Set dates for this page**, and
**Set dates for selected rows** apply one range to the chosen scope. The dialog
shows how many rows are affected; selected rows may span multiple pages. The
**Set dates** action beside an individual row opens that row's date editor.
Keep **Only fill rows missing work dates** checked to preserve existing dates;
uncheck it to replace dates in the chosen scope. **Cancel** changes nothing.
**Remove entered dates** returns those rows to printed dates or unresolved
status when no dates were printed. Date edits never confirm source-table
reviews or save extracted labor rows automatically.

The review table and Saved data show comparison dates and their source:
Printed, Reviewer entered, or Missing. Open a saved record to inspect original
source values. Saved documents also has **Set work dates**; for partial saves,
this covers the ready extraction including unsaved rows. Other saved documents
use their accepted rows. The existing comparison-details editor still supports
individual or bulk date corrections.

Reviewer dates are persisted separately from the original extraction and CSV;
source records and identifiers stay unchanged. New checks use the entered
range, and affected historical checks are marked outdated without rewriting
historical findings. Rerun the check after edits. Missing dates remain Needs
review; a supplied range must be covered in full by the approved schedule.

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
- Broad category names such as Laborer and Operator include compatible classifications in their trade (for example Laborer Journey Person and Operating Engineer Journey Person), even when the tracker also contains a row with the exact generic title. An exact generic row cannot hide eligible child classifications. Stated grades/qualifiers and explicit reviewer relationships continue to restrict the scope.
- When an exact plain title exists, also consider the same title with an explicit **Blended** qualifier. For example, Laborer Foreman can use Laborer Foreperson (Blended) when its approved dates cover the work period; a later plain-title schedule does not hide that candidate. Other stated qualifiers are retained, explicitly blended source titles are not broadened to plain roles, and reviewer-selected classification relationships keep precedence. The printed title is never rewritten.
- Only schedules marked **Approved** that cover the entire work period supply comparison rates. BU approval receipt remains evidence. Pending/withdrawn schedules cannot shadow applicable approved rates. Conflicting overlapping approved rates for the same classification still need review, as do missing dates, unknown/ambiguous contractors, invalid reference information and work periods spanning rate changes.
- Compare the submitted rate with the approved rates in that contractor/trade/role scope. A matching value is a rate match; preserve all supporting classification and row evidence. A broad title is not silently rewritten to a specific grade. If there is one applicable rate, calculate the signed difference. If several grades have different approved rates and none equals the submission, flag **Not in approved rates**, list the possible rates/classifications, and leave the single expected rate and per-hour difference blank. Never choose the nearest price or cross a stated role/grade to make a rate match. A rate match from a broad description establishes membership in the eligible schedule, not independent verification of a worker's exact grade.
- Only regular/ST rates are compared, using exact Python Decimal values with no tolerance. A single printed Rate is treated as regular (REG), and explicit ST columns map to regular/`reg_rate`. OT and DT remain in source extraction/storage but do not create findings or contribute to new metrics, reports or exports. OT/DT-only selections cannot start a check; mixed selections disclose how many rows were skipped. Historical rate-type overrides are ignored. This change leaves existing run results and their status unchanged; rerun to get regular-only results. Normal staleness checks for changed details/references continue to apply.
- A rate that exists in an approved candidate classification but only outside the entered work period is labeled **Outside approved period**. The reason names the matching classification and schedule dates, and is included in reports/CSV exports. This does not change the outcome into a match or change the work dates automatically; only an applicable approved schedule can match.
- Both higher and lower submitted rates are differences. The signed difference per hour is submitted minus approved. The checker does not calculate total financial impact, decide contractual compliance beyond these rules, or approve/reject requests.

The CSV export contains one finding per differing source row/rate type, with finding/run/record/document IDs, project, contractor, classification, work period, source location, submitted/approved rates, signed difference, reference_rate_field (reg_rate for regular), reference version and tracker row, approval evidence, comparison details, matching method/explanation, possible classifications, approved rate set, and all supporting reference rows. Spreadsheet formula prefixes in textual source labels are escaped. All differences in the selected run are exported; search filters affect the screen only. Outdated runs are labeled in the interface and download filename.

## Results metrics and printable PCI reports

Labor checks and Differences include a summary and **Results by document**.
Select a document, contractor, or project to scope the metrics, findings, and
printable report together. Documents are grouped by source identity, so two
versions with the same filename remain separate. A document row shows matching
rates / total rates checked and its percentage, plus counts of differences and
unresolved checks. Click the row to focus on that document.

**Match percentage = matching rates ÷ total rate comparisons** in the selected
document/contractor/project scope. New runs count one comparison per regular/ST
rate; OT/DT-only rows are excluded. Previously saved runs retain their original
results and denominator. Unresolved regular checks stay in
the denominator and are not confirmed differences. An empty scope shows no
percentage. Search filters only the findings list, leaving the summary and
report denominator intact. Select prior check runs to inspect their saved
results; metrics never combine reruns into a misleading cumulative total.

Choose **Print PCI report** to preview a report, then **Print / Save PDF** to
open the browser print dialog. It includes scope, check/preparation dates,
reference version, per-document summaries, and detailed confirmed differences
with contractor/classification, source page/ticket, work dates, submitted and
approved rates, per-hour difference when uniquely determined, tracker rows,
and the checker explanation. Items needing review appear separately by default;
they may be excluded explicitly but remain counted and disclosed. Matching
rate details are omitted. Reports of outdated runs display a rerun warning.

Reports contain saved comparisons only; unsaved extraction rows and processing
failures are not counted. Source page numbers are evidence citations, not the
report's location within the original PCI. The report does not approve/reject
the PCI or calculate total financial impact. Client reports should be shared
only through approved channels. The existing **Download differences CSV**
continues to export all confirmed differences from the entire selected run;
its scope is disclosed separately from the filtered print report.

## Classification map

Open **Classification map** in Labor checks or Differences. The active tracker generates a local hierarchy: contractor → trade family → actual tracker classification → source schedule/rate. It covers every known nonblank classification in that reference, with unfamiliar titles under Other classifications. Family labels and spelling aliases organize known data; this is not a claim to know every construction occupation or every possible synonym.

Reviewers can save a contractor-specific equivalent job title targeting an actual classification in the active tracker, then rerun checks. Relationships are editable by saving the same source title again and removable from the map. They cannot target another contractor or an invented classification, and they never overwrite source wording. The check snapshot retains its selected classifications, matching method/explanation, approved rate set and reference rows. Relationship changes make prior runs outdated. All graph data and saved relationships stay local; no external model is called.

## Storage and operation

Accepted rows remain in `data/document_line_items.csv` with the existing lock, append recovery, duplicate protection, and `document_line_items_private/` evidence. Equal-looking source rows remain distinct. Exact reuploads and renamed copies skip already-saved IDs; modified/rescanned documents remain separate versions.

New originals are stored in `data/reviewer/uploads/`. PostgreSQL (when `DATABASE_URL` is set), or `data/reviewer/reviewer.sqlite3` locally, stores accounts, token hashes, extraction sessions, immutable reference versions, active-reference selection, current comparison details, contractor-specific classification relationships, and immutable check-run snapshots. These artifacts are excluded from Git; hosted database records stay in the configured PostgreSQL service. Browser storage contains only tab/session/run identifiers. Refreshing or restarting preserves completed extraction and checks; interrupted jobs are marked failed and can be retried through reupload. A single extraction worker processes queued documents and exposes page progress.

`WARREN_DATA_DIR` can point to another local data directory, useful for isolated demos/tests. It must contain any intended reference and accepted dataset; the default is the repository's `data/`. The local server runs on 127.0.0.1:8000. Authentication is handled by the app. Railway deployments listen on the assigned port and require a PostgreSQL connection, an HTTPS public origin, and a persistent app volume; document processing stays on the reviewer server. Original documents, extracted worker information, evidence, and exported findings are sensitive local artifacts.

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
