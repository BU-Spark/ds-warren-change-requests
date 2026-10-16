# Warren Towers: Contractor Change Request Validation

An AI-assisted review project for Boston University construction change requests. The initial scope is to compare labor rates in contractor PDFs against schedules applicable to the work dates, check approval status, and show source evidence to a human reviewer.

## Repository layout

- `data/`: local source and generated CSV datasets; only its `README.MD` is committed.
- `data_for_analysis/data_cleaning.ipynb`: step-by-step cleaning, schema normalization, and verified CSV exports.
- `data_for_analysis/Data_Analysis.MD`: overview of the analysis workflow.
- `brandsafway_data/brandsafway_analytics.ipynb`: starter notebook for the next PDF analysis phase.
- `dataset-documentation/DATASETDOC.md`: general dataset documentation.
- `requirements.txt`: notebook and data-processing dependencies.

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

Saved notebook outputs can contain sensitive records. Clear **all outputs**, execution counts, and sensitive metadata before staging a notebook, and review code and Markdown cells for embedded client values. Outputs will still display when running notebooks locally. Inspect the complete staged diff and file list before every commit; ignore rules alone do not inspect notebook content or protect files already tracked by Git.

## Cleaning decisions

The full cleaned tracker retains source row references, original position spellings, context, and approval history. The condensed table keeps fields needed for contractor, classification, date, rate-type, and approval checks. Missing values and source date issues remain available for review. Reviewed spelling variations use Journey Person; any broader equivalence with Journeyman needs confirmation for the applicable contractor. Snapshot fields such as Current / Expired do not determine historical work-date validity.

## Contribution workflow

Create working branches from `dev` and open pull requests targeting `dev`. Add the project PM and TPM as reviewers. Semester wrap-up changes merge from `dev` to `main`.
