import pytest

from reviewer.benchmark import score


def case(identifier, expected):
    return {
        "case_id": identifier,
        "record_id": identifier,
        "source_rate_field": "rate",
        "expected": expected,
        "source_evidence": "Synthetic page 1",
        "reference_evidence": "Synthetic approved schedule row 2",
        "verified_by": "test reviewer",
    }


def finding(identifier, outcome):
    return {
        "record_id": identifier,
        "source_rate_field": "rate",
        "outcome": outcome,
        "reference_version": "test",
    }


def test_missing_and_unresolved_wrong_rates_count_against_recall():
    labels = {
        "reference_version": "test",
        "cases": [
            case("1", "difference"),
            case("2", "difference"),
            case("3", "difference"),
            case("4", "match"),
            case("5", "match"),
            case("6", "pending"),
        ],
    }
    findings = [
        finding("1", "difference"),
        finding("2", "needs_review"),
        finding("4", "difference"),
        finding("5", "match"),
        finding("6", "difference"),
    ]
    result = score(labels, findings)
    assert result["metrics"]["wrong_rate_recall"] == 1 / 3
    assert result["metrics"]["flag_precision_on_verified_cases"] == 0.5
    assert result["metrics"]["decision_coverage"] == 3 / 5
    assert result["counts"]["missed_wrong_missing"] == 1
    assert result["counts"]["missed_wrong_needs_review"] == 1
    assert result["unverified_flags"] == 1


def test_pending_answer_sheet_cannot_claim_accuracy():
    result = score(
        {"reference_version": "test", "cases": [case("1", "pending")]},
        [finding("1", "match")],
    )
    assert result["metrics"]["wrong_rate_recall"] is None
    assert result["metrics"]["accuracy_on_decided_verified_cases"] is None
    assert result["metrics"]["label_coverage"] == 0


def test_duplicate_labels_and_wrong_reference_and_missing_evidence_rejected():
    label = case("1", "match")
    for labels, findings in [
        ({"reference_version": "test", "cases": [label, label]}, []),
        ({"reference_version": "other", "cases": [label]}, [finding("1", "match")]),
        ({"reference_version": "test", "cases": [{**label, "verified_by": ""}]}, []),
        (
            {"reference_version": "test", "cases": [label]},
            [finding("1", "match"), finding("1", "match")],
        ),
    ]:
        with pytest.raises(ValueError):
            score(labels, findings)
