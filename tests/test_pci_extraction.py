"""Regressions for selectively integrated PCI extraction; synthetic documents only."""

import shutil

import pymupdf
import pytest

from ocr_ingestion import append_records, extract_document, load_records
from reviewer.checker import compare, parse_reference
from tests.helpers import write_pdf
from tests.test_checker import reference_bytes, schedule
from tests.test_trade_extraction import worker_ledger_lines, write_worker_ledger


def extract_lines(tmp_path, lines, **metadata):
    return extract_document(
        write_pdf(tmp_path / "source.pdf", lines), use_ocr=False, **metadata
    )


def test_table_and_line_parsers_share_source_coverage_not_business_values(tmp_path):
    lines = [
        (70, [(20, "TRADE"), (260, "HRS"), (350, "RATE"), (440, "COST")]),
        (
            100,
            [
                (20, "Field Labor Carpenter"),
                (260, "8"),
                (350, "$20.00"),
                (440, "$160.00"),
            ],
        ),
        (
            130,
            [
                (20, "Field Labor Carpenter"),
                (260, "8"),
                (350, "$20.00"),
                (440, "$160.00"),
            ],
        ),
        (160, [(20, "Total"), (440, "$320.00")]),
        (190, [(20, "Labor: 8 hours @ $20.00 $160.00")]),
    ]
    result = extract_lines(tmp_path, lines)
    assert len(result.records) == 3
    assert len({r["record_id"] for r in result.records}) == 3
    assert len(result.tables) == 2
    selected = [r["record_id"] for r in result.records]
    reviewed = [t.table_id for t in result.tables]
    csv = tmp_path / "accepted.csv"
    with pytest.raises(ValueError, match="review"):
        append_records(result, csv, selected)
    append_records(result, csv, selected, reviewed_table_ids=reviewed)
    append_records(result, csv, selected, reviewed_table_ids=reviewed)
    assert len(load_records(csv)) == 3


@pytest.mark.parametrize("section", ["MATERIALS", "TRUCKING", "EQUIPMENT", "RENTAL"])
def test_acme_nonlabor_statement_is_not_offered(tmp_path, section):
    result = extract_lines(
        tmp_path,
        [
            (40, [(20, "ACME Waterproofing")]),
            (70, [(20, section)]),
            (100, [(20, "Labor: 8 hours @ $20.00 $160.00")]),
        ],
        contractor="ACME Waterproofing",
    )
    assert not result.records
    assert not result.tables


def test_acme_mixed_sections_only_keep_labor_and_reset_slip_context(tmp_path):
    lines = [
        (40, [(20, "LABOR")]),
        (60, [(20, "T&M Slip 1001 - Monday 4/27/2026")]),
        (80, [(20, "PF Carpenter-ST 8 $20.00 $160.00")]),
        (100, [(20, "MATERIALS")]),
        (120, [(20, "Labor: 8 hours @ $99.00 $792.00")]),
        (140, [(20, "LABOR")]),
        (160, [(20, "PF Carpenter-OT 2 $30.00 $60.00")]),
        (180, [(20, "Labor: 4 hours @ $20.00 $80.00")]),
    ]
    result = extract_lines(tmp_path, lines, contractor="ACME Waterproofing")
    assert len(result.records) == 2
    assert result.records[0]["reg_rate"] == "20.00"
    assert result.records[1]["rate"] == "20.00"
    assert result.records[1]["work_start"] == ""
    assert all(r["contractor"] == "" for r in result.records)


@pytest.mark.parametrize(
    "suffix,field",
    [("ST", "reg"), ("RT", "reg"), ("OT", "ot"), ("DT", "dt"), ("PT", "")],
)
def test_dated_slips_preserve_explicit_pay_suffixes(tmp_path, suffix, field):
    result = extract_lines(
        tmp_path,
        [
            (60, [(20, "T&M Slip 1001 - Monday 4/27/2026")]),
            (90, [(20, f"PF Carpenter-{suffix} 8 $20.00 $160.00")]),
        ],
        contractor="Packet Company",
        project="Example project",
    )
    assert len(result.records) == 1
    row = result.records[0]
    assert row["ticket_id"] == "1001"
    assert row["work_start"] == row["work_end"] == "2026-04-27"
    assert row["contractor"] == ""
    assert row["project"] == "Example project"
    assert row["rate_basis_raw"] == suffix
    assert row[field + "_rate" if field else "rate"] == "20.00"
    assert row[field + "_hours" if field else "hours"] == "8"
    assert row["total_amount"] == "160.00"
    assert result.tables[0].requires_review


