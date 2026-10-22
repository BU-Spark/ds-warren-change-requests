"""Shared ingestion schema. Empty strings mean unknown, never an inferred zero."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re


SCHEMA_VERSION = 1
FIELDS = [
    "record_id", "document_id", "source_file", "source_page", "table_id", "row_index",
    "row_type", "contractor", "project", "document_reference", "ticket_id",
    "work_start", "work_end", "worker_name", "description", "position_original",
    "rate_basis_raw", "hours", "rate", "reg_hours", "ot_hours", "dt_hours",
    "reg_rate", "ot_rate", "dt_rate", "reg_amount", "ot_amount", "dt_amount",
    "quantity", "unit", "unit_rate", "extension_amount", "overhead_profit_amount",
    "total_amount", "unlabeled_date_raw", "extraction_method",
]
NUMBER_FIELDS = {
    "hours", "rate", "reg_hours", "ot_hours", "dt_hours", "reg_rate", "ot_rate",
    "dt_rate", "reg_amount", "ot_amount", "dt_amount", "quantity", "unit_rate",
    "extension_amount", "overhead_profit_amount", "total_amount",
}
DATE_FIELDS = {"work_start", "work_end"}
# Parser layouts and accepted legacy row types. Stored rows use only "labor".
LABOR_TYPES = {"labor", "labor_detail", "labor_tally"}
RATE_FIELDS = {"rate", "reg_rate", "ot_rate", "dt_rate"}


def is_labor_rate(record):
    """A usable labor row needs an explicit rate and a source label."""
    if record.get("row_type") not in LABOR_TYPES or not any(
        character.isalpha() for field in ("description", "position_original", "worker_name")
        for character in str(record.get(field) or "")
    ):
        return False
    for field in RATE_FIELDS:
        try:
            if number(record.get(field, "")):
                return True
        except ValueError:
            pass
    return False


def number(value: str) -> str:
    value = ("" if value is None else str(value)).strip().replace("$", "").replace(",", "")
    if re.search(r"\d\s+\d", value):
        raise ValueError("Multiple numeric tokens require review")
    value = value.replace(" ", "")
    if value in {"", "-", "—", "–"}:
        return ""
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Not a single numeric value: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("Non-finite numbers are not supported")
    return format(result, "f")


def date(value: str) -> str:
    value = ("" if value is None else str(value)).strip()
    if not value:
        return ""
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Not an explicit supported date: {value!r}")


def normalize_record(record: dict) -> dict[str, str]:
    """Validate without inventing values or renaming labor classifications."""
    extra = set(record) - set(FIELDS)
    if extra:
        raise ValueError(f"Unexpected record columns: {sorted(extra)}")
    result = {key: re.sub(r"\s+", " ", "" if record.get(key) is None else str(record.get(key, ""))).strip() for key in FIELDS}
    if result["row_type"] in LABOR_TYPES:
        result["row_type"] = "labor"
    for key in NUMBER_FIELDS:
        result[key] = number(result[key])
    for key in DATE_FIELDS:
        result[key] = date(result[key])
    for key in ("source_page", "row_index"):
        if result[key] and (not result[key].isdigit() or int(result[key]) < 1):
            raise ValueError(f"{key} must be a positive integer")
    return result


def row_id(document_id: str, table_id: str, row_index: int) -> str:
    return hashlib.sha256(f"{document_id}:{table_id}:{row_index}".encode()).hexdigest()


@dataclass
class Table:
    table_id: str
    page: int
    kind: str
    headers: list[str]
    rows: list[list[str]]
    bbox: list[float]
    method: str
    requires_review: bool = False
    record_ids: list[str] = field(default_factory=list)


@dataclass
class Extraction:
    document_id: str
    source_file: str
    records: list[dict] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)

    def issue(self, page: int, code: str, message: str, **details):
        self.issues.append({"page": page, "code": code, "message": message, **details})

    def evidence(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    def as_json(self) -> str:
        return json.dumps(self.evidence(), ensure_ascii=False, indent=2)
