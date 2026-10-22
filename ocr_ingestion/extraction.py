"""Geometry-based printed-table extraction. No contract validation or rate lookups."""

from collections import Counter
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import re
from typing import Callable

import pymupdf

from .models import (
    DATE_FIELDS, FIELDS, LABOR_TYPES, NUMBER_FIELDS, RATE_FIELDS,
    Extraction, Table, date, is_labor_rate, normalize_record, row_id,
)


SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})\b")
REFERENCE_RE = re.compile(r"\b(?:AD|CD|CR)\d{3,}(?:\.\d+)?[A-Z]*(?:R\d+)?\b", re.I)
TICKET_RE = re.compile(r"\b\d{3,5}-\d{3,8}\b")
MAX_BYTES = 200 * 1024 * 1024


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def x(self):
        return (self.x0 + self.x1) / 2

    @property
    def y(self):
        return (self.y0 + self.y1) / 2


def _native_words(page) -> tuple[list[Word], int]:
    spans = [span for block in page.get_text("dict")["blocks"] if "lines" in block
             for line in block["lines"] for span in line["spans"]]
    base_fonts = {span["font"] for span in spans if span["color"] == 0 and span["text"].strip()}
    removed = []
    for span in spans:
        text = span["text"].strip()
        # Different-font colored overlays are present in the supplied flattened reviews.
        # Colored source text in the document's normal fonts is preserved.
        if any(mark in text for mark in "✓✔☑") or (
            span["color"] != 0 and base_fonts and span["font"] not in base_fonts
        ):
            removed.append(pymupdf.Rect(span["bbox"]))
    result = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        center = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
        if any(center in rectangle for rectangle in removed):
            continue
        rectangle = pymupdf.Rect(x0, y0, x1, y1) * page.rotation_matrix
        result.append(Word(*rectangle, text))
    return result, len(removed)


def _lines(words: list[Word]) -> list[list[Word]]:
    lines = []
    for word in sorted(words, key=lambda item: (item.y, item.x0)):
        # A small tolerance accommodates bold/numeric font baseline differences.
        if not lines or abs(word.y - sum(w.y for w in lines[-1]) / len(lines[-1])) > 2.0:
            lines.append([word])
        else:
            lines[-1].append(word)
    return [sorted(line, key=lambda item: item.x0) for line in lines]


def _text(line):
    return " ".join(word.text for word in line)


