"""Evidence-based comparisons. Extracted source values are never modified."""

import csv
import hashlib
import io
import re
from datetime import date
from decimal import Decimal, localcontext

from ocr_ingestion.models import number

from .matching import canonical, classification_candidates, resolve_contractor

REFERENCE_FIELDS = [
    "source_csv_row_number",
    "subcontractor",
    "position",
    "effective_time_period_start",
    "effective_time_period_finish",
    "reg_rate",
    "ot_rate",
    "dt_rate",
    "status",
    "bu_approval_received",
]
CHECKER_VERSION = 3
RATE_TYPES = {"reg_rate": "REG", "ot_rate": "OT", "dt_rate": "DT"}
EXPORT_FIELDS = [
    "finding_id",
    "run_id",
    "record_id",
    "document_id",
    "project",
    "contractor",
    "classification",
    "work_start",
    "work_end",
    "source_file",
    "source_page",
    "table_id",
    "document_reference",
    "ticket_id",
    "rate_type",
    "submitted_rate",
    "approved_rate",
    "difference_per_hour",
    "reference_rate_field",
    "reference_version",
    "reference_row",
    "effective_start",
    "effective_finish",
    "approval_status",
    "bu_approval_received",
    "review_details",
    "finding_kind",
    "contractor_original",
    "match_method",
    "match_explanation",
    "trade_family",
    "matched_classifications",
    "approved_rates",
    "reference_rows",
]


def key(value):
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def parse_reference(contents: bytes, name: str) -> dict:
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Use a UTF-8 CSV file for the rate schedule.") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("The rate schedule needs unique column headings.")
    missing = set(REFERENCE_FIELDS) - set(reader.fieldnames)
    if missing:
        raise ValueError("Missing schedule columns: " + ", ".join(sorted(missing)))
    rows, seen, issues = [], set(), []
    for line, raw in enumerate(reader, 2):
        if None in raw or any(v is None for v in raw.values()):
            raise ValueError(f"CSV row {line} has missing or extra cells.")
        row = {field: raw[field].strip() for field in REFERENCE_FIELDS}
        source = row["source_csv_row_number"]
        if not source or source in seen:
            raise ValueError(f"CSV row {line} needs a unique source_csv_row_number.")
        seen.add(source)
        try:
            for field in RATE_TYPES:
                row[field] = number(row[field])
            for field in [
                "effective_time_period_start",
                "effective_time_period_finish",
            ]:
                if row[field]:
                    parsed = date.fromisoformat(row[field])
                    if parsed.isoformat() != row[field]:
                        raise ValueError("Use YYYY-MM-DD dates.")
        except ValueError as exc:
            raise ValueError(
                f"CSV row {line} contains an invalid rate or ISO date."
            ) from exc
        reasons = []
        if not all(
            row[f]
            for f in [
                "subcontractor",
                "position",
                "effective_time_period_start",
                "effective_time_period_finish",
            ]
        ):
            reasons.append("Missing contractor, classification, or effective dates")
        if (
            row["effective_time_period_start"]
            and row["effective_time_period_finish"]
            and row["effective_time_period_start"] > row["effective_time_period_finish"]
        ):
            reasons.append("Effective finish is before effective start")
        if not any(row[f] for f in RATE_TYPES):
            reasons.append("No reference rates")
        row["issues"] = reasons
        if reasons:
            issues.append({"reference_row": source, "messages": reasons})
        rows.append(row)
    if not rows:
        raise ValueError("The rate schedule is empty.")
    return {
        "id": hashlib.sha256(contents).hexdigest(),
        "name": name,
        "rows": rows,
        "issues": issues,
    }


