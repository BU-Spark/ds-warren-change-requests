"""Synthetic tests only: no client data or private snapshots."""

from pathlib import Path
import pytest
from ocr_ingestion import append_records, extract_document, load_records
from ocr_ingestion.models import FIELDS
from tests.helpers import write_pdf, detail_lines, acme_lines


def test_upload_app_boots_and_renders_labor_preview(tmp_path, monkeypatch):
    import io
    import streamlit
    import ocr_ingestion
    from streamlit.testing.v1 import AppTest
    source = write_pdf(tmp_path / "source.pdf", detail_lines())
    result = extract_document(source, use_ocr=False)
    uploaded = io.BytesIO(source.read_bytes())
    uploaded.name = source.name
    monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setattr(ocr_ingestion, "load_records", lambda *args: [])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ocr_ingestion/app.py"))
    app.session_state["extraction"] = result
    app.session_state["source_path"] = source
    app.session_state["upload_hash"] = result.document_id
    app.run(timeout=15)
    assert not app.exception
    assert any(button.label == "Add to dataset" for button in app.button)


def test_view_saved_data_search_and_refresh(tmp_path, monkeypatch):
    import streamlit
    import ocr_ingestion
    from streamlit.testing.v1 import AppTest

    source = write_pdf(tmp_path / "source.pdf", detail_lines())
    result = extract_document(source, use_ocr=False)
    destination = tmp_path / "rows.csv"
    ids = [row["record_id"] for row in result.records]
    append_records(result, destination, ids[:1])
    monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(ocr_ingestion, "load_records", lambda *args: load_records(destination))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ocr_ingestion/app.py")).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Upload document", "View data"]
    assert len(app.dataframe[0].value) == 1
    assert app.dataframe[0].value.iloc[0]["reg_rate"] == result.records[0]["reg_rate"]
    search = next(field for field in app.text_input if field.label == "Search saved data")
    search.set_value("nonexistent.[literal]").run()
    assert app.dataframe[0].value.empty
    next(field for field in app.text_input if field.label == "Search saved data").set_value("").run()
    append_records(result, destination, ids)
    next(button for button in app.button if button.label == "Refresh data").click().run()
    assert not app.exception
    assert len(app.dataframe[0].value) == len(ids)
    assert len(load_records(destination)) == len(ids)


@pytest.mark.parametrize("failure", [False, True])
def test_view_saved_data_empty_or_invalid(monkeypatch, failure):
    import streamlit
    import ocr_ingestion
    from streamlit.testing.v1 import AppTest

    def read_dataset(*args):
        if failure:
            raise ValueError("Existing CSV has an incompatible schema; no data was overwritten.")
        return []

    monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(ocr_ingestion, "load_records", read_dataset)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ocr_ingestion/app.py")).run()
    assert not app.exception
    assert not app.dataframe
    if failure:
        assert "incompatible schema" in app.error[0].value
    else:
        assert any("No saved rows yet" in message.value for message in app.info)


def test_client_table_preserves_internal_ids_and_source_descriptions(tmp_path):
    import pandas as pd
    from ocr_ingestion.app import client_table

    result = extract_document(write_pdf(tmp_path / "PR123 - Supplier.pdf", acme_lines()), use_ocr=False)
    rows = pd.DataFrame(result.records, columns=FIELDS)
    original = rows.copy(deep=True)
    display = client_table(rows)
    assert display["project_id"].eq("PR123").all()
    assert display["record_id"].str.len().eq(12).all()
    assert display["description"].equals(rows["description"])
    assert "2 Workers at 4 hours" in display["description"].tolist()
    assert "table_id" not in display and "document_id" not in display
    pd.testing.assert_frame_equal(rows, original)
    pd.testing.assert_frame_equal(client_table(rows, technical=True), original)
    rows.loc[0, "record_id"] = "a" * 12 + "1" * 52
    rows.loc[1, "record_id"] = "a" * 12 + "2" * 52
    display = client_table(rows)
    assert display.loc[0, "record_id"] != display.loc[1, "record_id"]
    assert len(display.loc[0, "record_id"]) == 13


