"""Synthetic tests only: no client data or private snapshots."""

import json
import shutil
import pytest
from ocr_ingestion import append_records, extract_document, load_records
from ocr_ingestion.storage import _paths
from tests.helpers import write_pdf, detail_lines


def test_append_reupload_rename_and_partial_selection(tmp_path):
    source = write_pdf(tmp_path / "original.pdf", detail_lines())
    result = extract_document(source, use_ocr=False)
    ids = [row["record_id"] for row in result.records]
    destination = tmp_path / "rows.csv"
    assert append_records(result, destination, ids[:1], source_path=source)["added"] == 1
    before = destination.read_bytes()
    renamed = tmp_path / "renamed.pdf"
    shutil.copyfile(source, renamed)
    rerun = extract_document(renamed, use_ocr=False)
    assert rerun.document_id == result.document_id
    assert append_records(rerun, destination, ids, source_path=renamed)["added"] == 1
    assert destination.read_bytes().startswith(before)
    assert append_records(rerun, destination, ids)["added"] == 0
    assert len(load_records(destination)) == 2


def test_schema_error_does_not_overwrite_existing_csv(tmp_path):
    destination = tmp_path / "rows.csv"
    original = "wrong,columns\n1,2\n"
    destination.write_text(original)
    result = extract_document(write_pdf(tmp_path / "source.pdf", detail_lines()), use_ocr=False)
    with pytest.raises(ValueError, match="schema"):
        append_records(result, destination, [row["record_id"] for row in result.records])
    assert destination.read_text() == original


def test_interrupted_append_is_rolled_back(tmp_path):
    result = extract_document(write_pdf(tmp_path / "source.pdf", detail_lines()), use_ocr=False)
    destination = tmp_path / "rows.csv"
    ids = [row["record_id"] for row in result.records]
    append_records(result, destination, ids[:1])
    original = destination.read_bytes()
    private, _, journal = _paths(destination)
    journal.write_text(json.dumps({"transaction": "interrupted", "original_size": len(original)}))
    with destination.open("ab") as stream:
        stream.write(b"partial,data,without,a,complete,row")
    assert len(load_records(destination)) == 1
    assert destination.read_bytes() == original
    assert not journal.exists()


def test_committed_append_survives_stale_journal(tmp_path):
    result = extract_document(write_pdf(tmp_path / "source.pdf", detail_lines()), use_ocr=False)
    destination = tmp_path / "rows.csv"
    append_records(result, destination, [row["record_id"] for row in result.records])
    _, manifest, journal = _paths(destination)
    transaction = json.loads(manifest.read_text())["last_transaction"]
    journal.write_text(json.dumps({"transaction": transaction, "original_size": 0}))
    assert len(load_records(destination)) == 2


def test_changed_source_and_invalid_selection_are_rejected(tmp_path):
    source = write_pdf(tmp_path / "source.pdf", detail_lines())
    result = extract_document(source, use_ocr=False)
    with pytest.raises(ValueError, match="do not belong"):
        append_records(result, tmp_path / "rows.csv", ["unknown"])
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        append_records(result, tmp_path / "rows.csv", [row["record_id"] for row in result.records], source_path=source)


def test_manifest_failure_recovers_actual_append(tmp_path, monkeypatch):
    import ocr_ingestion.storage as storage
    result = extract_document(write_pdf(tmp_path / "source.pdf", detail_lines()), use_ocr=False)
    ids = [row["record_id"] for row in result.records]
    destination = tmp_path / "rows.csv"
    append_records(result, destination, ids[:1])
    original = destination.read_bytes()
    atomic = storage._atomic_json

    def fail_manifest(path, obj):
        if path.name == "manifest.json":
            raise OSError("simulated manifest write failure")
        return atomic(path, obj)

    monkeypatch.setattr(storage, "_atomic_json", fail_manifest)
    with pytest.raises(OSError, match="simulated"):
        append_records(result, destination, ids)
    assert len(load_records(destination)) == 1
    assert destination.read_bytes() == original


def test_partial_selections_preserve_evidence_history(tmp_path):
    result = extract_document(write_pdf(tmp_path / "source.pdf", detail_lines()), use_ocr=False)
    ids = [row["record_id"] for row in result.records]
    destination = tmp_path / "rows.csv"
    append_records(result, destination, ids[:1])
    append_records(result, destination, ids[1:])
    private, _, _ = _paths(destination)
    evidence = json.loads((private / "evidence" / f"{result.document_id}.json").read_text())
    assert len(evidence["extractions"]) == 2
    assert evidence["extractions"][0]["records"][0]["record_id"] == ids[0]


@pytest.mark.parametrize("updates", [
    {"reg_rate": "", "ot_rate": "", "dt_rate": ""},
    {"position_original": "", "worker_name": "", "description": ""},
    {"row_type": "material"},
    {"row_type": "table_summary"},
])
def test_append_rejects_unusable_or_nonlabor_rows_without_writing_data(tmp_path, updates):
    result = extract_document(write_pdf(tmp_path / "source.pdf", detail_lines()), use_ocr=False)
    result.records[0].update(updates)
    destination = tmp_path / "rows.csv"
    with pytest.raises(ValueError, match="Only labor rows"):
        append_records(result, destination, [result.records[0]["record_id"]])
    assert not destination.exists()
    private, _, _ = _paths(destination)
    assert not private.exists()


@pytest.mark.parametrize("legacy_type", ["labor_detail", "labor_tally"])
def test_legacy_row_types_load_as_labor_without_changing_ids_or_duplicate_behavior(tmp_path, legacy_type):
    import csv
    from ocr_ingestion.models import FIELDS

    result = extract_document(write_pdf(tmp_path / "source.pdf", detail_lines()), use_ocr=False)
    assert {row["row_type"] for row in result.records} == {"labor"}
    assert result.tables[0].kind == "labor_detail"
    legacy = [{**row, "row_type": legacy_type} for row in result.records]
    destination = tmp_path / "rows.csv"
    with destination.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(legacy)
    before = destination.read_bytes()
    assert load_records(destination) == result.records
    summary = append_records(result, destination, [row["record_id"] for row in result.records])
    assert summary == {"added": 0, "already_present": 2, "total": 2}
    assert destination.read_bytes() == before


def test_new_save_normalizes_legacy_preview_row_types(tmp_path):
    import csv

    result = extract_document(write_pdf(tmp_path / "source.pdf", detail_lines()), use_ocr=False)
    ids = [row["record_id"] for row in result.records]
    for row in result.records:
        row["row_type"] = "labor_detail"
    destination = tmp_path / "rows.csv"
    assert append_records(result, destination, ids)["added"] == 2
    with destination.open() as stream:
        rows = list(csv.DictReader(stream))
    assert {row["row_type"] for row in rows} == {"labor"}
    assert [row["record_id"] for row in rows] == ids
