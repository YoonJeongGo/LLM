import copy
import json
from pathlib import Path

import pytest

from edu_tutor.training.data import DatasetError, load_records, validate_dataset

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def records():
    return load_records(sorted((ROOT / "data" / "demo").glob("*.jsonl")))


def test_authored_data_counts_and_status(records):
    report = validate_dataset(records=records)
    assert report["counts"] == {"test": 12, "train": 25, "validation": 8}
    assert all(r["review_status"] == "generated_unreviewed" and r["demo_only"] for r in records)
    assert report["human_review"] == "not_reviewed"


@pytest.mark.parametrize("mutation,match", [
    (lambda r: r[0].update(extra=True), "schema"),
    (lambda r: r[0]["source"].update(rights_note=" "), "rights"),
    (lambda r: r[0].update(review_status="rejected"), "rejected"),
    (lambda r: r[0].update(demo_only=False), "demo_only"),
    (lambda r: r[0]["messages"].reverse(), "single"),
    (lambda r: r[1].update(id=r[0]["id"]), "duplicate id"),
    (lambda r: r[-1].update(problem_family_id=r[0]["problem_family_id"]), "family leakage"),
    (lambda r: r[1]["messages"][0].update(content=r[0]["messages"][0]["content"]), "duplicate user"),
    (lambda r: r[0]["fixture"]["tables"][0]["rows"][0].append(0), "width"),
    (lambda r: r[0]["fixture"]["tables"][0]["rows"][0].__setitem__(1, "NULL"), "JSON null"),
    (lambda r: r[0]["fixture"]["tables"][0]["rows"][0].__setitem__(2, float("nan")), "nonfinite"),
])
def test_bad_records_are_rejected(records, mutation, match):
    mutation(records)
    with pytest.raises(DatasetError, match=match):
        validate_dataset(records=records)


def test_production_rejects_generated_data(records):
    with pytest.raises(DatasetError, match="production"):
        validate_dataset(records=records, profile="production")


def test_dataset_hash_is_independent_of_file_enumeration_order(records):
    assert validate_dataset(records=records)["sha256"] == validate_dataset(records=list(reversed(records)))["sha256"]


def test_renamed_numeric_variant_leakage(records):
    original = next(r for r in records if r["problem_family_id"] == "numeric_where_filter")
    variant = copy.deepcopy(original)
    variant.update(id="renamed", split="test", problem_family_id="different_but_leaking")
    variant["messages"][0]["content"] += " 새 이름을 쓴 변형"
    variant["messages"][1]["content"] += " 변형 정답"
    variant["expected"]["sql"] = "SELECT item_id FROM items WHERE cost > 20"
    table = variant["fixture"]["tables"][0]
    table["name"] = "items"
    table["columns"][0]["name"] = "item_id"
    table["columns"][2]["name"] = "cost"
    with pytest.raises(DatasetError, match="structural SQL family leakage"):
        validate_dataset(records=records + [variant])


def test_reference_sql_matches_authored_expected(records):
    from edu_tutor.evaluation.sql_sandbox import evaluate_sql
    checked = 0
    for record in records:
        if "expected" not in record:
            continue
        result = evaluate_sql(record["expected"]["sql"], record)
        assert result.get("result_match", result.get("match")), (record["id"], result)
        checked += 1
    assert checked == 42
