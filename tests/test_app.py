"""API regression tests replace the retired Streamlit interface tests."""

import csv
import io
import time

import pytest
from fastapi.testclient import TestClient

from ocr_ingestion import load_records
from reviewer.api import create_app
from tests.helpers import acme_lines, detail_lines, write_pdf
from tests.test_checker import reference_bytes, schedule


@pytest.fixture
def client(tmp_path):
    (tmp_path / "labor_rates_fa.csv").write_bytes(reference_bytes())
    with TestClient(create_app(tmp_path)) as client:
        yield client


def upload(client, source, **metadata):
    response = client.post(
        "/api/sessions",
        files={"file": (source.name, source.read_bytes(), "application/pdf")},
        data={
            "project": "Example project",
            "contractor": "Example Contractor",
            "use_ocr": "false",
            **metadata,
        },
    )
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    for _ in range(100):
        result = client.get(f"/api/sessions/{identifier}").json()
        if result["status"] not in {"queued", "processing"}:
            return result
        time.sleep(0.02)
    pytest.fail("Extraction did not finish")


def save(client, session, ids=None, **updates):
    body = {
        "record_ids": ids or [r["record_id"] for r in session["extraction"]["records"]],
        "revision": session["revision"],
        "reviewed": session["review_tokens"],
        **updates,
    }
    return client.post(f"/api/sessions/{session['id']}/save", json=body)


def test_document_review_save_compare_and_source_evidence(client, tmp_path):
    session = upload(client, write_pdf(tmp_path / "example.pdf", detail_lines()))
    assert session["status"] == "ready"
    assert len(session["extraction"]["records"]) == 2
    assert "path" not in session
    assert save(client, session).json()["added"] == 2
    assert save(client, session).json()["already_present"] == 2
    saved = client.get("/api/records").json()["records"]
    assert all(len(r["record_id"]) == 64 for r in saved)
    assert all(
        r["project"] == "Example project" and r["contractor"] == "Example Contractor"
        for r in saved
    )
    check = client.post(
        "/api/checks", json={"record_ids": [r["record_id"] for r in saved]}
    ).json()
    assert check["counts"] == {"match": 2, "difference": 0, "needs_review": 0}
    assert (
        client.get(f"/api/sessions/{session['id']}/pages/1").headers["content-type"]
        == "image/png"
    )
    assert (
        client.get(f"/api/documents/{saved[0]['document_id']}/pages/1").status_code
        == 200
    )
    assert client.get(f"/api/sessions/{session['id']}/pages/100").status_code == 404
    evidence = client.get(f"/api/sessions/{session['id']}/evidence")
    assert evidence.json()["records"][0]["record_id"] == saved[0]["record_id"]
    assert "attachment" in evidence.headers["content-disposition"]
    assert client.get("/api/checks").json()[0]["id"] == check["id"]


def test_missing_metadata_invalid_file_and_unknown_api(client, tmp_path):
    source = write_pdf(tmp_path / "example.pdf", detail_lines())
    for field in ["project", "contractor"]:
        response = client.post(
            "/api/sessions",
            files={"file": ("example.pdf", source.read_bytes())},
            data={"project": "Example", "contractor": "Example", field: "   "},
        )
        assert response.status_code == 400
    assert (
        client.post(
            "/api/sessions",
            files={"file": ("wrong.zip", b"bad")},
            data={"project": "Example", "contractor": "Example"},
        ).status_code
        == 400
    )
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/api/sessions/missing").status_code == 404
    failed = upload(client, tmp_path / "example.pdf")
    assert failed["status"] == "ready"
    empty = client.post(
        "/api/sessions",
        files={"file": ("empty.pdf", b"")},
        data={"project": "Example", "contractor": "Example"},
    )
    assert empty.status_code == 400
    (tmp_path / "invalid.pdf").write_bytes(b"not a PDF")
    assert upload(client, tmp_path / "invalid.pdf")["status"] == "failed"


