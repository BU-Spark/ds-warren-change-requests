"""Loopback-only reviewer API. No document content is sent to external services."""

import hashlib
import json
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from filelock import Timeout as LockTimeout

from ocr_ingestion import append_records, extract_document, load_records
from ocr_ingestion.extraction import SUPPORTED, map_table
from ocr_ingestion.models import is_labor_rate

from .checker import CHECKER_VERSION, compare, differences_csv, parse_reference
from .documents import page_image, receive_upload, restore_extraction
from .matching import canonical, classification_graph, compatible
from .review import review_progress, table_tokens
from .schemas import (
    ActivationRequest,
    BulkDetails,
    CheckRequest,
    ClassificationAlias,
    MappingRequest,
    ReviewDetails,
    ReviewRequest,
    SaveRequest,
)
from .state import State, fingerprint, now

ROOT = Path(__file__).resolve().parents[1]


def create_app(data_dir=None, frontend_dir=None):
    data = Path(data_dir or os.environ.get("WARREN_DATA_DIR", ROOT / "data")).resolve()
    state = State(data / "reviewer")
    operation_lock = threading.RLock()
    executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="document-extraction"
    )
    # Jobs interrupted by an earlier server stop must never remain stuck in Processing.
    for session in state.list("session"):
        if session["status"] in {"queued", "processing"}:
            session.update(
                status="failed",
                error="Processing was interrupted. Upload the document again to retry.",
            )
            state.put("session", session["id"], session)

    @asynccontextmanager
    async def lifespan(app):
        yield
        executor.shutdown(wait=True)

    app = FastAPI(title="Warren labor review", lifespan=lifespan)
    app.state.store = state
    app.state.data_dir = data
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def local_origin(request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin
            not in {
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:5173",
                "http://localhost:5173",
                f"http://{request.headers.get('host')}",
            }
        ):
            return Response(
                "This local application does not accept requests from other websites.",
                status_code=403,
            )
        response = await call_next(request)
        if request.url.path.startswith("/api") or request.url.path in {
            "/",
            "/index.html",
        }:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid_value(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(LockTimeout)
    async def locked_dataset(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {
                "detail": "The dataset is busy with another save. Wait a moment, then try again."
            },
            status_code=409,
        )

    @app.exception_handler(OSError)
    async def storage_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {
                "detail": "The local file could not be read or written. Check available disk space and folder permissions, then retry."
            },
            status_code=503,
        )

    def entity(kind, identifier):
        result = state.get(kind, identifier)
        if result is None:
            raise HTTPException(404, "This item could not be found.")
        return result

    def retain_reference_source(contents, identifier):
        folder = data / "reviewer" / "reference_sources"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (identifier + ".csv")
        # Exclusive creation keeps a content-addressed original immutable.
        try:
            with path.open("xb") as stream:
                stream.write(contents)
        except FileExistsError:
            if hashlib.sha256(path.read_bytes()).hexdigest() != identifier:
                raise ValueError(
                    "The saved reference source is damaged. Restore it before continuing."
                )

    def active_reference():
        with operation_lock:
            identifier = state.get("setting", "active_reference")
            if identifier:
                return entity("reference", identifier)
            initial = data / "labor_rates_fa.csv"
            if not initial.exists():
                return None
            contents = initial.read_bytes()
            reference = parse_reference(contents, initial.name)
            retain_reference_source(contents, reference["id"])
            reference["created_at"] = now()
            state.put("reference", reference["id"], reference)
            state.put("setting", "active_reference", reference["id"])
            return reference

    def details():
        return {
            item["record_id"]: {
                k: v
                for k, v in item["values"].items()
                if k in ReviewDetails.model_fields
            }
            for item in state.list("detail")
        }

    def aliases():
        return sorted(
            state.list("classification_alias"),
            key=lambda item: (item["contractor"], canonical(item["source_label"])),
        )

    def saved_records():
        return [
            r
            for r in load_records(data / "document_line_items.csv")
            if is_labor_rate(r)
        ]

    def session_view(session, saved_ids=None):
        if saved_ids is None:
            saved_ids = {r["record_id"] for r in saved_records()}
        public = {k: v for k, v in session.items() if k != "path"}
        public["review_summary"] = review_progress(session, saved_ids)
        if session.get("extraction"):
            public["review_tokens"] = table_tokens(session["extraction"])
            public["reviewed"] = {
                key: token
                for key, token in session.get("reviewed", {}).items()
                if public["review_tokens"].get(key) == token
            }
            public["saved_ids"] = list(saved_ids)
        return public

    def extract_job(identifier):
        try:
            session = entity("session", identifier)
            session["status"] = "processing"
            state.put("session", identifier, session)

            def progress(page, total):
                session.update(page=page, total_pages=total)
                state.put("session", identifier, session)

            result = extract_document(
                session["path"],
                contractor=session["contractor"],
                project=session["project"],
                use_ocr=session["use_ocr"],
                progress=progress,
            )
            session.update(status="ready", extraction=result.evidence(), revision=1)
            state.put("session", identifier, session)
        except Exception as exc:
            session = entity("session", identifier)
            session.update(status="failed", error=str(exc))
            state.put("session", identifier, session)

    def current_session(identifier, revision):
        session = entity("session", identifier)
        if session["status"] != "ready":
            raise HTTPException(
                409, "Wait for extraction to finish before reviewing or saving."
            )
        if session["revision"] != revision:
            raise HTTPException(
                409, "The extraction changed. Refresh it and review the current values."
            )
        return session

    @app.get("/api/health")
    def health():
        import shutil

        return {"status": "ok", "ocr_available": shutil.which("tesseract") is not None}

    @app.get("/api/sessions")
    def sessions():
        saved_ids = {r["record_id"] for r in saved_records()}
        return [
            {
                **{
                    k: v
                    for k, v in s.items()
                    if k not in {"path", "extraction", "reviewed"}
                },
                "review_summary": review_progress(s, saved_ids),
            }
            for s in state.list("session")
        ]

    @app.post("/api/sessions", status_code=202)
    async def upload(
        file: UploadFile = File(...),
        project: str = Form(...),
        contractor: str = Form(...),
    ):
        project, contractor = project.strip(), contractor.strip()
        if not project or not contractor:
            raise ValueError("Enter a project and contractor before extracting tables.")
        if len(project) > 300 or len(contractor) > 300:
            raise ValueError(
                "Project and contractor names must be 300 characters or fewer."
            )
        filename = Path((file.filename or "document").replace("\\", "/")).name
        if Path(filename).suffix.lower() not in SUPPORTED:
            raise ValueError("Choose a PDF, PNG, JPEG, or TIFF file.")
        content = await receive_upload(file)
        identifier = uuid.uuid4().hex
        folder = data / "reviewer" / "uploads" / identifier
        folder.mkdir(parents=True)
        path = folder / filename
        path.write_bytes(content)
        session = {
            "id": identifier,
            "filename": filename,
            "project": project,
            "contractor": contractor,
            "use_ocr": True,
            "path": str(path),
            "created_at": now(),
            "status": "queued",
            "page": 0,
            "total_pages": 0,
            "revision": 0,
        }
        state.put("session", identifier, session)
        executor.submit(extract_job, identifier)
        return session_view(session)

    @app.get("/api/sessions/{identifier}")
    def get_session(identifier: str):
        return session_view(entity("session", identifier))

    @app.put("/api/sessions/{identifier}/tables/{table_id}")
    def mapping(identifier: str, table_id: str, body: MappingRequest):
        with operation_lock:
            session = current_session(identifier, body.revision)
            result = restore_extraction(session["extraction"])
            table = next((t for t in result.tables if t.table_id == table_id), None)
            if table is None or table.kind != "unfamiliar":
                raise ValueError(
                    "Only an unfamiliar detected labor table can be mapped."
                )
            # Same mapping choices exposed by the previous reviewed UI.
            allowed = {
                "description",
                "position_original",
                "worker_name",
                "hours",
                "rate",
                "reg_hours",
                "ot_hours",
                "dt_hours",
                "reg_rate",
                "ot_rate",
                "dt_rate",
                "work_start",
                "work_end",
                "rate_basis_raw",
                "ticket_id",
                "document_reference",
            }
            if set(body.columns.values()) - allowed:
                raise ValueError("Select supported printed labor columns only.")
            map_table(result, table_id, body.columns, row_type="labor")
            for row in result.records:
                row["contractor"], row["project"] = (
                    session["contractor"],
                    session["project"],
                )
            session.update(
                extraction=result.evidence(), revision=session["revision"] + 1
            )
            state.put("session", identifier, session)
            return session_view(session)

    @app.put("/api/sessions/{identifier}/review")
    def confirm_review(identifier: str, body: ReviewRequest):
        with operation_lock:
            session = current_session(identifier, body.revision)
            tokens = table_tokens(session["extraction"])
            if any(tokens.get(key) != value for key, value in body.reviewed.items()):
                raise HTTPException(
                    409,
                    "The table values changed. Refresh and review the current source values.",
                )
            session["reviewed"] = body.reviewed
            state.put("session", identifier, session)
            return session_view(session)

    @app.post("/api/sessions/{identifier}/save")
    def save(identifier: str, body: SaveRequest):
        with operation_lock:
            session = current_session(identifier, body.revision)
            result = restore_extraction(session["extraction"])
            reviewed = []
            for table in result.tables:
                token = fingerprint(
                    [r for r in result.records if r["table_id"] == table.table_id]
                )
                if body.reviewed.get(table.table_id) == token:
                    reviewed.append(table.table_id)
            summary = append_records(
                result,
                data / "document_line_items.csv",
                body.record_ids,
                reviewed_table_ids=reviewed,
                source_path=session["path"],
            )
            session["reviewed"] = {
                **session.get("reviewed", {}),
                **{key: body.reviewed[key] for key in reviewed},
            }
            state.put("session", identifier, session)
            return summary

    @app.get("/api/sessions/{identifier}/evidence")
    def evidence(identifier: str):
        session = entity("session", identifier)
        if not session.get("extraction"):
            raise HTTPException(409, "Extraction evidence is not ready yet.")
        return Response(
            json.dumps(session["extraction"], indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{identifier}-evidence.json"'
            },
        )

    @app.get("/api/sessions/{identifier}/pages/{page_number}")
    def session_page(identifier: str, page_number: int):
        return page_image(Path(entity("session", identifier)["path"]), page_number)

    @app.get("/api/documents/{document_id}/pages/{page_number}")
    def saved_page(document_id: str, page_number: int):
        if not re.fullmatch("[0-9a-f]{64}", document_id):
            raise HTTPException(404, "Source document not found.")
        folder = data / "document_line_items_private" / "originals"
        paths = [
            p for p in folder.glob(document_id + ".*") if p.suffix.lower() in SUPPORTED
        ]
        if not paths:
            raise HTTPException(
                404, "The original source is unavailable. Reupload it to view evidence."
            )
        return page_image(paths[0], page_number)

    @app.get("/api/records")
    def records():
        return {"records": saved_records(), "details": details()}

    def validated_details(body):
        from datetime import date

        values = {k: v.strip() for k, v in body.model_dump().items()}
        for field in ["work_start", "work_end"]:
            if (
                values[field]
                and date.fromisoformat(values[field]).isoformat() != values[field]
            ):
                raise ValueError("Use work dates in YYYY-MM-DD format.")
        if (
            values["work_start"]
            and values["work_end"]
            and values["work_start"] > values["work_end"]
        ):
            raise ValueError("Work finish must be on or after work start.")
        return values

    @app.post("/api/records/details")
    def bulk_details(body: BulkDetails):
        known = {r["record_id"] for r in saved_records()}
        if set(body.records) - known:
            raise HTTPException(404, "One or more saved records could not be found.")
        # Validate the entire selection before committing any comparison details.
        values = {
            identifier: validated_details(detail)
            for identifier, detail in body.records.items()
        }
        with operation_lock:
            state.put_many(
                "detail",
                {
                    identifier: {
                        "record_id": identifier,
                        "values": value,
                        "updated_at": now(),
                    }
                    for identifier, value in values.items()
                },
            )
        return values

    @app.put("/api/records/{record_id}/details")
    def put_details(record_id: str, body: ReviewDetails):
        return bulk_details(BulkDetails(records={record_id: body}))[record_id]

    @app.get("/api/classification-map")
    def get_classification_map():
        reference = active_reference()
        if reference is None:
            raise ValueError(
                "Activate a reference schedule before viewing the classification map."
            )
        return classification_graph(reference, aliases())

    @app.put("/api/classification-aliases")
    def put_classification_alias(body: ClassificationAlias):
        with operation_lock:
            reference = active_reference()
            if reference is None:
                raise ValueError("Activate a reference schedule first.")
            values = {k: v.strip() for k, v in body.model_dump().items()}
            if not canonical(values["source_label"]):
                raise ValueError("Enter the job title as it appears in the document.")
            if not any(
                r["subcontractor"] == values["contractor"]
                and r["position"] == values["target_position"]
                for r in reference["rows"]
            ):
                raise ValueError(
                    "Choose a classification that belongs to this contractor in the active reference."
                )
            if not compatible(values["source_label"], values["target_position"]):
                raise ValueError(
                    "The relationship must preserve the stated grade, shift, group and specialty."
                )
            identifier = hashlib.sha256(
                (
                    values["contractor"] + ":" + canonical(values["source_label"])
                ).encode()
            ).hexdigest()
            return state.put(
                "classification_alias", identifier, {"id": identifier, **values}
            )

    @app.delete("/api/classification-aliases/{identifier}")
    def delete_classification_alias(identifier: str):
        with operation_lock:
            entity("classification_alias", identifier)
            state.delete("classification_alias", identifier)
            return {"removed": True}

    @app.get("/api/reference")
    def get_reference():
        return {
            "active": active_reference(),
            "versions": [
                {k: v for k, v in r.items() if k != "rows"}
                for r in state.list("reference")
            ],
        }

    @app.post("/api/reference/preview")
    async def preview_reference(file: UploadFile = File(...)):
        contents = await receive_upload(file, 10 * 1024 * 1024)
        reference = parse_reference(
            contents, Path(file.filename or "schedule.csv").name
        )
        with operation_lock:
            retain_reference_source(contents, reference["id"])
            existing = state.get("reference", reference["id"])
            if not existing:
                reference["created_at"] = now()
                state.put("reference", reference["id"], reference)
            else:
                reference = existing
        return reference

    @app.get("/api/reference/{identifier}/source")
    def reference_source(identifier: str):
        reference = entity("reference", identifier)
        path = data / "reviewer" / "reference_sources" / (reference["id"] + ".csv")
        if not path.exists():
            raise HTTPException(404, "The original reference CSV is unavailable.")
        return Response(
            path.read_bytes(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="reference-{identifier[:12]}.csv"'
            },
        )

    @app.post("/api/reference/activate")
    def activate_reference(body: ActivationRequest):
        with operation_lock:
            reference = entity("reference", body.reference_id)
            state.put("setting", "active_reference", reference["id"])
            return reference

    def with_staleness(run):
        reference = active_reference()
        run["rules_changed"] = run.get("checker_version", 1) != CHECKER_VERSION
        run["stale"] = (
            run["rules_changed"]
            or not reference
            or run["reference_version"] != reference["id"]
            or run["details_fingerprint"] != fingerprint(details())
            or run.get("aliases_fingerprint") != fingerprint(aliases())
        )
        return run

    @app.post("/api/checks")
    def check(body: CheckRequest):
        with operation_lock:
            reference = active_reference()
            if reference is None:
                raise ValueError(
                    "Upload and activate a reference rate schedule before running checks."
                )
            requested = set(body.record_ids)
            records = [r for r in saved_records() if r["record_id"] in requested]
            if len(records) != len(requested):
                raise ValueError(
                    "One or more selected records are not in the saved dataset."
                )
            current_details = details()
            identifier = uuid.uuid4().hex
            current_aliases = aliases()
            results = compare(
                records, reference, current_details, identifier, current_aliases
            )
            run = {
                "id": identifier,
                "created_at": now(),
                "checker_version": CHECKER_VERSION,
                "reference_version": reference["id"],
                "aliases_fingerprint": fingerprint(current_aliases),
                "reference_name": reference["name"],
                "details_fingerprint": fingerprint(current_details),
                "record_ids": list(requested),
                "results": results,
                "counts": {
                    outcome: sum(r["outcome"] == outcome for r in results)
                    for outcome in ["match", "difference", "needs_review"]
                },
            }
            state.put("run", identifier, run)
            return with_staleness(run)

    @app.get("/api/checks")
    def checks():
        return [with_staleness(r) for r in state.list("run")]

    @app.get("/api/checks/{identifier}/differences.csv")
    def export(identifier: str):
        run = with_staleness(entity("run", identifier))
        return Response(
            differences_csv(run["results"]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="labor-differences-{identifier[:8]}{"-outdated" if run["stale"] else ""}.csv"'
            },
        )

    # Unknown API routes remain API errors rather than serving the SPA.
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    def missing_api(path: str):
        raise HTTPException(404, "API route not found.")

    frontend = Path(frontend_dir or ROOT / "frontend" / "dist")
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
