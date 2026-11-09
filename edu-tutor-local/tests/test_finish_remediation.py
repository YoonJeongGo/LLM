from copy import deepcopy

import pytest

from edu_tutor.training.finish_data import exercise
from edu_tutor.training.finish_remediation import restate, diversify


@pytest.mark.parametrize('family', ['count_all','count_value','boolean_sum','null','nonnull','zero','sum','average'])
def test_restated_explanations_keep_original_family_data_and_sql(family):
    record,_=exercise(family,7,'train');before=deepcopy(record)
    changed,proof=restate(record)
    assert record==before
    assert changed['fixture']==record['fixture'] and changed['expected']==record['expected']
    assert changed['problem_family_id']==record['problem_family_id'] and changed['split']=='train'
    assert proof['sqlite_rows']==proof['independent_rows']
    assert changed['messages'][-1]['content']!=record['messages'][-1]['content']
    assert '평문' in changed['messages'][-2]['content']


def test_count_prose_is_computed_not_fixed_to_original_row_counts():
    record,_=exercise('count_value',2,'train')
    record['fixture']['tables'][0]['rows']=[[71,'새',0],[72,'새',None],[73,'다른',None]]
    record['expected']['rows']=[[1]]
    changed,proof=restate(record)
    assert proof['claims']['nonnull_count']==1 and proof['claims']['excluded_null_count']==2
    assert 'NULL이 아닌 값 1개' in changed['messages'][-1]['content']
    assert 'NULL 2개만 제외' in changed['messages'][-1]['content']


def test_validation_and_unknown_families_cannot_enter_restatement_path():
    record,_=exercise('count_value',0,'validation')
    with pytest.raises(ValueError,match='training families'):restate(record)


@pytest.mark.parametrize('family', ['count_all','count_value','boolean_sum','null','nonnull','zero','sum','average'])
def test_diverse_nonempty_subsets_keep_schema_query_and_original_value_pool(family):
    record,_=exercise(family,9,'train')
    lengths=[];values=[]
    for variant in range(5):
        staged,layout=diversify(record,variant)
        changed,proof=restate(staged)
        table=changed['fixture']['tables'][0]
        assert all(row in record['fixture']['tables'][0]['rows'] for row in table['rows'])
        assert changed['expected']['sql']==record['expected']['sql']
        assert proof['independent_rows']==proof['sqlite_rows']
        assert len(layout)==len(table['rows'])
        lengths.append(len(table['rows']));values.append(proof['independent_rows'])
    assert lengths==[1,2,3,6,8]
    if family in {'count_all','count_value','boolean_sum','sum','average'}:
        assert any(value!=values[0] for value in values[1:])
    record,_=exercise('project',0,'train')
    with pytest.raises(ValueError,match='training families'):restate(record)
