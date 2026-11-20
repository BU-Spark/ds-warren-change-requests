"""Synthetic document lifecycle, storage recovery, and deletion-race regressions."""

import threading

import pytest
from fastapi.testclient import TestClient

from ocr_ingestion import append_records, extract_document, load_records, storage
from reviewer.api import create_app
from tests.helpers import detail_lines, write_pdf
from tests.test_app import save, upload
from tests.test_checker import reference_bytes


@pytest.fixture
def client(tmp_path):
    (tmp_path / "labor_rates_fa.csv").write_bytes(reference_bytes())
    with TestClient(create_app(tmp_path)) as connection:
        yield connection


def make_document(folder, name="first.pdf", reference="AD0001"):
    return write_pdf(folder / name, [(50, [(20, reference)]), *detail_lines()])


def delete(client, path):
    preview = client.get(path + "/deletion-preview")
    assert preview.status_code == 200, preview.text
    return client.request(
        "DELETE", path, json={"confirmation": preview.json()["confirmation"]}
    )


def test_saved_library_partial_and_complete_documents(client, tmp_path):
    session = upload(client, make_document(tmp_path))
    assert client.get("/api/documents").json() == []
    ids = [r["record_id"] for r in session["extraction"]["records"]]
    assert save(client, session, ids[:1]).status_code == 200
    document = client.get("/api/documents").json()[0]
    assert document["status"] == "partially_saved" and document["unsaved_rows"] == 1
    assert save(client, session).status_code == 200
    document = client.get("/api/documents").json()[0]
    assert document["status"] == "saved" and document["saved_rows"] == 2
    assert document["session_id"] == session["id"]


def test_delete_saved_source_removes_aliases_rates_details_and_affected_runs(
    client, tmp_path
):
    first = upload(client, make_document(tmp_path))
    second = upload(client, make_document(tmp_path, "second.pdf", "AD0002"))
    save(client, first)
    save(client, second)
    alias = upload(client, tmp_path / "first.pdf")
    first_rows, second_rows = (
        first["extraction"]["records"],
        second["extraction"]["records"],
    )
    updates = {
        r["record_id"]: {"classification": "Carpenter"}
        for r in first_rows + second_rows
    }
    assert (
        client.post("/api/records/details", json={"records": updates}).status_code
        == 200
    )
    check = client.post("/api/checks", json={"record_ids": list(updates)})
    assert check.status_code == 200
    document_id = first["extraction"]["document_id"]
    preview = client.get(f"/api/documents/{document_id}/deletion-preview").json()
    assert preview["saved_rows"] == 2 and preview["uploads"] == 2
    assert preview["check_runs"] == preview["shared_runs"] == 1
    response = delete(client, f"/api/documents/{document_id}")
    assert response.status_code == 200, response.text
    assert client.get(f"/api/sessions/{first['id']}").status_code == 404
    assert client.get(f"/api/sessions/{alias['id']}").status_code == 404
    assert client.get(f"/api/sessions/{second['id']}").status_code == 200
    records = client.get("/api/records").json()
    assert {r["record_id"] for r in records["records"]} == {
        r["record_id"] for r in second_rows
    }
    assert set(records["details"]) == {r["record_id"] for r in second_rows}
    assert client.get("/api/checks").json() == []
    assert client.get(f"/api/documents/{document_id}/pages/1").status_code == 404
    assert (
        client.get(
            f"/api/documents/{second['extraction']['document_id']}/pages/1"
        ).status_code
        == 200
    )
    private = tmp_path / "document_line_items_private"
    assert not (private / "evidence" / f"{document_id}.json").exists()
    assert document_id not in (private / "manifest.json").read_text()
    assert client.get("/api/reference").json()["active"] is not None
    restarted = upload(client, tmp_path / "first.pdf")
    assert save(client, restarted).json()["added"] == 2


def test_delete_requires_current_confirmation(client, tmp_path):
    session = upload(client, make_document(tmp_path))
    endpoint = f"/api/sessions/{session['id']}"
    assert client.request("DELETE", endpoint).status_code == 422
    preview = client.get(endpoint + "/deletion-preview").json()
    save(client, session)
    assert (
        client.request(
            "DELETE", endpoint, json={"confirmation": preview["confirmation"]}
        ).status_code
        == 409
    )
    assert len(client.get("/api/records").json()["records"]) == 2


def test_failed_upload_can_be_deleted_and_invalid_identity_is_rejected(
    client, tmp_path
):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"synthetic invalid PDF")
    session = upload(client, path)
    assert session["status"] == "failed"
    assert delete(client, f"/api/sessions/{session['id']}").status_code == 200
    assert client.get("/api/sessions").json() == []
    assert client.get("/api/documents/not-a-hash/deletion-preview").status_code == 404


def test_finishing_worker_cannot_resurrect_deleted_document(
    client, tmp_path, monkeypatch
):
    from reviewer import api

    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = api.extract_document

    def blocked(*args, **kwargs):
        result = original(*args, **kwargs)
        started.set()
        release.wait(10)
        finished.set()
        return result

    monkeypatch.setattr(api, "extract_document", blocked)
    path = make_document(tmp_path)
    response = client.post(
        "/api/sessions",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"project": "Synthetic", "contractor": "Example Contractor"},
    )
    identifier = response.json()["id"]
    try:
        assert started.wait(3)
        assert delete(client, f"/api/sessions/{identifier}").status_code == 200
    finally:
        release.set()
    assert finished.wait(3)
    assert client.get(f"/api/sessions/{identifier}").status_code == 404
    assert client.get("/api/sessions").json() == []


