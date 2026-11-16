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
REFERENCE_RE = re.compile(r"\b(?:AD|CD|CR|UC)\d{3,}(?:\.\d+)?[A-Z]*(?:R\d+)?\b", re.I)
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
    # Filter source spans, not rectangles: a correction can occupy the exact
    # same coordinates as the original rate without replacing its PDF text.
    spans = [span for block in page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)["blocks"] if "lines" in block
             for line in block["lines"] for span in line["spans"]]
    def dark_neutral(color):
        channels = [(color >> shift) & 255 for shift in (16, 8, 0)]
        return max(channels) <= 80 and max(channels) - min(channels) <= 16

    base_fonts = {span["font"] for span in spans if dark_neutral(span["color"])
                  and any(c["c"].strip() for c in span["chars"])}
    kept = []
    removed = 0
    for span in spans:
        text = "".join(char["c"] for char in span["chars"])
        if any(mark in text for mark in "✓✔☑") or (
            not dark_neutral(span["color"]) and base_fonts and span["font"] not in base_fonts
        ):
            removed += 1
        else:
            kept.append(span)
    result = []
    if not removed:
        for x0, y0, x1, y1, text, *_ in page.get_text("words"):
            rectangle = pymupdf.Rect(x0, y0, x1, y1) * page.rotation_matrix
            result.append(Word(*rectangle, text))
        return result, 0
    for span in kept:
        token = []
        for char in [*span["chars"], {"c": " "}]:
            if not char["c"].isspace():
                token.append(char)
            elif token:
                rectangle = pymupdf.Rect(token[0]["bbox"])
                for item in token[1:]:
                    rectangle |= pymupdf.Rect(item["bbox"])
                result.append(Word(*(rectangle * page.rotation_matrix), "".join(item["c"] for item in token)))
                token = []
    return result, removed


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
        if centers[i][1] in {"quantity", "_job"} and centers[i + 1][1] == "description":
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
    if {"fwd", "ticket", "date", "area", "job", "description", "worker", "craft", "hours", "rate", "cost"}.issubset(keys):
        # Printed worker-detail ledger; retain contractor/date evidence rather
        # than deriving identities or rate types from a price match.
        mapping = {"fwd": "_fwd", "ticket": "ticket_id", "date": "work_start",
                   "area": "_area", "job": "_job", "description": "description",
                   "worker": "worker_name", "craft": "position_original",
                   "hours": "hours", "rate": "rate", "cost": "total_amount"}
        groups = []
        for word in line:
            if _key(word.text) in mapping:
                groups.append((mapping[_key(word.text)], [word.x]))
            elif groups:
                groups[-1][1].append(word.x)
        centers = [(sum(xs) / len(xs), field) for field, xs in groups]
        if len(centers) == len(mapping):
            return "labor_detail", sorted(centers), True
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
    if keys == ["time", "hrs", "hours", "time", "hrs", "rate", "rate", "rate"]:
        # Two-line proposal heading: ST/OT/DT are explicit, not inferred from prices.
        above = [w for row in lines[max(0, index - 2):index] for w in row]
        top = [w for w in above if _key(w.text) in {"labor", "straight", "overtime", "double"}]
        totals = [w for w in above if _key(w.text) == "totals"]
        if [_key(w.text) for w in top] == ["labor", "straight", "overtime", "double", "straight", "overtime", "double"] and len(totals) == 1:
            fields = ["position_original", "reg_hours", "ot_hours", "dt_hours", "reg_rate", "ot_rate", "dt_rate"]
            return "labor_tally", _columns(top, fields) + [(totals[0].x, "total_amount")], True
    if keys == ["trade", "hrs", "rate", "cost"]:
        # Preserve printed trade abbreviations and generic billing basis. These
        # proposal tables do not establish a work date or an approved rate.
        return "labor", _columns(line, ["position_original", "hours", "rate", "extension_amount"]), True
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


def _source_line_key(line):
    """Identify one source location, never equal-looking business values."""
    return tuple((w.x0, w.y0, w.x1, w.y1, w.text) for w in line)