def test_stale_revision_and_forged_selection_rejected(client, tmp_path):
    session = upload(client, write_pdf(tmp_path / "example.pdf", detail_lines()))
    assert save(client, session, revision=0).status_code == 409
    assert save(client, session, ids=["not-in-this-extraction"]).status_code == 400
    assert not load_records(tmp_path / "document_line_items.csv")


def test_review_tokens_are_enforced_by_backend(client, tmp_path):
    source = write_pdf(
        tmp_path / "example.pdf",
        detail_lines(),
        overlays=[(470, 120, "12.00", (1, 0, 0), "hebo")],
    )
    session = upload(client, source)
    assert session["review_tokens"]
    assert save(client, session, reviewed={}).status_code == 400
    assert (
        save(
            client, session, reviewed={k: "forged" for k in session["review_tokens"]}
        ).status_code
        == 400
    )
    assert save(client, session).status_code == 200


def test_generic_labor_comparison_details_and_staleness(client, tmp_path):
    session = upload(client, write_pdf(tmp_path / "labor.pdf", acme_lines()))
    save(client, session)
    records = client.get("/api/records").json()["records"]
    ids = [r["record_id"] for r in records]
    original = (tmp_path / "document_line_items.csv").read_bytes()
    first = client.post("/api/checks", json={"record_ids": ids}).json()
    assert first["counts"] == {"match": 2, "difference": 1, "needs_review": 0}
    assert all(r["match_method"] == "contractor_rate" for r in first["results"])
    for identifier in ids:
        response = client.put(
            f"/api/records/{identifier}/details", json={"classification": "Carpenter"}
        )
        assert response.status_code == 200
    second = client.post("/api/checks", json={"record_ids": ids}).json()
    assert second["counts"] == {"match": 2, "difference": 1, "needs_review": 0}
    assert (tmp_path / "document_line_items.csv").read_bytes() == original
    runs = client.get("/api/checks").json()
    assert runs[0]["stale"] is False and runs[1]["stale"] is True
    export = client.get(f"/api/checks/{second['id']}/differences.csv")
    rows = list(csv.DictReader(io.StringIO(export.text)))
    assert (
        len(rows) == 1
        and rows[0]["rate_type"] == "REG"
        and rows[0]["difference_per_hour"] == "5.00"
    )
    assert (
        client.put(
            f"/api/records/{ids[0]}/details", json={"work_start": "invalid"}
        ).status_code
        == 400
    )


def test_reference_preview_activation_and_immutable_history(client, tmp_path):
    session = upload(client, write_pdf(tmp_path / "example.pdf", detail_lines()))
    save(client, session)
    ids = [r["record_id"] for r in session["extraction"]["records"]]
    first = client.post("/api/checks", json={"record_ids": ids}).json()
    initial = client.get("/api/reference").json()["active"]
    contents = reference_bytes([schedule(reg_rate="9.00")])
    preview = client.post(
        "/api/reference/preview", files={"file": ("new.csv", contents)}
    ).json()
    assert client.get("/api/reference").json()["active"]["id"] == initial["id"]
    assert (
        client.post(
            "/api/reference/activate", json={"reference_id": preview["id"]}
        ).status_code
        == 200
    )
    assert client.get("/api/checks").json()[0]["stale"] is True
    assert client.get("/api/checks").json()[0]["results"] == first["results"]
    second = client.post("/api/checks", json={"record_ids": ids}).json()
    assert second["counts"]["difference"] == 2
    assert (tmp_path / "labor_rates_fa.csv").read_bytes() == reference_bytes()
    assert (
        client.post(
            "/api/reference/preview", files={"file": ("bad.csv", b"bad,header\n1,2")}
        ).status_code
        == 400
    )


