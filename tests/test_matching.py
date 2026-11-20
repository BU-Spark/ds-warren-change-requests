"""Synthetic contractor/trade graphs and rate-based matching; no client fixtures."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from reviewer.api import create_app
from reviewer.checker import compare, differences_csv, parse_reference
from reviewer.matching import classification_graph, resolve_contractor
from tests.helpers import detail_lines, write_pdf
from tests.test_app import save, upload
from tests.test_checker import record, reference_bytes, schedule


def reference(rows):
    return parse_reference(reference_bytes(rows), "synthetic.csv")


def masonry():
    return reference(
        [
            schedule(position="Bricklayer Journey Person", reg_rate="12.00"),
            schedule(
                source_csv_row_number="3",
                position="Bricklayer Foreperson",
                reg_rate="18.00",
            ),
        ]
    )


def test_masons_resolves_to_bricklayer_by_contractor_trade_date_and_regular_rate():
    original = record(position_original="Masons", reg_rate="12.00")
    result = compare([original], masonry(), {}, "test")[0]
    assert result["outcome"] == "match"
    assert result["matched_classifications"] == ["Bricklayer Journey Person"]
    assert result["trade_family"] == "Masonry" and result["reference_row"] == "2"
    assert result["match_method"] == "trade_family"
    assert original["position_original"] == "Masons"


def test_unknown_grade_nonmatching_rate_flags_rate_absent_without_guessing_nearest_grade():
    result = compare(
        [record(position_original="Mason", reg_rate="17.99")], masonry(), {}, "test"
    )[0]
    assert (
        result["outcome"] == "difference"
        and result["finding_kind"] == "rate_not_in_schedule"
    )
    assert result["approved_rates"] == ["12.00", "18.00"]
    assert result["approved_rate"] == "" and result["difference_per_hour"] == ""
    assert result["reference_rows"] == ["2", "3"]
    exported = list(csv.DictReader(io.StringIO(differences_csv([result]))))[0]
    assert exported["approved_rates"] == '["12.00", "18.00"]'
    assert exported["matched_classifications"]


@pytest.mark.parametrize(
    "label,submitted,expected",
    [
        ("Mason Foreman", "12.00", "-6.00"),
        ("Bricklayer Journeyman", "18.00", "6.00"),
    ],
)
def test_stated_seniority_is_never_replaced_with_a_cheaper_matching_grade(
    label, submitted, expected
):
    result = compare(
        [record(position_original=label, reg_rate=submitted)], masonry(), {}, "test"
    )[0]
    assert (
        result["outcome"] == "difference" and result["difference_per_hour"] == expected
    )
    assert len(result["matched_classifications"]) == 1


def test_matching_rate_from_another_contractor_cannot_hide_a_difference():
    ref = reference(
        [
            schedule(reg_rate="10.00"),
            schedule(
                source_csv_row_number="3",
                subcontractor="Other Company",
                reg_rate="11.00",
            ),
        ]
    )
    result = compare([record(reg_rate="11.00")], ref, {}, "test")[0]
    assert result["outcome"] == "difference" and result["approved_rate"] == "10.00"


def test_known_wrong_trade_cannot_match_a_different_trade_with_the_same_price():
    result = compare(
        [record(position_original="Electrician", reg_rate="10.00")],
        reference([schedule()]),
        {},
        "test",
    )[0]
    assert result["outcome"] == "needs_review"
    assert not result["candidates"]


def test_contractor_rate_fallback_handles_missing_classification_and_explains_limits():
    result = compare(
        [record(position_original="")], reference([schedule()]), {}, "test"
    )[0]
    assert result["outcome"] == "match" and result["match_method"] == "contractor_rate"
    assert "not recognized" in result["match_explanation"]


def test_conflicting_approved_revisions_still_need_review():
    ref = reference([schedule(), schedule(source_csv_row_number="3", reg_rate="30.00")])
    result = compare([record()], ref, {}, "test")[0]
    assert result["outcome"] == "needs_review" and "conflicting" in result["reason"]


@pytest.mark.parametrize(
    "label,positions",
    [
        (
            "Electrician Apprentice 50%",
            ["Electrician Apprentice 50%", "Electrician Apprentice 80%"],
        ),
        ("Operator Group 1", ["Operator Group 1", "Operator Group 2"]),
        (
            "Electrician Foreman 2nd Shift",
            ["Electrician Foreperson 2nd Shift", "Electrician Foreperson 3rd Shift"],
        ),
    ],
)
def test_explicit_apprentice_group_and_shift_qualifiers_are_preserved(label, positions):
    ref = reference(
        [
            schedule(position=positions[0], reg_rate="10.00"),
            schedule(
                source_csv_row_number="3", position=positions[1], reg_rate="15.00"
            ),
        ]
    )
    result = compare(
        [record(position_original=label, reg_rate="15.00")], ref, {}, "test"
    )[0]
    assert result["outcome"] == "difference" and result["difference_per_hour"] == "5.00"


def test_company_normalization_does_not_cross_into_parenthetical_context():
    ref = reference(
        [
            schedule(subcontractor="Example Masonry, Inc."),
            schedule(
                source_csv_row_number="3",
                subcontractor="Other Welding (Example Masonry)",
            ),
        ]
    )
    assert resolve_contractor("Example Masonry", ref["rows"]) == "Example Masonry, Inc."
    assert resolve_contractor("", ref["rows"]) == ""


def test_graph_contains_all_tracker_classifications_and_only_actual_schedules():
    ref = masonry()
    graph = classification_graph(ref, [])
    assert graph["contractors"][0]["families"][0]["label"] == "Masonry"
    names = [
        c["name"]
        for contractor in graph["contractors"]
        for family in contractor["families"]
        for c in family["classifications"]
    ]
    assert set(names) == {r["position"] for r in ref["rows"]}
    assert "mason" in graph["contractors"][0]["families"][0]["aliases"]


def test_saved_relationships_are_scoped_versioned_and_reversible(tmp_path):
    (tmp_path / "labor_rates_fa.csv").write_bytes(
        reference_bytes(
            [
                schedule(position="Carpenter Journey Person"),
                schedule(
                    source_csv_row_number="3",
                    position="Bricklayer Journey Person",
                    reg_rate="12.00",
                ),
            ]
        )
    )
    source = write_pdf(tmp_path / "sample.pdf", detail_lines())
    with TestClient(create_app(tmp_path)) as client:
        session = upload(client, source)
        save(client, session)
        ids = [r["record_id"] for r in session["extraction"]["records"]]
        client.post("/api/checks", json={"record_ids": ids})
        assert client.get("/api/classification-map").status_code == 200
        alias = client.put(
            "/api/classification-aliases",
            json={
                "contractor": "Example Contractor",
                "source_label": "Carpenter",
                "target_position": "Carpenter Journey Person",
            },
        )
        assert alias.status_code == 200
        assert client.get("/api/checks").json()[0]["stale"]
        changed = client.post("/api/checks", json={"record_ids": ids}).json()
        assert changed["results"][0]["match_method"] == "classification_alias"
        assert changed["results"][0]["matched_classifications"] == [
            "Carpenter Journey Person"
        ]
        assert (
            client.put(
                "/api/classification-aliases",
                json={
                    "contractor": "Unknown Company",
                    "source_label": "Worker",
                    "target_position": "Bricklayer Journey Person",
                },
            ).status_code
            == 400
        )
        assert (
            client.put(
                "/api/classification-aliases",
                json={
                    "contractor": "Example Contractor",
                    "source_label": "Worker",
                    "target_position": "Invented Classification",
                },
            ).status_code
            == 400
        )
        identifier = alias.json()["id"]
    with TestClient(create_app(tmp_path)) as restarted:
        assert (
            restarted.get("/api/classification-map").json()["aliases"][0]["id"]
            == identifier
        )
        assert (
            restarted.delete("/api/classification-aliases/" + identifier).status_code
            == 200
        )
        assert restarted.get("/api/classification-map").json()["aliases"] == []
        assert restarted.get("/api/checks").json()[0]["stale"]
        original = restarted.get("/api/records").json()["records"]
        assert all(r["position_original"] == "Carpenter" for r in original)


def test_contractor_generic_role_schedules_can_support_a_broad_trade_label():
    ref = reference(
        [
            schedule(position="Journey Person", reg_rate="10.00"),
            schedule(
                source_csv_row_number="3", position="Foreperson", reg_rate="15.00"
            ),
        ]
    )
    result = compare([record(position_original="Laborers")], ref, {}, "test")[0]
    assert result["outcome"] == "match" and result["match_method"] == "contractor_role"
    assert result["matched_classifications"] == ["Journey Person"]


def test_group_numerals_are_normalized_without_crossing_groups():
    ref = reference(
        [
            schedule(position="Operator Group II Journey Person", reg_rate="10.00"),
            schedule(
                source_csv_row_number="3",
                position="Operator Group I Journey Person",
                reg_rate="15.00",
            ),
        ]
    )
    result = compare(
        [record(position_original="Operator Group 2 Journeyman", reg_rate="15.00")],
        ref,
        {},
        "test",
    )[0]
    assert result["outcome"] == "difference" and result["approved_rate"] == "10.00"


def test_saved_alias_cannot_erase_an_explicit_grade(tmp_path):
    (tmp_path / "labor_rates_fa.csv").write_bytes(
        reference_bytes([schedule(position="Bricklayer Journey Person")])
    )
    with TestClient(create_app(tmp_path)) as client:
        response = client.put(
            "/api/classification-aliases",
            json={
                "contractor": "Example Contractor",
                "source_label": "Mason Foreman",
                "target_position": "Bricklayer Journey Person",
            },
        )
        assert response.status_code == 400 and "grade" in response.json()["detail"]


def test_same_economic_rate_in_different_formats_is_one_comparison_rate():
    ref = reference(
        [
            schedule(position="Bricklayer Journey Person", reg_rate="12"),
            schedule(
                source_csv_row_number="3",
                position="Bricklayer Foreperson",
                reg_rate="12.00",
            ),
        ]
    )
    result = compare(
        [record(position_original="Masons", reg_rate="13.00")], ref, {}, "test"
    )[0]
    assert result["finding_kind"] == "rate_difference"
    assert len(result["approved_rates"]) == 1
    assert result["difference_per_hour"] == "1.00"


def test_generic_business_words_do_not_identify_a_contractor():
    ref = reference([schedule(subcontractor="Example Masonry, Inc.")])
    assert resolve_contractor("Inc", ref["rows"]) == ""
    assert resolve_contractor("Masonry", ref["rows"]) == ""
    assert resolve_contractor("Example", ref["rows"]) == "Example Masonry, Inc."


def blended_foreman_reference(**updates):
    return reference(
        [
            schedule(
                position="Laborer Foreperson (Blended)",
                effective_time_period_start="2026-01-01",
                effective_time_period_finish="2026-05-31",
                reg_rate="12.34",
                **updates,
            ),
            schedule(
                source_csv_row_number="3",
                position="Laborer Foreperson",
                effective_time_period_start="2026-06-01",
                effective_time_period_finish="2026-11-30",
                reg_rate="15.67",
            ),
        ]
    )


def test_future_exact_title_does_not_hide_applicable_blended_role():
    source = record(position_original="Laborer Foreman", reg_rate="12.34")
    result = compare([source], blended_foreman_reference(), {}, "blended")[0]
    assert result["outcome"] == "match"
    assert result["matched_classifications"] == ["Laborer Foreperson (Blended)"]
    assert result["reference_rows"] == ["2"]
    assert result["match_method"] == "classification_variants"
    assert source["position_original"] == "Laborer Foreman"


@pytest.mark.parametrize(
    "submitted,outcome", [("15.67", "match"), ("12.34", "difference")]
)
def test_expired_blended_rate_cannot_override_current_plain_schedule(
    submitted, outcome
):
    source = record(
        position_original="Laborer Foreman",
        reg_rate=submitted,
        work_start="2026-06-01",
        work_end="2026-06-30",
    )
    result = compare([source], blended_foreman_reference(), {}, "plain")[0]
    assert result["outcome"] == outcome
    assert result["approved_rate"] == "15.67" and result["reference_rows"] == ["3"]


def test_explicit_blended_label_is_not_broadened_to_plain_role():
    source = record(
        position_original="Laborer Foreman (Blended)",
        reg_rate="15.67",
        work_start="2026-06-01",
        work_end="2026-06-30",
    )
    result = compare([source], blended_foreman_reference(), {}, "explicit")[0]
    assert result["outcome"] == "needs_review"
    assert "covers" in result["reason"]


@pytest.mark.parametrize("status", ["Pending Approval", "Withdrawn"])
def test_blended_variant_still_requires_approval(status):
    result = compare(
        [record(position_original="Laborer Foreman", reg_rate="12.34")],
        blended_foreman_reference(status=status),
        {},
        "approval",
    )[0]
    assert result["outcome"] == "needs_review" and "Approved" in result["reason"]


@pytest.mark.parametrize(
    "qualifier,wrong",
    [("2nd Shift", "3rd Shift"), ("Group 1", "Group 2"), ("50%", "80%")],
)
def test_blended_variant_keeps_other_stated_qualifiers(qualifier, wrong):
    role = "Laborer Apprentice" if "%" in qualifier else "Laborer Foreperson"
    ref = reference(
        [
            schedule(
                position=f"{role} {qualifier}", effective_time_period_start="2026-06-01"
            ),
            schedule(
                source_csv_row_number="3",
                position=f"{role} {wrong} (Blended)",
                reg_rate="12.34",
            ),
            schedule(
                source_csv_row_number="4",
                position=f"{role} {qualifier} (Blended)",
                reg_rate="15.67",
            ),
        ]
    )
    source = record(position_original=f"{role} {qualifier}", reg_rate="12.34")
    result = compare([source], ref, {}, "qualified")[0]
    assert result["outcome"] == "difference"
    assert result["approved_rate"] == "15.67"
    assert result["matched_classifications"] == [f"{role} {qualifier} (Blended)"]


def test_blended_variants_cannot_cross_contractors_or_seniority():
    ref = reference(
        [
            schedule(
                position="Laborer Foreperson", effective_time_period_start="2026-06-01"
            ),
            schedule(
                source_csv_row_number="3",
                position="Laborer Journey Person (Blended)",
                reg_rate="12.34",
            ),
            schedule(
                source_csv_row_number="4",
                subcontractor="Another Contractor",
                position="Laborer Foreperson (Blended)",
                reg_rate="12.34",
            ),
        ]
    )
    result = compare(
        [record(position_original="Laborer Foreman", reg_rate="12.34")],
        ref,
        {},
        "scope",
    )[0]
    assert result["outcome"] == "needs_review"
    assert {r["source_csv_row_number"] for r in result["candidates"]} == {"2"}


def test_explicit_relationship_still_controls_target_instead_of_blended_variant():
    row = record(position_original="Laborer Foreman", reg_rate="12.34")
    aliases = [
        {
            "contractor": "Example Contractor",
            "source_label": "Laborer Foreman",
            "target_position": "Laborer Foreperson",
        }
    ]
    result = compare([row], blended_foreman_reference(), {}, "alias", aliases)[0]
    assert result["match_method"] == "classification_alias"
    assert result["outcome"] == "needs_review"


def test_conflicting_blended_approved_schedules_remain_unresolved():
    ref = blended_foreman_reference()
    ref["rows"].append(
        {**ref["rows"][0], "source_csv_row_number": "4", "reg_rate": "13.45"}
    )
    result = compare(
        [record(position_original="Laborer Foreman", reg_rate="12.34")],
        ref,
        {},
        "conflict",
    )[0]
    assert result["outcome"] == "needs_review" and "conflicting" in result["reason"]


def test_blended_fix_does_not_narrow_existing_trade_family_candidates():
    ref = reference(
        [
            schedule(
                position="Carpenter Foreperson (Example Supervisor)",
                effective_time_period_finish="2026-05-31",
                reg_rate="12.34",
            ),
            schedule(
                source_csv_row_number="3",
                position="Carpenter Foreperson (Blended)",
                effective_time_period_start="2026-06-01",
                reg_rate="15.67",
            ),
        ]
    )
    result = compare(
        [record(position_original="Carpenter Foreman", reg_rate="12.34")],
        ref,
        {},
        "historical-family",
    )[0]
    assert result["outcome"] == "match"
    assert result["matched_classifications"] == [
        "Carpenter Foreperson (Example Supervisor)"
    ]
    assert result["match_method"] == "trade_family"
