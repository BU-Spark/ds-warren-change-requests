"""Run from the repository root: python -m streamlit run ocr_ingestion/app.py."""

import hashlib
import json
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

# Streamlit executes this file as a script; resolve imports from the checked-out repository.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ocr_ingestion import append_records, extract_document, load_records
from ocr_ingestion.extraction import map_table
from ocr_ingestion.models import FIELDS, is_labor_rate


CSV_PATH = ROOT / "data/document_line_items.csv"
PRIVATE = ROOT / "data/ocr_ingestion"


def client_table(rows, *, technical=False, known_ids=()):
    """Format a copy for clients; never shorten stored identifiers or change source values."""
    display = rows.copy()
    if technical:
        return display
    # Filename prefixes are user-requested labels, not verified project identifiers.
    display.insert(0, "project_id", display["source_file"].map(lambda name: Path(name).stem.split("-", 1)[0].strip()))
    all_ids = set(known_ids) | set(display["record_id"])
    short_ids = {}
    for record_id in all_ids:
        length = 12
        # Extend a prefix if necessary so distinct records never share a displayed ID.
        while length < len(record_id) and any(
            other != record_id and other[:length] == record_id[:length] for other in all_ids
        ):
            length += 1
        short_ids[record_id] = record_id[:length]
    display["record_id"] = display["record_id"].map(short_ids)
    hidden = {"document_id", "table_id", "row_index", "extraction_method", "quantity", "unit", "unit_rate",
              "reg_amount", "ot_amount", "dt_amount", "extension_amount", "overhead_profit_amount", "total_amount"}
    always = {"Add", "project_id", "project", "record_id", "source_file", "source_page", "contractor", "row_type"}
    # Empty layout-specific fields remain in the CSV and technical view, not the client table.
    return display[[column for column in display if column not in hidden and (
        column in always or display[column].fillna("").ne("").any()
    )]]


def column_labels(columns):
    labels = {"project_id": "Project ID (filename)", "project": "Project name",
              "position_original": "Classification (as printed)", "reg_rate": "ST rate",
              "reg_hours": "ST hours", "reg_amount": "ST amount", "document_id": "Document hash (internal)"}
    return {column: labels.get(column, column.replace("_", " ").capitalize()) for column in columns}


def source_preview(path, page_number):
    import pymupdf
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as document:
            st.image(document[page_number - 1].get_pixmap(dpi=120, annots=False).tobytes("png"),
                     caption=f"Source page {page_number}. Flattened marks may still be visible.")
    else:
        from PIL import Image
        with Image.open(path) as image:
            image.seek(page_number - 1)
            st.image(image.convert("RGB"), caption=f"Source image {page_number}")


def main():
    st.set_page_config(page_title="Printed table ingestion", layout="wide")
    st.title("Printed table ingestion")
    st.write("Upload a document, review its printed labor rates, and add selected rows to the shared local dataset.")
    st.caption("Local processing only. Handwriting and reviewer corrections are excluded. Rate validation is a later step.")
    upload_tab, data_tab = st.tabs(["Upload document", "View data"])
    with upload_tab:
        upload_document()
    with data_tab:
        view_data()


def view_data():
    """Read the accumulated CSV without changing its values or accepting preview rows."""
    st.subheader("Saved dataset")
    st.caption("data/document_line_items.csv · Saved labor-rate rows only, not unsaved extraction previews. This view is read-only.")
    # A button interaction reruns the app, loading the latest CSV under the storage lock.
    st.button("Refresh data", key="refresh_saved_data")
    try:
        records = [record for record in load_records(CSV_PATH) if is_labor_rate(record)]
    except Exception as exc:
        st.error(f"Cannot load the saved dataset: {exc}")
        return
    if not records:
        st.info("No saved rows yet. Upload a document, review its rows, and click Add to dataset first.")
        return
    # Keep original strings so identifiers, empty fields, and exact decimal rates stay intact.
    rows = pd.DataFrame(records, columns=FIELDS)
    technical = st.checkbox("Show technical columns and full IDs", key="saved_technical")
    display = client_table(rows, technical=technical)
    query = st.text_input("Search saved data", help="Search all columns without changing the CSV.").strip()
    visible = display
    if query:
        matches = rows.apply(lambda column: column.str.contains(query, case=False, regex=False, na=False)).any(axis=1)
        matches |= display.apply(lambda column: column.str.contains(query, case=False, regex=False, na=False)).any(axis=1)
        visible = display.loc[matches]
    st.write(f"Showing {len(visible)} of {len(rows)} saved rows.")
    st.caption("Project ID is the filename before the first '-'; it is not a verified project number. Short record IDs are display labels only.")
    st.dataframe(visible, hide_index=True, column_config=column_labels(visible.columns))


