"""Contractor-scoped classification relationships derived from the active tracker.

Families group possible classifications; they do not assert equal pay or seniority.
Only actual approved reference schedules supply rates.
"""

import re

FAMILIES = [
    (
        "masonry",
        "Masonry",
        ("mason", "masons", "masonry", "bricklayer", "bricklayers", "bricklaying"),
    ),
    ("carpentry", "Carpentry", ("carpenter", "carpenters", "carpentry")),
    (
        "labor",
        "Labor",
        ("laborer", "laborers", "labourer", "labourers", "labor", "labour"),
    ),
    ("electrical", "Electrical", ("electrician", "electricians", "electrical")),
    ("plumbing", "Plumbing", ("plumber", "plumbers", "plumbing")),
    ("pipefitting", "Pipefitting", ("pipefitter", "pipefitters", "pipefitting")),
    (
        "sprinkler",
        "Sprinkler fitting",
        ("sprinkler fitter", "sprinkler fitters", "sprinkler"),
    ),
    ("sheet_metal", "Sheet metal", ("sheet metal", "sheetmetal")),
    ("teledata", "Telecommunications", ("teledata", "tele data")),
    ("teamster", "Teamster / driving", ("teamster", "teamsters")),
    (
        "floorcovering",
        "Floor covering",
        ("floorcoverer", "floorcoverers", "floorcovering", "floor covering"),
    ),
    ("tile", "Tile and ceramic", ("tile", "ceramic", "marble")),
    ("insulation", "Insulation", ("insulator", "insulators", "insulation")),
    ("ironwork", "Ironwork", ("ironworker", "ironworkers", "ironwork")),
    ("glazing", "Glazing", ("glazier", "glaziers", "glazing")),
    ("painting", "Painting", ("painter", "painters", "painting")),
    ("roofing", "Roofing", ("roofer", "roofers", "roofing")),
    ("elevator", "Elevator work", ("elevator", "elevators")),
    ("surveying", "Surveying", ("field crew chief", "instrument operator")),
    (
        "operating",
        "Operating equipment",
        ("operating engineer", "operator", "operators", "driller"),
    ),
    (
        "cement",
        "Cement finishing",
        ("cement finisher", "cement finishers", "cement finishing"),
    ),
    ("plastering", "Plastering", ("plasterer", "plasterers", "plastering")),
    ("pile_driving", "Pile driving", ("pile driver", "pile drivers")),
    ("taping", "Taping", ("taper", "tapers", "taping")),
    ("security", "Security", ("security officer", "security")),
    ("management", "Project management", ("project manager",)),
    ("engineering", "Engineering", ("engineer",)),
]


def words(value):
    return re.sub(
        r"\s+", " ", re.sub(r"[^a-z0-9%]+", " ", (value or "").casefold())
    ).strip()


def canonical(value):
    text = words(value)
    substitutions = [
        (
            r"\b(?:journeyman|journeymen|journeyperson|journey person)\b",
            "journey person",
        ),
        (r"\b(?:foreman|foremen|forewoman)\b", "foreperson"),
        (r"\b(?:app|appr)\b", "apprentice"),
        (r"\bgen\b", "general"),
        (r"\bcarpenters\b", "carpenter"),
        (r"\blabou?rers?\b", "laborer"),
        (r"\bmasons\b", "mason"),
        (r"\bbricklayers\b", "bricklayer"),
    ]
    for pattern, replacement in substitutions:
        text = re.sub(pattern, replacement, text)
    roman = {
        "i": "1",
        "ii": "2",
        "iii": "3",
        "iv": "4",
        "v": "5",
        "vi": "6",
        "vii": "7",
        "viii": "8",
        "ix": "9",
        "x": "10",
    }
    text = re.sub(
        r"\b(?:gr|group)\s+([ivx]+|[0-9]+[a-z]?)\b",
        lambda match: "group " + roman.get(match[1], match[1]),
        text,
    )
    return text


def family(value):
    text = words(value)
    matches = [
        (len(alias), code, title)
        for code, title, aliases in FAMILIES
        for alias in aliases
        if re.search(r"\b" + re.escape(alias) + r"\b", text)
    ]
    return max(matches, default=(0, "", ""), key=lambda x: x[0])[1:]


def level(value):
    text = canonical(value)
    if "general foreperson" in text:
        return "general foreperson"
    if "foreperson" in text:
        return "foreperson"
    if "apprentice" in text:
        return "apprentice"
    if "journey person" in text:
        return "journey person"
    return ""


def compatible(source, target):
    """Keep stated seniority, shifts, groups and specialties; broad titles can include children."""
    source, target = canonical(source), canonical(target)
    if level(source) and level(source) != level(target):
        return False
    for pattern in [
        r"\b[23](?:nd|rd)? shift\b",
        r"\b(?:group|gr)\s+[a-z0-9]+\b",
        r"\b\d+%",
    ]:
        for qualifier in re.findall(pattern, source):
            if qualifier not in target:
                return False
    for qualifier in [
        "spray",
        "blended",
        "non union",
        "helper",
        "finisher",
        "mechanic",
        "lead",
        "supporting",
    ]:
        if re.search(r"\b" + qualifier + r"\b", source) and not re.search(
            r"\b" + qualifier + r"\b", target
        ):
            return False
    return True