def test_upload_requires_project_and_saves_using_full_ids(tmp_path, monkeypatch):
    import io
    import ocr_ingestion.app as interface
    from streamlit.testing.v1 import AppTest

    source = write_pdf(tmp_path / "PR123 - Supplier.pdf", detail_lines())
    uploaded = io.BytesIO(source.read_bytes())
    uploaded.name = source.name
    monkeypatch.setattr(interface.st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setattr(interface, "PRIVATE", tmp_path / "uploads")
    monkeypatch.setattr(interface, "CSV_PATH", tmp_path / "rows.csv")
    saves = []

    def save(result, destination, selected_ids, **kwargs):
        saves.append((result, selected_ids))
        return {"added": len(selected_ids), "already_present": 0, "total": len(selected_ids)}

    monkeypatch.setattr(interface, "append_records", save)

    def run_app():
        from ocr_ingestion.app import main
        main()

    app = AppTest.from_function(run_app).run()
    next(button for button in app.button if button.label == "Extract tables").click().run()
    assert any("Enter a project name" in error.value for error in app.error)
    assert not saves
    next(field for field in app.text_input if field.label == "Project name (required)").set_value("Example project").run()
    next(button for button in app.button if button.label == "Extract tables").click().run()
    assert not app.exception
    next(button for button in app.button if button.label == "Add to dataset").click().run()
    assert not app.exception
    assert len(saves) == 1
    result, selected_ids = saves[0]
    assert selected_ids == [row["record_id"] for row in result.records]
    assert all(len(identifier) == 64 for identifier in selected_ids)
    assert all(row["project"] == "Example project" for row in result.records)
    next(field for field in app.text_input if field.label == "Project name (required)").set_value("Different project").run()
    assert next(button for button in app.button if button.label == "Add to dataset").disabled


def test_acme_labor_preview_ignores_supporting_tables(tmp_path, monkeypatch):
    import io
    import ocr_ingestion.app as interface
    from streamlit.testing.v1 import AppTest

    labor = acme_lines()
    supporting = [(y + 150, cells) for y, cells in acme_lines()]
    supporting[0] = (230, [(20, "Trucking RATE 15%")])
    source = write_pdf(tmp_path / "example.pdf", [(40, [(20, "ACME Waterproofing")])] + labor + supporting)
    result = extract_document(source, use_ocr=False)
    uploaded = io.BytesIO(source.read_bytes())
    uploaded.name = source.name
    monkeypatch.setattr(interface.st, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setattr(interface, "load_records", lambda *args: [])

    def run_app():
        from ocr_ingestion.app import main
        main()

    app = AppTest.from_function(run_app)
    app.session_state["extraction"] = result
    app.session_state["source_path"] = source
    app.session_state["upload_hash"] = result.document_id
    app.run()
    assert not app.exception
    preview = app.dataframe[-1].value
    assert len(preview) == 3  # Only usable labor rates, with no totals.
    assert preview["Add"].tolist() == [True, True, True]
    assert len(app.expander) == 2  # Labor table and extraction notes.
    assert not any(box.label.startswith("Show supporting") for box in app.checkbox)
    assert "total_amount" not in preview.columns


def test_saved_view_ignores_legacy_nonlabor_and_missing_rate_rows(tmp_path, monkeypatch):
    import ocr_ingestion.app as interface
    from streamlit.testing.v1 import AppTest

    result = extract_document(write_pdf(tmp_path / "source.pdf", detail_lines()), use_ocr=False)
    good = result.records[0]
    bad_rate = {**good, "reg_rate": "", "ot_rate": "", "dt_rate": ""}
    summary = {**good, "row_type": "table_summary"}
    original = [good.copy(), bad_rate.copy(), summary.copy()]
    records = [good, bad_rate, summary]
    monkeypatch.setattr(interface.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(interface, "load_records", lambda *args: records)

    def run_app():
        from ocr_ingestion.app import main
        main()

    app = AppTest.from_function(run_app).run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 1
    assert app.dataframe[0].value.iloc[0]["reg_rate"] == good["reg_rate"]
    assert records == original
