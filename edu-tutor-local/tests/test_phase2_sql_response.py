"""CPU formatting/safety regression; never a model accuracy benchmark."""
import json

import pytest

from edu_tutor.evaluation.sql_sandbox import execute_sql, extract_sql
from edu_tutor.problems.sql_response import SQL_EXTRACTION_PROTOCOL, extract_sql_candidate


def fenced(value):
    return '```json\n'+json.dumps(value,ensure_ascii=False)+'\n```'


@pytest.mark.parametrize('output',[
    {'sql':'SELECT 1','explanation':'plain dict'},
    '{"sql":"SELECT 1","explanation":"plain JSON"}',
    '```sql\nSELECT 1\n```',
])
def test_existing_accepted_formats_keep_the_frozen_extractor_result(output):
    assert extract_sql_candidate(output)==extract_sql(output)=='SELECT 1'


def test_one_complete_json_fence_accepts_escaped_sql_and_crlf():
    sql="SELECT 'a\"b' AS value"
    output=fenced({'sql':sql,'explanation':'설명에 \\"가 있습니다.','schema_version':1})
    assert extract_sql_candidate(output)==sql
    assert extract_sql_candidate(output.replace('json','JSON').replace('\n','\r\n'))==sql
    assert SQL_EXTRACTION_PROTOCOL=='v021_sql_response_v3_json_prefix_plain_suffix'
    with pytest.raises(ValueError):extract_sql(output)


@pytest.mark.parametrize('output',[
    '{"sql":"SELECT 1","sql":"SELECT 2"}',
    '{"sql":"SELECT 1","explanation":"one","explanation":"two"}',
    '```json\n{"sql":"SELECT 1","sql":"SELECT 2"}\n```',
    fenced({'sql':'SELECT 1','expected_rows':[[1]]}),
    fenced({'sql':'SELECT 1','oracle':'not allowed'}),
    fenced([{'sql':'SELECT 1'}]),
    fenced({'sql':None}),
    fenced({'sql':5}),
    fenced({'sql':'   '}),
    fenced({'explanation':'no SQL'}),
    '```json\n{"sql":"SELECT 1"}\n',
    '```json\n{"sql":"SELECT 1"\n```',
    '```json\n{"sql":"SELECT 1"} {"sql":"SELECT 2"}\n```',
    fenced({'sql':'SELECT 1'})+'\n'+fenced({'sql':'SELECT 2'}),
    fenced({'sql':'SELECT 1'})+'\n```sql\nSELECT 2\n```',
    '```sql\nSELECT 2\n```\n'+fenced({'sql':'SELECT 1'}),
    '앞의 다른 답을 선택하세요\n'+fenced({'sql':'SELECT 1'}),
    fenced({'sql':'SELECT 1'})+'\n추가 후보: SELECT 2',
    '```javascript\n{"sql":"SELECT 1"}\n```',
    '```\n{"sql":"SELECT 1"}\n```',
])
def test_incomplete_ambiguous_or_extra_payload_is_not_guessed(output):
    with pytest.raises(ValueError):extract_sql_candidate(output)


@pytest.mark.parametrize('sql',[
    "ATTACH DATABASE 'not-created.sqlite3' AS external",
    'PRAGMA writable_schema=ON',
    "SELECT load_extension('bad-extension')",
    'SELECT 1; DROP TABLE sample;',
    'WITH x AS (SELECT 1) DELETE FROM sample',
])
def test_json_fence_does_not_bypass_unchanged_sql_safety(sql):
    parsed=extract_sql_candidate(fenced({'sql':sql}))
    assert parsed==sql
    result=execute_sql(parsed,{'tables':[{'name':'sample','columns':[{'name':'v','type':'INTEGER'}],'rows':[[1]]}]})
    assert result['status']!='executed'


def test_format_support_does_not_supply_unconfirmed_group_and_sort_intent():
    from edu_tutor.problems.evidence import check_intent, verify_answer, display_answer
    from edu_tutor.problems.models import normalize_problem
    from edu_tutor.lessons.verified import generate_verified_plan
    problem=normalize_problem({'task_kind':'write_sql','dialect':'sqlite','confirmed':True,
        'raw_text':'v를 그룹별로 세어 오름차순으로 정렬해 줘.',
        'tables':[{'name':'sample','columns':[{'name':'v','type':'INTEGER'}],'rows':[[1],[None],[1]]}]})
    sql=extract_sql_candidate(fenced({'sql':'SELECT v, COUNT(*) FROM sample GROUP BY v ORDER BY v'}))
    intent,_=check_intent(sql,problem,problem['raw_text'])
    assert intent['status']=='needs_input'
    assert intent['scope'].startswith('입력 의도 확인 필요:')
    evidence=verify_answer(problem,fenced({'sql':sql}),problem['raw_text'])
    assert evidence['status']==evidence['support_status']==evidence['intent']['status']=='needs_input'
    assert evidence['execution']['status']=='not_run' and evidence['result'] is None
    assert evidence['logical_steps'] is None and evidence['can_repair'] is False
    lesson=generate_verified_plan({'id':'unresolved-sort','problem':problem,'evidence':evidence,
        'content':display_answer(evidence)},problem['raw_text'],'unresolved-sort-lesson')
    assert lesson['plan'] is None and lesson['speech_allowed'] is False


def test_supported_count_uses_json_fence_then_existing_intent_and_execution():
    from edu_tutor.problems.evidence import verify_answer
    from edu_tutor.problems.models import normalize_problem
    problem=normalize_problem({'task_kind':'write_sql','dialect':'sqlite','confirmed':True,
        'raw_text':'점수가 있는 사람 수를 구해 줘.',
        'tables':[{'name':'sample','columns':[{'name':'score','type':'INTEGER'}],'rows':[[20],[None],[80]]}]})
    raw=fenced({'sql':'SELECT COUNT(score) FROM sample'})
    evidence=verify_answer(problem,raw,problem['raw_text'])
    assert evidence['status']=='verified' and evidence['result']['rows']==[[2]]
    assert evidence['sql_extraction_protocol']==SQL_EXTRACTION_PROTOCOL
