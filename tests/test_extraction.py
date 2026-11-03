"""Synthetic tests only: no client data or private snapshots."""

import shutil

import pymupdf
import pytest

from ocr_ingestion import append_records, extract_document
from ocr_ingestion.extraction import map_table
from ocr_ingestion.models import Extraction, Table, normalize_record
from tests.helpers import acme_lines, detail_lines, write_pdf


def test_detail_preserves_repeated_workers_and_distinct_tickets(tmp_path):
    result = extract_document(
        write_pdf(tmp_path / "arbitrary.pdf", detail_lines()), use_ocr=False
    )
    assert result.tables[0].kind == "labor_detail"
    rows = [row for row in result.records if row["row_type"] == "labor"]
    assert len(rows) == 2
    assert [row["ticket_id"] for row in rows] == ["1000-1001", "1000-1002"]
    assert rows[0]["work_start"] == "2026-01-02"
    assert rows[0]["reg_rate"] == "10.00"
    assert rows[0]["ot_hours"] == ""  # A dash is not a fabricated zero.
    assert rows[0]["position_original"] == "Carpenter"
    assert rows[0]["record_id"] != rows[1]["record_id"]


def test_grouped_dates_generic_rates_and_flattened_corrections(tmp_path):
    source = write_pdf(
        tmp_path / "grouped.pdf",
        acme_lines(),
        overlays=[
            (430, 137, "$999.00", (0, 0.5, 0), "helv"),
        ],
    )
    result = extract_document(source, contractor="Example supplier", use_ocr=False)
    rows = [row for row in result.records if row["row_type"] == "labor"]
    assert len(rows) == 3
    assert [row["work_start"] for row in rows] == [
        "2026-01-02",
        "2026-01-02",
        "2026-01-03",
    ]
    assert rows[0]["rate"] == "10.00"
    assert rows[0]["position_original"] == "Workers"
    assert rows[1]["rate_basis_raw"] == "Premium"
    assert all(
        row["reg_rate"] == row["ot_rate"] == row["dt_rate"] == "" for row in rows
    )
    assert rows[0]["extension_amount"] == "80.00"
    assert rows[0]["overhead_profit_amount"] == "12.00"
    assert rows[0]["total_amount"] == "92.00"
    assert any(issue["code"] == "overlay_excluded" for issue in result.issues)
    assert not any(issue["code"] == "unresolved_field" for issue in result.issues)


def test_source_colored_text_is_preserved(tmp_path):
    source = write_pdf(
        tmp_path / "colored.pdf",
        acme_lines()[:4],
        overlays=[
            (210, 150, "1 Worker", (0, 0.4, 0), "cour"),
            (380, 150, "2", (0, 0.4, 0), "cour"),
            (430, 150, "$10.00", (0, 0.4, 0), "cour"),
            (650, 150, "$20.00", (0, 0.4, 0), "cour"),
        ],
    )
    result = extract_document(source, use_ocr=False)
    assert any(row["hours"] == "2" and row["rate"] == "10.00" for row in result.records)


def test_unlabeled_tally_date_is_not_a_work_date(tmp_path):
    lines = [
        (80, [(20, "T&M Tally"), (500, "1000-1001")]),
        (100, [(20, "Rating"), (170, "Billing Rate"), (350, "Hours Worked")]),
        (
            120,
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
        (
            140,
            [
                (20, "Worker"),
                (170, "10.00"),
                (220, "15.00"),
                (270, "20.00"),
                (350, "4"),
                (400, "-"),
                (450, "-"),
                (510, "40.00"),
                (650, "12/31/26"),
            ],
        ),
    ]
    result = extract_document(write_pdf(tmp_path / "tally.pdf", lines), use_ocr=False)
    assert result.tables[0].kind == "labor_tally"
    row = next(row for row in result.records if row["row_type"] == "labor")
    assert row["work_start"] == row["work_end"] == ""
    assert row["unlabeled_date_raw"] == "12/31/26"


def test_manual_mapping_preserves_unknown_fields_and_requires_review(tmp_path):
    result = Extraction("a" * 64, "synthetic.pdf")
    table = Table(
        "p1-grid0",
        1,
        "unfamiliar",
        ["Role", "Hours", "Quoted Rate"],
        [["Specialist", "3", "25.00"], ["Specialist", "3", "25.00"]],
        [0, 0, 100, 100],
        "native",
        True,
    )
    result.tables.append(table)
    map_table(
        result,
        table.table_id,
        {0: "position_original", 1: "hours", 2: "rate"},
        row_type="labor",
    )
    assert len(result.records) == 2
    assert result.records[0]["record_id"] != result.records[1]["record_id"]
    with pytest.raises(ValueError, match="review"):
        append_records(result, tmp_path / "rows.csv", table.record_ids)
    assert (
        append_records(
            result,
            tmp_path / "rows.csv",
            table.record_ids,
            reviewed_table_ids=[table.table_id],
        )["added"]
        == 2
    )


def test_bad_files_and_invalid_numeric_values(tmp_path):
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"not a PDF")
    with pytest.raises(ValueError, match="cannot be opened"):
        extract_document(source)
    with pytest.raises(ValueError, match="ZIP"):
        extract_document(tmp_path / "unsupported.zip")
    for value in ["NaN", "inf", "10 20", "Not provided"]:
        with pytest.raises(ValueError):
            normalize_record({"rate": value})
    assert normalize_record({"rate": 0})["rate"] == "0"


