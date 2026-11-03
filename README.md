# Warren Towers: Contractor Change Request Validation

An AI-assisted review project for Boston University construction change requests. The local reviewer compares printed labor rates in contractor documents against approved schedules applicable to the work dates and shows source evidence to a human reviewer.

## Repository layout

- `data/`: local source and generated CSV datasets; only its `README.MD` is committed.
- `data_for_analysis/data_cleaning.ipynb`: step-by-step cleaning, schema normalization, and verified CSV exports.
- `brandsafway_data/brandsafway_analytics.ipynb`: starter notebook for the next PDF analysis phase.
- `ocr_ingestion/`: printed-table extraction, protected CSV storage, and evaluation tools.
- `reviewer/`: local FastAPI application, persistent review sessions, reference versions, and labor checker.
- `frontend/`: React/TypeScript client interface; see the [reviewer guide](reviewer/README.md).
- `tests/`: synthetic extraction, storage, and interface regression tests with shared document builders.
- `dataset-documentation/DATASETDOC.md`: course dataset-documentation template and semester wrap-up instructions.
- `requirements.txt`: notebook and data-processing dependencies.
- `requirements-dev.txt`: runtime dependencies plus pytest for development.

See [data/README.MD](data/README.MD) for dataset names and local placement. Client datasets, PDFs, project instructions, meeting notes, and detailed source findings are excluded from Git. Obtain them through the restricted shared drive or the project maintainer; no private drive link is published here.

## Local setup

Run these commands from the repository root:

```bash
python3 -m venv warren_towers
source warren_towers/bin/activate
python -m pip install -r requirements.txt
python -m jupyterlab
```

Select the `warren_towers` interpreter when using an editor. Place the original tracker at `data/Labor_rate_data.csv`, then run the cleaning notebook in order. Its paths work from the repository root or a notebook subfolder. The last cell regenerates and verifies both cleaned CSVs in `data/`.

CSV files do not store Python types; use the schema in the notebook when reloading them. The regular, overtime, and double-time fields are named `reg_rate`, `ot_rate`, and `dt_rate`. Their unlabeled source group does not establish approval; check `status` separately.

## Privacy before committing

The ignore rules exclude CSVs, PDFs, spreadsheet files, local data, client project notes, notebook checkpoints, and the virtual environment. Detailed client findings belong in the ignored `data/data_quality_notes.md` or restricted shared drive.

Keep uploaded images, extracted JSON evidence, and evaluation reports inside `data/` as well. Local handoff files (`MEMORY.md` and `ocr_ingestion/INSTRUCTIONS.md`) stay on disk and are ignored because they contain private findings and temporary implementation history. Source code, synthetic tests, setup configuration, and public usage documentation belong in Git.

Saved notebook outputs can contain sensitive records. Clear **all outputs**, execution counts, and sensitive metadata before staging a notebook, and review code and Markdown cells for embedded client values. Outputs will still display when running notebooks locally. Inspect the complete staged diff and file list before every commit; ignore rules alone do not inspect notebook content or protect files already tracked by Git.

## Cleaning decisions

The full cleaned tracker retains source row references, original position spellings, context, and approval history. The condensed table keeps fields needed for contractor, classification, date, rate-type, and approval checks. Missing values and source date issues remain available for review. Stored position spellings remain unchanged. The checker separately uses contractor-scoped spelling aliases, trade families and saved title relationships to retrieve applicable schedules. Snapshot fields such as Current / Expired do not determine historical work-date validity.

## Printed labor-table ingestion

With the Python environment active, build and start the reviewer:

```bash
python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m reviewer
```

Open **http://127.0.0.1:8000**. Use **Upload & review** to extract and save printed labor rates, **Saved data** to browse records, and **Labor checks** to compare them against the rate tracker. **Differences** shows and exports only confirmed rate differences. Matches and unresolved checks stay in Labor checks.

Node.js 22+ is recommended for the frontend build; Node is not needed to run an already built UI. All document processing and storage remain local. See the [reviewer guide](reviewer/README.md) for reference updates, matching rules, and development/browser tests, and the [ingestion guide](ocr_ingestion/README.md) for OCR and the unchanged CSV schema.

## Contribution workflow

Install development dependencies with `python -m pip install -r requirements-dev.txt` and run `python -m pytest -q`. Tests generate synthetic documents in temporary directories; client data is not needed.

Create working branches from `dev` and open pull requests targeting `dev`. Add the project PM and TPM as reviewers. Semester wrap-up changes merge from `dev` to `main`.