def _key(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _columns(line, fields):
    """Map column centers from header words and retain field order."""
    return sorted([(word.x, field) for word, field in zip(line, fields)], key=lambda item: item[0])


def _split(line, centers):
    cells = [[] for _ in centers]
    boundaries = [(centers[i][0] + centers[i + 1][0]) / 2 for i in range(len(centers) - 1)]
    for i in range(len(boundaries)):
        if centers[i][1] == "quantity" and centers[i + 1][1] == "description":
            # Wide description headings are centered; the quantity column is narrow.
            boundaries[i] = centers[i][0] + (centers[i + 1][0] - centers[i][0]) * .25
    for word in line:
        index = sum(word.x > boundary for boundary in boundaries)
        cells[index].append(word)
    return [" ".join(word.text for word in sorted(cell, key=lambda w: w.x0)) for cell in cells]


ALIASES = {
    "date": "work_start", "description": "description", "rating": "position_original",
    "classification": "position_original", "role": "position_original", "craft": "position_original",
    "hrs": "hours", "hours": "hours", "rate": "rate", "quantity": "quantity", "qty": "quantity",
    "amount": "total_amount", "total": "total_amount", "extension": "extension_amount",
    "ohp": "overhead_profit_amount", "price": "unit_rate", "unitprice": "unit_rate",
    "item": "description", "name": "worker_name", "ticket": "ticket_id", "unit": "unit",
}


def _section_heading(line):
    match = re.fullmatch(
        r"(LABOR|TRUCKING|MATERIALS?|EQUIPMENT|RENTALS?)(?:\s+RATE(?:\s+\d+(?:\.\d+)?\s*%)?)?",
        _text(line).strip(), re.I,
    )
    return match.group(1).upper() if match else ""


def _labor_words(words):
    """Keep only printed LABOR sections, bounded by other sections or labor totals."""
    selected = []
    active = False
    for line in _lines(words):
        section = _section_heading(line)
        if section:
            active = section == "LABOR"
        if active:
            selected.extend(line)
            if re.match(r"^TOTAL\s+LABOR\b", _text(line), re.I):
                active = False
    return selected


def _detect_header(lines, index):
    line = lines[index]
    keys = [_key(word.text) for word in line]
    if {"date", "ticket", "name", "rating"}.issubset(keys) and keys.count("st") == 3:
        fields = []
        groups = Counter()
        for key in keys:
            if key in {"st", "ot", "dt"}:
                prefix = "reg" if key == "st" else key
                fields.append(prefix + ("_hours", "_rate", "_amount")[groups[key]])
                groups[key] += 1
            else:
                fields.append({"date": "work_start", "ticket": "ticket_id", "name": "worker_name",
                               "rating": "position_original", "day": "_day"}.get(key, "_ignore"))
        return "labor_detail", _columns(line, fields), False
    if keys.count("st") == 2 and keys.count("ot") == 2 and keys.count("dt") == 2:
        previous = " ".join(_text(v) for v in lines[max(0, index - 2):index]).lower()
        if "rating" in previous and "billing" in previous and "hours" in previous:
            column_words = [w for w in line if _key(w.text) in {"st", "ot", "dt"}]
            rating = next(w for earlier in lines[max(0, index - 2):index]
                          for w in earlier if _key(w.text) == "rating")
            amount_words = [w for w in line if _key(w.text) in {"billing", "amount"}]
            centers = [(rating.x, "position_original")]
            for n, word in enumerate(column_words):
                prefix = "reg" if _key(word.text) == "st" else _key(word.text)
                centers.append((word.x, prefix + ("_rate" if n < 3 else "_hours")))
            if not amount_words:
                return None
            centers.append((sum(w.x for w in amount_words) / len(amount_words), "total_amount"))
            # Preserve the trailing unlabeled date without assigning it a work-date meaning.
            following_dates = [w.x for row in lines[index + 1:index + 8] for w in row
                               if DATE_RE.fullmatch(w.text) and w.x > centers[-1][0]]
            if following_dates:
                centers.append((sum(following_dates) / len(following_dates), "unlabeled_date_raw"))
            return "labor_tally", sorted(centers), False
    if {"description", "hrs", "rate", "extension", "total"}.issubset(keys):
        # ACME reuses these columns for Trucking. The printed section, rather
        # than a filename, contractor input, or rate value, determines its kind.
        kind = "labor"
        for earlier in reversed(lines[max(0, index - 3):index]):
            label = _section_heading(earlier)
            if label:
                kind = "labor" if label == "LABOR" else "other_cost"
                break
        return kind, _columns(line, [ALIASES.get(k, "_ignore") for k in keys]), False
    if "description" in keys and "quantity" in keys and "price" in keys:
        # Retain the boundary so preceding labor rows cannot consume this table.
        return "other_cost", [], False
    mapped = [ALIASES.get(key, "") for key in keys]
    if sum(bool(v) for v in mapped) >= 3 and any(v in mapped for v in ("description", "position_original")):
        return "unfamiliar", _columns(line, [v or "_ignore" for v in mapped]), True
    return None


def _record(result, table, row_index, values, metadata):
    record = dict(metadata)
    record.update({field: value for field, value in values.items() if field in FIELDS})
    record.update({"record_id": row_id(result.document_id, table.table_id, row_index),
                   "document_id": result.document_id, "source_file": result.source_file,
                   "source_page": str(table.page), "table_id": table.table_id,
                   "row_index": str(row_index), "extraction_method": table.method})
    for key in NUMBER_FIELDS | DATE_FIELDS:
        if record.get(key):
            try:
                normalize_record({key: record[key]})
            except ValueError:
                result.issue(table.page, "unresolved_field", "A cell could not be interpreted as one value.",
                             table_id=table.table_id, row_index=row_index, field=key, raw=record[key])
                record[key] = ""
                table.requires_review = True
    normalized = normalize_record(record)
    if not is_labor_rate(normalized):
        return
    result.records.append(normalized)
    table.record_ids.append(normalized["record_id"])


def _has_tabular_body(header, body, centers):
    """Require separated column headings and an aligned cost row, not prose keywords."""
    gaps = [right.x0 - left.x1 for left, right in zip(header, header[1:])]
    character_width = sum(word.x1 - word.x0 for word in header) / max(1, sum(len(word.text) for word in header))
    if sum(gap >= max(8, character_width * 1.5) for gap in gaps) < 2:
        return False
    for line in body:
        values = {field: cell for (_, field), cell in zip(centers, _split(line, centers))}
        values["row_type"] = "labor"
        if not re.match(r"^(?:TOTAL|SUBTOTAL)\b", _text(line), re.I) and is_labor_rate(values):
            return True
    return False


def _extract_known_tables(result, words, page_number, method, metadata):
    lines = _lines(words)
    detected = [(i, _detect_header(lines, i)) for i in range(len(lines))]
    detected = [(i, value) for i, value in detected if value]
    tables = []
    for n, (index, (kind, centers, review)) in enumerate(detected):
        if kind not in LABOR_TYPES | {"unfamiliar"}:
            continue
        end = detected[n + 1][0] if n + 1 < len(detected) else len(lines)
        body = lines[index + 1:end]
        if (method == "ocr" or kind == "unfamiliar") and not _has_tabular_body(lines[index], body, centers):
            continue
        table_id = f"p{page_number}-y{round(lines[index][0].y)}-{kind}"
        table = Table(table_id, page_number, kind, [field for _, field in centers], [],
                      [min(w.x0 for w in lines[index]), min(w.y0 for w in lines[index]),
                       max(w.x1 for w in lines[index]), max(w.y1 for w in (body[-1] if body else lines[index]))],
                      method, review or method == "ocr")
        current_date = ""
        for row_index, line in enumerate(body, 1):
            text = _text(line)
            upper = text.upper()
            if re.match(r"^(?:TOTAL(?:S)?\b|SUBTOTAL\b)", upper):
                break
            if re.match(r"^(?:SDC\s+(?:ADJUSTED|COMMENT)|ADJUSTED\s+TOTAL|REVIEWED\b|SIGNATURE\b|PREVIOUSLY\s+INVOICED|DUE THIS\b|PROJECTED\b)", upper):
                break
            if kind == "labor_detail" and "BY CRAFT" in upper:
                break
            cells = _split(line, centers)
            table.rows.append(cells)
            values = {field: value for (_, field), value in zip(centers, cells) if not field.startswith("_")}
            if kind == "labor":
                # Date-only group headings belong to the rows below, bounded by this table.
                raw_date = values.get("work_start", "")
                if DATE_RE.fullmatch(raw_date):
                    current_date = date(raw_date)
                elif raw_date:
                    # Do not carry a prior group's date across an unreadable/new group label.
                    current_date = ""
                    result.issue(page_number, "unresolved_group_date", "Printed group date needs review.",
                                 table_id=table_id, row_index=row_index, raw=raw_date)
                    table.requires_review = True
                values["work_start"] = current_date
                values["work_end"] = current_date
                description = values.get("description", "")
                # Quote an explicitly printed role substring without mapping it to a tracker title.
                role = re.match(r"^\d+(?:\.\d+)?\s+(.+?)\s+at\s+\d", description, re.I)
                values["position_original"] = role.group(1) if role else ""
                premium = re.search(r"\bpremium\b.*", description, re.I)
                values["rate_basis_raw"] = premium.group(0) if premium else ""
            if kind == "unfamiliar":
                continue  # Users explicitly map the raw table before records are created.
            if kind in {"labor_detail", "labor_tally"} and not any(
                values.get(field, "").strip() not in {"", "-", "—", "–"}
                for field in ("reg_hours", "ot_hours", "dt_hours", "reg_amount", "ot_amount", "dt_amount", "total_amount")
            ):
                continue  # Blank BrandSafway template rows can contain preprinted rates.
            if kind == "labor_detail":
                if not DATE_RE.fullmatch(values.get("work_start", "")):
                    continue
                values["work_end"] = values["work_start"]
            values["row_type"] = "labor"
            _record(result, table, row_index, values, metadata)
        if table.rows and (table.record_ids or kind == "unfamiliar"):
            tables.append(table)
    return tables


def _fallback_tables(page, words, page_number):
    """Offer ruled unfamiliar tables for explicit mapping using cleaned source words."""
    result = []
    # Avoid treating engineering drawings and handwritten form grids as cost tables.
    text = " ".join(word.text.lower() for word in words)
    if sum(bool(re.search(r"\b" + key + r"\b", text)) for key in ("rate", "amount", "price", "hours", "quantity")) < 2:
        return result
    for index, found in enumerate(page.find_tables().tables):
        if found.row_count < 2 or found.col_count < 2:
            continue
        rows = []
        for row in found.rows:
            cells = []
            for box in row.cells:
                if box is None:
                    cells.append("")
                else:
                    x0, y0, x1, y1 = box
                    cells.append(" ".join(word.text for line in _lines([
                        word for word in words if x0 <= word.x <= x1 and y0 <= word.y <= y1
                    ]) for word in line))
            rows.append(cells)
        fields = [ALIASES.get(_key(cell), "") for cell in rows[0]]
        if not RATE_FIELDS.intersection(fields):
            continue
        if not any(is_labor_rate({**dict(zip(fields, row)), "row_type": "labor"}) for row in rows[1:]):
            continue
        result.append(Table(f"p{page_number}-grid{index}", page_number, "unfamiliar", rows[0], rows[1:],
                            list(found.bbox), "native", True))
    return result


def _ocr_words(image, *, sparse=False):
    import pytesseract
    from pytesseract import Output
    try:
        data = pytesseract.image_to_data(image, output_type=Output.DICT,
                                        config="--psm 11" if sparse else "--psm 6", timeout=60)
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract is not installed or is not on PATH. Install it to read scanned printed tables.") from exc
    words = []
    for i, text in enumerate(data["text"]):
        if text.strip():
            x, y = data["left"][i], data["top"][i]
            words.append(Word(x, y, x + data["width"][i], y + data["height"][i], text.strip()))
    return words


def _printed_scan_words(page, *, labor_only=False):
    from PIL import Image
    # Probe only the printed header region before OCR of an entire scanned table page.
    scale = min(180 / 72, 2400 / max(page.rect.width, page.rect.height))
    image = Image.open(io.BytesIO(page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), annots=False).tobytes("png"))).convert("RGB")
    header_image = image.crop((0, 0, image.width, int(image.height * .45)))
    probe = _ocr_words(header_image)
    sections = []
    if labor_only and not any(_section_heading(line) == "LABOR" for line in _lines(probe)):
        # Ruled borders can merge a section label into nearby marks. Sparse
        # text detection can recover the heading without guessing its wording.
        sparse = _ocr_words(header_image, sparse=True)
        sections = [line for line in _lines(sparse) if _section_heading(line)]
        if not any(_section_heading(line) == "LABOR" for line in sections):
            return []
    keys = {_key(word.text) for word in probe}
    if not ({"rate", "hrs", "hours", "price", "amount", "extension"} & keys) or not (
        {"description", "rating", "quantity", "item", "classification"} & keys
    ):
        return []
    # Raster classification is deliberately not treated as proof that every value is printed.
    # Every OCR-derived table requires a user's review of the original page before persistence.
    words = _ocr_words(image)
    for section in sections:
        top, bottom = min(word.y0 for word in section), max(word.y1 for word in section)
        words = [word for word in words if not top <= word.y <= bottom] + section
    return [Word(word.x0 / scale, word.y0 / scale, word.x1 / scale, word.y1 / scale, word.text)
            for word in words]


