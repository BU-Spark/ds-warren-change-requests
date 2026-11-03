"""Review progress derived from extraction evidence, confirmations and saved source IDs."""

from .state import fingerprint


def table_tokens(extraction):
    return {
        table["table_id"]: fingerprint(
            [
                row
                for row in extraction["records"]
                if row["table_id"] == table["table_id"]
            ]
        )
        for table in extraction["tables"]
        if table["requires_review"]
    }


def review_progress(session, saved_ids):
    extraction = session.get("extraction")
    if session["status"] != "ready" or not extraction:
        return {
            "status": session["status"],
            "pending_tables": 0,
            "reviewed_tables": 0,
            "unsaved_rows": 0,
            "items": [],
            "problem_pages": [],
        }
    tokens = table_tokens(extraction)
    confirmations = session.get("reviewed", {})
    items = []
    for table in extraction["tables"]:
        records = [
            r for r in extraction["records"] if r["table_id"] == table["table_id"]
        ]
        if not records and table["kind"] != "unfamiliar":
            continue
        unsaved = sum(r["record_id"] not in saved_ids for r in records)
        if records and not unsaved:
            status = "saved"
        elif not records and table["kind"] == "unfamiliar":
            status = "mapping"
        elif table["requires_review"]:
            status = (
                "reviewed"
                if confirmations.get(table["table_id"]) == tokens[table["table_id"]]
                else "needs_review"
            )
        else:
            status = "ready"
        label = {
            "labor_detail": "Worker details",
            "labor_tally": "Labor tally",
            "unfamiliar": "Match printed columns",
        }.get(table["kind"], "Labor rates")
        reason = {
            "mapping": "Match the printed columns before reviewing rates.",
            "needs_review": "Compare the extracted values with the original printed table.",
            "reviewed": "Source checked. Selected rows can be saved.",
            "ready": "No additional confirmation required. Review and save the rows you need.",
            "saved": "All extracted rows in this table are already saved.",
        }[status]
        items.append(
            {
                "table_id": table["table_id"],
                "page": table["page"],
                "label": label,
                "status": status,
                "requires_review": table["requires_review"],
                "row_count": len(records),
                "unsaved_rows": unsaved,
                "reason": reason,
            }
        )
    rank = {"mapping": 0, "needs_review": 1, "reviewed": 2, "ready": 3, "saved": 4}
    items.sort(key=lambda item: (rank[item["status"]], item["page"], item["table_id"]))
    pending = sum(i["status"] in {"mapping", "needs_review"} for i in items)
    unsaved = sum(r["record_id"] not in saved_ids for r in extraction["records"])
    problems = [
        p["page"]
        for p in extraction["pages"]
        if p.get("status") in {"extraction_failed", "scan_not_processed"}
    ]
    status = (
        "needs_review"
        if pending
        else "check_pages"
        if problems
        else "ready_to_save"
        if unsaved
        else "saved"
        if extraction["records"]
        else "no_rates"
    )
    return {
        "status": status,
        "pending_tables": pending,
        "reviewed_tables": sum(
            i["requires_review"] and i["status"] in {"reviewed", "saved"} for i in items
        ),
        "unsaved_rows": unsaved,
        "items": items,
        "problem_pages": problems,
    }
