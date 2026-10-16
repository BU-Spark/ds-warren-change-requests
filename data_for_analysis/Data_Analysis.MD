# Data preparation and analysis

Run `data_cleaning.ipynb` using the `warren_towers` environment. The notebook reads `../data/Labor_rate_data.csv` and produces:

- `../data/cleaned_raw_labor_rates_tracker.csv`: full cleaned tracker.
- `../data/labor_rates_fa.csv`: labor rates for analysis (FA), containing the fields needed for rate validation.

All CSVs remain local and are excluded from Git. See `../data/README.MD` for access and placement instructions. Clear notebook outputs and review source cells before committing.

The next analysis phase lives in `../brandsafway_data/brandsafway_analytics.ipynb`. It will compare extracted PDF labor lines to the applicable rate schedule, check approval status, and provide evidence for human review.
