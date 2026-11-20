"""Document library and recoverable deletion across CSV, metadata and managed files."""

import shutil
from pathlib import Path

from ocr_ingestion.storage import delete_document, load_records

from .review import review_progress
from .state import fingerprint


def source_id(session):
    return session.get("document_id") or session.get("extraction", {}).get(
        "document_id"
    )


def managed_folder(data, folder):
    path = Path(folder).resolve()
    roots = (data / "reviewer/uploads", data / "ocr_ingestion/uploads")
    if not any(
        path.is_relative_to(root.resolve()) and path != root.resolve() for root in roots
    ):
        raise ValueError("Refusing to delete a source outside managed upload storage.")
    return path


def library(records, sessions):
    grouped = {}
    for record in records:
        grouped.setdefault(record["document_id"], []).append(record)
    saved_ids = {r["record_id"] for r in records}
    result = []
    for document_id, rows in grouped.items():
        related = [s for s in sessions if source_id(s) == document_id]
        related.sort(key=lambda s: (s["created_at"], s["id"]), reverse=True)
        latest = related[0] if related else None
        progress = review_progress(latest, saved_ids) if latest else None
        result.append(
            {
                "document_id": document_id,
                "filename": latest["filename"] if latest else rows[0]["source_file"],
                "projects": sorted({r["project"] for r in rows if r.get("project")}),
                "contractors": sorted(
                    {r["contractor"] for r in rows if r.get("contractor")}
                ),
                "record_ids": [r["record_id"] for r in rows],
                "saved_rows": len(rows),
                "session_id": latest["id"] if latest else None,
                "uploaded_at": latest["created_at"] if latest else None,
                "status": "saved"
                if not progress or progress["status"] == "saved"
                else "partially_saved",
                "unsaved_rows": progress["unsaved_rows"] if progress else 0,
            }
        )
    return sorted(
        result, key=lambda d: (d["uploaded_at"] or "", d["document_id"]), reverse=True
    )


def deletion_plan(state, data, *, document_id=None, session_id=None):
    sessions = state.list("session")
    target = (
        next((s for s in sessions if s["id"] == session_id), None)
        if session_id
        else None
    )
    if session_id and target is None:
        return None
    document_id = document_id or (source_id(target) if target else None)
    related = (
        [s for s in sessions if source_id(s) == document_id]
        if document_id
        else [target]
    )
    rows = load_records(data / "document_line_items.csv")
    saved = [r for r in rows if document_id and r["document_id"] == document_id]
    if not related and not saved:
        return None
    record_ids = {r["record_id"] for r in saved}
    for session in related:
        record_ids.update(
            r["record_id"] for r in session.get("extraction", {}).get("records", [])
        )
    runs = [
        run
        for run in state.list("run")
        if any(
            (document_id and f.get("document_id") == document_id)
            or f.get("record_id") in record_ids
            for f in run["results"]
        )
    ]
    related.sort(key=lambda s: (s["created_at"], s["id"]), reverse=True)
    plan = {
        "id": document_id or "session-" + session_id,
        "document_id": document_id,
        "filename": related[0]["filename"] if related else saved[0]["source_file"],
        "session_ids": sorted(s["id"] for s in related),
        "record_ids": sorted(record_ids),
        "run_ids": sorted(r["id"] for r in runs),
        "upload_folders": sorted(
            {str(Path(s["path"]).parent) for s in related if s.get("path")}
        ),
        "saved_rows": len(saved),
        "check_runs": len(runs),
        "shared_runs": sum(
            any(f.get("document_id") != document_id for f in r["results"]) for r in runs
        ),
        "session_versions": [(s["id"], s["status"], s["revision"]) for s in related],
    }
    plan["confirmation"] = fingerprint(plan)
    for folder in plan["upload_folders"]:
        managed_folder(data, folder)
    return plan


def public_plan(plan):
    return {
        key: plan[key]
        for key in (
            "filename",
            "document_id",
            "saved_rows",
            "check_runs",
            "shared_runs",
            "confirmation",
        )
    } | {"uploads": len(plan["session_ids"])}


def finish_deletions(state, data):
    """Retry confirmed operations after interruption; never leave orphaned check results."""
    for plan in state.list("document_deletion"):
        if plan["document_id"]:
            delete_document(data / "document_line_items.csv", plan["document_id"])
        for folder in plan["upload_folders"]:
            path = managed_folder(data, folder)
            if path.exists():
                shutil.rmtree(path)
        # Commit metadata removal and completion together on SQLite or PostgreSQL.
        with state.database.connect(write=True) as db:
            for kind, ids in (
                ("session", plan["session_ids"]),
                ("detail", plan["record_ids"]),
                ("run", plan["run_ids"]),
                ("document_deletion", [plan["id"]]),
            ):
                for identifier in ids:
                    db.execute(
                        "DELETE FROM entities WHERE kind=? AND id=?", (kind, identifier)
                    )
