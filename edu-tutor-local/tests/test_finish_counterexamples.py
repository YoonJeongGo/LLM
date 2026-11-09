from copy import deepcopy
import json

from edu_tutor.training.finish_counterexamples import check_saved_sql


def record():
    return {'id': 'original_cpu_example', 'fixture': {'tables': [{'name': 'cells',
        'columns': [{'name': 'id', 'type': 'INTEGER'}, {'name': 'points', 'type': 'INTEGER'}],
        'rows': [[1, 2], [2, None], [3, 0], [4, -2]]}]},
        'expected': {'sql': 'SELECT COUNT(DISTINCT points) FROM cells', 'columns': ['n'],
                     'rows': [[3]], 'row_order': 'ordered'}}


def test_same_original_result_does_not_prove_distinct_semantics():
    value=record();before=deepcopy(value)
    score=check_saved_sql(value,json.dumps({'sql':'SELECT COUNT(*) FROM cells WHERE points IS NOT NULL','explanation':'fixture'}),'eos')
    assert score['counterexample_found'] and score['semantic_pass'] is None
    witness=next(p for p in score['probes'] if p['kind']=='duplicate_nonnull')
    assert witness['reference']['rows']==[[1]] and witness['actual']['rows']==[[3]]
    assert value==before
    for probe in score['probes']:
        assert [r[0] for r in probe['fixture']['tables'][0]['rows']]==[1,2,3,4]


def test_no_counterexample_is_not_a_semantic_or_human_pass():
    score=check_saved_sql(record(),json.dumps({'sql':'SELECT COUNT(DISTINCT points) FROM cells','explanation':'fixture'}),'eos')
    assert score['counterexample_found'] is False and score['checked_probes']>=4
    assert score['semantic_pass'] is None and score['human_review']=='H_PENDING'