def _extract_known_tables(result, words, page_number, method, metadata, *, consumed_rows=None):
    lines = _lines(words)
    detected = [(i, _detect_header(lines, i)) for i in range(len(lines))]
    detected = [(i, value) for i, value in detected if value]
    tables = []
    for n, (index, (kind, centers, review)) in enumerate(detected):
        if kind not in LABOR_TYPES | {"unfamiliar"}:
            continue
        end = detected[n + 1][0] if n + 1 < len(detected) else len(lines)
        body = lines[index + 1:end]
        worker_ledger = "_fwd" in [field for _, field in centers]
        trade_table = [field for _, field in centers] == ["position_original", "hours", "rate", "extension_amount"]
        if (method == "ocr" or kind == "unfamiliar" or trade_table or worker_ledger) and not _has_tabular_body(lines[index], body, centers):
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
            if re.match(r"^(?:TOTAL(?:S)?\b|SUBTOTAL\b|LABOR\s+SUB[- ]?TOTAL\b)", upper):
                break
            if re.match(r"^(?:SDC\s+(?:ADJUSTED|COMMENT)|ADJUSTED\s+TOTAL|REVIEWED\b|SIGNATURE\b|PREVIOUSLY\s+INVOICED|DUE THIS\b|PROJECTED\b)", upper):
                break
            if kind == "labor_detail" and "BY CRAFT" in upper:
                break
            if trade_table and re.match(r"^(?:FREIGHT|HARDCOSTS|RENTAL|MATERIALS?|EQUIPMENT)\b", upper):
                break
            cells = _split(line, centers)
            if trade_table:
                trade_values = dict(zip([field for _, field in centers], cells))
                if not any(character.isalpha() for character in trade_values.get("position_original", "")):
                    continue
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
                if not trade_table:
                    values["position_original"] = role.group(1) if role else ""
                premium = re.search(r"\bpremium\b.*", description, re.I)
                values["rate_basis_raw"] = premium.group(0) if premium else ""
            if kind == "unfamiliar":
                if consumed_rows is not None:
                    consumed_rows.add(_source_line_key(line))
                continue  # Users explicitly map the raw table before records are created.
            # Capture printed hourly prices, including unused roles. Hours and
            # billed amounts do not determine whether a labeled rate is usable.
            # _record still rejects rows without an explicit rate/source label.
            if worker_ledger:
                values["contractor"] = ""  # A packet-level company is not worker-employer evidence.
                if not any(values.get(field, "").strip() for field in ("worker_name", "description", "ticket_id", "work_start")):
                    continue  # Craft-only totals are not worker-detail rows, even if OCR splits "By Craft".
            if kind == "labor_detail":
                if not DATE_RE.fullmatch(values.get("work_start", "")):
                    result.issue(page_number, "unresolved_field", "Confirm the printed work date against the source.",
                                 table_id=table_id, row_index=row_index, field="work_start", raw=values.get("work_start", ""))
                    values["work_start"] = ""
                    table.requires_review = True
                values["work_end"] = values["work_start"]
            values["row_type"] = "labor"
            previous_count = len(table.record_ids)
            _record(result, table, row_index, values, metadata)
            if consumed_rows is not None and len(table.record_ids) > previous_count:
                consumed_rows.add(_source_line_key(line))
        if table.rows and (table.record_ids or kind == "unfamiliar"):
            if worker_ledger:
                result.issue(page_number, "worker_ledger_review_required", "Confirm worker details, contractor, and printed work dates against the source.", table_id=table_id)
            if trade_table:
                result.issue(page_number, "trade_table_review_required",
                             "Confirm printed trade abbreviations, generic rate basis, and missing work dates against the source.",
                             table_id=table_id)
            tables.append(table)
    return tables



