"""Locked, recoverable CSV append operations. All artifacts belong in private data/."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile

from filelock import FileLock

from .models import FIELDS, SCHEMA_VERSION, Extraction, is_labor_rate, normalize_record


def _atomic_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ingestion-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(obj, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _paths(csv_path: Path):
    folder = csv_path.parent / (csv_path.stem + "_private")
    return folder, folder / "manifest.json", folder / "pending_append.json"


def _recover(csv_path: Path, manifest_path: Path, journal_path: Path):
    if not journal_path.exists():
        return
    journal = json.loads(journal_path.read_text())
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if manifest.get("last_transaction") != journal["transaction"]:
        if csv_path.exists():
            with csv_path.open("r+b") as stream:
                stream.truncate(journal["original_size"])
                stream.flush()
                os.fsync(stream.fileno())
    journal_path.unlink()


def load_records(csv_path: str | Path) -> list[dict]:
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(csv_path) + ".lock", timeout=30):
        _, manifest_path, journal_path = _paths(csv_path)
        _recover(csv_path, manifest_path, journal_path)
        return _read_records(csv_path)


def _read_records(csv_path: Path) -> list[dict]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return []
    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError("Existing CSV has an incompatible schema; no data was overwritten.")
        rows = list(reader)
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Existing CSV has an incomplete row; restore it before appending.")
        normalized = normalize_record(row)
        row["row_type"] = normalized["row_type"]
        if not row["record_id"] or not row["document_id"]:
            raise ValueError("Existing CSV contains a row without provenance identifiers.")
    return rows


def append_records(
    extraction: Extraction,
    csv_path: str | Path,
    selected_ids: list[str],
    *,
    reviewed_table_ids: list[str] | None = None,
    source_path: str | Path | None = None,
) -> dict:
    """Save selected rows; repeated uploads preserve existing data and add no duplicates."""
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    private, manifest_path, journal_path = _paths(csv_path)
    selected = set(selected_ids)
    reviewed = set(reviewed_table_ids or [])
    candidates = {record["record_id"]: record for record in extraction.records}
    if selected - candidates.keys():
        raise ValueError("Selected rows do not belong to this extraction.")
    rows = [normalize_record(r) for r in extraction.records if r["record_id"] in selected]
    if any(not is_labor_rate(row) for row in rows):
        raise ValueError("Only labor rows with an explicit rate and source description, classification, or worker name can be saved.")
    for table in extraction.tables:
        if table.requires_review and selected.intersection(table.record_ids) and table.table_id not in reviewed:
            raise ValueError("OCR or unfamiliar tables require explicit review before saving.")
    if len({r["record_id"] for r in rows}) != len(rows):
        raise ValueError("Extraction contains duplicate record identifiers.")
    if any(r["document_id"] != extraction.document_id for r in rows):
        raise ValueError("A selected record has inconsistent document provenance.")
    original_bytes = None
    if source_path is not None:
        source_path = Path(source_path)
        original_bytes = source_path.read_bytes()
        if hashlib.sha256(original_bytes).hexdigest() != extraction.document_id:
            raise ValueError("Source document has changed since extraction.")

    with FileLock(str(csv_path) + ".lock", timeout=30):
        _recover(csv_path, manifest_path, journal_path)
        existing = _read_records(csv_path)
        known = {r["record_id"] for r in existing}
        new_rows = [r for r in rows if r["record_id"] not in known]
        if not new_rows:
            return {"added": 0, "already_present": len(rows), "total": len(existing)}
        private.mkdir(parents=True, exist_ok=True)
        # Evidence is written before the data commit so every saved row has its source evidence.
        evidence_path = private / "evidence" / f"{extraction.document_id}.json"
        prior_evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {
            "document_id": extraction.document_id, "extractions": [],
        }
        prior_evidence["extractions"].append(extraction.evidence())
        _atomic_json(evidence_path, prior_evidence)
        if source_path is not None:
            original = private / "originals" / (extraction.document_id + source_path.suffix.lower())
            original.parent.mkdir(parents=True, exist_ok=True)
            if not original.exists():
                fd, temporary = tempfile.mkstemp(prefix=".original-", dir=original.parent)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(original_bytes)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, original)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
            "schema_version": SCHEMA_VERSION, "documents": {},
        }
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Manifest schema is incompatible; no CSV records were appended.")
        transaction = hashlib.sha256(os.urandom(32)).hexdigest()
        size = csv_path.stat().st_size if csv_path.exists() else 0
        # Recovery checks whether the manifest commit happened; otherwise it rolls back these bytes.
        _atomic_json(journal_path, {"original_size": size, "transaction": transaction})
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
        if not size:
            writer.writeheader()
        writer.writerows(new_rows)
        with csv_path.open("ab") as stream:
            stream.write(buffer.getvalue().encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        manifest["documents"][extraction.document_id] = {
            "source_file": extraction.source_file,
            "saved_rows": sum(r["document_id"] == extraction.document_id for r in existing) + len(new_rows),
        }
        manifest["last_transaction"] = transaction
        _atomic_json(manifest_path, manifest)
        journal_path.unlink()
        return {"added": len(new_rows), "already_present": len(rows) - len(new_rows), "total": len(existing) + len(new_rows)}
