"""Synthetic review-queue rules, independent from the UI presentation."""

from reviewer.review import review_progress, table_tokens


def session(kind="labor", records=True, pages=None):
    return {
        "status": "ready",
        "extraction": {
            "records": [{"record_id": "row", "table_id": "table", "rate": "10"}]
            if records
            else [],
            "tables": [
                {"table_id": "table", "page": 2, "requires_review": True, "kind": kind}
            ],
            "pages": pages or [{"page": 2, "status": "tables_found"}],
        },
    }


def test_mapping_remains_pending_until_usable_rows_exist():
    source = session("unfamiliar", records=False)
    source["reviewed"] = table_tokens(source["extraction"])
    result = review_progress(source, set())
    assert result["pending_tables"] == 1
    assert result["items"][0]["status"] == "mapping"


def test_changed_values_invalidate_review_and_saved_rows_need_no_repeat():
    source = session()
    source["reviewed"] = table_tokens(source["extraction"])
    assert review_progress(source, set())["status"] == "ready_to_save"
    source["extraction"]["records"][0]["rate"] = "11"
    assert review_progress(source, set())["pending_tables"] == 1
    saved = review_progress(source, {"row"})
    assert saved["status"] == "saved" and saved["pending_tables"] == 0


def test_unreadable_pages_are_actionable_even_without_pending_tables():
    source = session(records=False, pages=[{"page": 1, "status": "extraction_failed"}])
    summary = review_progress(source, set())
    assert summary["status"] == "check_pages" and summary["problem_pages"] == [1]
    source["extraction"]["pages"] = []
    assert review_progress(source, set())["status"] == "no_rates"


def test_in_progress_sessions_are_not_presented_as_review_ready():
    assert review_progress({"status": "processing"}, set())["status"] == "processing"