def contractor_key(value):
    # Parenthetical context is not a second contractor identity.
    text = words(re.sub(r"\([^)]*\)", "", value or ""))
    text = re.sub(
        r"\b(?:incorporated|inc|llc|ltd|limited|corporation|corp|company|co)\b",
        "",
        text,
    )
    return re.sub(r"\s+", "", text)


def resolve_contractor(value, rows):
    names = sorted({r["subcontractor"] for r in rows if r["subcontractor"]})
    exact = [name for name in names if words(name) == words(value)]
    if len(exact) == 1:
        return exact[0]
    wanted_key = contractor_key(value)
    normalized = (
        [name for name in names if contractor_key(name) == wanted_key]
        if wanted_key
        else []
    )
    if len(normalized) == 1:
        return normalized[0]
    # Unique short names such as an entered company name without its trade suffix.
    tokens = set(words(value).split())
    generic_words = {
        "inc",
        "incorporated",
        "llc",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "company",
        "co",
        "contractor",
        "contractors",
        "construction",
        "services",
        "service",
        "waterproofing",
        "electric",
        "electrical",
        "masonry",
        "flooring",
        "interiors",
        "mechanical",
        "painting",
        "plumbing",
    }
    if tokens - generic_words and all(len(token) >= 3 for token in tokens):
        candidates = [
            name
            for name in names
            if tokens <= set(words(re.sub(r"\([^)]*\)", "", name)).split())
        ]
        if len(candidates) == 1:
            return candidates[0]
    return ""


def classification_candidates(contractor, classification, rows, aliases=()):
    scoped = [r for r in rows if r["subcontractor"] == contractor]
    text = canonical(classification)
    # Explicit user relationships target actual classifications, never other aliases.
    alias = next(
        (
            a
            for a in aliases
            if a["contractor"] == contractor and canonical(a["source_label"]) == text
        ),
        None,
    )
    if alias:
        targets = [
            r
            for r in scoped
            if r["position"] == alias["target_position"]
            and compatible(classification, r["position"])
        ]
        if targets:
            return targets, "classification_alias", family(alias["target_position"])[1]
    code, title = family(classification)
    broad_category = any(
        family_code == code and text in {canonical(alias) for alias in names}
        for family_code, _, names in FAMILIES
    )
    exact = [r for r in scoped if text and canonical(r["position"]) == text]
    if exact and not broad_category and "blended" not in text.split():
        # A generic printed role can use its explicitly Blended schedule.
        # Keep every other word/qualifier intact, and let approval/work dates
        # determine applicability instead of a later plain title hiding it.
        blended = [
            r
            for r in scoped
            if "blended" in canonical(r["position"]).split()
            and canonical(re.sub(r"\bblended\b", "", canonical(r["position"]))) == text
            and compatible(classification, r["position"])
        ]
        if blended:
            return exact + blended, "classification_variants", family(classification)[1]
    if exact and not broad_category:
        return exact, "exact_classification", family(classification)[1]
    if code:
        candidates = [
            r
            for r in scoped
            if family(r["position"])[0] == code
            and compatible(classification, r["position"])
        ]
        if not candidates:
            # Some contractor schedules state only Foreperson / Journey Person, without a trade.
            generic_roles = {
                "foreperson",
                "general foreperson",
                "journey person",
                "apprentice",
            }
            candidates = [
                r
                for r in scoped
                if canonical(r["position"]) in generic_roles
                and compatible(classification, r["position"])
            ]
            if candidates:
                return candidates, "contractor_role", title
        return candidates, "trade_family", title
    # With no recognizable trade, a rate can only be checked within this contractor.
    return (
        [r for r in scoped if compatible(classification, r["position"])],
        "contractor_rate",
        "",
    )


def classification_graph(reference, aliases):
    contractors = []
    for name in sorted(
        {r["subcontractor"] for r in reference["rows"] if r["subcontractor"]}
    ):
        families = {}
        for row in reference["rows"]:
            if row["subcontractor"] != name or not row["position"]:
                continue
            code, title = family(row["position"])
            code, title = code or "other", title or "Other classifications"
            group = families.setdefault(
                code,
                {
                    "id": code,
                    "label": title,
                    "aliases": next((list(a) for c, _, a in FAMILIES if c == code), []),
                    "classifications": {},
                },
            )
            node = group["classifications"].setdefault(
                row["position"],
                {
                    "name": row["position"],
                    "level": level(row["position"]),
                    "aliases": [
                        a["source_label"]
                        for a in aliases
                        if a["contractor"] == name
                        and a["target_position"] == row["position"]
                    ],
                    "schedules": [],
                },
            )
            node["schedules"].append(
                {
                    "row": row["source_csv_row_number"],
                    "reg_rate": row["reg_rate"],
                    "status": row["status"],
                    "start": row["effective_time_period_start"],
                    "finish": row["effective_time_period_finish"],
                    "issues": row["issues"],
                }
            )
        groups = []
        for group in sorted(families.values(), key=lambda g: g["label"]):
            group["classifications"] = sorted(
                group["classifications"].values(), key=lambda c: c["name"]
            )
            groups.append(group)
        contractors.append({"name": name, "families": groups})
    return {
        "reference_version": reference["id"],
        "contractors": contractors,
        "aliases": list(aliases),
    }
