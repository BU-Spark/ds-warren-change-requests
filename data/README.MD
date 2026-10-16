# Local datasets

This directory holds client datasets locally. Its contents are ignored by Git except for this README. The source files and generated datasets must be transferred through the restricted shared drive, not through GitHub.

| Filename | Purpose |
| --- | --- |
| `Labor_rate_data.csv` | Original client labor-rate tracker; preserve as supplied. |
| `cleaned_raw_labor_rates_tracker.csv` | Full cleaned tracker with source row numbers, original position names, context, and approval history. |
| `labor_rates_fa.csv` | Condensed labor rates for analysis (FA), with contractor, position, effective dates, Reg/OT/DT rates, approval status, BU approval date, and source row number. |
| `data_quality_notes.md` | Optional private source-record findings and unresolved issues; also ignored. |

Place the original tracker here, then run `../data_for_analysis/data_cleaning.ipynb` to generate both cleaned CSVs. Their filenames remain unchanged. All source row references point to `Labor_rate_data.csv`.

Store the local BrandSafway PDF at `../brandsafway_data/AD0015.04-BrandSafway.pdf` and client instructions at `../brandsafway_data/project_instructions.md`; both are excluded from Git. Request access or file copies from the project maintainer. The shared-drive location will be provided privately.

The rate fields use neutral names `reg_rate`, `ot_rate`, and `dt_rate`; approval depends on the separate `status` field. Do not infer approval from the presence of a rate.
