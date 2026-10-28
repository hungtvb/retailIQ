"""Conservatively analyze observed business-pilot CSV data, never invent results.

The generated blank sheet produces NOT_MEASURED. Partial participation produces
INCOMPLETE, without a numerical time-saving headline. Full, valid records
produce descriptive *synthetic-data internal pilot* statistics only.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import median

from .business_pilot_export import TASKS, PARTICIPANTS, _assignments

EXPECTED_COLUMNS = set(_assignments()[0])
MEASUREMENT_FIELDS = ("answer_recorded", "duration_seconds", "correct")


def _read_sheet(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if set(reader.fieldnames or []) != EXPECTED_COLUMNS:
            raise ValueError("Study sheet has changed; expected original column names")
        return list(reader)


def summarize(folder: Path) -> dict:
    """Validate allocation and preserve honest incompleteness status."""
    folder = Path(folder)
    manifest_path = folder / "manifest.json"
    sheet_path = folder / "assignments_and_results.csv"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("dataset_type") != "synthetic" or
            manifest.get("planned_trials") != 24 or
            manifest.get("participants") != list(PARTICIPANTS)):
        raise ValueError("Only the published balanced synthetic study is supported")
    rows = _read_sheet(sheet_path)
    expected = _assignments()
    if len(rows) != len(expected):
        raise ValueError("Task assignment rows are missing or duplicated")
    index = {(r["participant_id"], r["task_id"]): r for r in expected}
    seen = set()
    complete = []
    for row in rows:
        key = (row["participant_id"], row["task_id"])
        if key in seen or key not in index:
            raise ValueError("Unexpected or repeated participant/task")
        seen.add(key)
        match = index[key]
        for field in ("trial_order", "method", "question", "required_fields"):
            if str(row[field]) != str(match[field]):
                raise ValueError("Assignment was changed: " + str(key) + "/" + field)
        filled = any((row.get(field) or "").strip() for field in MEASUREMENT_FIELDS)
        if not filled:
            continue
        if not all((row.get(field) or "").strip() for field in MEASUREMENT_FIELDS):
            raise ValueError("Partial measurement row for " + str(key))
        answer = row["answer_recorded"].strip()
        raw_duration = row["duration_seconds"].strip()
        try:
            seconds = float(raw_duration)
        except ValueError as error:
            raise ValueError("duration_seconds must be numeric for " + str(key)) from error
        if not math.isfinite(seconds) or not 0 < seconds <= 1800:
            raise ValueError("duration_seconds must be within (0,1800] for " + str(key))
        if row["correct"].strip() not in ("0", "1"):
            raise ValueError("correct must be 0 or 1 for " + str(key))
        steps_raw = (row["manual_steps"] or "").strip()
        if steps_raw:
            if not steps_raw.isdigit() or int(steps_raw) > 100:
                raise ValueError("manual_steps must be integer 0..100")
        complete.append({
            "participant_id": row["participant_id"], "task_id": row["task_id"],
            "method": row["method"], "duration_seconds": seconds,
            "correct": int(row["correct"]),
            "manual_steps": int(steps_raw) if steps_raw else None,
        })
    if len(seen) != len(index):
        raise ValueError("Assignment coverage mismatch")

    result = {
        "study": "internal synthetic-data usability experiment",
        "dataset_type": "synthetic",
        "business_impact_verified": False,
        "participants_planned": len(PARTICIPANTS),
        "trials_planned": len(expected),
        "trials_recorded": len(complete),
        "status": "NOT_MEASURED" if not complete else "INCOMPLETE",
        "caveat": ("The observations are internal measurements on synthetic data. "
                   "No verified real-retailer productivity, savings or ROI claim."),
    }
    if len(complete) != len(expected):
        result["missing_measurements"] = len(expected)-len(complete)
        return result

    # Each task is counterbalanced with two observations per condition.
    by_task = defaultdict(lambda: defaultdict(list))
    by_method = defaultdict(list)
    for row in complete:
        by_task[row["task_id"]][row["method"]].append(row)
        by_method[row["method"]].append(row)
    for task_id, *_ in TASKS:
        if any(len(by_task[task_id][method]) != 2
               for method in ("manual", "retailiq")):
            raise ValueError("Task-by-method allocation is not balanced")

    result["status"] = "COMPLETE_EXPLORATORY"
    summary = {}
    for method in ("manual", "retailiq"):
        subset = by_method[method]
        correct_times = [r["duration_seconds"] for r in subset if r["correct"]]
        summary[method] = {
            "n": len(subset), "correct": sum(r["correct"] for r in subset),
            "accuracy": round(sum(r["correct"] for r in subset)/len(subset), 4),
            "median_seconds_correct_only": (
                round(median(correct_times), 2) if correct_times else None),
            "n_correct_timed": len(correct_times),
            "median_manual_steps_recorded": (
                round(median([r["manual_steps"] for r in subset
                              if r["manual_steps"] is not None]), 2)
                if any(r["manual_steps"] is not None for r in subset) else None),
        }
    result["method_summary"] = summary
    result["task_summary"] = {}
    for task_id, *_ in TASKS:
        result["task_summary"][task_id] = {
            method: {
                "correct": sum(r["correct"] for r in by_task[task_id][method]),
                "n": 2,
                "median_seconds_correct_only": (
                    round(median([r["duration_seconds"]
                                  for r in by_task[task_id][method] if r["correct"]]), 2)
                    if any(r["correct"] for r in by_task[task_id][method]) else None),
            } for method in ("manual", "retailiq")
        }
    manual_median = summary["manual"]["median_seconds_correct_only"]
    copilot_median = summary["retailiq"]["median_seconds_correct_only"]
    if manual_median and copilot_median:
        result["exploratory_median_time_difference_percent"] = round(
            (manual_median-copilot_median)/manual_median * 100, 1)
        result["metric_warning"] = (
            "Only correct answers are timed for this descriptive metric. "
            "Accuracy must be interpreted jointly; small n=4 internal volunteers; "
            "different tasks by method per participant, counterbalanced by task. "
            "No causality, statistical significance or production ROI inferred.")
    else:
        result["metric_warning"] = (
            "No valid correct-answer median in at least one condition; "
            "do not calculate time saving.")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, default=Path("data/business_pilot_run1"))
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional JSON path; never overwrites participant input sheet")
    opts = parser.parse_args()
    report = summarize(opts.folder)
    if opts.output is not None:
        if opts.output.resolve() == (opts.folder/"assignments_and_results.csv").resolve():
            raise ValueError("Cannot overwrite participant measurements")
        opts.output.parent.mkdir(parents=True, exist_ok=True)
        opts.output.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
