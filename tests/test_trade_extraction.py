"""Synthetic regressions for additional printed trade tables; no client records."""

import shutil

import pymupdf
import pytest

from ocr_ingestion import append_records, extract_document
from tests.helpers import write_pdf


def trade_lines():
    return [
        (50, [(20, "UC0123G")]),
        (100, [(20, "Trade"), (160, "Hrs"), (280, "Rate"), (420, "Cost")]),
        (120, [(20, "CF"), (160, "8"), (280, "$123.45"), (420, "$999.99")]),
        (140, [(20, "LJ"), (160, "4"), (280, "$20.00"), (420, "$80.00")]),
        (160, [(20, "LJ"), (160, "4"), (280, "$20.00"), (420, "$80.00")]),
        (180, [(20, "Total"), (160, "16"), (420, "$1159.99")]),
        (200, [(20, "Freight"), (160, "2"), (280, "$30.00"), (420, "$60.00")]),
    ]


def test_trade_source_values_identifiers_and_review_gate(tmp_path):
    result = extract_document(
        write_pdf(tmp_path / "test.pdf", trade_lines()), use_ocr=False
    )
    assert len(result.records) == 3
    first = result.records[0]
    assert (
        first["position_original"],
        first["hours"],
        first["rate"],
        first["extension_amount"],
    ) == ("CF", "8", "123.45", "999.99")
    assert first["document_reference"] == "UC0123G"
    assert (
        first["contractor"]
        == first["work_start"]
        == first["work_end"]
        == first["reg_rate"]
        == ""
    )
    assert len({row["record_id"] for row in result.records}) == 3
    assert result.tables[0].kind == "labor"
    assert result.tables[0].requires_review
    with pytest.raises(ValueError, match="review"):
        append_records(result, tmp_path / "rows.csv", [first["record_id"]])


@pytest.mark.parametrize(
    "ending", ["Freight", "Rental", "Hardcosts", "Materials", "Equipment"]
)
def test_trade_stops_at_supporting_costs(tmp_path, ending):
    lines = trade_lines()[:3] + [
        (140, [(20, ending), (160, "2"), (280, "30.00"), (420, "60.00")])
    ]
    result = extract_document(write_pdf(tmp_path / "test.pdf", lines), use_ocr=False)
    assert len(result.records) == 1


def test_trade_rate_only_rows_are_retained_but_prose_is_not_labor(tmp_path):
    lines = trade_lines()[:2] + [(120, [(20, "CF"), (280, "123.45")])]
    result = extract_document(write_pdf(tmp_path / "blank.pdf", lines), use_ocr=False)
    assert len(result.records) == 1
    assert result.records[0]["rate"] == "123.45"
    assert result.records[0]["hours"] == result.records[0]["extension_amount"] == ""
    prose = [(100, [(20, "Trade Hrs Rate Cost")]), (120, [(20, "CF 8 123.45 987.60")])]
    assert not extract_document(
        write_pdf(tmp_path / "prose.pdf", prose), use_ocr=False
    ).records


def test_scanned_trade_table_uses_ocr_and_requires_review(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(tmp_path / "test.pdf", trade_lines())
    with pymupdf.open(source) as doc:
        doc[0].get_pixmap(dpi=180).save(tmp_path / "scan.png")
    result = extract_document(tmp_path / "scan.png")
    assert len(result.records) == 3
    assert result.records[0]["rate"] == "123.45"
    assert result.records[0]["extension_amount"] == "999.99"
    assert all(t.requires_review and t.method == "ocr" for t in result.tables)


def test_overlapping_colored_correction_does_not_delete_original_rate(tmp_path):
    source = write_pdf(
        tmp_path / "overlap.pdf",
        trade_lines(),
        overlays=[(280, 120, "$10.00", (0, 0.5, 0), "helv")],
    )
    result = extract_document(source, use_ocr=False)
    assert len(result.records) == 3
    assert result.records[0]["rate"] == "123.45"
    assert result.tables[0].requires_review
    assert any(issue["code"] == "overlay_excluded" for issue in result.issues)


def test_new_trade_rows_reach_checker_without_guessing_dates_or_reference_values(
    tmp_path,
):
    from reviewer.checker import compare, parse_reference
    from tests.test_checker import reference_bytes, schedule

    source = write_pdf(tmp_path / "trade.pdf", trade_lines()[:3])
    result = extract_document(source, contractor="Example Contractor", use_ocr=False)
    reference = parse_reference(
        reference_bytes([schedule(position="CF", reg_rate="100.00")]), "reference.csv"
    )
    findings = compare(result.records, reference, {}, "test")
    assert findings[0]["outcome"] == "needs_review"
    details = {
        result.records[0]["record_id"]: {
            "work_start": "2026-01-02",
            "work_end": "2026-01-02",
        }
    }
    findings = compare(result.records, reference, details, "test")
    assert findings[0]["outcome"] == "difference"
    assert findings[0]["difference_per_hour"] == "23.45"
    assert findings[0]["reference_rate_field"] == "reg_rate"
    assert result.records[0]["rate"] == "123.45"
    assert result.records[0]["work_start"] == ""


def proposal_lines():
    return [
        (
            100,
            [
                (20, "Labor"),
                (200, "STRAIGHT"),
                (280, "OVERTIME"),
                (360, "DOUBLE"),
                (440, "STRAIGHT"),
                (520, "OVERTIME"),
                (600, "DOUBLE"),
            ],
        ),
        (104, [(730, "TOTALS")]),
        (
            110,
            [
                (200, "TIME HRS"),
                (280, "HOURS"),
                (360, "TIME HRS"),
                (440, "RATE"),
                (520, "RATE"),
                (600, "RATE"),
            ],
        ),
        (
            130,
            [
                (20, "Carpenter Foreman"),
                (200, "8"),
                (280, "2"),
                (440, "10.00"),
                (520, "15.00"),
                (730, "110.00"),
            ],
        ),
        (150, [(20, "Shop Fabrication"), (200, "0"), (440, "25.00"), (730, "0.00")]),
        (170, [(20, "LABOR SUB-TOTAL"), (730, "110.00")]),
        (190, [(20, "Delivery"), (200, "2"), (440, "50.00"), (730, "100.00")]),
    ]


def test_multiline_proposal_preserves_explicit_rate_types_and_unused_roles(
    tmp_path,
):
    result = extract_document(
        write_pdf(tmp_path / "proposal.pdf", proposal_lines()), use_ocr=False
    )
    assert len(result.records) == 2
    row = result.records[0]
    assert (
        row["position_original"],
        row["reg_rate"],
        row["ot_rate"],
        row["dt_rate"],
    ) == ("Carpenter Foreman", "10.00", "15.00", "")
    assert row["reg_hours"] == "8" and row["ot_hours"] == "2"
    assert row["work_start"] == row["contractor"] == ""
    assert result.tables[0].requires_review
    assert result.records[1]["position_original"] == "Shop Fabrication"
    assert result.records[1]["reg_rate"] == "25.00"
    assert result.records[1]["reg_hours"] == "0"
    assert result.records[1]["total_amount"] == "0.00"


def write_worker_ledger(path, lines):
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=600)
    for y, cells in lines:
        for x, text in cells:
            page.insert_text((x, y), text, fontsize=8, fontname="cour")
    doc.save(path)
    doc.close()
    return path


