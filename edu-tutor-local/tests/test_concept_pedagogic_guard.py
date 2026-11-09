"""Versioned new-generation guard, disposable SQLite and fake text inference."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
import pytest

from edu_tutor.problems.ddl_examples import build_ddl_example
from edu_tutor.problems.models import normalize_problem
from edu_tutor.storage.db import Store

@pytest.fixture
def proposed():
    from edu_tutor.lessons import concepts
    return concepts


QUESTION = '열을 추가하는 것과 기존 행의 값을 바꾸는 차이를 설명해 줘.'
EMPTY = "CREATE TABLE parcel (code INTEGER, note TEXT); ALTER TABLE parcel ADD COLUMN units INTEGER; UPDATE parcel SET units=3 WHERE code=7;"
CORRECT = "CREATE TABLE parcel (code INTEGER, note TEXT); INSERT INTO parcel VALUES (7, 'ready'); ALTER TABLE parcel ADD COLUMN units INTEGER; UPDATE parcel SET units=-3 WHERE code=7;"


def message(sql, question=QUESTION):
    raw = '설명용 새 예시\n```sql\n' + sql + '\n```'
    return {'id': 'source', 'session_id': 'session', 'content': raw, 'raw_model_response': raw,
            'problem': normalize_problem({'task_kind': 'concept', 'raw_text': question, 'dialect': 'sqlite', 'confirmed': True}),
            'sources': [], 'generation_snapshot': {'adapter_id': 'base', 'model_id': 'cpu-fixture', 'revision': 'cpu-fixture-revision'}}


def invoke(proposed, tmp_path, item, *, cancel=None):
    store = Store(tmp_path)
    store.put('sessions', {'id': 'session'})
    if store.get('messages', item['id']) is None:
        store.put('messages', item)
    result = proposed.generate_concept_plan(item, item['problem']['raw_text'], 'new-lesson', root=tmp_path,
        store=store, lock=threading.RLock(), job_id='cpu-job', cancel_event=cancel or threading.Event(), generation_epoch=1)
    return result, store


def fake_generator(monkeypatch, sql):
    import edu_tutor.models.runtime as runtime
    calls = []
    def generate(messages, **kwargs):
        calls.append({'messages': messages, 'max_new_tokens': kwargs['max_new_tokens'], 'adapter': kwargs['adapter']})
        kwargs['metadata_out'].update(finish_reason='eos', adapter_id='base', model_id='cpu-fixture', revision='cpu-fixture-revision')
        yield message(sql)['raw_model_response']
    monkeypatch.setattr(runtime, 'generate', generate)
    return calls


@pytest.mark.parametrize('sql', [EMPTY,
    'CREATE TABLE counter(v INTEGER); INSERT INTO counter VALUES(0); UPDATE counter SET v=0;',
    'CREATE TABLE counter(v INTEGER); INSERT INTO counter VALUES(-2); UPDATE counter SET v=3 WHERE v=10;'])
def test_valid_sql_no_effect_is_preserved_but_new_lesson_stops(proposed, sql):
    original = message(sql)
    unchanged = copy.deepcopy(original)
    result = proposed.checked_concept_plan(original, QUESTION, 'new-lesson')
    assert build_ddl_example(original['content'])['status'] == 'verified'
    assert result['example_evidence']['status'] == 'verified'
    assert result['example_evidence']['execution']['status'] == 'executed'
    assert result['example_evidence']['steps'][-1]['effects']['changed_cells'] == []
    assert result['plan'] is None and result['speech_allowed'] is False
    assert result['pedagogic_evidence']['status'] == 'ineffective_update_illustration'
    assert result['generation']['pedagogic_guard_version'] == 1
    assert original == unchanged


def test_one_repair_effective_example_accepted_and_original_immutable(proposed, tmp_path, monkeypatch):
    original = message(EMPTY)
    calls = fake_generator(monkeypatch, CORRECT)
    result, store = invoke(proposed, tmp_path, original)
    assert len(calls) == 1 and calls[0]['max_new_tokens'] == 384 and calls[0]['adapter'] == 'base'
    sent = json.loads(calls[0]['messages'][1]['content'])
    assert sent['actual_execution_error'] is None and sent['pedagogic_failure']['status'] == 'ineffective_update_illustration'
    assert sent['raw_candidate'] == original['content']
    assert result['status'] == 'verified_example_plan' and result['speech_allowed']
    assert result['pedagogic_evidence']['status'] == 'passed'
    assert result['example_evidence']['execution']['statement_count'] == 4
    assert result['example_evidence']['steps'][-1]['effects']['changed_cells'] == [[0, 2]]
    assert result['plan']['steps'][-1]['title'] == '기존 값 바꾸기'
    assert store.get('messages', 'source') == original
    second, _ = invoke(proposed, tmp_path, original)
    assert second['speech_allowed'] and len(calls) == 1
    assert second['generation']['repair_model_calls_this_generation'] == 0
    audit = store.list('audit')[0]
    assert audit['example_model_attempts'][0]['check_result']['status'] == 'verified'
    assert audit['example_model_attempts'][0]['pedagogic_check']['status'] == 'ineffective_update_illustration'
    assert audit['example_model_attempts'][1]['pedagogic_check']['status'] == 'passed'


@pytest.mark.parametrize('repair', [EMPTY,
    'CREATE TABLE parcel (code INTEGER, note TEXT); INSERT INTO parcel VALUES(7, \'ready\'); ALTER TABLE parcel ADD COLUMN units INTEGER;',
    'CREATE TABLE parcel (code INTEGER); INSERT INTO parcel VALUES(7); UPDATE parcel SET code=8;',
    CORRECT + ' INSERT INTO parcel VALUES(8, \'late\', 1);'])
def test_noop_omitted_operation_or_over_four_repair_stops_once(proposed, tmp_path, monkeypatch, repair):
    calls = fake_generator(monkeypatch, repair)
    original = message(EMPTY)
    result, _ = invoke(proposed, tmp_path, original)
    assert result['plan'] is None and not result['speech_allowed']
    assert result['generation']['example_model_attempts'][1]['accepted'] is False
    second, _ = invoke(proposed, tmp_path, original)
    assert second['plan'] is None and len(calls) == 1


@pytest.mark.parametrize('question', ['UPDATE가 0행을 바꾸는 이유는?', '같은 값을 SET하면 어떻게 돼?', '왜 값이 안 바뀌어?', 'Explain a no-op UPDATE.'])
def test_explicit_no_effect_intent_stops_without_changing_question(proposed, tmp_path, monkeypatch, question):
    calls = fake_generator(monkeypatch, CORRECT)
    result, store = invoke(proposed, tmp_path, message(EMPTY, question))
    assert result['pedagogic_evidence']['status'] == 'unsupported_no_effect_intent'
    assert result['example_evidence']['execution']['status'] == 'executed'
    assert result['plan'] is None and not result['speech_allowed']
    assert not calls and not store.list('audit')


@pytest.mark.parametrize('count, noun', [(10, '행'), (20, 'rows')])
def test_nonzero_row_count_is_not_misread_as_zero(proposed, count, noun):
    sql = 'CREATE TABLE counter(v INTEGER); INSERT INTO counter VALUES ' + ','.join('(' + str(n) + ')' for n in range(count)) + '; UPDATE counter SET v=-1;'
    question = f'{count}{noun}의 기존 값을 바꾸는 UPDATE 예시를 보여 줘.'
    result = proposed.checked_concept_plan(message(sql, question), question, 'positive-row-count')
    assert result['pedagogic_evidence']['status'] == 'passed'
    assert result['plan'] is not None and result['speech_allowed']
    assert len(result['example_evidence']['steps'][-1]['effects']['changed_cells']) == count