def _extract_labor_items(result, words, page_number, method, metadata, *, consumed_rows=()):
    """Explicit proposal/slip rows and hours-at-rate labor statements.

    No arithmetic reconstruction, date propagation across pages, or contractor
    inheritance in mixed-company packets. Every new row requires source review.
    """
    money = r"\$?\s*([\d,]+\.\d{2})"
    proposal = re.compile(r"^(?:\d+\s+)?(Field Labor\s*.+?)\s+(\d+(?:\.\d+)?)\s+" + money + r"\s*:?\s+" + money + r"\s*$", re.I)
    slip_row = re.compile(r"^(PF\s+.+?-(?:ST|RT|OT|DT|PT))\s+(\d+(?:\.\d+)?)\s+" + money + r"\s+" + money + r"\s*$", re.I)
    statement = re.compile(r"^(Labor\s*:|Field Labor\s+.+?|Mason|Laborer)\s*(\d+(?:\.\d+)?)\s*(?:hrs|hours)\s*(?:@|x)\s*" + money + r"\s*:?\s+" + money + r"\s*$", re.I)
    tables = []
    work_date = ticket = ""
    for line in _lines(words):
        text = _text(line).strip()
        if re.match(r"^T&M Slip\b", text, re.I):
            work_date = ticket = ""
            heading = re.fullmatch(r"T&M Slip\s+(\d+)\s*-\s*[A-Za-z]+\s+(\d{1,2}/\d{1,2}/\d{2,4})", text, re.I)
            if heading:
                try:
                    work_date = date(heading[2])
                    ticket = heading[1]
                except ValueError:
                    result.issue(page_number, "unresolved_group_date", "Confirm the printed slip work date.", raw=heading[2])
            continue
        if _section_heading(line) or re.match(r"^(?:\d+\s+Total Hours|Materials?|Subtotal|Total|LABOR\s+SUB[- ]?TOTAL|Terrace|Quote|Proposal)\b", text, re.I):
            work_date = ticket = ""
        if _source_line_key(line) in consumed_rows:
            continue
        match = statement.fullmatch(text) or proposal.fullmatch(text)
        is_slip = False
        if not match and ticket:
            match = slip_row.fullmatch(text)
            is_slip = bool(match)
        if not match:
            continue
        label, hours, rate, amount = match.groups()
        table_id = f"p{page_number}-y{round(line[0].y)}-labor_item"
        values = {"row_type": "labor", "description": label, "position_original": label,
                  "hours": hours, "rate": rate, "total_amount": amount,
                  "contractor": "", "ticket_id": ticket if is_slip else "",
                  "work_start": work_date if is_slip else "", "work_end": work_date if is_slip else ""}
        basis = re.search(r"-\s*(ST|RT|OT|DT|PT)\s*$", label, re.I)
        if basis:
            values["rate_basis_raw"] = basis[1].upper()
            field = {"ST": "reg", "RT": "reg", "OT": "ot", "DT": "dt"}.get(basis[1].upper())
            if field:
                values.update({field + "_hours": hours, field + "_rate": rate, "hours": "", "rate": ""})
        table = Table(table_id, page_number, "labor", ["description", "hours", "rate", "total_amount"],
                      [[label, hours, rate, amount]],
                      [min(w.x0 for w in line), min(w.y0 for w in line), max(w.x1 for w in line), max(w.y1 for w in line)], method, True)
        _record(result, table, 1, values, metadata)
        if table.record_ids:
            tables.append(table)
            result.issue(page_number, "labor_item_review_required", "Confirm source classification, contractor, work dates, and original submitted values for this proposal/slip row.", table_id=table_id)
    return tables


def _extract_page_labor(result, words, page_number, method, metadata):
    consumed_rows = set()
    tables = _extract_known_tables(result, words, page_number, method, metadata, consumed_rows=consumed_rows)
    tables.extend(_extract_labor_items(result, words, page_number, method, metadata, consumed_rows=consumed_rows))
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
        {"description", "rating", "quantity", "item", "classification", "trade"} & keys
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
                tables = _extract_page_labor(result, relevant_words, page_number, method, metadata)
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
                    tables = _extract_page_labor(result, relevant_words, page_number, method, metadata)
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
