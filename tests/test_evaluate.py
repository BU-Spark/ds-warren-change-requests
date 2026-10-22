"""Synthetic reference comparisons keep layout separate from stored row types."""

import csv
import json

from ocr_ingestion.evaluate import evaluate
from tests.helpers import acme_lines, detail_lines, write_pdf


def write_reference(path, count=1):
    row = {
        "Document": "CD0123", "Type": "Labor", "Source Page": "1",
        "ST Hours": "4", "OT Hours": "", "DT Hours": "",
        "ST Rate": "10.00", "OT Rate": "15.00", "DT Rate": "20.00",
        "Amount USD": "40.00", "Rate Basis": "Full rate",
    }
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerows([row] * count)
    return path


def test_reference_comparison_matches_unified_labor_using_source_layout(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    write_pdf(inputs / "CD0123.pdf", detail_lines())
    reference = write_reference(tmp_path / "reference.csv", count=2)
    output = tmp_path / "reports"
    summary = evaluate(reference, [inputs], output)
    assert summary["status_counts"] == {"printed_numeric_fields_match": 2}
    assert summary["documents"][0]["row_types"] == {"labor": 2}
    comparisons = json.loads((output / "reference_comparison.json").read_text())
    assert len({row["record_id"] for row in comparisons}) == 2
    with (output / "extracted_labor.csv").open() as stream:
        assert {row["row_type"] for row in csv.DictReader(stream)} == {"labor"}
    evidence = json.loads(next(output.glob("*-evidence.json")).read_text())
    assert evidence["tables"][0]["kind"] == "labor_detail"


def test_generic_acme_layout_is_not_compared_as_explicit_st_ot_dt(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    write_pdf(inputs / "CD0123.pdf", acme_lines())
    reference = write_reference(tmp_path / "reference.csv")
    output = tmp_path / "reports"
    evaluate(reference, [inputs], output)
    comparisons = json.loads((output / "reference_comparison.json").read_text())
    assert comparisons[0]["status"] == "requires_source_reconciliation"
    assert comparisons[0]["extracted_candidates"] == []