def test_password_protected_pdf(tmp_path):
    source = tmp_path / "encrypted.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(
        source,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="example",
        owner_pw="owner",
    )
    document.close()
    with pytest.raises(ValueError, match="Password"):
        extract_document(source)


def test_scanned_printed_table_needs_review(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(tmp_path / "source.pdf", acme_lines())
    image_path = tmp_path / "printed.png"
    with pymupdf.open(source) as document:
        document[0].get_pixmap(dpi=180).save(image_path)
    result = extract_document(image_path)
    assert result.tables
    assert all(table.requires_review for table in result.tables)
    assert any(row["rate"] == "10.00" for row in result.records)


def test_missing_tesseract_has_actionable_error(tmp_path, monkeypatch):
    import pytesseract

    monkeypatch.setattr(
        pytesseract.pytesseract, "tesseract_cmd", "/does/not/exist/tesseract"
    )
    source = write_pdf(tmp_path / "source.pdf", acme_lines())
    with pymupdf.open(source) as document:
        document[0].get_pixmap().save(tmp_path / "printed.png")
    with pytest.raises(RuntimeError, match="Tesseract is not installed"):
        extract_document(tmp_path / "printed.png")


def test_handwritten_form_headers_do_not_trigger_scan_ingestion(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(
        tmp_path / "form.pdf",
        [
            (80, [(20, "TIME AND MATERIALS SHEET")]),
            (
                100,
                [(20, "NAME"), (200, "CRAFT"), (300, "ST"), (400, "OT"), (500, "DT")],
            ),
        ],
    )
    with pymupdf.open(source) as document:
        document[0].get_pixmap(dpi=150).save(tmp_path / "form.png")
    result = extract_document(tmp_path / "form.png")
    assert not result.records
    assert result.pages[0]["status"] == "no_printed_cost_table_header"


def test_short_native_table_does_not_require_ocr(tmp_path):
    source = write_pdf(
        tmp_path / "short.pdf",
        [
            (100, [(20, "Description"), (200, "HRS"), (300, "RATE")]),
            (120, [(20, "Specialist"), (200, "2"), (300, "12.00")]),
        ],
    )
    result = extract_document(source, use_ocr=False)
    assert len(result.tables) == 1
    assert result.tables[0].method == "native"
    assert result.tables[0].requires_review


def test_scanned_table_with_native_footer_still_uses_ocr(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(tmp_path / "source.pdf", acme_lines())
    with pymupdf.open(source) as printed:
        image = printed[0].get_pixmap(dpi=150).tobytes("png")
    document = pymupdf.open()
    page = document.new_page(width=820, height=600)
    page.insert_image(page.rect, stream=image)
    page.insert_textbox(
        pymupdf.Rect(20, 450, 780, 580), "Reviewer footer " * 30, fontsize=8
    )
    document.save(tmp_path / "hybrid.pdf")
    document.close()
    result = extract_document(tmp_path / "hybrid.pdf")
    assert any(table.method == "ocr" for table in result.tables)
    assert any(row["rate"] == "10.00" for row in result.records)


@pytest.mark.parametrize(
    "heading", ["Trucking RATE 15%", "MATERIAL", "EQUIPMENT", "RENTAL RATE 20%"]
)
def test_acme_shared_headers_respect_printed_section(tmp_path, heading):
    labor = acme_lines()
    supporting = [(y + 150, cells) for y, cells in acme_lines()]
    supporting[0] = (230, [(20, heading)])
    source = write_pdf(tmp_path / "arbitrary.pdf", labor + supporting)
    result = extract_document(source, contractor="Example supplier", use_ocr=False)
    assert [table.kind for table in result.tables] == ["labor"]
    rows = [row for row in result.records if row["row_type"] == "labor"]
    assert len(rows) == 3
    assert [row["work_start"] for row in rows] == [
        "2026-01-02",
        "2026-01-02",
        "2026-01-03",
    ]
    assert rows[0]["description"] == "2 Workers at 4 hours"
    assert (
        rows[0]["hours"],
        rows[0]["rate"],
        rows[0]["extension_amount"],
        rows[0]["overhead_profit_amount"],
        rows[0]["total_amount"],
    ) == ("8", "10.00", "80.00", "12.00", "92.00")
    assert rows[1]["rate_basis_raw"] == "Premium"
    assert all(
        row["reg_rate"] == row["ot_rate"] == row["dt_rate"] == "" for row in rows
    )
    assert len(result.records) == 3
    assert all(row["row_type"] == "labor" for row in result.records)


@pytest.mark.parametrize(
    "heading", ["Trucking RATE 15%", "MATERIAL", "EQUIPMENT", "RENTAL", "Cost summary"]
)
def test_acme_nonlabor_pages_never_enter_mapping_or_review(
    tmp_path, monkeypatch, heading
):
    import ocr_ingestion.extraction as extraction

    lines = acme_lines()
    lines[0] = (80, [(20, heading)])
    source = write_pdf(tmp_path / "arbitrary.pdf", lines)

    def unexpected_fallback(*args):
        pytest.fail("A page without a LABOR section must not enter table mapping")

    monkeypatch.setattr(extraction, "_fallback_tables", unexpected_fallback)
    result = extract_document(source, contractor="ACME Waterproofing", use_ocr=False)
    assert not result.records
    assert not result.tables
    assert not result.issues
    assert result.pages[0]["status"] == "skipped_no_labor_section"


def test_acme_mixed_page_keeps_only_labor_and_saves_without_irrelevant_review(tmp_path):
    supporting = [(y + 150, cells) for y, cells in acme_lines()]
    supporting[0] = (230, [(20, "Trucking RATE 15%")])
    source = write_pdf(
        tmp_path / "arbitrary.pdf",
        [(40, [(20, "ACME Waterproofing")])] + acme_lines() + supporting,
    )
    result = extract_document(source, use_ocr=False)
    assert [table.kind for table in result.tables] == ["labor"]
    assert len(result.records) == 3
    assert not result.issues
    assert not result.tables[0].requires_review
    ids = [row["record_id"] for row in result.records if row["row_type"] == "labor"]
    assert append_records(result, tmp_path / "rows.csv", ids)["added"] == 3


def test_acme_unfamiliar_labor_table_still_requires_review(tmp_path):
    source = write_pdf(
        tmp_path / "arbitrary.pdf",
        [
            (80, [(20, "LABOR")]),
            (100, [(20, "Description"), (200, "HRS"), (300, "RATE")]),
            (120, [(20, "Specialist"), (200, "2"), (300, "12.00")]),
        ],
    )
    result = extract_document(source, contractor="ACME Waterproofing", use_ocr=False)
    assert len(result.tables) == 1
    table = result.tables[0]
    assert table.kind == "unfamiliar"
    assert table.requires_review
    map_table(
        result,
        table.table_id,
        {0: "description", 1: "hours", 2: "rate"},
        row_type="labor",
    )
    with pytest.raises(ValueError, match="review"):
        append_records(result, tmp_path / "rows.csv", table.record_ids)


@pytest.mark.parametrize(
    "heading, labor",
    [("LABOR", True), ("MATERIAL", False), ("Trucking RATE 15%", False)],
)
def test_acme_scanned_nonlabor_is_ignored_and_labor_still_requires_review(
    tmp_path, heading, labor
):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    lines = acme_lines()
    lines[0] = (80, [(20, heading)])
    source = write_pdf(tmp_path / "source.pdf", lines)
    image = tmp_path / "scanned.png"
    with pymupdf.open(source) as document:
        document[0].get_pixmap(dpi=180).save(image)
    result = extract_document(image, contractor="ACME Waterproofing")
    if labor:
        assert result.records
        assert all(table.requires_review for table in result.tables)
        assert any(issue["code"] == "ocr_review_required" for issue in result.issues)
        with pytest.raises(ValueError, match="review"):
            append_records(result, tmp_path / "rows.csv", result.tables[0].record_ids)
    else:
        assert not result.records
        assert not result.tables
        assert not result.issues
        assert result.pages[0]["status"] == "skipped_no_labor_section"


@pytest.mark.parametrize(
    "body",
    [
        [
            (100, [(20, "Description hours rate are discussed here.")]),
            (120, [(20, "Please review the attached supporting notes.")]),
        ],
        [(100, [(20, "Description"), (200, "HRS"), (300, "RATE")])],
        [
            (100, [(20, "Description"), (200, "HRS"), (300, "RATE")]),
            (120, [(20, "No work was itemized on this page.")]),
        ],
        [
            (100, [(20, "Description"), (200, "HRS"), (300, "RATE")]),
            (120, [(20, "TOTAL LABOR"), (200, "8"), (300, "20.00")]),
        ],
    ],
)
def test_scanned_labor_notes_or_empty_headers_are_not_tables(tmp_path, body):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(tmp_path / "notes.pdf", [(80, [(20, "LABOR")])] + body)
    image = tmp_path / "notes.png"
    with pymupdf.open(source) as document:
        document[0].get_pixmap(dpi=180).save(image)
    result = extract_document(image, contractor="ACME Waterproofing")
    assert not result.tables
    assert not result.records
    assert not result.issues


def test_scanned_regular_table_is_recognized_without_manual_mapping(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(tmp_path / "source.pdf", acme_lines())
    image = tmp_path / "printed.png"
    with pymupdf.open(source) as document:
        document[0].get_pixmap(dpi=180).save(image)
    result = extract_document(image, contractor="ACME Waterproofing")
    assert [table.kind for table in result.tables] == ["labor"]
    assert len([row for row in result.records if row["row_type"] == "labor"]) == 3
    assert result.tables[0].requires_review
    assert result.tables[0].method == "ocr"


def test_native_header_without_rows_does_not_hide_scanned_table(tmp_path):
    if not shutil.which("tesseract"):
        pytest.skip("Local Tesseract is not installed")
    source = write_pdf(tmp_path / "source.pdf", acme_lines())
    with pymupdf.open(source) as printed:
        image = printed[0].get_pixmap(dpi=150).tobytes("png")
    document = pymupdf.open()
    page = document.new_page(width=820, height=600)
    page.insert_image(page.rect, stream=image)
    for x, text in [(20, "Description"), (200, "HRS"), (300, "RATE")]:
        page.insert_text((x, 500), text, fontsize=8)
    document.save(tmp_path / "hybrid.pdf")
    document.close()
    result = extract_document(tmp_path / "hybrid.pdf")
    assert [table.kind for table in result.tables] == ["labor"]
    assert result.tables[0].method == "ocr"
    assert any(row["rate"] == "10.00" for row in result.records)


@pytest.mark.parametrize(
    "headers, values",
    [
        (["Description", "Description", "Total"], ["Services", "Labor", "100.00"]),
        (["Description", "Hours", "Amount"], ["Specialist", "2", "100.00"]),
        (["Description", "HRS", "RATE"], ["Specialist", "2", "-"]),
    ],
)
def test_unfamiliar_tables_without_explicit_labor_rates_are_ignored(
    tmp_path, headers, values
):
    source = write_pdf(
        tmp_path / "no_rates.pdf",
        [
            (80, [(20, "LABOR")]),
            (100, list(zip([20, 200, 300], headers))),
            (120, list(zip([20, 200, 300], values))),
        ],
    )
    result = extract_document(source, contractor="ACME Waterproofing", use_ocr=False)
    assert not result.tables
    assert not result.records
    assert not result.issues


@pytest.mark.parametrize("row_type", ["labor", "labor_detail", "labor_tally"])
def test_manual_labor_mapping_skips_incomplete_rows_and_preserves_explicit_zero(
    tmp_path, row_type
):
    result = Extraction("b" * 64, "synthetic.pdf")
    table = Table(
        "p1-grid0",
        1,
        "unfamiliar",
        ["Role", "Hours", "Rate"],
        [
            ["Specialist", "2", "25.00"],
            ["Specialist", "2", "-"],
            ["", "2", "25.00"],
            ["Specialist", "2", "0"],
        ],
        [0, 0, 100, 100],
        "native",
        True,
    )
    result.tables.append(table)
    mapping = {0: "position_original", 1: "hours", 2: "rate"}
    map_table(result, table.table_id, mapping, row_type=row_type)
    assert all(row["row_type"] == "labor" for row in result.records)
    assert table.kind == "unfamiliar"
    assert [row["rate"] for row in result.records] == ["25.00", "0"]
    assert [row["row_index"] for row in result.records] == ["1", "4"]
    ids = list(table.record_ids)
    with pytest.raises(ValueError, match="explicit labor rate"):
        map_table(result, table.table_id, {0: "description", 2: "total_amount"})
    assert table.record_ids == ids
    with pytest.raises(ValueError, match="Only labor-rate"):
        map_table(result, table.table_id, mapping, row_type="material")
    assert table.record_ids == ids
    assert (
        append_records(
            result, tmp_path / "rows.csv", ids, reviewed_table_ids=[table.table_id]
        )["added"]
        == 2
    )


@pytest.mark.parametrize("omit_rate, expected", [(True, 2), (False, 3)])
def test_known_labor_rows_require_rates_but_not_optional_hours(
    tmp_path, omit_rate, expected
):
    lines = acme_lines()
    # The first data row has an explicit rate but no hours or amounts.
    y, cells = lines[3]
    keep = {210} if omit_rate else {210, 430}
    lines[3] = (y, [(x, value) for x, value in cells if x in keep])
    result = extract_document(write_pdf(tmp_path / "rates.pdf", lines), use_ocr=False)
    assert len(result.records) == expected
    if not omit_rate:
        assert result.records[0]["rate"] == "10.00"
        assert result.records[0]["hours"] == ""
        assert result.records[0]["total_amount"] == ""


def test_scanned_ruled_heading_recovery_keeps_known_labor_layout(tmp_path, monkeypatch):
    import ocr_ingestion.extraction as extraction

    source = write_pdf(tmp_path / "source.pdf", acme_lines())
    image_path = tmp_path / "printed.png"
    with pymupdf.open(source) as document:
        native, _ = extraction._native_words(document[0])
        document[0].get_pixmap(dpi=180).save(image_path)
    passes = []

    def read_words(image, *, sparse=False):
        passes.append(sparse)
        scale = image.width / 820
        return [
            extraction.Word(
                word.x0 * scale,
                word.y0 * scale,
                word.x1 * scale,
                word.y1 * scale,
                "LABOR|" if word.text == "LABOR" and not sparse else word.text,
            )
            for word in native
            if word.y * scale < image.height
        ]

    monkeypatch.setattr(extraction, "_ocr_words", read_words)
    result = extract_document(image_path, contractor="ACME Waterproofing")
    assert any(passes)
    assert [table.kind for table in result.tables] == ["labor"]
    assert len(result.records) == 3
    assert result.tables[0].requires_review


def test_tally_preprinted_rates_without_work_entries_stay_excluded(tmp_path):
    source = write_pdf(
        tmp_path / "tally.pdf",
        [
            (80, [(20, "T&M Tally")]),
            (100, [(20, "Rating"), (170, "Billing Rate"), (350, "Hours Worked")]),
            (
                120,
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
            (
                140,
                [
                    (20, "Worker"),
                    (170, "10.00"),
                    (220, "15.00"),
                    (270, "20.00"),
                    (350, "4"),
                    (510, "40.00"),
                ],
            ),
            (160, [(20, "Worker"), (170, "10.00"), (220, "15.00"), (270, "20.00")]),
        ],
    )
    result = extract_document(source, use_ocr=False)
    assert len(result.records) == 1
    assert result.records[0]["reg_hours"] == "4"
