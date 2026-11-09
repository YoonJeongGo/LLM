import json

from edu_tutor.training.finish_claims import check_explicit_result_claim


def sample(explanation):
    return {'id':'cpu_fixture','sql':'SELECT COUNT(v) FROM values_table',
        'actual_answer':json.dumps({'sql':'SELECT COUNT(v) FROM values_table','explanation':explanation},ensure_ascii=False),
        'actual':{'status':'executed','columns':['n'],'rows':[[4]]}}


def test_correct_sql_result_does_not_validate_an_inconsistent_explanation():
    checked=check_explicit_result_claim(sample('NULL을 제외합니다. 결과 [[3]]입니다.'))
    assert checked['explicit_numeric_mismatch']
    assert checked['claims'][0]['claimed_rows']==[[3]]
    assert checked['full_explanation_quality']=='H_PENDING'


def test_matching_or_unparseable_claims_are_not_general_explanation_passes():
    checked=check_explicit_result_claim(sample('결과 [[4]]입니다.'))
    assert not checked['explicit_numeric_mismatch'] and checked['human_review']=='H_PENDING'
    absent=check_explicit_result_claim(sample('NULL인 행만 센다는 잘못된 문장.'))
    assert not absent['claims'] and absent['full_explanation_quality']=='H_PENDING'
    invalid=check_explicit_result_claim(sample('결과 [[unquoted]]입니다.'))
    assert invalid['claims'][0]['matches_sql_execution'] is None