def test_renamed_partial_upload_and_saved_data_schema_errors(client, tmp_path):
    source = write_pdf(tmp_path / "example.pdf", detail_lines())
    session = upload(client, source)
    first_id = session["extraction"]["records"][0]["record_id"]
    assert save(client, session, ids=[first_id]).json()["added"] == 1
    renamed = tmp_path / "renamed.pdf"
    renamed.write_bytes(source.read_bytes())
    second = upload(client, renamed)
    assert save(client, second).json() == {"added": 1, "already_present": 1, "total": 2}
    (tmp_path / "document_line_items.csv").write_text("wrong,columns\n1,2\n")
    response = client.get("/api/records")
    assert (
        response.status_code == 400
        and "incompatible schema" in response.json()["detail"]
    )


def test_source_and_request_boundaries(client):
    assert client.get("/api/documents/not-a-hash/pages/1").status_code == 404
    assert (
        client.post("/api/checks", json={"record_ids": ["unknown"]}).status_code == 400
    )
    assert client.post("/api/checks", json={"record_ids": []}).status_code == 422
    assert (
        client.post(
            "/api/checks",
            json={"record_ids": ["unknown"]},
            headers={"Origin": "https://unrelated.example"},
        ).status_code
        == 403
    )
    assert (
        client.get("/api/records", headers={"Host": "unrelated.example"}).status_code
        == 400
    )
    assert client.get("/api/records").headers["cache-control"] == "no-store"


def test_sessions_and_checks_survive_server_restart(tmp_path):
    (tmp_path / "labor_rates_fa.csv").write_bytes(reference_bytes())
    source = write_pdf(tmp_path / "example.pdf", detail_lines())
    with TestClient(create_app(tmp_path)) as first:
        session = upload(first, source)
        save(first, session)
        result = first.post(
            "/api/checks",
            json={
                "record_ids": [r["record_id"] for r in session["extraction"]["records"]]
            },
        ).json()
    with TestClient(create_app(tmp_path)) as second:
        assert second.get(f"/api/sessions/{session['id']}").json()["status"] == "ready"
        assert second.get("/api/checks").json()[0]["id"] == result["id"]
        state = second.app.state.store
        state.put(
            "session", "interrupted", {"id": "interrupted", "status": "processing"}
        )
    with TestClient(create_app(tmp_path)) as third:
        interrupted = third.get("/api/sessions/interrupted").json()
        assert (
            interrupted["status"] == "failed" and "interrupted" in interrupted["error"]
        )


def test_bulk_comparison_details_commit_atomically(client, tmp_path):
    session = upload(client, write_pdf(tmp_path / "example.pdf", detail_lines()))
    save(client, session)
    ids = [r["record_id"] for r in session["extraction"]["records"]]
    before = (tmp_path / "document_line_items.csv").read_bytes()
    response = client.post(
        "/api/records/details",
        json={
            "records": {
                ids[0]: {"contractor": "Another Contractor"},
                ids[1]: {"work_start": "not-a-date"},
            }
        },
    )
    assert response.status_code == 400
    assert client.get("/api/records").json()["details"] == {}
    response = client.post(
        "/api/records/details",
        json={
            "records": {
                identifier: {"contractor": "Confirmed Contractor"} for identifier in ids
            }
        },
    )
    assert response.status_code == 200
    assert all(
        v["contractor"] == "Confirmed Contractor"
        for v in client.get("/api/records").json()["details"].values()
    )
    assert (tmp_path / "document_line_items.csv").read_bytes() == before


