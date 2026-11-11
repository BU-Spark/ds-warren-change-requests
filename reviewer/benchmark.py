"""Score independently labeled cases, including missing rows and abstentions.

python -m reviewer.benchmark --labels private-labels.json --findings findings.json
Labels are human source judgments, never generated from checker outcomes.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

SOURCE_FIELDS = {"rate", "reg_rate", "ot_rate", "dt_rate"}


def score(labels, findings):
    version = labels.get("reference_version")
    if not version:
        raise ValueError("Labels must identify the reference schedule version.")
    predictions = {}
    for finding in findings:
        if finding.get("reference_version") != version:
            raise ValueError("Findings and labels use different reference schedules.")
        field = finding.get("source_rate_field")
        if field not in SOURCE_FIELDS:
            raise ValueError(
                "Findings need a source_rate_field; rerun the current checker."
            )
        key = (finding["record_id"], field)
        if key in predictions:
            raise ValueError("Duplicate finding for a source rate cell.")
        if finding["outcome"] not in {"match", "difference", "needs_review"}:
            raise ValueError("Unknown checker outcome.")
        predictions[key] = finding
    seen_ids, seen_cells, counts, cases = set(), set(), Counter(), []
    for case in labels["cases"]:
        identifier = case.get("case_id")
        if not identifier or identifier in seen_ids:
            raise ValueError("Cases need unique case_id values.")
        seen_ids.add(identifier)
        expected = case.get("expected", "pending")
        if expected not in {"match", "difference", "unresolved", "pending"}:
            raise ValueError("Unknown expected outcome.")
        field = case.get("source_rate_field")
        if field not in SOURCE_FIELDS:
            raise ValueError("Each case needs the intended source rate field.")
        key = (case.get("record_id", ""), field)
        if key[0]:
            if key in seen_cells:
                raise ValueError("The same source rate cell is labeled twice.")
            seen_cells.add(key)
        if expected != "pending" and not all(
            case.get(f, "").strip()
            for f in ("source_evidence", "reference_evidence", "verified_by")
        ):
            raise ValueError(
                "Reviewed labels require source/reference evidence and a reviewer."
            )
        predicted = predictions.get(key, {}).get("outcome", "missing")
        counts["cases"] += 1
        counts[expected] += 1
        if expected in {"match", "difference"}:
            counts["verified_binary_cases"] += 1
            counts["decided"] += predicted in {"match", "difference"}
            counts["correct"] += predicted == expected
            if expected == "difference":
                counts[
                    "true_positives" if predicted == "difference" else "false_negatives"
                ] += 1
                if predicted != "difference":
                    counts[f"missed_wrong_{predicted}"] += 1
            elif predicted == "difference":
                counts["false_positives"] += 1
            elif predicted == "match":
                counts["true_negatives"] += 1
        cases.append(
            {"case_id": identifier, "expected": expected, "predicted": predicted}
        )

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    tp, fp, fn = (
        counts[k] for k in ("true_positives", "false_positives", "false_negatives")
    )
    verified = counts["verified_binary_cases"]
    return {
        "reference_version": version,
        "counts": dict(counts),
        "metrics": {
            "wrong_rate_recall": ratio(tp, tp + fn),
            "flag_precision_on_verified_cases": ratio(tp, tp + fp),
            "correct_result_fraction_including_abstentions": ratio(
                counts["correct"], verified
            ),
            "accuracy_on_decided_verified_cases": ratio(
                counts["correct"], counts["decided"]
            ),
            "decision_coverage": ratio(counts["decided"], verified),
            "label_coverage": ratio(verified, counts["cases"]),
        },
        "unlabeled_predictions": len(set(predictions) - seen_cells),
        "unverified_flags": sum(
            f["outcome"] == "difference"
            for k, f in predictions.items()
            if k
            not in {
                (c.get("record_id", ""), c["source_rate_field"])
                for c in labels["cases"]
                if c.get("expected") in {"match", "difference"}
            }
        ),
        "cases": cases,
        "scope_note": "Metrics describe only independently verified cases. Pending labels and unresolved truth are excluded; unresolved or missing predictions on verified wrong cases count as missed errors. No result establishes population accuracy without a complete representative answer set.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--findings", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            score(
                json.loads(args.labels.read_text()),
                json.loads(args.findings.read_text()),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