def compare(
    records: list[dict], reference: dict, details: dict, run_id: str, aliases=()
) -> list[dict]:
    results = []
    for record in records:
        supplied = {
            k: v
            for k, v in details.get(record["record_id"], {}).items()
            if k != "generic_rate_type"
        }
        original_contractor = supplied.get("contractor") or record.get("contractor", "")
        contractor = resolve_contractor(original_contractor, reference["rows"])
        classification = (
            supplied.get("classification")
            or record.get("position_original")
            or record.get("description", "")
        )
        start = supplied.get("work_start") or record.get("work_start", "")
        end = supplied.get("work_end") or record.get("work_end", "") or start
        candidates, method, trade = classification_candidates(
            contractor, classification, reference["rows"], aliases
        )
        regular = record.get("reg_rate", "") or record.get("rate", "")
        rates = [("REG", regular)] if regular != "" else []
        rates.extend(
            (kind, record.get(field, ""))
            for field, kind in RATE_TYPES.items()
            if field != "reg_rate" and record.get(field, "") != ""
        )
        for rate_index, (kind, submitted) in enumerate(rates):
            rate_field = next(
                field for field, label in RATE_TYPES.items() if label == kind
            )
            result = {field: record.get(field, "") for field in EXPORT_FIELDS}
            result.update(
                run_id=run_id,
                contractor=contractor or original_contractor,
                contractor_original=original_contractor,
                classification=classification,
                work_start=start,
                work_end=end,
                rate_type=kind,
                submitted_rate=submitted,
                reference_version=reference["id"],
                review_details=supplied,
                reference_rate_field=rate_field,
                outcome="needs_review",
                finding_kind="needs_review",
                reason="",
                approved_rate="",
                difference_per_hour="",
                match_method=method,
                trade_family=trade,
                match_explanation="",
                matched_classifications=[],
                approved_rates=[],
                reference_rows=[],
            )
            result["finding_id"] = hashlib.sha256(
                f"{run_id}:{record['record_id']}:{rate_index}:{kind}".encode()
            ).hexdigest()
            reason = ""
            if not original_contractor:
                reason = "Confirm the contractor before checking labor rates. You can apply it to all rows from this document."
            elif not contractor:
                reason = "No schedule matches this contractor unambiguously. Confirm the contractor name."
            elif not start or not end:
                reason = "Confirm the dates when the work occurred."
            else:
                try:
                    if (
                        date.fromisoformat(start).isoformat() != start
                        or date.fromisoformat(end).isoformat() != end
                    ):
                        raise ValueError("Use YYYY-MM-DD dates.")
                except ValueError:
                    reason = "Work dates must be valid ISO dates."
                if not reason and start > end:
                    reason = "The work finish is before the work start."
            valid = [r for r in candidates if not r["issues"]]
            applicable = [
                r
                for r in valid
                if start
                and end
                and r["effective_time_period_start"] <= start
                and r["effective_time_period_finish"] >= end
            ]
            approved = [r for r in applicable if key(r["status"]) == "approved"]
            overlaps = [
                r
                for r in valid
                if start
                and end
                and key(r["status"]) == "approved"
                and r["effective_time_period_start"] <= end
                and r["effective_time_period_finish"] >= start
            ]
            conflicts = {}
            for row in overlaps:
                if row[rate_field] != "":
                    conflicts.setdefault(canonical(row["position"]), set()).add(
                        Decimal(row[rate_field])
                    )
            if not reason:
                if not candidates:
                    reason = "No schedule matches this contractor and classification or trade. Review the classification map."
                elif not valid:
                    reason = "Matching schedules contain incomplete or invalid reference information."
                elif not applicable:
                    reason = "No single approved schedule covers the full work period. Check the dates or split work across schedule periods."
                elif not approved:
                    reason = "The applicable schedule is not marked Approved."
                elif any(len(values) > 1 for values in conflicts.values()):
                    reason = "Approved schedules for the same classification overlap with conflicting rates. Review the reference schedule."
            rates_by_value = {}
            for row in approved:
                if row[rate_field] != "":
                    rates_by_value.setdefault(Decimal(row[rate_field]), row[rate_field])
            available = [rates_by_value[value] for value in sorted(rates_by_value)]
            result["approved_rates"] = available
            if not reason and not available:
                reason = f"The applicable approved schedules have no {kind} rate."
            chosen = []
            if not reason:
                matches = [
                    r
                    for r in approved
                    if r[rate_field] != ""
                    and Decimal(r[rate_field]) == Decimal(number(submitted))
                ]
                chosen = matches or [r for r in approved if r[rate_field] != ""]
                result["matched_classifications"] = sorted(
                    {r["position"] for r in chosen}
                )
                if matches or len(available) == 1:
                    expected = matches[0][rate_field] if matches else available[0]
                    with localcontext() as context:
                        context.prec = max(28, len(submitted) + len(expected) + 2)
                        delta = Decimal(number(submitted)) - Decimal(expected)
                    result.update(
                        approved_rate=expected,
                        difference_per_hour=format(delta, "f"),
                        outcome="match" if matches else "difference",
                        finding_kind="rate_match" if matches else "rate_difference",
                    )
                    reason = (
                        "Rate matches an applicable approved schedule for this contractor."
                        if matches
                        else "Submitted rate differs from the applicable approved rate."
                    )
                else:
                    result.update(
                        outcome="difference", finding_kind="rate_not_in_schedule"
                    )
                    reason = "Submitted rate is not among the applicable approved rates for this contractor and trade. Multiple classifications are possible; no single difference per hour is assumed."
                label = trade or "contractor schedule"
                result["match_explanation"] = (
                    f"{classification or 'Classification not printed'} → {label} → "
                    + "; ".join(result["matched_classifications"])
                )
                if method == "contractor_rate":
                    result["match_explanation"] = (
                        "Checked by contractor, work dates and approved rate; the printed classification was not recognized. "
                        + result["match_explanation"]
                    )
            if chosen or len(applicable) == 1:
                primary = chosen[0] if chosen else applicable[0]
                result.update(
                    reference_row=primary["source_csv_row_number"],
                    reference_rows=[r["source_csv_row_number"] for r in chosen],
                    effective_start=primary["effective_time_period_start"],
                    effective_finish=primary["effective_time_period_finish"],
                    approval_status=primary["status"],
                    bu_approval_received=primary["bu_approval_received"],
                )
            result["reason"] = reason
            result["candidates"] = candidates
            results.append(result)
    return results


def differences_csv(results):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=EXPORT_FIELDS, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for result in results:
        if result["outcome"] != "difference":
            continue
        row = dict(result)
        import json

        for field, value in row.items():
            if isinstance(value, (dict, list)):
                row[field] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        # Keep spreadsheet applications from interpreting source labels as formulas.
        for field, value in row.items():
            if (
                field not in {"submitted_rate", "approved_rate", "difference_per_hour"}
                and isinstance(value, str)
                and value.startswith(("=", "+", "-", "@", "\t", "\r"))
            ):
                row[field] = "'" + value
        writer.writerow(row)
    return buffer.getvalue()
