from copy import deepcopy
import json

import pytest

from edu_tutor.training.finish_data import exercise
from edu_tutor.training.finish_reason_only import strip_result_suffix


@pytest.mark.parametrize('family',['positive','count_value','sum','average','boolean_sum','having_sum','inner'])
def test_removes_only_exact_select_result_suffix_and_keeps_query_literals(family):
    original,_=exercise(family,3,'train');before=deepcopy(original)
    changed,proof=strip_result_suffix(original)
    old=json.loads(original['messages'][-1]['content']);new=json.loads(changed['messages'][-1]['content'])
    assert original==before and new['sql']==old['sql']
    assert ' 결과 [[' not in new['explanation']
    assert changed['expected']==original['expected'] and changed['fixture']==original['fixture']
    assert proof['removed_rows']==original['expected']['rows']
    if family=='count_value':assert '0과 음수도 셉니다.' in new['explanation']
    if family in {'sum','average','boolean_sum'}:assert '중간값 [' in new['explanation']
    if family=='having_sum':assert 'HAVING SUM(val) > 1' in new['sql']


@pytest.mark.parametrize('family',['create','insert','update','delete'])
def test_keeps_ddl_dml_literals_and_only_removes_documented_result_rows(family):
    original,proof=exercise(family,2,'train')
    changed,change=strip_result_suffix(original,concept_proof=proof)
    if family=='create':
        assert changed==original and '0개' in changed['messages'][-1]['content']
    else:
        sql=proof['intermediate']['sql']
        assert changed['messages'][-1]['content'].startswith(sql+'; ')
        assert '결과 행은' not in changed['messages'][-1]['content']
        assert change['before_rows']==proof['intermediate']['before']
    assert changed['messages'][:-1]==original['messages'][:-1]


def test_mismatched_or_arbitrary_numeric_text_is_rejected_not_deleted():
    original,_=exercise('count_value',0,'train')
    parsed=json.loads(original['messages'][-1]['content'])
    parsed['explanation']='COUNT의 개념 42를 임의로 삭제하지 마세요. 결과 [[999]]입니다.'
    original['messages'][-1]['content']=json.dumps(parsed,ensure_ascii=False)
    with pytest.raises(ValueError,match='exact documented'):
        strip_result_suffix(original)
