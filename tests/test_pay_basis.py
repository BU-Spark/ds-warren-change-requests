"""Synthetic premium cases: a matching price must never select the pay type."""

import pytest

from tests.test_checker import record, run, schedule


@pytest.mark.parametrize(
    "wording",
    [
        "Premium",
        "Premium Sunday",
        "OT premium only",
        "shift differential",
        "Field Labor-PT",
    ],
)
def test_ambiguous_pay_requires_evidence_even_when_price_matches(wording):
    row = record(reg_rate="", rate="10", description=wording)
    finding = run(row)[0]
    assert finding["outcome"] == "needs_review"
    assert finding["rate_type"] == "UNRESOLVED"
    assert finding["reference_rate_field"] == ""
    assert finding["source_rate_field"] == "rate"


@pytest.mark.parametrize(
    "wording,basis,rate",
    [
        ("2 hours overtime", "OT", "15"),
        ("Carpenter-DT", "DT", "20"),
        ("Straight time", "REG", "10"),
        ("Work on Sunday", "REG", "10"),
    ],
)
def test_explicit_full_rate_wording_and_no_calendar_guess(wording, basis, rate):
    finding = run(record(reg_rate="", rate=rate, description=wording))[0]
    assert finding["outcome"] == "match"
    assert finding["rate_type"] == basis


def test_conflicting_explicit_labels_require_review():
    assert (
        run(record(reg_rate="", rate="15", description="ST/OT"))[0]["outcome"]
        == "needs_review"
    )


@pytest.mark.parametrize(
    "basis,submitted,expected",
    [
        ("REG", "10", "10.00"),
        ("OT", "15", "15.00"),
        ("DT", "20", "20.00"),
        ("OT_PREMIUM", "5", "5.00"),
        ("DT_PREMIUM", "10", "10.00"),
    ],
)
def test_confirmed_basis_keeps_original_and_supports_increment(
    basis, submitted, expected
):
    row = record(reg_rate="", rate=submitted, description="Premium")
    details = {
        row["record_id"]: {
            "confirmed_pay_basis": basis,
            "pay_basis_evidence": "Approved agreement section 2; source page 1.",
        }
    }
    result = run(row, details=details)[0]
    assert result["outcome"] == "match" and result["approved_rate"] == expected
    assert row["rate"] == submitted and row["reg_rate"] == ""
    assert result["review_details"] == details[row["record_id"]]


def test_unsubstantiated_confirmation_cannot_make_a_match():
    row = record(reg_rate="", rate="15", description="Premium")
    assert (
        run(row, details={row["record_id"]: {"confirmed_pay_basis": "OT"}})[0][
            "outcome"
        ]
        == "needs_review"
    )


def test_explicit_columns_keep_their_basis_despite_description():
    findings = run(record(description="Premium", ot_rate="15", dt_rate="20"))
    assert [f["rate_type"] for f in findings] == ["REG", "OT", "DT"]
    assert all(f["outcome"] == "match" for f in findings)


@pytest.mark.parametrize("regular,overtime", [("", "15"), ("10", ""), ("20", "15")])
def test_increment_needs_valid_full_and_regular_rates(regular, overtime):
    row = record(reg_rate="", rate="5", description="Premium")
    result = run(
        row,
        schedules=[schedule(reg_rate=regular, ot_rate=overtime)],
        details={
            row["record_id"]: {
                "confirmed_pay_basis": "OT_PREMIUM",
                "pay_basis_evidence": "Agreement: OT minus regular",
            }
        },
    )[0]
    assert result["outcome"] == "needs_review"


def test_conflicting_schedules_remain_unresolved_for_confirmed_premium():
    row = record(reg_rate="", rate="5", description="Premium")
    result = run(
        row,
        schedules=[schedule(), schedule(source_csv_row_number="3", ot_rate="17")],
        details={
            row["record_id"]: {
                "confirmed_pay_basis": "OT_PREMIUM",
                "pay_basis_evidence": "Agreement section 2",
            }
        },
    )[0]
    assert result["outcome"] == "needs_review"
    assert result["conflicting_reference_rows"] == ["2", "3"]