def test_mapping_invalidates_previous_confirmation_tokens(client, tmp_path):
    from ocr_ingestion.models import Extraction, Table

    store = client.app.state.store
    source = write_pdf(tmp_path / "unknown.pdf", detail_lines())
    import hashlib

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    table = Table(
        "p1-grid0",
        1,
        "unfamiliar",
        ["Trade", "Rate"],
        [["Carpenter", "11.00"]],
        [0, 0, 800, 200],
        "native",
        True,
    )
    result = Extraction(digest, source.name, tables=[table])
    store.put(
        "session",
        "mapping",
        {
            "id": "mapping",
            "filename": source.name,
            "project": "Example project",
            "contractor": "Example Contractor",
            "status": "ready",
            "path": str(source),
            "revision": 1,
            "extraction": result.evidence(),
        },
    )
    first = client.put(
        "/api/sessions/mapping/tables/p1-grid0",
        json={"revision": 1, "columns": {"0": "position_original", "1": "rate"}},
    )
    assert first.status_code == 200
    second = client.put(
        "/api/sessions/mapping/tables/p1-grid0",
        json={"revision": 2, "columns": {"0": "description", "1": "reg_rate"}},
    )
    assert second.status_code == 200
    first_body, second_body = first.json(), second.json()
    assert first_body["review_tokens"] != second_body["review_tokens"]
    assert save(client, first_body).status_code == 409
    assert (
        save(client, second_body, reviewed=first_body["review_tokens"]).status_code
        == 400
    )
    assert save(client, second_body).json()["added"] == 1
    record = load_records(tmp_path / "document_line_items.csv")[0]
    assert record["reg_rate"] == "11.00" and record["rate"] == ""
    assert record["contractor"] == "Example Contractor"


def test_original_reference_csv_evidence_is_retained(client):
    active = client.get("/api/reference").json()["active"]
    response = client.get(f"/api/reference/{active['id']}/source")
    assert response.status_code == 200 and response.content == reference_bytes()
    contents = reference_bytes([schedule(reg_rate="12.00")])
    replacement = client.post(
        "/api/reference/preview", files={"file": ("replacement.csv", contents)}
    ).json()
    client.post("/api/reference/activate", json={"reference_id": replacement["id"]})
    assert (
        client.get(f"/api/reference/{active['id']}/source").content == reference_bytes()
    )
    assert client.get(f"/api/reference/{replacement['id']}/source").content == contents


def test_ocr_is_automatic_and_old_preferences_cannot_disable_it(client, tmp_path):
    client.app.state.store.put("setting", "user_settings", {"ocr_enabled": False})
    source = write_pdf(tmp_path / "example.pdf", detail_lines())
    session = upload(client, source, use_ocr="false")
    assert session["use_ocr"] is True
    assert session["status"] == "ready"
    assert client.get("/api/settings").status_code == 404
    assert client.put("/api/settings", json={"ocr_enabled": False}).status_code == 404
    assert client.get("/").headers["cache-control"] == "no-store"


def test_review_queue_progress_persists_and_distinguishes_saved_rows(client, tmp_path):
    from tests.helpers import write_review_pdf

    session = upload(client, write_review_pdf(tmp_path / "review.pdf"))
    summary = session["review_summary"]
    assert summary["status"] == "needs_review" and summary["pending_tables"] == 3
    assert [item["page"] for item in summary["items"]] == [2, 2, 3, 1]
    first = summary["items"][0]["table_id"]
    reviewed = {first: session["review_tokens"][first]}
    response = client.put(
        f"/api/sessions/{session['id']}/review",
        json={"revision": session["revision"], "reviewed": reviewed},
    )
    assert response.status_code == 200
    assert response.json()["review_summary"]["pending_tables"] == 2
    assert client.get(f"/api/sessions/{session['id']}").json()["reviewed"] == reviewed
    listed = next(
        s for s in client.get("/api/sessions").json() if s["id"] == session["id"]
    )
    assert listed["review_summary"]["pending_tables"] == 2
    with TestClient(create_app(tmp_path)) as restarted:
        assert (
            restarted.get(f"/api/sessions/{session['id']}").json()["reviewed"]
            == reviewed
        )
    ids = [
        r["record_id"]
        for r in session["extraction"]["records"]
        if r["table_id"] == first
    ]
    assert save(client, session, ids=ids, reviewed=reviewed).status_code == 200
    partial = client.get(f"/api/sessions/{session['id']}").json()["review_summary"]
    assert partial["pending_tables"] == 2 and partial["reviewed_tables"] == 1
    assert (
        next(i for i in partial["items"] if i["table_id"] == first)["status"] == "saved"
    )
    assert save(client, session).status_code == 200
    complete = client.get(f"/api/sessions/{session['id']}").json()["review_summary"]
    assert complete["status"] == "saved" and complete["pending_tables"] == 0
    assert complete["reviewed_tables"] == 3


