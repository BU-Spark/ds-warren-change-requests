"""Confirmed contractor display metadata never rewrites original source records."""

from fastapi.testclient import TestClient

from reviewer.api import create_app
from tests.helpers import detail_lines, write_pdf
from tests.test_app import save, upload
from tests.test_row_rate_extraction import summary_lines


def test_library_and_session_expose_confirmed_contractors_without_rewriting_source(
    tmp_path,
):
    with TestClient(create_app(tmp_path)) as client:
        session = upload(
            client,
            write_pdf(tmp_path / "contractor.pdf", summary_lines()[:6]),
            contractor="Packet customer",
        )
        assert save(client, session).status_code == 200
        assert client.get("/api/documents").json()[0]["contractors"] == []
        ids = [r["record_id"] for r in session["extraction"]["records"]]
        original_csv = (tmp_path / "document_line_items.csv").read_bytes()
        assert (
            client.post(
                "/api/records/details",
                json={
                    "records": {
                        ids[0]: {"contractor": "Confirmed employer A"},
                        ids[1]: {"contractor": "Confirmed employer B"},
                    }
                },
            ).status_code
            == 200
        )
        assert client.get("/api/documents").json()[0]["contractors"] == [
            "Confirmed employer A",
            "Confirmed employer B",
        ]
        data = client.get("/api/records").json()
        assert all(r["contractor"] == "" for r in data["records"])
        assert data["details"][ids[0]]["contractor"] == "Confirmed employer A"
        review = client.get(f"/api/sessions/{session['id']}").json()
        assert (
            review["comparison_details"][ids[0]]["contractor"] == "Confirmed employer A"
        )
        assert all(r["contractor"] == "" for r in review["extraction"]["records"])
        assert (tmp_path / "document_line_items.csv").read_bytes() == original_csv


def test_clearing_contractor_override_restores_original_library_name(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        session = upload(
            client,
            write_pdf(tmp_path / "source.pdf", detail_lines()),
            contractor="Original employer",
        )
        save(client, session)
        ids = [r["record_id"] for r in session["extraction"]["records"]]
        assert client.get("/api/documents").json()[0]["contractors"] == [
            "Original employer"
        ]
        client.post(
            "/api/records/details",
            json={"records": {i: {"contractor": "Reviewed employer"} for i in ids}},
        )
        assert client.get("/api/documents").json()[0]["contractors"] == [
            "Reviewed employer"
        ]
        client.put(f"/api/records/{ids[0]}/details", json={"contractor": ""})
        assert client.get("/api/documents").json()[0]["contractors"] == [
            "Original employer",
            "Reviewed employer",
        ]
        client.put(f"/api/records/{ids[1]}/details", json={"contractor": ""})
        assert client.get("/api/documents").json()[0]["contractors"] == [
            "Original employer"
        ]
        assert all(
            r["contractor"] == "Original employer"
            for r in client.get("/api/records").json()["records"]
        )