def test_new_slip_with_unknown_date_cannot_inherit_previous_date(tmp_path):
    result = extract_lines(
        tmp_path,
        [
            (50, [(20, "T&M Slip 1001 - Monday 4/27/2026")]),
            (80, [(20, "PF Carpenter-ST 8 $20.00 $160.00")]),
            (110, [(20, "T&M Slip 1002 - Tuesday Unknown")]),
            (140, [(20, "PF Carpenter-OT 2 $30.00 $60.00")]),
            (170, [(20, "Field Labor Carpenter 4 $20.00 $80.00")]),
        ],
    )
    assert len(result.records) == 2
    assert result.records[0]["ticket_id"] == "1001"
    assert result.records[1]["work_start"] == result.records[1]["ticket_id"] == ""


def test_proposals_statements_zeros_and_missing_values(tmp_path):
    result = extract_lines(
        tmp_path,
        [
            (40, [(20, "Quote 4/27/2026")]),
            (60, [(20, "Field Labor Carpenter 8 $20.00 $160.00")]),
            (90, [(20, "Labor: 4 hours @ $20.00 $80.00")]),
            (120, [(20, "Labor: 0 hours @ $20.00 $0.00")]),
            (150, [(20, "Labor: 4 hours @ $0.00 $0.00")]),
            (180, [(20, "Labor: 4 hours @ $20.00")]),
            (210, [(20, "Material: 4 hours @ $20.00 $80.00")]),
        ],
        contractor="Packet Company",
    )
    assert len(result.records) == 3
    assert [r["rate"] for r in result.records] == ["20.00", "20.00", "0.00"]
    assert all(
        r["work_start"] == r["contractor"] == r["reg_rate"] == ""
        for r in result.records
    )
    assert all(t.requires_review for t in result.tables)


def test_ledger_contractor_requires_confirmation_without_discarding_rates(tmp_path):
    lines = worker_ledger_lines()
    lines[1] = (110, [(x, text) for x, text in lines[1][1] if x not in (150, 730, 890)])
    result = extract_document(
        write_worker_ledger(tmp_path / "ledger.pdf", lines),
        contractor="Packet Company",
        use_ocr=False,
    )
    assert len(result.records) == 2
    assert all(r["contractor"] == "" for r in result.records)
    assert result.records[0]["work_start"] == result.records[0]["hours"] == ""
    assert result.records[0]["rate"] == "20.00"
    reference = parse_reference(reference_bytes([schedule()]), "synthetic.csv")
    assert all(
        f["outcome"] == "needs_review"
        for f in compare(result.records, reference, {}, "synthetic")
    )


def test_dark_neutral_rate_in_another_font_is_printed_text(tmp_path):
    source = write_pdf(
        tmp_path / "gray.pdf",
        [
            (70, [(20, "TRADE"), (260, "HRS"), (350, "RATE"), (440, "COST")]),
            (100, [(20, "CF"), (260, "8"), (440, "$160.00")]),
        ],
        overlays=[(350, 100, "$20.00", (0.2, 0.2, 0.2), "helv")],
    )
    result = extract_document(source, use_ocr=False)
    assert len(result.records) == 1
    assert result.records[0]["rate"] == "20.00"
    assert not any(issue["code"] == "overlay_excluded" for issue in result.issues)


def test_scanned_trade_row_has_one_source_record(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(
        tmp_path / "trade.pdf",
        [
            (70, [(20, "TRADE"), (260, "HRS"), (350, "RATE"), (440, "COST")]),
            (
                100,
                [
                    (20, "Field Labor Carpenter"),
                    (260, "8"),
                    (350, "$20.00"),
                    (440, "$160.00"),
                ],
            ),
        ],
    )
    with pymupdf.open(source) as document:
        document[0].get_pixmap(dpi=144).save(tmp_path / "scan.png")
    result = extract_document(tmp_path / "scan.png")
    assert len(result.records) == 1
    assert result.tables[0].method == "ocr"
    assert result.tables[0].requires_review
