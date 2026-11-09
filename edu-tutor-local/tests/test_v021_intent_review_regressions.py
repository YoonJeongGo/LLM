"""Disclosed v1 failure and read-only review regressions, not a new holdout."""
import pytest
from edu_tutor.problems.models import normalize_problem, infer_basic_intent


def problem(q):
    return normalize_problem({'task_kind':'write_sql','raw_text':q,'confirmed':True,
        'tables':[{'name':'inventory','columns':[{'name':'code','type':'INTEGER'},
            {'name':'units','type':'INTEGER'},{'name':'price','type':'REAL'}],
            'rows':[[1,None,1.5],[2,0,-3.2],[3,7,0.0]]}]})


@pytest.mark.parametrize('prefix',[
    'SQLite의 inventory 표를 사용합니다. ',
    'inventory 테이블에서 조회합니다. ',
    '원본 표 inventory를 사용하세요. ',
])
@pytest.mark.parametrize('suffix',[
    '', ' SQL과 계산 과정을 설명해 주세요.',
    ' 요청에 맞는 SQL과 원본 행에서 결과까지의 계산 과정을 설명해 주세요.',
])
def test_confirmed_table_declaration_and_explanation_request_are_not_conditions(prefix,suffix):
    q=prefix+'출력 열: code, price. 행 조건: price >= -3.2 AND units IS NOT NULL. 정렬 기준: price DESC, code ASC.'+suffix
    p=problem(q); intent,reason=infer_basic_intent(p,q)
    assert intent,reason
    assert intent['select_columns']==['code','price']
    assert intent['where']=='price >= -3.2 AND NOT units IS NULL'
    assert intent['order_by']==[{'column':'price','direction':'desc'},{'column':'code','direction':'asc'}]


@pytest.mark.parametrize('prefix,suffix',[
    ('SQLite의 different_table 표를 사용합니다. ',''),
    ('inventory와 other_table을 함께 사용합니다. ',''),
    ('units가 양수인 inventory 표를 사용합니다. ',''),
    ('',' SQL과 계산 과정을 설명하되 units가 양수인 행만 보여 주세요.'),
    ('',' 요청에 맞는 SQL과 상위 2개의 결과를 설명해 주세요.'),
    ('',' SQL과 계산 과정을 설명해 주세요. 단 code는 3이어야 합니다.'),
])
def test_additional_or_different_source_conditions_are_never_trimmed(prefix,suffix):
    q=prefix+'출력: code; 정렬: code ASC.'+suffix
    assert infer_basic_intent(problem(q),q)[0] is None


@pytest.mark.parametrize('selection',[
    'NULL을 제외한 COUNT(*)', 'NULL이 아닌 COUNT(*)',
    'NULL을 제외한 SUM(units), COUNT(*)',
    'NULL을 제외한 SUM(units), SUM(price)',
])
def test_null_exclusion_without_one_explicit_aggregate_column_needs_clarification(selection):
    q='출력: '+selection
    intent,reason=infer_basic_intent(problem(q),q)
    assert intent is None
    assert 'NULL' in reason


@pytest.mark.parametrize('selection',['NULL을 제외한 SUM(units)','NULL이 아닌 COUNT(units)'])
def test_null_modifier_on_named_single_column_aggregate_keeps_semantics(selection):
    q='출력: '+selection
    assert infer_basic_intent(problem(q),q)[0] is not None


@pytest.mark.parametrize('tie,valid',[('units',True),('price',False),('unknown',False)])
def test_named_tie_condition_must_name_the_immediately_preceding_order_key(tie,valid):
    q=f'units 내림차순, 같은 {tie}는 code 오름차순으로 code와 units를 보여 주세요.'
    assert (infer_basic_intent(problem(q),q)[0] is not None) is valid


@pytest.mark.parametrize('ending',['정렬은 지정하지 않습니다','결과 순서는 보장하지 않습니다'])
def test_explicit_unordered_sentence_keeps_all_filters(ending):
    q='SQLite의 inventory 표를 사용합니다. 출력: COUNT(*), SUM(units). 행 조건: price >= -3.2 AND units IS NOT NULL. '+ending+'. SQL과 계산 과정을 설명해 주세요.'
    intent,reason=infer_basic_intent(problem(q),q)
    assert intent,reason
    assert intent['order_by']==[] and intent['where']=='price >= -3.2 AND NOT units IS NULL'


@pytest.mark.parametrize('q',[
    '출력: code; 정렬: code ASC. 정렬은 지정하지 않습니다.',
    '출력: code; 행 조건: price >= 0. 정렬은 지정하지 않습니다. units가 양수인 것만.',
])
def test_unordered_declaration_cannot_discard_conflicts_or_extra_conditions(q):
    assert infer_basic_intent(problem(q),q)[0] is None


@pytest.mark.parametrize('q',[
    '출력: ROW_NUMBER() OVER (ORDER BY code), code',
    'inventory를 another와 JOIN해서 결과를 보여 주세요.',
    '출력: RANDOM(), code',
    'WITH 구문으로 원본 표를 묶어 집계해 주세요.',
    'CTE를 이용한 결과를 설명해 주세요.',
])
def test_clear_unsupported_operation_has_an_explicit_scope_reason(q):
    intent,reason=infer_basic_intent(problem(q),q)
    assert intent is None and '미지원' in reason


def test_language_markers_inside_string_values_are_not_removed():
    q="출력: code; 행 조건: code = 'JOIN해서. 정렬은 지정하지 않습니다.'"
    intent,reason=infer_basic_intent(problem(q),q)
    assert intent,reason
    assert "'JOIN해서. 정렬은 지정하지 않습니다.'" in intent['where']
