"""Synthetic schedule comparisons; no private rate values or client fixtures."""

import csv
import io

import pytest

from reviewer.checker import REFERENCE_FIELDS, compare, differences_csv, parse_reference


def schedule(**updates):
    return {
        **dict.fromkeys(REFERENCE_FIELDS, ""),
        "source_csv_row_number": "2",
        "subcontractor": "Example Contractor",
        "position": "Carpenter",
        "effective_time_period_start": "2026-01-01",
        "effective_time_period_finish": "2026-12-31",
        "reg_rate": "10.00",
        "ot_rate": "15.00",
        "dt_rate": "20.00",
        "status": "Approved",
        **updates,
    }


def reference_bytes(rows=None):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REFERENCE_FIELDS)
    writer.writeheader()
    writer.writerows(rows if rows is not None else [schedule()])
    return output.getvalue().encode()


def record(**updates):
    return {
        "record_id": "a" * 64,
        "document_id": "b" * 64,
        "contractor": "Example Contractor",
        "position_original": "Carpenter",
        "project": "Example project",
        "work_start": "2026-01-02",
        "work_end": "2026-01-02",
        "reg_rate": "10.00",
        "source_file": "example.pdf",
        "source_page": "1",
        "table_id": "p1-labor",
        **updates,
    }


def run(row=None, schedules=None, details=None):
    reference = parse_reference(reference_bytes(schedules), "synthetic.csv")
    return compare([row or record()], reference, details or {}, "test-run")


def test_exact_decimal_comparison_and_all_rate_types():
    findings = run(record(reg_rate="10.000", ot_rate="16.25", dt_rate="19.00"))
    assert [f["outcome"] for f in findings] == ["match", "difference", "difference"]
    assert [f["difference_per_hour"] for f in findings] == ["0.000", "1.25", "-1.00"]
    assert [f["rate_type"] for f in findings] == ["REG", "OT", "DT"]
    assert all(f["reference_row"] == "2" for f in findings)


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"contractor": ""}, "contractor"),
        ({"work_start": "", "work_end": ""}, "dates"),
        ({"work_start": "bad-date"}, "valid ISO"),
        ({"work_start": "2026-02-01", "work_end": "2026-01-01"}, "before"),
        ({"contractor": "Unrelated"}, "No schedule"),
        ({"position_original": "Journeyman"}, "No schedule"),
        ({"work_start": "2025-01-01", "work_end": "2025-01-01"}, "covers"),
        ({"work_start": "2026-12-31", "work_end": "2027-01-01"}, "covers"),
    ],
)
def test_uncertain_comparisons_never_become_differences(change, reason):
    findings = run(record(**change))
    assert findings[0]["outcome"] == "needs_review"
    assert reason in findings[0]["reason"]
    assert not list(csv.DictReader(io.StringIO(differences_csv(findings))))


@pytest.mark.parametrize(
    "status",
    [
        "Pending Approval",
        "Pending Final Approval",
        "Withdrawn",
        "",
        "Sub Withdrawing Rates",
    ],
)
def test_approval_required(status):
    finding = run(schedules=[schedule(status=status)])[0]
    assert finding["outcome"] == "needs_review"
    assert "not marked Approved" in finding["reason"]
    assert finding["approval_status"] == status


def test_approval_receipt_is_evidence_not_additional_requirement():
    assert run(schedules=[schedule(bu_approval_received="")])[0]["outcome"] == "match"


@pytest.mark.parametrize("day", ["2026-01-01", "2026-12-31"])
def test_inclusive_schedule_boundaries(day):
    assert run(record(work_start=day, work_end=day))[0]["outcome"] == "match"


def test_case_whitespace_normalization_without_classification_aliases():
    assert (
        run(
            record(
                contractor="  EXAMPLE   Contractor ", position_original=" carpenter "
            )
        )[0]["outcome"]
        == "match"
    )


def test_single_printed_rate_is_regular_without_a_reviewer_choice():
    row = record(reg_rate="", rate="11.00")
    finding = run(row)[0]
    assert finding["outcome"] == "difference"
    assert finding["rate_type"] == "REG"
    assert finding["reference_rate_field"] == "reg_rate"
    assert finding["approved_rate"] == "10.00"
    assert finding["difference_per_hour"] == "1.00"
    assert row["rate"] == "11.00" and not row["reg_rate"]


