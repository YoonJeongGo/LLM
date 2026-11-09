"""CPU-only semantic checks for Korean condition speech and original cells."""
import copy

import pytest

from edu_tutor.lessons.conditions import simple_where_speech
from edu_tutor.problems.models import normalize_problem
from test_selected_row_lessons import answer, development_problem, supplement


@pytest.mark.parametrize("predicate,actual,passed,spoken",[
    ("amount = 7",7,True,"2열이 7인 조건"),("amount = 7",8,False,"2열이 7인 조건"),
    ("amount <> 7",8,True,"2열이 7이 아닌 조건"),("amount != 7",7,False,"2열이 7이 아닌 조건"),
    ("amount > 7",8,True,"2열이 7보다 큰 조건"),("amount > 7",7,False,"2열이 7보다 큰 조건"),
    ("amount >= 7",7,True,"2열이 7 이상인 조건"),("amount >= 7",6,False,"2열이 7 이상인 조건"),
    ("amount < 7",6,True,"2열이 7보다 작은 조건"),("amount < 7",7,False,"2열이 7보다 작은 조건"),
    ("amount <= 7",7,True,"2열이 7 이하인 조건"),("amount <= 7",8,False,"2열이 7 이하인 조건"),
    ("amount IS NULL",None,True,"2열이 널인 조건"),("amount IS NULL",0,False,"2열이 널인 조건"),
    ("amount IS NOT NULL",0,True,"2열이 널이 아닌 조건"),("amount IS NOT NULL",None,False,"2열이 널이 아닌 조건"),
    ("amount >= 7",None,False,"2열이 7 이상인 조건"),
    ("amount > -3",-2,True,"2열이 마이너스 3보다 큰 조건"),
    ("amount <= 1.25",1.25,True,"2열이 1.25 이하인 조건"),
])
def test_comparison_words_and_values_match_independent_sql_membership(predicate,actual,passed,spoken):
    p=normalize_problem({"task_kind":"query_result","confirmed":True,"raw_text":"독립 개발 검증용 조건 비교",
        "query":"SELECT COUNT(*) FROM readings WHERE "+predicate,
        "tables":[{"name":"readings","columns":[{"name":"name","type":"TEXT"},{"name":"amount","type":"REAL"}],
            "rows":[["새 예시",actual]]}]})
    message=answer(p,0,0,stage=0)
    evidence=message["evidence"]
    assert evidence["result"]["rows"]==[[int(passed)]]
    result=supplement(message);unit=result["plan"]["steps"][0]
    assert spoken in unit["speech"]
    assert ("포함됩니다" if passed else "제외됩니다") in unit["speech"]
    assert "amount" not in unit["speech"] and "WHERE" not in unit["speech"]
    expected_cell=evidence["working_tables"][0]["cell_ids"][0][1]
    highlight=next(a for a in unit["board_actions"] if a["type"]=="highlight")
    assert highlight["cell_ids"][0]==expected_cell
    board=next(a["text"] for a in unit["board_actions"] if a["type"]=="text")
    assert unit["speech"] in board and "원본 열 amount" in board
    assert evidence["logical_steps"]["where_sql"] in board


@pytest.mark.parametrize("predicate",["attended=1 AND score>20","attended BETWEEN 0 AND 1","attended=score", "1=attended", "team > '가'", "attended = NULL"])
def test_unsupported_predicate_is_not_paraphrased_or_silently_simplified(predicate):
    p=development_problem();p["query"]="SELECT COUNT(*) FROM study_results WHERE "+predicate
    message=answer(p,0,stage=0)
    result=supplement(message);unit=result["plan"]["steps"][0]
    assert "지원 범위 밖" in unit["speech"]
    assert "조건을 만족" not in unit["speech"] and "WHERE" not in unit["speech"]
    board=next(a["text"] for a in unit["board_actions"] if a["type"]=="text")
    assert message["evidence"]["logical_steps"]["where_sql"] in board


def test_qualified_column_and_text_equality_bind_to_visible_column_without_hardcoded_schema():
    p=development_problem();p["query"]="SELECT COUNT(*) FROM study_results AS s WHERE s.team='홍'"
    message=answer(p,5,0,stage=0)
    speech=supplement(message)["plan"]["steps"][0]["speech"]
    assert "2열 값은 문자 홍" in speech and "2열이 문자 홍인 조건" in speech
    assert "포함됩니다" in speech


def test_real_failure_shape_gets_short_korean_speech_but_keeps_full_source_evidence():
    message=answer(development_problem(),0,3,stage=0)
    preserved=copy.deepcopy(message)
    result=supplement(message);unit=result["plan"]["steps"][0]
    assert unit["speech"]=="원본 1행의 4열 값은 1입니다. 4열이 1인 조건을 만족해 집계 입력에 포함됩니다."
    assert len(unit["speech"])<60
    assert message==preserved
    board=next(a["text"] for a in unit["board_actions"] if a["type"]=="text")
    assert "WHERE attended = 1" in board and "SUM(score)는 60" in board and "HAVING SUM(score) >= 50" in board


def test_sqlite_text_affinity_ordering_is_not_spoken_as_numeric_comparison():
    p=normalize_problem({"task_kind":"query_result","confirmed":True,"raw_text":"개발 검증용 문자 열 비교",
        "query":"SELECT COUNT(*) FROM entries WHERE token > 10", "tables":[{"name":"entries",
        "columns":[{"name":"token","type":"TEXT"}],"rows":[["2"]]}]})
    message=answer(p,0,stage=0)
    assert message["evidence"]["result"]["rows"]==[[1]]
    speech=supplement(message)["plan"]["steps"][0]["speech"]
    assert "지원 범위 밖" in speech and "10보다 큰" not in speech