def extract_document(
    source_path: str | Path, *, contractor: str = "", project: str = "",
    use_ocr: bool = True, progress: Callable[[int, int], None] | None = None,
) -> Extraction:
    source_path = Path(source_path)
    if source_path.suffix.lower() not in SUPPORTED:
        raise ValueError("Supported inputs are PDF, PNG, JPEG, and TIFF; ZIP files are not accepted.")
    if source_path.stat().st_size > MAX_BYTES:
        raise ValueError("Input exceeds the 200 MB limit.")
    contents = source_path.read_bytes()
    result = Extraction(hashlib.sha256(contents).hexdigest(), source_path.name)
    document = None
    try:
        if source_path.suffix.lower() == ".pdf":
            document = pymupdf.open(stream=contents, filetype="pdf")
        else:
            from PIL import Image, ImageSequence
            image = Image.open(io.BytesIO(contents))
            document = pymupdf.open()
            for frame in ImageSequence.Iterator(image):
                buffer = io.BytesIO()
                frame.convert("RGB").save(buffer, format="PNG")
                page = document.new_page(width=frame.width, height=frame.height)
                page.insert_image(page.rect, stream=buffer.getvalue())
        if document.needs_pass:
            raise ValueError("Password-protected PDFs must be unlocked locally before ingestion.")
        acme_document = bool(re.search(r"\bacme\b", contractor, re.I)) or any(
            re.search(r"\bacme\s+waterproofing\b", page.get_text(), re.I) for page in document
        )
        current_reference = ""
        for page_index, page in enumerate(document):
            if progress:
                progress(page_index + 1, len(document))
            page_number = page_index + 1
            try:
                words, removed = _native_words(page)
                page_text = "\n".join(_text(line) for line in _lines(words))
                references = REFERENCE_RE.findall(page_text)
                if references:
                    current_reference = references[0]
                ticket = TICKET_RE.search(page_text)
                metadata = {"contractor": contractor, "project": project,
                            "document_reference": current_reference,
                            "ticket_id": ticket.group(0) if ticket else ""}
                method = "native"
                relevant_words = _labor_words(words) if acme_document else words
                # Try native tables even when a short table contains very few words.
                tables = _extract_known_tables(result, relevant_words, page_number, method, metadata)
                if not tables and relevant_words:
                    tables = _fallback_tables(page, relevant_words, page_number)
                large_raster = False
                if not tables:
                    for image_info in page.get_images():
                        if image_info[2] < 300 or image_info[3] < 300:
                            continue
                        if any(rectangle.get_area() > page.mediabox.get_area() * .45
                               for rectangle in page.get_image_rects(image_info[0])):
                            large_raster = True
                            break
                # A scanned page can have many native reviewer labels; word count alone is unreliable.
                if not tables and large_raster:
                    if not use_ocr:
                        result.pages.append({"page": page_number, "status": "scan_not_processed"})
                        continue
                    words = _printed_scan_words(page, labor_only=acme_document)
                    method = "ocr"
                    if not acme_document and re.search(
                        r"\bacme\s+waterproofing\b", " ".join(word.text for word in words), re.I,
                    ):
                        acme_document = True
                    relevant_words = _labor_words(words) if acme_document else words
                    if not relevant_words:
                        result.pages.append({"page": page_number, "status": "skipped_no_labor_section" if acme_document else "no_printed_cost_table_header"})
                        continue
                    tables = _extract_known_tables(result, relevant_words, page_number, method, metadata)
                    if tables:
                        result.issue(page_number, "ocr_review_required", "Review the printed table against the page; do not accept handwritten values.")
                if removed:
                    if tables or not acme_document:
                        result.issue(page_number, "overlay_excluded", "Different-font colored overlays or check glyphs were excluded.", count=removed)
                    for table in tables:
                        table.requires_review = True
                result.tables.extend(tables)
                status = ("tables_found" if tables else "skipped_no_labor_section"
                          if acme_document and not relevant_words else "no_printed_table"
                          if method == "ocr" else "no_supported_cost_table")
                result.pages.append({"page": page_number, "status": status,
                                     "table_count": len(tables), "method": method})
            except RuntimeError:
                raise  # Missing OCR prerequisites must be actionable to the caller.
            except Exception as exc:
                result.issue(page_number, "page_extraction_failed", str(exc))
                result.pages.append({"page": page_number, "status": "extraction_failed"})
        return result
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise ValueError("The document cannot be opened; check that it is a valid supported file.") from exc
    finally:
        if document is not None:
            document.close()


