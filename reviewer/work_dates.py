"""Reviewer-supplied work periods, separate from immutable extracted records."""

from datetime import date

from .state import now


def validate_period(start, end):
    if not start and not end:
        return
    if not start or not end:
        raise ValueError("Enter both a work start and finish, or leave both blank.")
    try:
        if any(
            date.fromisoformat(value).isoformat() != value for value in (start, end)
        ):
            raise ValueError()
    except ValueError:
        raise ValueError("Use valid work dates in YYYY-MM-DD format.") from None
    if start > end:
        raise ValueError("Work finish must be on or after work start.")


def effective_period(record, detail):
    start = detail.get("work_start") or record.get("work_start", "")
    end = detail.get("work_end") or record.get("work_end", "") or start
    return start, end


def apply_period(
    state, records, work_start, work_end, *, only_missing=True, clear=False
):
    """Caller holds the workspace operation lock; write all row updates atomically."""
    start, end = work_start, work_end
    updates = {}
    for record in records:
        identifier = record["record_id"]
        item = state.get("detail", identifier) or {
            "record_id": identifier,
            "values": {},
        }
        values = dict(item["values"])
        if clear:
            if not values.get("work_start") and not values.get("work_end"):
                continue
            values.pop("work_start", None)
            values.pop("work_end", None)
        else:
            if only_missing and all(effective_period(record, values)):
                continue
            if values.get("work_start") == start and values.get("work_end") == end:
                continue
            values.update(work_start=start, work_end=end)
        updates[identifier] = {**item, "values": values, "updated_at": now()}
    if updates:
        state.put_many("detail", updates)
    return len(updates)
