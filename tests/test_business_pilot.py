"""Study instrumentation tests use ONLY synthetic fixtures and artificial test times.

Passing these tests must never be reported as measured business productivity.
"""
from collections import Counter, defaultdict
import csv
from datetime import date
from hashlib import sha256
import json

import pytest

from scripts.seed import seed
from scripts.business_pilot_export import export, _assignments
from scripts.business_pilot_analyze import summarize


@pytest.fixture
def pack(tmp_path):
    db = tmp_path / "synthetic.sqlite3"
    seed(db, write_support_files=False, reference_date=date(2026, 10, 28))
    original = sha256(db.read_bytes()).hexdigest()
    destination = tmp_path / "pilot"
    manifest = export(db, destination, reference_date=date(2026, 10, 28))
    assert sha256(db.read_bytes()).hexdigest() == original
    return destination, db, manifest


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_pilot_export_is_three_complete_source_views_and_readonly(pack):
    dest, db, manifest = pack
    products = read_csv(dest / "products.csv")
    inventory = read_csv(dest / "inventory.csv")
    sales = read_csv(dest / "sales.csv")
    assert len(products) == 10
    assert len(inventory) == 30
    assert len(sales) >= 120
    assert {"cancelled", "completed"} == {r["status"] for r in sales}
    assert "reserved" in inventory[0] and "updated_at" in inventory[0]
    assert "discount_vnd" in sales[0] and "ordered_at" in sales[0]
    assert "spec" in products[0]
    assert manifest["dataset_type"] == "synthetic"
    assert manifest["real_business_benefit_verified"] is False
    assert len(manifest["participants"]) == 4
    assert manifest["planned_trials"] == 24
    assert sha256(db.read_bytes()).hexdigest() == manifest["dataset_sha256"]


def test_balanced_crossover_and_no_repeated_exact_question(pack):
    dest, _, _ = pack
    assignments = read_csv(dest / "assignments_and_results.csv")
    assert len(assignments) == 24
    assert len({(r["participant_id"], r["task_id"]) for r in assignments}) == 24
    for task_id in ("T01", "T02", "T03", "T04", "T05", "T06"):
        counts = Counter(r["method"] for r in assignments if r["task_id"] == task_id)
        assert counts == {"manual": 2, "retailiq": 2}
    for participant in ("P01", "P02", "P03", "P04"):
        trials = [r for r in assignments if r["participant_id"] == participant]
        assert sorted(int(x["trial_order"]) for x in trials) == list(range(1, 7))
        assert Counter(x["method"] for x in trials) == {
            "manual": 3, "retailiq": 3
        }
        assert len({x["question"] for x in trials}) == 6


def test_facilitator_key_has_independent_reproducible_answers(pack):
    dest, _, _ = pack
    key = {r["task_id"]: json.loads(r["expected_json"]) for r in read_csv(
        dest / "FACILITATOR_ONLY_answer_key.csv")}
    assert set(key) == {"T01", "T02", "T03", "T04", "T05", "T06"}
    assert key["T01"]["sku"] == "EL-001"
    assert key["T01"]["available_total"] == sum(key["T01"]["by_location"].values())
    assert key["T04"]["total_vnd"] == sum(key["T04"]["channels"].values())
    assert key["T05"]["top5"][0]["sku"] == key["T06"]["sku"]
    assert key["T06"]["screening_outcome"] == (
        "REVIEW" if key["T06"]["available_total"] <
        key["T06"]["units_sold"] else "NO IMMEDIATE PRIORITY"
    )


def test_blank_and_partial_experiment_never_claim_time_savings(pack):
    dest, _, _ = pack
    result = summarize(dest)
    assert result["status"] == "NOT_MEASURED"
    assert result["trials_recorded"] == 0
    assert "method_summary" not in result
    assert "exploratory_median_time_difference_percent" not in result

    assignments_file = dest / "assignments_and_results.csv"
    rows = read_csv(assignments_file)
    rows[0].update({"answer_recorded": "real participant response",
                    "duration_seconds": "12.5", "correct": "1"})
    write_csv(assignments_file, rows)
    partial = summarize(dest)
    assert partial["status"] == "INCOMPLETE"
    assert partial["missing_measurements"] == 23
    assert "method_summary" not in partial


def test_completion_analysis_requires_all_observations_and_labels_scope(pack):
    dest, _, _ = pack
    assignments_file = dest / "assignments_and_results.csv"
    rows = read_csv(assignments_file)
    # ARTIFICIAL VALUES FOR TESTING ANALYSIS MATH ONLY. Not observed timings.
    for r in rows:
        r.update({
            "answer_recorded": "unit-test-only invented answer",
            "duration_seconds": "60" if r["method"] == "manual" else "10",
            "correct": "1",
            "manual_steps": "6" if r["method"] == "manual" else "1",
        })
    write_csv(assignments_file, rows)
    report = summarize(dest)
    assert report["status"] == "COMPLETE_EXPLORATORY"
    assert report["trials_recorded"] == 24
    assert report["business_impact_verified"] is False
    assert report["method_summary"]["manual"]["accuracy"] == 1
    assert report["method_summary"]["retailiq"]["median_seconds_correct_only"] == 10
    assert report["exploratory_median_time_difference_percent"] == 83.3
    assert len(report["task_summary"]) == 6


def test_tampered_assignments_partial_rows_and_inaccurate_times_rejected(pack):
    dest, _, _ = pack
    file = dest / "assignments_and_results.csv"
    rows = read_csv(file)
    rows[0]["method"] = "retailiq" if rows[0]["method"] == "manual" else "manual"
    write_csv(file, rows)
    with pytest.raises(ValueError, match="Assignment was changed"):
        summarize(dest)

    rows = _assignments()
    rows[0]["duration_seconds"] = "5"
    write_csv(file, rows)
    with pytest.raises(ValueError, match="Partial measurement"):
        summarize(dest)

    rows[0]["answer_recorded"] = "ok"
    rows[0]["correct"] = "1"
    rows[0]["duration_seconds"] = "nan"
    write_csv(file, rows)
    with pytest.raises(ValueError, match="duration_seconds"):
        summarize(dest)


def test_export_never_overwrites_existing_measurements(pack):
    destination, db, _ = pack
    with pytest.raises(FileExistsError, match="existing measurements"):
        export(db, destination, reference_date=date(2026, 10, 28))