def map_table(result: Extraction, table_id: str, mapping: dict[int, str], *, row_type: str = "labor"):
    """Explicit mapping for unfamiliar tables; retain original source cells as evidence."""
    table = next(table for table in result.tables if table.table_id == table_id)
    allowed = set(FIELDS) - {"record_id", "document_id", "source_file", "source_page", "table_id",
                            "row_index", "row_type", "extraction_method"}
    if any(field not in allowed for field in mapping.values()):
        raise ValueError("Mapping contains a provenance field or unsupported column.")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Map each destination field only once.")
    if any(index < 0 or index >= len(table.headers) for index in mapping):
        raise ValueError("Mapping column index is outside this table.")
    if not mapping:
        raise ValueError("Select at least one column mapping.")
    if row_type not in LABOR_TYPES:
        raise ValueError("Only labor-rate rows can be mapped for saving.")
    if not RATE_FIELDS.intersection(mapping.values()) or not {
        "description", "position_original", "worker_name",
    }.intersection(mapping.values()):
        raise ValueError("Map an explicit labor rate and a description, classification, or worker name.")
    old_ids = set(table.record_ids)
    result.records = [row for row in result.records if row["record_id"] not in old_ids]
    table.record_ids = []
    table.requires_review = True
    for index, row in enumerate(table.rows, 1):
        values = {field: row[column] for column, field in mapping.items() if column < len(row)}
        if any(value.strip() for value in values.values()):
            values["row_type"] = row_type
            _record(result, table, index, values, {})