def test_review_confirmations_can_be_revoked_and_stale_values_rejected(
    client, tmp_path
):
    from tests.helpers import write_review_pdf

    session = upload(client, write_review_pdf(tmp_path / "review.pdf"))
    route = f"/api/sessions/{session['id']}/review"
    assert (
        client.put(
            route, json={"revision": 0, "reviewed": session["review_tokens"]}
        ).status_code
        == 409
    )
    assert (
        client.put(
            route, json={"revision": 1, "reviewed": {"unknown": "token"}}
        ).status_code
        == 409
    )
    assert (
        client.put(
            route, json={"revision": 1, "reviewed": session["review_tokens"]}
        ).json()["review_summary"]["status"]
        == "ready_to_save"
    )
    revoked = client.put(route, json={"revision": 1, "reviewed": {}}).json()
    assert revoked["review_summary"]["pending_tables"] == 3
    assert save(client, session, reviewed={}).status_code == 400


def test_old_rate_type_choices_are_ignored_and_prior_rules_are_outdated(
    client, tmp_path
):
    source = write_pdf(tmp_path / "labor.pdf", acme_lines())
    session = upload(client, source)
    save(client, session)
    ids = [row["record_id"] for row in session["extraction"]["records"]]
    for identifier in ids:
        client.app.state.store.put(
            "detail",
            identifier,
            {
                "record_id": identifier,
                "values": {"classification": "Carpenter", "generic_rate_type": "OT"},
            },
        )
    details = client.get("/api/records").json()["details"]
    assert all("generic_rate_type" not in value for value in details.values())
    result = client.post("/api/checks", json={"record_ids": ids}).json()
    assert all(
        f["rate_type"] == "REG" and f["reference_rate_field"] == "reg_rate"
        for f in result["results"]
    )
    assert result["counts"] == {"match": 2, "difference": 1, "needs_review": 0}
    assert not result["stale"] and not result["rules_changed"]
    legacy = {k: v for k, v in result.items() if k != "checker_version"}
    client.app.state.store.put("run", result["id"], legacy)
    historical = client.get("/api/checks").json()[0]
    assert historical["stale"] and historical["rules_changed"]
    assert historical["results"] == result["results"]


def test_legacy_mixed_run_is_not_rewritten_or_marked_outdated(client, tmp_path):
    from copy import deepcopy

    session = upload(client, write_pdf(tmp_path / "history.pdf", detail_lines()))
    save(client, session)
    ids = [r["record_id"] for r in session["extraction"]["records"]]
    current = client.post("/api/checks", json={"record_ids": ids}).json()
    old = deepcopy(current)
    old["id"] = "legacy-mixed"
    old["results"].append(
        {
            **deepcopy(old["results"][0]),
            "rate_type": "OT",
            "reference_rate_field": "ot_rate",
            "finding_id": "legacy-ot",
        }
    )
    old["counts"]["match"] += 1
    old.pop("skipped_non_regular", None)
    client.app.state.store.put("run", old["id"], old)
    stored = deepcopy(client.app.state.store.get("run", old["id"]))
    history = client.get("/api/checks").json()
    legacy = next(r for r in history if r["id"] == old["id"])
    assert legacy["stale"] is False and legacy["rules_changed"] is False
    assert legacy["results"] == old["results"] and legacy["counts"] == old["counts"]
    assert client.app.state.store.get("run", old["id"]) == stored