def worker_ledger_lines():
    return [
        (
            80,
            [
                (20, "FWD"),
                (80, "Ticket #"),
                (150, "Date"),
                (230, "Area"),
                (310, "Job Name"),
                (430, "Description"),
                (560, "Worker"),
                (650, "Craft"),
                (730, "Hours"),
                (790, "Rate ($/hr)"),
                (890, "Cost ($)"),
            ],
        ),
        (
            110,
            [
                (20, "FWD 1"),
                (80, "1001"),
                (150, "4/27/2026"),
                (230, "Interior"),
                (310, "Example Job"),
                (400, "Repair panels"),
                (560, "Alex Smith"),
                (650, "Glazier - F"),
                (730, "7.5"),
                (790, "$20.00"),
                (890, "$150.00"),
            ],
        ),
        (
            135,
            [
                (20, "FWD 1"),
                (80, "1002"),
                (150, "4/28/2026"),
                (230, "Interior"),
                (310, "Example Job"),
                (400, "Repair panels"),
                (560, "Alex Smith"),
                (650, "Glazier - F"),
                (730, "7.5"),
                (790, "$20.00"),
                (890, "$150.00"),
            ],
        ),
        (
            160,
            [
                (20, "By Craft"),
                (650, "Glazier - F"),
                (730, "15"),
                (790, "$20.00"),
                (890, "$300.00"),
            ],
        ),
    ]


def test_worker_ledger_preserves_rates_dates_and_requires_review(tmp_path):
    result = extract_document(
        write_worker_ledger(tmp_path / "ledger.pdf", worker_ledger_lines()),
        use_ocr=False,
    )
    assert len(result.records) == 2
    row = result.records[0]
    assert (
        row["ticket_id"],
        row["worker_name"],
        row["position_original"],
        row["description"],
    ) == ("1001", "Alex Smith", "Glazier - F", "Repair panels")
    assert (row["hours"], row["rate"], row["total_amount"], row["work_start"]) == (
        "7.5",
        "20.00",
        "150.00",
        "2026-04-27",
    )
    assert row["contractor"] == row["reg_rate"] == ""
    assert result.records[1]["work_start"] == "2026-04-28"
    assert len({r["record_id"] for r in result.records}) == 2
    assert result.tables[0].requires_review
    with pytest.raises(ValueError, match="review"):
        append_records(result, tmp_path / "rows.csv", [row["record_id"]])


def test_worker_ledger_retains_zero_work_and_unresolved_date(tmp_path):
    lines = worker_ledger_lines()
    lines[1] = (
        110,
        [(x, "0" if x in (730, 890) else value) for x, value in lines[1][1]],
    )
    lines[2] = (
        135,
        [(x, "Unknown" if x == 150 else value) for x, value in lines[2][1]],
    )
    result = extract_document(
        write_worker_ledger(tmp_path / "ledger.pdf", lines), use_ocr=False
    )
    assert len(result.records) == 2
    assert result.records[0]["hours"] == result.records[0]["total_amount"] == "0"
    assert result.records[1]["ticket_id"] == "1002"
    assert result.records[1]["work_start"] == result.records[1]["work_end"] == ""
    assert result.records[1]["rate"] == "20.00"
    assert any(issue["code"] == "unresolved_field" for issue in result.issues)


def test_worker_ledger_scanned_printed_table(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_worker_ledger(tmp_path / "ledger.pdf", worker_ledger_lines())
    with pymupdf.open(source) as doc:
        doc[0].get_pixmap(dpi=180).save(tmp_path / "ledger.png")
    result = extract_document(tmp_path / "ledger.png")
    assert len(result.records) == 2
    assert [r["rate"] for r in result.records] == ["20.00", "20.00"]
    assert all(table.requires_review for table in result.tables)
