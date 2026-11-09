"""Computed sorting explanations, authored CPU regressions after disclosure."""
import copy
import pytest
from test_v021r3_explanation_repair import source,ask,words
from edu_tutor.lessons.requested_explanations import ordering_comparisons


@pytest.mark.parametrize('column,direction,null_first',[('reading','ASC',True),('units','DESC',False)])
def test_sort_uses_original_values_null_policy_and_first_different_key(column,direction,null_first):
    rows=[['C',None,1],['A',3,1],['B',3,1],['D',0,2]]
    m,lesson=source(rows=rows,column=column,query=f'SELECT label,{column},priority FROM observations ORDER BY priority ASC,{column} {direction},label ASC')
    before=copy.deepcopy(m)
    result=ask(m,lesson,'선택한 행의 정렬 우선순위와 동점 처리까지 설명해 줘.',row=1)
    assert result['speech_allowed'],result
    item=next(i for i in result['explanation_fulfillment']['items'] if i['kind']=='ordering')
    detail=item['evidence']['original_row_comparisons']
    assert detail['null_placement'][0]['nulls_first'] is null_first
    assert detail['null_placement'][0]['source_row_ids']==[m['evidence']['working_tables'][0]['row_ids'][0]]
    tie=next(p for p in detail['adjacent_pairs'] if p['first_different_key']=='label')
    assert tie['equal_prefix_length']==2 and tie['left_values']==[1,3,'A'] and tie['right_values']==[1,3,'B']
    assert f'{column} {"오름차순" if direction=="ASC" else "내림차순"}' in words(result)
    assert 'NULL을 '+('앞' if null_first else '뒤')+'에' in words(result)
    assert 'label=A' in words(result) and 'label=B' in words(result)
    assert '현재 결과에는 모든 정렬 키가 같은 행이 없습니다' in words(result)
    boards=[a for s in result['plan']['steps'] for a in s['board_actions'] if a.get('type')=='table' and '처음 다른 기준' in a.get('columns',[])]
    assert boards and any('A / B' in row for board in boards for row in board['rows'])
    assert all(len(s['speech'])<=220 for s in result['plan']['steps']) and len(result['plan']['steps'])<=12
    assert m==before


@pytest.mark.parametrize('value',[None,0,-4])
def test_complete_key_ties_do_not_claim_a_total_order(value):
    m,lesson=source(rows=[['second',value,1],['first',value,1],['other',7,2]],
        query='SELECT label,reading FROM observations ORDER BY priority ASC,reading DESC')
    result=ask(m,lesson,'정렬에서 동점인 행의 순서도 설명해 줘.')
    assert result['speech_allowed'],result
    item=next(i for i in result['explanation_fulfillment']['items'] if i['kind']=='ordering')
    detail=item['evidence']['original_row_comparisons']
    assert detail['complete_tie_pair_count']==1
    tie=next(p for p in detail['adjacent_pairs'] if p['first_different_key'] is None)
    assert tie['order_comparison']==0 and '순서 미지정' in tie['decision']
    assert '두 행 사이 순서는 미지정' in words(result)
    assert '현재 결과에는 모든 정렬 키가 같은 행이 없습니다' not in words(result)


def test_excluded_comparison_row_never_enters_order_trace():
    m,lesson=source(rows=[['kept',2,1],['excluded',None,1],['higher',4,1]])
    result=ask(m,lesson,'왜 선택한 행이 포함돼? NULL행과 비교하고 정렬 동점도 설명해 줘.')
    assert result['speech_allowed'],result
    detail=next(i for i in result['explanation_fulfillment']['items'] if i['kind']=='ordering')['evidence']['original_row_comparisons']
    table=m['evidence']['working_tables'][0]
    assert table['row_ids'][1] not in detail['ordered_source_row_ids'] and detail['null_placement']==[]


def test_duplicate_text_labels_use_original_row_numbers_instead_of_guessing():
    m,_=source(rows=[['same',2,1],['same',1,1]],query='SELECT label,reading FROM observations ORDER BY reading DESC')
    detail=ordering_comparisons(m['evidence']['logical_steps'],m['evidence']['working_tables'][0])
    assert detail['adjacent_pairs'][0]['before_label']=='원본 1행'
    assert detail['adjacent_pairs'][0]['after_label']=='원본 2행'


@pytest.mark.parametrize('rows',[[],[['only',None,1]]])
def test_zero_or_one_remaining_row_does_not_invent_comparison(rows):
    m,_=source(rows=rows,query='SELECT label,reading FROM observations ORDER BY reading DESC')
    detail=ordering_comparisons(m['evidence']['logical_steps'],m['evidence']['working_tables'][0])
    assert detail['adjacent_pairs']==[]
    assert any('비교할 두 행이 없습니다' in t for t in detail['sentences'])


def test_no_order_by_does_not_claim_an_ordering_proof():
    m,_=source(query='SELECT label,reading FROM observations')
    assert ordering_comparisons(m['evidence']['logical_steps'],m['evidence']['working_tables'][0]) is None


def test_reversed_verified_order_cannot_create_a_false_explanation():
    m,_=source()
    logical=copy.deepcopy(m['evidence']['logical_steps']);logical['ordered_row_ids'].reverse()
    with pytest.raises(ValueError,match='SQL 결과 순서'):
        ordering_comparisons(logical,m['evidence']['working_tables'][0])
