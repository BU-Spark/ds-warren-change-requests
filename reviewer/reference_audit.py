"""Explain reference conflicts without choosing a winning schedule."""

from collections import defaultdict
from decimal import Decimal
from itertools import combinations

from .matching import canonical, contractor_key


def reference_conflicts(reference):
    groups = defaultdict(list)
    for row in reference["rows"]:
        if not row["issues"] and row["status"].strip().casefold() == "approved":
            groups[
                (contractor_key(row["subcontractor"]), canonical(row["position"]))
            ].append(row)
    conflicts = []
    for rows in groups.values():
        for left, right in combinations(rows, 2):
            start = max(
                left["effective_time_period_start"],
                right["effective_time_period_start"],
            )
            finish = min(
                left["effective_time_period_finish"],
                right["effective_time_period_finish"],
            )
            if start > finish:
                continue
            fields = {
                field: [left[field], right[field]]
                for field in ("reg_rate", "ot_rate", "dt_rate")
                if left[field] != ""
                and right[field] != ""
                and Decimal(left[field]) != Decimal(right[field])
            }
            if fields:
                conflicts.append(
                    {
                        "contractor": left["subcontractor"],
                        "classification": left["position"],
                        "reference_rows": [
                            left["source_csv_row_number"],
                            right["source_csv_row_number"],
                        ],
                        "overlap_start": start,
                        "overlap_finish": finish,
                        "rates": fields,
                    }
                )
    return {"reference_version": reference["id"], "conflicts": conflicts}
