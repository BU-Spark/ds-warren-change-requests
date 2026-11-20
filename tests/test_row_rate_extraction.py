"""Explicit row-labelled pay types; fictional contractors, roles and prices only."""

import shutil

import pymupdf
import pytest
from fastapi.testclient import TestClient

from ocr_ingestion import append_records, extract_document, load_records
from reviewer.api import create_app
from reviewer.checker import compare, parse_reference
from tests.helpers import write_pdf
from tests.test_app import save, upload
from tests.test_checker import reference_bytes, schedule

ROLES = [
    "Signal General Foreman",
    "Signal Foreman",
    "Signal Senior Technician",
    "Signal Technician",
    "Signal Apprentice",
]
BASES = [("Reg Time", "reg"), ("Overtime", "ot"), ("Double Time", "dt")]


def summary_lines(*, label="Date/Personnel", hours="Manhours", amount="Extended"):
    lines = [
        (40, [(20, "Change proposal dated 04/01/2026")]),
        (65, [(20, "Labor")]),
        (90, [(20, label), (470, hours), (560, "Rate"), (660, amount)]),
    ]
    for index, role in enumerate(ROLES):
        for n, (basis, _) in enumerate(BASES):
            number = index * 3 + n
            lines.append(
                (
                    110 + number * 18,
                    [
                        (20, f"{role} ({basis})"),
                        (470, "2" if n == 0 and index < 4 else "0"),
                        (560, f"${20 + index + n * 10}.25"),
                        (650, "$"),
                        (680, "99.99" if n == 0 else "-"),
                    ],
                )
            )
    lines.extend(
        [
            (390, [(20, "Labor Sum"), (680, "999.00")]),
            (410, [(20, "Tower B Escalation 5%"), (560, "123.00")]),
            (430, [(20, "Markup 15%"), (560, "456.00")]),
            (450, [(20, "Labor Total"), (560, "789.00")]),
        ]
    )
    return lines


