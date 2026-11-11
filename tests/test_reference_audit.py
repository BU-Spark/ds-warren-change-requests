from reviewer.checker import parse_reference
from reviewer.reference_audit import reference_conflicts
from tests.test_checker import reference_bytes, schedule


def test_conflicts_are_scoped_to_contractor_role_approved_period_and_rate():
    rows = [
        schedule(),
        schedule(
            source_csv_row_number="3",
            ot_rate="16",
            effective_time_period_start="2026-06-01",
        ),
        schedule(source_csv_row_number="4", ot_rate="17", status="Pending"),
        schedule(source_csv_row_number="5", reg_rate="20", subcontractor="Other"),
        schedule(
            source_csv_row_number="6", reg_rate="20", position="Carpenter Foreman"
        ),
        schedule(
            source_csv_row_number="7",
            reg_rate="20",
            effective_time_period_start="2027-01-01",
            effective_time_period_finish="2027-12-31",
        ),
    ]
    reference = parse_reference(reference_bytes(rows), "example.csv")
    audit = reference_conflicts(reference)
    assert audit["reference_version"] == reference["id"]
    assert audit["conflicts"] == [
        {
            "contractor": "Example Contractor",
            "classification": "Carpenter",
            "reference_rows": ["2", "3"],
            "overlap_start": "2026-06-01",
            "overlap_finish": "2026-12-31",
            "rates": {"ot_rate": ["15.00", "16"]},
        }
    ]


def test_equal_numeric_rates_are_not_conflicts_and_boundaries_are_inclusive():
    ref = parse_reference(
        reference_bytes(
            [schedule(), schedule(source_csv_row_number="3", reg_rate="10.000")]
        ),
        "same.csv",
    )
    assert reference_conflicts(ref)["conflicts"] == []
    ref["rows"][1].update(reg_rate="11", effective_time_period_start="2026-12-31")
    assert reference_conflicts(ref)["conflicts"][0]["overlap_start"] == "2026-12-31"