def upload_document():
    uploaded = st.file_uploader("Choose a PDF or image", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff"])
    contractor = st.text_input("Contractor (as printed on the source)", help="Provide the contractor explicitly; the program does not infer it from a filename or rates.")
    project = st.text_input("Project name (required)", help="Enter the actual project name. It is saved in the project column for new rows.").strip()
    use_ocr = st.checkbox("Read scanned printed tables with local OCR", value=True,
                            help="Printed header detection skips handwritten backup forms. OCR-derived rows require review.")
    if uploaded is None:
        st.info("Original documents, extracted data, and review evidence stay in the ignored local data folder.")
        return
    st.caption(f"Project ID (filename): {Path(uploaded.name).stem.split('-', 1)[0].strip()}")
    if st.button("Extract tables", type="primary"):
        if not project:
            st.error("Enter a project name before extracting tables.")
            return
        contents = uploaded.getvalue()
        if not contents:
            st.error("The uploaded file is empty.")
            return
        digest = hashlib.sha256(contents).hexdigest()
        source = PRIVATE / "uploads" / digest / Path(uploaded.name).name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(contents)
        progress = st.progress(0, text="Reading document")
        try:
            extraction = extract_document(source, contractor=contractor, project=project, use_ocr=use_ocr,
                                          progress=lambda current, count: progress.progress(current / count, text=f"Reading page {current} of {count}"))
        except Exception as exc:
            st.error(str(exc))
            return
        st.session_state["extraction"] = extraction
        st.session_state["source_path"] = source
        st.session_state["upload_hash"] = digest
        progress.empty()
    result = st.session_state.get("extraction")
    if result is None:
        return
    if hashlib.sha256(uploaded.getvalue()).hexdigest() != st.session_state.get("upload_hash"):
        st.info("Extract the newly selected document before reviewing its rows.")
        return
    source = st.session_state["source_path"]
    st.subheader("Review tables")
    st.write(f"{len(result.tables)} tables detected; {len(result.records)} structured rows extracted.")
    try:
        existing = load_records(CSV_PATH)
    except Exception as exc:
        st.error(str(exc))
        return
    known_ids = {row["record_id"] for row in existing}
    document_existing = sum(row["document_id"] == result.document_id for row in existing)
    if document_existing:
        st.info(f"This document already has {document_existing} saved rows. Previously saved rows will be skipped.")
    review_tables = []
    for table in result.tables:
        if table.kind not in {"labor", "labor_detail", "labor_tally", "unfamiliar"}:
            continue
        layout = {"labor": "Labor", "labor_detail": "Labor · worker detail",
                  "labor_tally": "Labor · tally", "unfamiliar": "Labor · column mapping"}[table.kind]
        with st.expander(f"Page {table.page} · {layout}"):
            st.dataframe(pd.DataFrame(table.rows, columns=[f"{i}: {name}" for i, name in enumerate(table.headers)]), hide_index=True)
            if st.checkbox("Show original page", key=f"preview-{result.document_id}-{table.table_id}"):
                source_preview(source, table.page)
            if table.kind == "unfamiliar":
                st.write("Map the printed columns below. Do not map handwriting or corrections.")
                choices = ["Ignore", "description", "position_original", "worker_name", "hours", "rate",
                           "reg_hours", "ot_hours", "dt_hours", "reg_rate", "ot_rate", "dt_rate",
                           "work_start", "work_end", "rate_basis_raw", "ticket_id", "document_reference"]
                mapping = {}
                for index, heading in enumerate(table.headers):
                    selected = st.selectbox(f"Column {index}: {heading}", choices,
                                            key=f"map-{result.document_id}-{table.table_id}-{index}")
                    if selected != "Ignore":
                        mapping[index] = selected
                if st.button("Apply mapping", key=f"apply-{result.document_id}-{table.table_id}"):
                    try:
                        map_table(result, table.table_id, mapping, row_type="labor")
                        for row in result.records:
                            if row["table_id"] == table.table_id:
                                row["contractor"], row["project"] = contractor, project
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            if table.requires_review:
                st.warning("Review required after OCR, mapping, uncertain cells, or annotation filtering. Compare the values to the original printed source.")
                review_fingerprint = hashlib.sha256(json.dumps(
                    [row for row in result.records if row["table_id"] == table.table_id], sort_keys=True,
                ).encode()).hexdigest()[:16]
                if st.checkbox("I checked the original printed table; selected rows exclude handwriting and corrections",
                               key=f"review-{result.document_id}-{table.table_id}-{review_fingerprint}"):
                    review_tables.append(table.table_id)
    with st.expander("Extraction notes and skipped pages"):
        st.json({"issues": result.issues, "pages": result.pages})
    if not result.records:
        st.info("No structured rows are ready. Map a detected table above, or supply a clearer printed table document.")
        return
    rows = pd.DataFrame([row for row in result.records if is_labor_rate(row)], columns=FIELDS)
    if rows.empty:
        st.info("No usable labor rates found. Rows need an explicit rate and a printed description, classification, or worker name.")
        return
    rows.insert(0, "Add", ~rows["record_id"].isin(known_ids))
    st.subheader("Select rows to add")
    st.caption("Only labor-rate rows are available to save. Blank optional cells are unknown values. Rates are not checked against the contract tracker here.")
    technical = st.checkbox("Show technical columns and full IDs", key="preview_technical")
    display = client_table(rows, technical=technical, known_ids=known_ids)
    selection = st.data_editor(display, hide_index=True, disabled=[column for column in display if column != "Add"],
                               column_config={**column_labels(display.columns), "Add": st.column_config.CheckboxColumn("Add")},
                               key=f"rows-{result.document_id}-{len(result.records)}-{technical}")
    # Resolve selection by row index, never by the shortened presentation ID.
    selected_ids = rows.loc[selection.index[selection["Add"]], "record_id"].tolist()
    st.write(f"{len(selected_ids)} rows selected. Dataset: data/document_line_items.csv")
    metadata_changed = any(row["project"] != project or row["contractor"] != contractor for row in result.records)
    if not project or metadata_changed:
        st.info("Enter the project name and extract again after changing project or contractor details before saving.")
    if st.button("Add to dataset", type="primary", disabled=not selected_ids or not project or metadata_changed):
        try:
            summary = append_records(result, CSV_PATH, selected_ids, reviewed_table_ids=review_tables, source_path=source)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(f"Added {summary['added']} rows; {summary['already_present']} already present. Dataset now has {summary['total']} rows.")
    st.download_button("Download extraction evidence (private)", result.as_json(),
                       file_name=f"{result.document_id[:12]}-evidence.json", mime="application/json")


if __name__ == "__main__":
    main()
