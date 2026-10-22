"""Private, read-only source evaluation; writes reports only to ignored data/ storage.

Example:
python -m ocr_ingestion.evaluate --reference 'data/brandsafway_combined_clean (1).csv' \
    --inputs brandsafway_data ACME_data
"""

import argparse
from collections import Counter
import csv
from decimal import Decimal
import json
from pathlib import Path
import re

from .extraction import REFERENCE_RE, extract_document
from .models import FIELDS, is_labor_rate, number


def _numeric(value):
    try:
        return Decimal(number(value) or "0")
    except ValueError:
        return None


def _amount(row):
    if row["total_amount"]:
        return _numeric(row["total_amount"])
    parts = [row[key] for key in ("reg_amount", "ot_amount", "dt_amount")]
    return sum((_numeric(value) for value in parts if value), Decimal(0)) if any(parts) else None


def _signature(row):
    return tuple(_numeric(row[key]) for key in (
        "reg_hours", "ot_hours", "dt_hours", "reg_rate", "ot_rate", "dt_rate",
    )) + (_amount(row),)


def _expected_signature(row):
    return tuple(_numeric(row[key]) for key in (
        "ST Hours", "OT Hours", "DT Hours", "ST Rate", "OT Rate", "DT Rate", "Amount USD",
    ))


def evaluate(reference: Path, inputs: list[Path], output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    extractions = {}
    documents = []
    for folder in inputs:
        for source in sorted(folder.glob("*.pdf")):
            result = extract_document(source, use_ocr=False)
            key = REFERENCE_RE.search(source.stem)
            key = key.group(0).upper() if key else source.stem.upper()
            extractions[key] = result
            labor = [r for r in result.records if is_labor_rate(r)]
            documents.append({"file": source.name, "document_id": result.document_id,
                              "records": len(result.records), "labor_rows": len(labor),
                              "row_types": dict(Counter(r["row_type"] for r in result.records)),
                              "issue_counts": dict(Counter(i["code"] for i in result.issues)),
                              "labor_rows_missing_printed_work_date": sum(not r["work_start"] for r in labor)})
            (output / f"{result.document_id}-evidence.json").write_text(result.as_json(), encoding="utf-8")
    # Candidate extraction output for inspection, separate from the reviewed accumulated dataset.
    with (output / "extracted_labor.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(record for result in extractions.values() for record in result.records
                         if is_labor_rate(record))
    with reference.open(newline="", encoding="utf-8-sig") as stream:
        expected = list(csv.DictReader(stream))
    required = {"Document", "Type", "Source Page", "ST Hours", "OT Hours", "DT Hours",
                "ST Rate", "OT Rate", "DT Rate", "Amount USD", "Rate Basis"}
    if expected and not required.issubset(expected[0]):
        raise ValueError("Comparison CSV does not have the expected teammate export columns.")
    comparisons = []
    used = set()
    for index, expected_row in enumerate(expected, 2):
        name = expected_row["Document"].upper()
        result = extractions.get(name)
        if result is None:
            # Source revisions may add a suffix not present in the comparison export.
            options = [value for key, value in extractions.items() if re.fullmatch(re.escape(name) + r"R?\d*", key)]
            result = options[0] if len(options) == 1 else None
        entry = {"reference_csv_row": index, "document": name,
                 "source_page": expected_row["Source Page"], "rate_basis": expected_row["Rate Basis"]}
        if result is None:
            entry["status"] = "source_document_missing"
        elif expected_row["Type"].lower() != "labor":
            entry["status"] = "outside_labor_rate_comparison"
        else:
            reference_tables = {table.table_id for table in result.tables
                                if table.kind in {"labor_detail", "labor_tally"}}
            candidates = [row for row in result.records if row["source_page"] == expected_row["Source Page"]
                          and row["table_id"] in reference_tables and row["record_id"] not in used]
            expected_signature = _expected_signature(expected_row)
            matches = [row for row in candidates if _signature(row) == expected_signature]
            if matches:
                match = matches[0]
                used.add(match["record_id"])
                entry.update(status="printed_numeric_fields_match", record_id=match["record_id"])
            else:
                # This is a discrepancy, not a declaration that the reference is incorrect.
                # The private evidence permits source-by-source investigation without copying values.
                entry.update(status="requires_source_reconciliation", reference_values=expected_row,
                             extracted_candidates=candidates,
                             reason="Compare original printed cells with reference-derived/annotated values; fix extraction if unsupported.")
                same_rates = [row for row in candidates if _signature(row)[3:6] == expected_signature[3:6]]
                if same_rates:
                    entry["status"] = "printed_rates_match_hours_or_amount_differ"
                    entry["reason"] = "Rates agree; inspect whether the reference includes reviewed hour/amount adjustments that are excluded here."
                elif expected_row["Rate Basis"].strip().lower() == "premium only":
                    entry["reason"] = "Reference is labeled Premium only; original printed full rates are retained. Reconcile the reviewer/derived premium separately."
            if expected_row.get("Work Start") not in {None, "", "Not provided", "Not applicable"} and not any(r["work_start"] for r in candidates):
                entry["date_note"] = "No printed work date extracted; handwriting and unrelated dates are excluded."
        comparisons.append(entry)
    counts = Counter(row["status"] for row in comparisons)
    summary = {"documents": documents, "comparison_rows": len(expected),
               "labor_rows_with_matching_printed_rates": counts["printed_numeric_fields_match"] + counts["printed_rates_match_hours_or_amount_differ"],
               "status_counts": dict(Counter(row["status"] for row in comparisons)),
               "note": "Zero/dash equivalence and row amount sums are used only for comparison, never inserted into extraction. OCR is disabled for this native printed-table evaluation."}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "reference_comparison.json").write_text(json.dumps(comparisons, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=Path("data/ocr_ingestion/evaluation"))
    args = parser.parse_args()
    # Detailed reports contain client records; enforce the repository's ignored data location.
    private_root = Path(__file__).resolve().parents[1] / "data"
    if not args.output.resolve().is_relative_to(private_root):
        parser.error("Evaluation reports must be written under the repository's private data/ directory.")
    print(json.dumps(evaluate(args.reference, args.inputs, args.output), indent=2))


if __name__ == "__main__":
    main()
