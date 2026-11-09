import json

import pytest

from edu_tutor.problems.evidence import verify_answer
from edu_tutor.problems.models import infer_basic_intent, intent_question_text, normalize_problem


def problem():
    return normalize_problem({"task_kind": "write_sql", "confirmed": True, "dialect": "sqlite",
        "raw_text": "val의 서로 다른 값 개수를 구해 줘.",
        "tables": [{"name": "readings", "columns": [{"name": "tag", "type": "TEXT"},
                    {"name": "val", "type": "INTEGER"}],
                    "rows": [["west", 2], ["east", None], ["west", 0], ["west", 2]]}]})


@pytest.mark.parametrize("prefix,suffix", [("SQLite. ", ". val의 서로 다른 값 개수를 구해 줘."),
    ("", "\nval의 서로 다른 값 개수를 구해 줘."),
    ("원본: ", "; val의 서로 다른 값 개수를 구해 줘.")])
def test_exact_inline_data_does_not_become_a_numeric_condition(prefix, suffix):
    p = problem()
    source = 'readings(tag,val)=' + json.dumps(p["tables"][0]["rows"], ensure_ascii=False)
    p["raw_text"] = prefix + source + suffix
    stripped = intent_question_text(p, p["raw_text"])
    assert stripped == prefix + " " + suffix
    intent, _ = infer_basic_intent(p, p["raw_text"])
    assert intent["aggregates"] == [{"function": "count", "column": "val", "distinct": True}]
    answer = json.dumps({"sql": "SELECT COUNT(DISTINCT val) FROM readings"})
    evidence = verify_answer(p, answer, p["raw_text"])
    assert evidence["status"] == "verified" and evidence["result"]["rows"] == [[2]]
    assert source in p["raw_text"]


@pytest.mark.parametrize("condition", [" val이 0보다 큰 행만 세어 줘.",
    " WHERE val > 0의 COUNT(val)을 구해 줘.", " west 행만 COUNT(val)을 구해 줘."])
def test_following_numeric_or_named_filter_is_never_stripped(condition):
    p = problem()
    source = 'readings(tag,val)=' + json.dumps(p["tables"][0]["rows"])
    text = source + condition
    assert intent_question_text(p, text).endswith(condition)
    assert infer_basic_intent(p, text)[0] is None


@pytest.mark.parametrize("source", ['readings(tag,val)=[["west",999]]',
    'readings(val,tag)=[["west",2],["east",null],["west",0],["west",2]]',
    'other(tag,val)=[["west",2]]', 'readings(tag,val)=[["west",2], BROKEN'])
def test_different_or_malformed_table_is_not_accepted_as_original(source):
    p = problem()
    text = source + ' COUNT(val)을 구해 줘.'
    assert intent_question_text(p, text) == text
    assert infer_basic_intent(p, text)[0] is None
