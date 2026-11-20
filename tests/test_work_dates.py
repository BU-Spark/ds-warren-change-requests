"""Synthetic work-period assignment at upload, page and individual-row scope."""

import pymupdf
import pytest
from fastapi.testclient import TestClient

from reviewer.api import create_app
from tests.helpers import detail_lines
from tests.test_app import save, upload
from tests.test_checker import reference_bytes


def source(path):
    with pymupdf.open() as pdf:
        for dated in (True, False):
            page = pdf.new_page(width=820, height=600)
            for y, cells in detail_lines():
                for x, text in cells:
                    if not dated and y != 100 and x == 20:
                        continue
                    page.insert_text((x, y), text, fontsize=8, fontname="cour")
        pdf.save(path)
    return path


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "labor_rates_fa.csv").write_bytes(reference_bytes())
    with TestClient(create_app(tmp_path)) as client:
        session = upload(client, source(tmp_path / "work-period.pdf"))
        yield client, session


def change(client, session, **values):
    return client.post(
        f"/api/sessions/{session['id']}/work-dates",
        json={
            "revision": session["revision"],
            "scope": "document",
            "work_start": "2026-02-01",
            "work_end": "2026-02-10",
            **values,
        },
    )


def test_upload_dates_fill_missing_preserve_printed_and_survive_save(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        session = upload(
            client,
            source(tmp_path / "upload.pdf"),
            work_start="2026-02-01",
            work_end="2026-02-10",
        )
        records = session["extraction"]["records"]
        assert len(records) == 4
        assert len(session["comparison_details"]) == 2
        for row in records:
            if row["source_page"] == "1":
                assert row["work_start"] == "2026-01-02"
                assert row["record_id"] not in session["comparison_details"]
            else:
                assert row["work_start"] == ""
                assert (
                    session["comparison_details"][row["record_id"]]["work_end"]
                    == "2026-02-10"
                )
        assert save(client, session).status_code == 200
        saved = client.get("/api/records").json()
        assert sum(not row["work_start"] for row in saved["records"]) == 2
        assert len(saved["details"]) == 2
        # Reuploading the same bytes with another default must not replace earlier entries.
        again = upload(
            client,
            tmp_path / "upload.pdf",
            work_start="2026-03-01",
            work_end="2026-03-10",
        )
        assert all(
            d["work_start"] == "2026-02-01"
            for d in again["comparison_details"].values()
        )


def test_skipping_dates_keeps_missing_work_needs_review(workspace):
    client, session = workspace
    assert session["comparison_details"] == {}
    save(client, session)
    ids = [r["record_id"] for r in session["extraction"]["records"]]
    check = client.post("/api/checks", json={"record_ids": ids}).json()
    assert check["counts"]["needs_review"] == 2
    assert all(
        f["reason"] == "Confirm the dates when the work occurred."
        for f in check["results"]
        if f["outcome"] == "needs_review"
    )


def test_page_and_row_dates_preserve_details_and_can_be_removed(workspace):
    client, session = workspace
    rows = session["extraction"]["records"]
    page_two = [r for r in rows if r["source_page"] == "2"]
    assert change(client, session, scope="page", page=2).json() == {
        "updated": 2,
        "targeted": 2,
    }
    assert save(client, session).status_code == 200
    first = page_two[0]["record_id"]
    client.put(
        f"/api/records/{first}/details",
        json={
            "contractor": "Other contractor",
            "classification": "Foreperson",
            "work_start": "2026-02-01",
            "work_end": "2026-02-10",
        },
    )
    assert (
        change(
            client,
            session,
            scope="rows",
            record_ids=[first],
            only_missing=False,
            work_start="2026-02-05",
            work_end="2026-02-05",
        ).json()["updated"]
        == 1
    )
    details = client.get("/api/records").json()["details"]
    assert details[first]["classification"] == "Foreperson"
    assert details[first]["contractor"] == "Other contractor"
    assert details[first]["work_start"] == "2026-02-05"
    assert details[page_two[1]["record_id"]]["work_end"] == "2026-02-10"
    assert (
        change(client, session, scope="rows", record_ids=[first], clear=True).json()[
            "updated"
        ]
        == 1
    )
    details = client.get("/api/records").json()["details"][first]
    assert "work_start" not in details and details["classification"] == "Foreperson"
    original = client.get(f"/api/sessions/{session['id']}/evidence").json()["records"]
    assert original == rows


def test_replace_all_saved_document_dates_marks_checks_outdated(workspace):
    client, session = workspace
    save(client, session)
    ids = [r["record_id"] for r in session["extraction"]["records"]]
    old = client.post("/api/checks", json={"record_ids": ids}).json()
    document = session["extraction"]["document_id"]
    path = f"/api/documents/{document}/work-dates"
    response = client.post(
        path,
        json={
            "scope": "document",
            "work_start": "2026-04-01",
            "work_end": "2026-04-10",
            "only_missing": False,
        },
    )
    assert response.json() == {"updated": 4, "targeted": 4}
    assert client.get("/api/checks").json()[0]["stale"]
    assert old["results"] == client.get("/api/checks").json()[0]["results"]
    new = client.post("/api/checks", json={"record_ids": ids}).json()
    assert new["counts"] == {"match": 4, "difference": 0, "needs_review": 0}
    assert all(f["work_start"] == "2026-04-01" for f in new["results"])
    assert (
        client.post(path, json={"scope": "document", "clear": True}).json()["updated"]
        == 4
    )
    raw = client.get("/api/records").json()
    assert all(not d.get("work_start") for d in raw["details"].values())
    assert sum(bool(r["work_start"]) for r in raw["records"]) == 2


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-01-01", ""),
        ("", "2026-01-01"),
        ("2026-02-30", "2026-03-01"),
        ("2026-05-01", "2026-04-01"),
    ],
)
def test_invalid_ranges_are_rejected_before_any_changes(workspace, start, end):
    client, session = workspace
    assert change(client, session, work_start=start, work_end=end).status_code == 400
    assert (
        client.get(f"/api/sessions/{session['id']}").json()["comparison_details"] == {}
    )
    response = client.post(
        "/api/sessions",
        files={"file": ("invalid.pdf", b"unused")},
        data={
            "project": "Test",
            "contractor": "Test",
            "work_start": start,
            "work_end": end,
        },
    )
    assert response.status_code == 400
    assert len(client.get("/api/sessions").json()) == 1


