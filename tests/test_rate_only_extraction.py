"""Printed ST rates are eligible independently of billed work or approval."""

import shutil

import pymupdf
import pytest

from ocr_ingestion import append_records, extract_document, load_records
from reviewer.checker import compare, parse_reference
from tests.helpers import detail_lines, write_pdf
from tests.test_checker import reference_bytes, schedule

ROLES = [
    "Laborer Foreman",
    "Laborer",
    "Operator",
    "Teamster",
    "Carpenter Foreman",
    "Carpenter",
]


def tally_lines(unused_marker="-"):
    lines = [
        (60, [(20, "T&M Tally")]),
        (80, [(20, "Rating"), (170, "Billing Rate"), (350, "Hours Worked")]),
        (
            100,
            [
                (170, "ST"),
                (220, "OT"),
                (270, "DT"),
                (350, "ST"),
                (400, "OT"),
                (450, "DT"),
                (510, "Billing Amount"),
            ],
        ),
    ]
    for index, role in enumerate(ROLES):
        worked = role in {"Laborer", "Carpenter Foreman"}
        lines.append(
            (
                130 + index * 25,
                [
                    (20, role),
                    (170, f"{10 + index}.00"),
                    (350, "8" if worked else unused_marker),
                    (510, str((10 + index) * 8) if worked else unused_marker),
                ],
            )
        )
    lines.extend(
        [
            (290, [(20, "Role without a rate")]),
            (310, [(20, "TOTAL"), (170, "999.00"), (510, "999.00")]),
        ]
    )
    return lines


@pytest.mark.parametrize("unused_marker", ["", "-", "0"])
def test_all_six_st_rates_are_retained_without_billing_fields(tmp_path, unused_marker):
    source = write_pdf(tmp_path / "roles.pdf", tally_lines(unused_marker))
    result = extract_document(source, contractor="Example Contractor", use_ocr=False)
    assert [r["position_original"] for r in result.records] == ROLES
    assert [r["reg_rate"] for r in result.records] == [f"{10 + i}.00" for i in range(6)]
    assert all(r["ot_rate"] == r["dt_rate"] == r["rate"] == "" for r in result.records)
    assert all(r["work_start"] == r["work_end"] == "" for r in result.records)
    for row in result.records:
        if row["position_original"] not in {"Laborer", "Carpenter Foreman"}:
            expected = "0" if unused_marker == "0" else ""
            assert row["reg_hours"] == row["total_amount"] == expected
    assert len({r["record_id"] for r in result.records}) == 6


def test_checks_or_approval_do_not_control_extraction_or_regular_comparison(tmp_path):
    source = write_pdf(tmp_path / "roles.pdf", tally_lines())
    with pymupdf.open(source) as doc:
        for y in (155, 230):
            doc[0].add_text_annot((140, y), "Reviewer check")
        doc.save(tmp_path / "reviewed.pdf")
    result = extract_document(
        tmp_path / "reviewed.pdf", contractor="Example Contractor", use_ocr=False
    )
    assert len(result.records) == 6
    reference = parse_reference(
        reference_bytes(
            [
                schedule(
                    source_csv_row_number=str(i + 2),
                    position=role,
                    reg_rate="99.00" if role == "Teamster" else f"{10 + i}.00",
                    status="Pending" if role == "Operator" else "Approved",
                )
                for i, role in enumerate(ROLES)
            ]
        ),
        "synthetic.csv",
    )
    details = {
        r["record_id"]: {"work_start": "2026-01-02", "work_end": "2026-01-02"}
        for r in result.records
    }
    findings = compare(result.records, reference, details, "synthetic-run")
    assert len(findings) == 6
    assert {f["rate_type"] for f in findings} == {"REG"}
    assert {f["reference_rate_field"] for f in findings} == {"reg_rate"}
    assert sum(f["outcome"] == "match" for f in findings) == 4
    assert sum(f["outcome"] == "difference" for f in findings) == 1
    assert sum(f["outcome"] == "needs_review" for f in findings) == 1
    assert all(r["work_start"] == "" for r in result.records)


def test_existing_worked_rows_keep_identity_and_new_roles_append_once(tmp_path):
    result = extract_document(
        write_pdf(tmp_path / "roles.pdf", tally_lines()), use_ocr=False
    )
    worked = [r["record_id"] for r in result.records if r["reg_hours"]]
    all_ids = [r["record_id"] for r in result.records]
    reviewed = [t.table_id for t in result.tables]
    csv = tmp_path / "accepted.csv"
    assert (
        append_records(result, csv, worked, reviewed_table_ids=reviewed)["added"] == 2
    )
    assert (
        append_records(result, csv, all_ids, reviewed_table_ids=reviewed)["added"] == 4
    )
    assert (
        append_records(result, csv, all_ids, reviewed_table_ids=reviewed)["added"] == 0
    )
    assert len(load_records(csv)) == 6


def test_detail_rate_without_hours_or_date_is_not_discarded(tmp_path):
    lines = detail_lines()
    lines[1] = (120, [(x, text) for x, text in lines[1][1] if x not in (20, 350, 610)])
    result = extract_document(write_pdf(tmp_path / "detail.pdf", lines), use_ocr=False)
    assert len(result.records) == 2
    assert result.records[0]["reg_rate"] == "10.00"
    assert (
        result.records[0]["reg_hours"]
        == result.records[0]["reg_amount"]
        == result.records[0]["work_start"]
        == ""
    )
    assert result.tables[0].requires_review


def test_scanned_st_rates_without_hours_are_retained(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(tmp_path / "roles.pdf", tally_lines())
    with pymupdf.open(source) as document:
        document[0].get_pixmap(dpi=144).save(tmp_path / "scan.png")
    result = extract_document(tmp_path / "scan.png")
    assert [r["position_original"] for r in result.records] == ROLES
    assert [r["reg_rate"] for r in result.records] == [f"{10 + i}.00" for i in range(6)]
    assert all(t.requires_review for t in result.tables)
