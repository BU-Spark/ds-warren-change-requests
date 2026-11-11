"""Interpret pay wording without using the submitted price to choose a schedule."""

import re
from decimal import Decimal, localcontext

PAY_BASES = {"REG", "OT", "DT", "OT_PREMIUM", "DT_PREMIUM"}


def generic_basis(record, details):
    confirmed = details.get("confirmed_pay_basis", "")
    if confirmed:
        if (
            confirmed not in PAY_BASES
            or not details.get("pay_basis_evidence", "").strip()
        ):
            return (
                "UNRESOLVED",
                "A confirmed pay basis needs supporting source evidence.",
            )
        return confirmed, ""
    wording = " ".join(
        record.get(field, "")
        for field in ("rate_basis_raw", "description", "position_original")
    )
    # Premium can mean a full overtime rate, an increment, or a shift premium.
    # Neither a Sunday date nor a matching tracker price establishes its meaning.
    if re.search(
        r"\b(premium|increment|differential|surcharge|PT)\b", wording, re.IGNORECASE
    ):
        return "UNRESOLVED", (
            "Confirm whether this premium is a full hourly rate or an added premium, "
            "and which pay type applies; record the supporting evidence."
        )
    found = set()
    for kind, pattern in (
        ("REG", r"\b(?:regular|straight[ -]?time|ST|RT)\b"),
        ("OT", r"\b(?:over[ -]?time|OT)\b"),
        ("DT", r"\b(?:double[ -]?time|DT)\b"),
    ):
        if re.search(pattern, wording, re.IGNORECASE):
            found.add(kind)
    if len(found) > 1:
        return (
            "UNRESOLVED",
            "Multiple pay types describe this single rate. Confirm its basis with evidence.",
        )
    return next(iter(found), "REG"), ""


def reference_value(row, basis):
    field = {"REG": "reg_rate", "OT": "ot_rate", "DT": "dt_rate"}.get(basis)
    if field:
        return row.get(field, "")
    if basis in {"OT_PREMIUM", "DT_PREMIUM"}:
        regular = row.get("reg_rate", "")
        full = row.get("ot_rate" if basis == "OT_PREMIUM" else "dt_rate", "")
        if regular == "" or full == "":
            return ""
        with localcontext() as context:
            context.prec = max(28, len(regular) + len(full) + 2)
            delta = Decimal(full) - Decimal(regular)
        return format(delta, "f") if delta >= 0 else ""
    return ""