def test_scope_validation_and_stale_revision(workspace):
    client, session = workspace
    assert change(client, session, scope="page", page=99).status_code == 400
    assert change(client, session, scope="page").status_code == 400
    assert (
        change(client, session, scope="rows", record_ids=["unknown"]).status_code == 400
    )
    assert change(client, session, revision=-1).status_code == 409
    assert (
        change(
            client, session, scope="document", work_start="", work_end=""
        ).status_code
        == 400
    )
    assert (
        client.get(f"/api/sessions/{session['id']}").json()["comparison_details"] == {}
    )


def test_dates_survive_restart_and_deletion_clears_unsaved_entries(workspace, tmp_path):
    client, session = workspace
    assert change(client, session).json()["updated"] == 2
    with TestClient(create_app(tmp_path)) as restarted:
        assert (
            len(
                restarted.get(f"/api/sessions/{session['id']}").json()[
                    "comparison_details"
                ]
            )
            == 2
        )
        path = f"/api/sessions/{session['id']}"
        preview = restarted.get(path + "/deletion-preview").json()
        assert (
            restarted.request(
                "DELETE", path, json={"confirmation": preview["confirmation"]}
            ).status_code
            == 200
        )
        assert restarted.app.state.store.list("detail") == []
        again = upload(restarted, tmp_path / "work-period.pdf")
        assert again["comparison_details"] == {}