def test_obsolete_rate_type_overrides_do_not_change_regular_matching():
    row = record(reg_rate="", rate="10.00")
    finding = run(row, details={row["record_id"]: {"generic_rate_type": "OT"}})[0]
    assert finding["outcome"] == "match" and finding["rate_type"] == "REG"
    assert "generic_rate_type" not in finding["review_details"]


def test_explicit_regular_column_is_not_counted_twice():
    findings = run(record(rate="10.00", reg_rate="10.00"))
    assert len(findings) == 1 and findings[0]["rate_type"] == "REG"


def test_unapproved_schedules_do_not_shadow_an_applicable_approved_schedule():
    rows = [
        schedule(),
        schedule(source_csv_row_number="3", reg_rate="30", status="Pending Approval"),
    ]
    finding = run(schedules=rows)[0]
    assert finding["outcome"] == "match"
    assert finding["approved_rate"] == "10.00"
    assert len(finding["candidates"]) == 2


def test_work_range_spanning_schedules_requires_review():
    rows = [
        schedule(effective_time_period_finish="2026-06-30"),
        schedule(source_csv_row_number="3", effective_time_period_start="2026-07-01"),
    ]
    assert (
        run(record(work_start="2026-06-01", work_end="2026-07-02"), schedules=rows)[0][
            "outcome"
        ]
        == "needs_review"
    )


def test_invalid_reference_period_and_missing_rate_are_unresolved():
    ref = parse_reference(
        reference_bytes([schedule(effective_time_period_finish="2025-01-01")]),
        "bad.csv",
    )
    assert len(ref["issues"]) == 1
    assert compare([record()], ref, {}, "test")[0]["outcome"] == "needs_review"
    assert (
        run(record(ot_rate="15"), schedules=[schedule(ot_rate="")])[1]["outcome"]
        == "needs_review"
    )


@pytest.mark.parametrize(
    "contents",
    [
        b"wrong,header\n1,2\n",
        reference_bytes([]),
        reference_bytes([schedule(), schedule()]),
        reference_bytes([schedule(reg_rate="NaN")]),
        reference_bytes([schedule(effective_time_period_start="01/02/26")]),
        b"\xff",
    ],
)
def test_invalid_reference_rejected(contents):
    with pytest.raises(ValueError):
        parse_reference(contents, "invalid.csv")


def test_one_hundred_checks_export_only_eight_differences_and_keep_repeated_rows():
    records = [
        record(record_id=f"{i:064x}", reg_rate="11.00" if i < 8 else "10.00")
        for i in range(100)
    ]
    findings = compare(
        records, parse_reference(reference_bytes(), "synthetic.csv"), {}, "test-run"
    )
    assert len(findings) == 100
    exported = list(csv.DictReader(io.StringIO(differences_csv(findings))))
    assert len(exported) == 8
    assert len({r["record_id"] for r in exported}) == 8
    assert all(
        r["difference_per_hour"] == "1.00" and r["contractor"] == "Example Contractor"
        for r in exported
    )
    assert records[0]["reg_rate"] == "11.00"


def test_explicit_zero_is_a_rate_and_export_escapes_spreadsheet_formulas():
    finding = run(record(reg_rate="0", source_file='=HYPERLINK("bad")'))[0]
    assert finding["outcome"] == "difference"
    exported = list(csv.DictReader(io.StringIO(differences_csv([finding]))))[0]
    assert exported["source_file"].startswith("'=")
    assert exported["difference_per_hour"] == "-10.00"


def test_rate_difference_preserves_precision_beyond_default_decimal_context():
    approved = "10.123456789012345678901234567890123"
    submitted = "10.123456789012345678901234567890124"
    finding = run(record(reg_rate=submitted), schedules=[schedule(reg_rate=approved)])[
        0
    ]
    assert finding["outcome"] == "difference"
    assert finding["difference_per_hour"] == "0.000000000000000000000000000000001"