def test_all_row_pay_types_preserve_source_and_review_gate(tmp_path):
    source = write_pdf(tmp_path / "fictional.pdf", summary_lines())
    result = extract_document(source, contractor="Packet Company", use_ocr=False)
    assert len(result.records) == 15
    assert len(result.tables) == 1 and result.tables[0].requires_review
    assert len({r["record_id"] for r in result.records}) == 15
    for index, row in enumerate(result.records):
        role = ROLES[index // 3]
        basis, prefix = BASES[index % 3]
        assert row["description"] == f"{role} ({basis})"
        assert row["position_original"] == role
        assert row["rate_basis_raw"] == basis
        assert row[prefix + "_rate"] == f"{20 + index // 3 + (index % 3) * 10}.25"
        assert all(
            not row[other + "_rate"] for other in ("reg", "ot", "dt") if other != prefix
        )
        assert row["hours"] == row["rate"] == row["total_amount"] == ""
        assert row["work_start"] == row["work_end"] == row["contractor"] == ""
        if index % 3:
            assert row[prefix + "_hours"] == "0"
            assert row[prefix + "_amount"] == ""
    assert (
        result.records[0]["reg_amount"] == "99.99"
    )  # Never replace a printed extension with arithmetic.
    ids = [r["record_id"] for r in result.records]
    with pytest.raises(ValueError, match="review"):
        append_records(result, tmp_path / "rows.csv", ids)
    reviewed = [t.table_id for t in result.tables]
    assert (
        append_records(result, tmp_path / "rows.csv", ids, reviewed_table_ids=reviewed)[
            "added"
        ]
        == 15
    )
    assert (
        append_records(result, tmp_path / "rows.csv", ids, reviewed_table_ids=reviewed)[
            "added"
        ]
        == 0
    )
    assert len(load_records(tmp_path / "rows.csv")) == 15


@pytest.mark.parametrize(
    "label,hours,amount",
    [
        ("Description", "Hours", "Amount"),
        ("Classification", "Hrs", "Cost"),
        ("Personnel", "Man Hours", "Extended Amount"),
        ("Trade", "Hrs", "Cost"),
    ],
)
def test_layout_is_not_contractor_specific(tmp_path, label, hours, amount):
    result = extract_document(
        write_pdf(
            tmp_path / "other.pdf",
            summary_lines(label=label, hours=hours, amount=amount),
        ),
        contractor="Another Contractor",
        use_ocr=False,
    )
    assert len(result.records) == 15
    assert result.records[1]["ot_rate"] == "30.25"
    assert result.records[2]["dt_rate"] == "40.25"


@pytest.mark.parametrize(
    "basis,prefix",
    [
        ("ST", "reg"),
        ("Regular Time", "reg"),
        ("Straight Time", "reg"),
        ("RT", "reg"),
        ("OT", "ot"),
        ("O.T.", "ot"),
        ("Over Time", "ot"),
        ("DT", "dt"),
        ("Double-Time", "dt"),
    ],
)
def test_explicit_abbreviations_and_plain_suffixes(tmp_path, basis, prefix):
    lines = summary_lines()[:3] + [
        (115, [(20, f"Signal Technician - {basis}"), (560, "0.00")])
    ]
    result = extract_document(write_pdf(tmp_path / "basis.pdf", lines), use_ocr=False)
    assert len(result.records) == 1
    row = result.records[0]
    assert row["position_original"] == "Signal Technician"
    assert row["rate_basis_raw"] == basis
    assert row[prefix + "_rate"] == "0.00"
    assert row[prefix + "_hours"] == row[prefix + "_amount"] == ""


def test_unknown_conflicting_and_malformed_rates_are_not_guessed(tmp_path):
    labels = [
        "Signal Technician (Premium)",
        "Signal Technician (OT) (DT)",
        "Signal Technician ST/OT",
        "Signal Technician (OT)",
    ]
    lines = summary_lines()[:3] + [
        (
            115 + i * 20,
            [
                (20, label),
                (470, "8"),
                (560, "20.00 21.00" if i == 3 else "25.00"),
                (680, "200.00"),
            ],
        )
        for i, label in enumerate(labels)
    ]
    result = extract_document(
        write_pdf(tmp_path / "uncertain.pdf", lines), use_ocr=False
    )
    assert result.records == []
    assert any(i["code"] == "unresolved_rate_basis" for i in result.issues)
    assert any(
        i["code"] == "unresolved_field" and i["field"] == "ot_rate"
        for i in result.issues
    )


@pytest.mark.parametrize(
    "ending",
    [
        "Labor Sum",
        "Labor Subtotal",
        "Labor Total",
        "Materials",
        "Equipment",
        "Rental",
        "Markup 15%",
        "Tower C Escalation 10%",
    ],
)
def test_supporting_costs_stop_the_labor_table(tmp_path, ending):
    lines = summary_lines()[:4] + [
        (140, [(20, ending), (560, "1000.00")]),
        (160, [(20, "Unrelated Worker (OT)"), (470, "1"), (560, "12.00")]),
    ]
    result = extract_document(
        write_pdf(tmp_path / "boundary.pdf", lines), use_ocr=False
    )
    assert len(result.records) == 1


def test_section_and_prose_safeguards_and_repeated_occurrences(tmp_path):
    for section in ("Materials", "Equipment", "Trucking"):
        lines = [(65, [(20, section)])] + summary_lines()[2:4]
        assert not extract_document(
            write_pdf(tmp_path / f"{section}.pdf", lines), use_ocr=False
        ).records
    prose = [
        (90, [(20, "Date/Personnel Manhours Rate Extended")]),
        (110, [(20, "Signal Technician (OT) 8 $25.00 $200.00")]),
    ]
    assert not extract_document(
        write_pdf(tmp_path / "prose.pdf", prose), use_ocr=False
    ).records
    lines = summary_lines()[:4] + [(140, summary_lines()[3][1])]
    result = extract_document(
        write_pdf(tmp_path / "repeated.pdf", lines), use_ocr=False
    )
    assert len(result.records) == 2
    assert result.records[0]["reg_rate"] == result.records[1]["reg_rate"]
    assert result.records[0]["record_id"] != result.records[1]["record_id"]


def test_scan_preserves_row_specific_rate_types(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(tmp_path / "printed.pdf", summary_lines())
    with pymupdf.open(source) as pdf:
        pdf[0].get_pixmap(dpi=200).save(tmp_path / "scan.png")
    result = extract_document(tmp_path / "scan.png")
    assert len(result.records) == 15
    assert all(t.method == "ocr" and t.requires_review for t in result.tables)
    assert [r["ot_rate"] for r in result.records if r["ot_rate"]] == [
        f"{30 + i}.25" for i in range(5)
    ]
    assert [r["dt_rate"] for r in result.records if r["dt_rate"]] == [
        f"{40 + i}.25" for i in range(5)
    ]


def test_pay_types_reach_correct_checker_fields_after_date_and_contractor_review(
    tmp_path,
):
    source = write_pdf(tmp_path / "check.pdf", summary_lines())
    result = extract_document(source, use_ocr=False)
    reference = parse_reference(
        reference_bytes(
            [
                schedule(
                    source_csv_row_number=str(i + 2),
                    position=role,
                    reg_rate=f"{20 + i}.25",
                    ot_rate=f"{30 + i}.25",
                    dt_rate=f"{40 + i}.25",
                )
                for i, role in enumerate(ROLES)
            ]
        ),
        "fictional.csv",
    )
    assert all(
        f["outcome"] == "needs_review"
        for f in compare(result.records, reference, {}, "undated")
    )
    details = {
        r["record_id"]: {
            "contractor": "Example Contractor",
            "classification": r["position_original"],
            "work_start": "2026-02-01",
            "work_end": "2026-02-10",
        }
        for r in result.records
    }
    findings = compare(result.records, reference, details, "reviewed")
    assert len(findings) == 15 and all(f["outcome"] == "match" for f in findings)
    assert [f["rate_type"] for f in findings] == [
        kind for _ in ROLES for kind in ("REG", "OT", "DT")
    ]
    assert [f["reference_rate_field"] for f in findings] == [
        field for _ in ROLES for field in ("reg_rate", "ot_rate", "dt_rate")
    ]


def test_reviewer_upload_date_defaults_and_bulk_details_work_with_row_rates(tmp_path):
    (tmp_path / "labor_rates_fa.csv").write_bytes(
        reference_bytes(
            [
                schedule(
                    position=ROLES[0],
                    reg_rate="20.25",
                    ot_rate="30.25",
                    dt_rate="40.25",
                )
            ]
        )
    )
    with TestClient(create_app(tmp_path)) as client:
        session = upload(
            client,
            write_pdf(tmp_path / "api.pdf", summary_lines()[:6]),
            work_start="2026-02-01",
            work_end="2026-02-10",
        )
        assert len(session["extraction"]["records"]) == 3
        assert len(session["comparison_details"]) == 3
        assert save(client, session, reviewed={}).status_code == 400
        assert save(client, session).json()["added"] == 3
        details = client.get("/api/records").json()["details"]
        ids = list(details)
        assert (
            client.post(
                "/api/records/details",
                json={
                    "records": {
                        identifier: {**values, "contractor": "Example Contractor"}
                        for identifier, values in details.items()
                    }
                },
            ).status_code
            == 200
        )
        checked = client.post("/api/checks", json={"record_ids": ids}).json()
        assert checked["counts"] == {"match": 3, "difference": 0, "needs_review": 0}


def test_typed_table_rows_cannot_be_reinterpreted_by_the_standalone_parser(tmp_path):
    lines = summary_lines()[:3] + [
        (
            110,
            [
                (20, "Field Labor Carpenter (OT)"),
                (470, "8"),
                (560, "20.00"),
                (680, "160.00"),
            ],
        ),
        (
            140,
            [
                (20, "Field Labor Carpenter (Premium)"),
                (470, "8"),
                (560, "30.00"),
                (680, "240.00"),
            ],
        ),
    ]
    result = extract_document(write_pdf(tmp_path / "overlap.pdf", lines), use_ocr=False)
    assert len(result.records) == 1
    assert result.records[0]["ot_rate"] == "20.00"
    assert result.records[0]["rate"] == result.records[0]["reg_rate"] == ""
    assert any(issue["code"] == "unresolved_rate_basis" for issue in result.issues)