def test_confirmed_deletion_recovers_after_restart(tmp_path, monkeypatch):
    from reviewer import document_lifecycle

    with TestClient(create_app(tmp_path)) as client:
        session = upload(client, make_document(tmp_path))
        save(client, session)
        original = document_lifecycle.delete_document
        monkeypatch.setattr(
            document_lifecycle,
            "delete_document",
            lambda *a: (_ for _ in ()).throw(OSError("synthetic interrupted deletion")),
        )
        assert delete(client, f"/api/sessions/{session['id']}").status_code == 503
        assert client.app.state.store.list("document_deletion")
        monkeypatch.setattr(document_lifecycle, "delete_document", original)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/sessions").json() == []
        assert client.get("/api/records").json()["records"] == []
        assert client.app.state.store.list("document_deletion") == []


def test_legacy_saved_document_without_session_can_restart(client, tmp_path):
    path = make_document(tmp_path)
    extraction = extract_document(path, contractor="Example Contractor", use_ocr=False)
    append_records(
        extraction,
        tmp_path / "document_line_items.csv",
        [r["record_id"] for r in extraction.records],
        source_path=path,
    )
    document = client.get("/api/documents").json()[0]
    assert document["session_id"] is None and document["status"] == "saved"
    assert (
        client.get(f"/api/documents/{extraction.document_id}/source-info").json()[
            "page_count"
        ]
        == 1
    )
    assert delete(client, f"/api/documents/{extraction.document_id}").status_code == 200
    assert path.exists()
    assert client.get("/api/documents").json() == []


def test_deletion_rejects_unmanaged_source_path_before_changing_data(client, tmp_path):
    session = upload(client, make_document(tmp_path))
    save(client, session)
    store = client.app.state.store
    stored = store.get("session", session["id"])
    stored["path"] = str(tmp_path / "first.pdf")
    store.put("session", session["id"], stored)
    assert (
        client.get(f"/api/sessions/{session['id']}/deletion-preview").status_code == 400
    )
    assert len(client.get("/api/records").json()["records"]) == 2
    assert store.list("document_deletion") == []


def test_same_filename_different_source_identities_are_not_deleted_together(
    client, tmp_path
):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    first = upload(client, make_document(tmp_path / "one", "document.pdf", "AD0001"))
    second = upload(client, make_document(tmp_path / "two", "document.pdf", "AD0002"))
    save(client, first)
    save(client, second)
    assert len(client.get("/api/documents").json()) == 2
    assert (
        delete(
            client, f"/api/documents/{first['extraction']['document_id']}"
        ).status_code
        == 200
    )
    remaining = client.get("/api/documents").json()
    assert (
        len(remaining) == 1
        and remaining[0]["document_id"] == second["extraction"]["document_id"]
    )


def stored_sources(tmp_path):
    csv = tmp_path / "accepted.csv"
    extractions = []
    for index in (1, 2):
        path = make_document(tmp_path, f"source-{index}.pdf", f"AD000{index}")
        extraction = extract_document(path, use_ocr=False)
        append_records(
            extraction,
            csv,
            [r["record_id"] for r in extraction.records],
            source_path=path,
        )
        extractions.append(extraction)
    return csv, extractions


def test_csv_delete_failure_restores_exact_bytes_and_other_sources(
    tmp_path, monkeypatch
):
    csv, extractions = stored_sources(tmp_path)
    before = csv.read_bytes()
    original = storage._atomic_json

    def fail_manifest(path, value):
        if path.name == "manifest.json":
            raise OSError("synthetic manifest failure")
        original(path, value)

    monkeypatch.setattr(storage, "_atomic_json", fail_manifest)
    with pytest.raises(OSError):
        storage.delete_document(csv, extractions[0].document_id)
    assert len(load_records(csv)) == 4
    assert csv.read_bytes() == before
    private = storage._paths(csv)[0]
    assert (private / "originals" / f"{extractions[0].document_id}.pdf").exists()


def test_committed_csv_deletion_finishes_artifact_cleanup_after_interruption(
    tmp_path, monkeypatch
):
    csv, extractions = stored_sources(tmp_path)
    original = storage._purge_document_artifacts
    monkeypatch.setattr(
        storage,
        "_purge_document_artifacts",
        lambda *a: (_ for _ in ()).throw(OSError("synthetic cleanup failure")),
    )
    with pytest.raises(OSError):
        storage.delete_document(csv, extractions[0].document_id)
    monkeypatch.setattr(storage, "_purge_document_artifacts", original)
    rows = load_records(csv)
    assert len(rows) == 2 and all(
        r["document_id"] == extractions[1].document_id for r in rows
    )
    private = storage._paths(csv)[0]
    assert not (private / "originals" / f"{extractions[0].document_id}.pdf").exists()
    assert (private / "originals" / f"{extractions[1].document_id}.pdf").exists()
