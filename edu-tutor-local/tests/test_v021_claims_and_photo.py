import json
from edu_tutor.problems.pipeline import from_photo
from edu_tutor.problems.response_claims import audit_model_explanation
from edu_tutor.training.finish_claims import check_explicit_result_claim

def evidence():
    return {"id":"dev-claim", "sql":"SELECT n FROM t ORDER BY n",
        "execution":{"status":"executed","columns":["n"],"rows":[[0],[2]]}}

def test_wrong_array_is_never_promoted_to_verified_speech():
    raw=json.dumps({"sql":"SELECT n FROM t ORDER BY n","explanation":"결과 [[2], [0]]입니다."})
    r=audit_model_explanation(raw,evidence())
    assert r["status"]=="detected_contradiction"
    assert r["explicit_result_claims"]["explicit_numeric_mismatch"]
    assert not r["raw_explanation_approved"] and not r["used_as_student_speech"]

def test_no_parseable_claim_is_not_an_explanation_pass():
    r=audit_model_explanation(json.dumps({"sql":"SELECT n FROM t","explanation":"좋은 결과입니다."}),evidence())
    assert r["status"]=="unverified_free_explanation"
    assert r["human_review"]=="H_PENDING" and not r["raw_explanation_approved"]

def test_count_star_rule_detects_only_clear_positive_false_statement():
    wrong=audit_model_explanation(json.dumps({"explanation":"COUNT(*)는 NULL인 행을 제외합니다."}),evidence())
    right=audit_model_explanation(json.dumps({"explanation":"COUNT(*)는 NULL인 행을 제외하지 않습니다."}),evidence())
    assert wrong["concept_contradictions"] and not right["concept_contradictions"]
    assert not right["raw_explanation_approved"]

def photo(question,sql=""):
    return {"id":"dev-photo","question":question,"sql":sql,"confirmed":True,"revision":3,
        "tables":[{"name":"logs","columns":[["n","INTEGER"]],"rows":[[0],[None]]}],"missing_conditions":[]}

def test_photo_writing_task_has_no_promoted_candidate_query():
    p=from_photo(photo("SQL을 작성해 주세요. 출력 열: n; 행 조건: n IS NOT NULL"))
    assert p["task_kind"]=="write_sql" and "query" not in p
    assert p["source"]=={"kind":"photo","photo_id":"dev-photo"} and p["revision"]==3

def test_photo_given_sql_remains_student_query_with_missing_conditions():
    source=photo("이 SQL의 결과를 설명해 주세요.","SELECT n FROM logs WHERE n >=")
    source["missing_conditions"]=["비교할 기준값이 사진에서 잘렸습니다."]
    p=from_photo(source)
    assert p["task_kind"]=="query_result" and p["query"]==source["sql"]
    assert p["missing_conditions"]==source["missing_conditions"]

def test_historical_claim_api_is_still_available():
    r=check_explicit_result_claim({"id":"old","actual_answer":"not JSON","actual":{}})
    assert r["status"]=="structured_explanation_unavailable"

