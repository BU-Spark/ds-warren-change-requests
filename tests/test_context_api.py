from fastapi.testclient import TestClient

from reviewer.api import create_app
from tests.helpers import acme_lines, write_pdf, write_review_pdf
from tests.test_app import save, upload
from tests.test_checker import reference_bytes, schedule


def test_table_context_is_scoped_preserves_source_and_rejects_invalid_dates(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        session = upload(client, write_review_pdf(tmp_path / "mixed.pdf"))
        assert save(client, session).status_code == 200
        rows = client.get("/api/records").json()["records"]
        before = (tmp_path / "document_line_items.csv").read_bytes()
        body = {
            "document_id": rows[0]["document_id"],
            "table_id": rows[0]["table_id"],
            "contractor": "Confirmed submitting company",
            "work_start": "2026-01-03",
            "work_end": "2026-01-03",
            "context_evidence": "Table heading and ticket 1000-1001, page 1.",
        }
        assert (
            client.post(
                "/api/records/table-context", json={**body, "work_end": "2025-01-01"}
            ).status_code
            == 400
        )
        assert client.get("/api/records").json()["details"] == {}
        response = client.post("/api/records/table-context", json=body)
        assert response.status_code == 200
        selected = {r["record_id"] for r in rows if r["table_id"] == body["table_id"]}
        assert set(response.json()) == selected and len(selected) < len(rows)
        assert set(client.get("/api/records").json()["details"]) == selected
        assert (tmp_path / "document_line_items.csv").read_bytes() == before
        assert (
            client.post(
                "/api/records/table-context", json={**body, "context_evidence": " "}
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/records/table-context", json={**body, "document_id": "missing"}
            ).status_code
            == 404
        )


def test_confirmation_requires_evidence_survives_old_clients_and_is_versioned(tmp_path):
    (tmp_path / "labor_rates_fa.csv").write_bytes(reference_bytes())
    with TestClient(create_app(tmp_path)) as client:
        session = upload(client, write_pdf(tmp_path / "generic.pdf", acme_lines()))
        save(client, session)
        row = session["extraction"]["records"][1]
        identifier = row["record_id"]
        route = f"/api/records/{identifier}/details"
        original = (tmp_path / "document_line_items.csv").read_bytes()
        old = client.post("/api/checks", json={"record_ids": [identifier]}).json()
        assert old["counts"]["needs_review"] == 1
        assert client.put(route, json={"confirmed_pay_basis": "OT"}).status_code == 400
        assert (
            client.put(
                route,
                json={
                    "classification": "Carpenter",
                    "confirmed_pay_basis": "OT",
                    "pay_basis_evidence": "Agreement section 4: full OT rate.",
                },
            ).status_code
            == 200
        )
        assert (
            client.put(route, json={"classification": "Carpenter"}).status_code == 200
        )
        details = client.get("/api/records").json()["details"][identifier]
        assert details["confirmed_pay_basis"] == "OT" and details["pay_basis_evidence"]
        new = client.post("/api/checks", json={"record_ids": [identifier]}).json()
        assert new["counts"]["match"] == 1
        assert new["results"][0]["rate_type"] == "OT"
        assert any(
            r["id"] == old["id"] and r["stale"]
            for r in client.get("/api/checks").json()
        )
        assert (
            client.put(
                route,
                json={
                    "classification": "Carpenter",
                    "work_start": "2026-02-01",
                    "work_end": "2026-02-01",
                },
            ).status_code
            == 200
        )
        assert (
            client.get("/api/records").json()["details"][identifier][
                "confirmed_pay_basis"
            ]
            == ""
        )
        assert (
            client.put(
                route, json={"confirmed_pay_basis": "", "pay_basis_evidence": ""}
            ).status_code
            == 200
        )
        assert (
            client.post("/api/checks", json={"record_ids": [identifier]}).json()[
                "counts"
            ]["needs_review"]
            == 1
        )
        assert (tmp_path / "document_line_items.csv").read_bytes() == original


def test_conflict_endpoint_also_works_for_stored_reference_versions(tmp_path):
    (tmp_path / "labor_rates_fa.csv").write_bytes(
        reference_bytes(
            [schedule(), schedule(source_csv_row_number="3", reg_rate="11")]
        )
    )
    with TestClient(create_app(tmp_path)) as client:
        ref = client.get("/api/reference").json()["active"]
        audit = client.get(f"/api/reference/{ref['id']}/conflicts").json()
        assert audit["conflicts"][0]["reference_rows"] == ["2", "3"]
        assert (
            client.get(f"/api/reference/{ref['id']}/source").content
            == (tmp_path / "labor_rates_fa.csv").read_bytes()
        )
