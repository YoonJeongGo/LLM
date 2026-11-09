"""Executed operation supplies trusted DDL/DML labels; no model calls."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

from edu_tutor.problems.models import normalize_problem

@pytest.fixture
def concept_plan():
    from edu_tutor.lessons.verified import concept_plan
    return concept_plan


@pytest.mark.parametrize('sql, operation, category', [
    ('CREATE TABLE fixture(v INTEGER);', 'create_table', 'DDL'),
    ('CREATE TABLE fixture(v INTEGER); INSERT INTO fixture VALUES(-7);', 'insert_rows', 'DML'),
    ('CREATE TABLE fixture(v INTEGER); ALTER TABLE fixture ADD COLUMN label TEXT;', 'add_column', 'DDL'),
    ('CREATE TABLE fixture(v INTEGER); INSERT INTO fixture VALUES(0); UPDATE fixture SET v=4;', 'update_values', 'DML'),
    ('CREATE TABLE fixture(v INTEGER); DROP TABLE fixture;', 'drop_table', 'DDL')])
def test_executed_operation_supplies_classification_without_rewriting_evidence(concept_plan, sql, operation, category):
    raw = '설명용 새 예시\n```sql\n'+sql+'\n```'
    item = {'id': 'cpu', 'content': raw, 'raw_model_response': raw, 'sources': [],
            'problem': normalize_problem({'task_kind': 'concept', 'raw_text': '구조와 행 데이터를 설명해 줘.', 'dialect': 'sqlite', 'confirmed': True})}
    before = copy.deepcopy(item)
    result = concept_plan(item, item['problem']['raw_text'], 'cpu-lesson')
    evidence = result['example_evidence']['steps'][-1]
    speech = result['plan']['steps'][-1]['speech']
    assert evidence['operation'] == operation and evidence['execution_status'] == 'executed_in_disposable_sqlite'
    assert speech.startswith(evidence['narration']+' ')
    assert speech.count(category+'입니다.') == 1
    assert ('DML' if category == 'DDL' else 'DDL')+'입니다.' not in speech
    assert 'DDL입니다.' not in evidence['narration'] and 'DML입니다.' not in evidence['narration']
    assert speech in result['plan']['final_summary']
    assert result['generation']['operation_classification'] == 'ddl_dml_from_executed_operation_v1'
    assert item == before

