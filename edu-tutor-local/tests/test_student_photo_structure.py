"""Saved OCR/program checks; no vision model or human review."""
import pytest
from edu_tutor.vision.structure import structure_candidate

def test_collapsed_spacing_parses_actual_typed_rows_without_inventing_values():
    text='marks(person TEXT, points INTEGER)\n이름(person) 점수(points)\n하람 17\n다솔 NULL\n미래 -4\nSELECT AVG(points) FROM marks;\n설명 999'
    result=structure_candidate({'original_text':text})
    assert result['tables'][0]['rows']==[['하람',17],['다솔',None],['미래',-4]]
    assert result['original_text']==text
    assert result['structure_extraction']['status']=='candidate_requires_confirmation'
    assert result['structure_extraction']['accuracy']=='not_established'

@pytest.mark.parametrize('bad',[
    '하람 17\n다 솔 20', '하람 17\n다솔 [읽기 불가]', '하람 17\n다솔',
    '하람 17\n다솔 이십',
])
def test_broken_or_ambiguous_row_prevents_partial_table(bad):
    result=structure_candidate({'original_text':'marks(person TEXT, points INTEGER)\n'+bad+'\nSELECT SUM(points) FROM marks;'})
    assert not result.get('tables')

def test_two_text_columns_need_explicit_delimiters():
    assert not structure_candidate({'original_text':'places(city TEXT, country TEXT)\nNew York USA'}).get('tables')

def test_missing_schema_or_condition_is_not_inferred():
    from edu_tutor.vision.conditions import check_transcription
    result=check_transcription(structure_candidate({'original_text':'하람 17 / 다솔 NULL\nSELECT COUNT(*) FROM marks\nWHERE points >='}))
    assert not result.get('tables') and not result.get('sql')
    assert result['missing_conditions']


def test_visible_markdown_grid_is_only_a_type_inferred_confirmation_candidate():
    text='테이블: receipts\n| code | cost |\n| --- | ---: |\n| A | 0 |\n| B | NULL |\n| C | -2.5 |\nSELECT SUM(cost) FROM receipts;'
    result=structure_candidate({'original_text':text, 'confirmed':False})
    assert result['tables']==[{'name':'receipts','columns':[{'name':'code','type':'TEXT'},{'name':'cost','type':'REAL'}],
                              'rows':[['A',0.0],['B',None],['C',-2.5]]}]
    assert result['original_text']==text and not result['confirmed']
    extraction=result['structure_extraction']
    assert extraction['requires_confirmation'] and extraction['accuracy']=='not_established'
    assert all(not item['source_type_visible'] for item in extraction['type_inferences'])


def test_grid_literal_strings_and_all_null_column_do_not_gain_unseen_source_types():
    text="| token | unknown |\n| --- | --- |\n| 'NULL' | NULL |\n| '007' | NULL |\nSELECT COUNT(*) FROM tokens;"
    result=structure_candidate({'original_text':text})
    assert result['tables'][0]['rows']==[['NULL',None],['007',None]]
    assert result['structure_extraction']['type_inferences'][1]['basis']=='all_NULL_affinity_unknown'


@pytest.mark.parametrize('grid,sql,reason',[
    ('| x | value |\n| --- | --- |\n| A | 1 |\n| B | |','SELECT SUM(value) FROM t;','missing_or_unreadable'),
    ('| x | value |\n| --- | --- |\n| A | 1 |\n| B | [확인 필요] |','SELECT SUM(value) FROM t;','missing_or_unreadable'),
    ('| x | value |\n| --- | --- |\n| A | 1 |\n| B |','SELECT SUM(value) FROM t;','malformed_grid'),
    ('| x | value |\n| --- | --- |\n| A | 1 |\nB 2','SELECT SUM(value) FROM t;','ambiguous_grid_boundary'),
    ('| x | X |\n| --- | --- |\n| A | 1 |','SELECT COUNT(*) FROM t;','column_headers'),
    ('| x | value |\n| --- | --- |\n| A | 1 |','SELECT * FROM t JOIN u ON t.x=u.x;','unambiguous'),
    ('| x | value |\n| --- | --- |\n| A | 1 |','SELECT * FROM t a, u b;','multiple_SQL_sources'),
    ('테이블: other\n| x | value |\n| --- | --- |\n| A | 1 |','SELECT COUNT(*) FROM t;','disagree'),
    ('| x | value |\n| --- | --- |\n| A | 1 |\n\n| x | value |\n| --- | --- |\n| B | 2 |','SELECT COUNT(*) FROM t;','multiple_grids'),
])
def test_ambiguous_grid_is_not_silently_repaired_or_partially_published(grid,sql,reason):
    result=structure_candidate({'original_text':grid+'\n'+sql})
    assert not result.get('tables')
    assert reason in result['structure_extraction']['reason']


def test_visible_grid_does_not_complete_a_cropped_condition():
    from edu_tutor.vision.conditions import check_transcription
    text='| item | balance |\n| --- | --- |\n| pen | 8 |\n| pad | 2 |\nSELECT item FROM supplies\nWHERE balance >='
    result=check_transcription(structure_candidate({'original_text':text,'confirmed':False}))
    assert result['tables'][0]['rows']==[['pen',8],['pad',2]]
    assert not result.get('sql') and result['missing_conditions'] and result['original_text']==text

def test_restructure_retains_original_and_history_invalidates_lesson_without_model(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from edu_tutor.api import create_app
    from edu_tutor.storage.db import Store
    from edu_tutor.models import runtime
    monkeypatch.setattr(runtime,'run_worker',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('No model allowed')))
    app=create_app(tmp_path)
    store=Store(tmp_path)
    raw='marks(person TEXT, points INTEGER)\n하람 17\n다솔 NULL\nSELECT AVG(points) FROM marks;'
    photo={'id':'test-photo','original_text':raw,'question':raw,'sql':'','tables':[], 'choices':[],
           'unreadable_regions':[],'missing_conditions':[],'confirmed':True,'revision':2,'history':[]}
    store.put('photos',photo)
    store.put('lessons',{'id':'old','problem':{'source':{'photo_id':'test-photo'}},'valid':True})
    token=(tmp_path/'.local/auth-token').read_text(encoding='utf-8').strip()
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert client.post('/api/photos/test-photo/restructure').status_code==401
        response=client.post('/api/photos/test-photo/restructure',headers={'Authorization':'Bearer '+token})
        assert response.status_code==200,response.text
        changed=response.json()
        assert changed['original_text']==raw and not changed['confirmed'] and changed['revision']==3
        assert changed['history'][-1]['tables']==[] and changed['tables'][0]['rows']==[['하람',17],['다솔',None]]
        assert store.get('lessons','old')['valid'] is False
        assert not store.list('jobs')
