"""Remove redundant generated answer arrays from the SQL-format training subset.

Only exact, independently documented generator suffixes are removed. Queries,
literals, conditions, operation reasons and the40 varied plain explanations
remain. This is a data-format hypothesis, not an established cause or fix.
"""
from copy import deepcopy
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from .data import load_records, validate_dataset
from .finish_data import database, dumps


def strip_result_suffix(record, *, concept_proof=None):
    value = deepcopy(record)
    original = value['messages'][-1]['content']
    if original.startswith('{'):
        parsed = json.loads(original)
        if set(parsed) != {'sql', 'explanation'} or parsed['sql'] != value['expected']['sql']:
            raise ValueError('Expected unchanged generator SQL/explanation JSON')
        rows = value['expected']['rows']
        conn = database(value['fixture']['tables'])
        try:
            actual = [list(row) for row in conn.execute(parsed['sql'])]
        finally:
            conn.close()
        if actual != rows:
            raise ValueError('Reference rows no longer match the preserved SQL')
        suffix = ' 결과 ' + dumps(rows) + '입니다.'
        explanation = parsed['explanation']
        if not explanation.endswith(suffix):
            raise ValueError('Result-array suffix is not the exact documented generator output')
        reason = explanation[:-len(suffix)]
        if reason.endswith(','):
            # Aggregate examples have "중간값 [...], 결과 [[...]]입니다."
            # Keep the intermediate list; only remove the result-array suffix.
            reason = reason[:-1] + '입니다.'
        if not reason or not reason.endswith('.'):
            raise ValueError('Operation reason would be empty or incomplete')
        parsed['explanation'] = reason
        changed = dumps(parsed)
        proof = {'kind': 'select_result_suffix', 'removed_rows': rows,
                 'sqlite_rows': actual, 'sql_unchanged': True,
                 'intermediate_numbers_and_rule_prefix_preserved': True}
    elif value['concept'] in {'insert', 'update', 'delete'}:
        if not concept_proof or concept_proof.get('id') != value['id'] or not concept_proof.get('passed'):
            raise ValueError('The matching original isolated SQLite mutation proof is required')
        middle = concept_proof['intermediate']
        suffix = ' 결과 행은 ' + dumps(middle['after']) + '입니다.'
        if not original.endswith(suffix) or not original.startswith(middle['sql'] + '; '):
            raise ValueError('Mutation SQL or documented result-array suffix changed')
        match = re.match(r'(?:INSERT INTO|UPDATE|DELETE FROM) ([A-Za-z_][A-Za-z_0-9]*)\b', middle['sql'])
        if not match or middle['columns'] != ['id', 'val']:
            raise ValueError('Original bounded DML fixture schema changed')
        with sqlite3.connect(':memory:') as conn:
            name = match.group(1)
            conn.execute(f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY, val INTEGER)')
            conn.executemany(f'INSERT INTO "{name}" VALUES (?,?)', middle['before'])
            conn.execute(middle['sql'])
            after = [list(row) for row in conn.execute(f'SELECT id,val FROM "{name}"')]
            if after != middle['after']:
                raise ValueError('Fresh isolated DML execution disagrees with original proof')
        changed = original[:-len(suffix)]
        if not changed.endswith('.'):
            raise ValueError('Mutation operation reason would be incomplete')
        proof = {'kind': 'dml_result_suffix', 'removed_rows': middle['after'],
                 'sql_unchanged': True, 'sql': middle['sql'],
                 'before_rows': middle['before'], 'after_rows': middle['after'],
                 'schema_columns': middle['columns']}
    elif value['concept'] == 'create':
        return value, {'id': value['id'], 'kind': 'create_unchanged',
                       'reason': 'No redundant result array; retain DDL literals, schema and verified zero-row explanation.'}
    else:
        raise ValueError('Unrecognized SQL-format training record; never remove arbitrary numbers')
    value['messages'][-1]['content'] = changed
    value['verification_notes'].append('Removed only the exact documented generator result-array suffix. SQL/conditions/literals/reasons remain; numeric plain explanations remain in the separate40-example subset. No claim that removal proves educational improvement.')
    return value, {'id': value['id'], **proof, 'original_assistant': original,
                   'new_assistant': changed, 'human_review': 'H_PENDING'}


def build(root, destination):
    root, destination = Path(root), Path(destination)
    previous = root / 'runs/finish-v2/20261029/education/candidate-diverse-v2'
    source = previous / 'train.jsonl'
    validation = root / 'runs/finish-v2/20261028/education/development/validation.jsonl'
    original_claims = root / 'runs/finish-v2/20261028/education/development/train-claims.jsonl'
    protected = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [source, validation, previous / 'audit.json', previous / 'claims.jsonl']}
    plain_ids = {value['id'] for value in load_records([previous / 'claims.jsonl'])}
    concept_proofs = {value['id']: value for value in load_records([original_claims])}
    records, changes = [], []
    old_records = load_records([source])
    for old in old_records:
        if old['id'] in plain_ids:
            records.append(deepcopy(old))
        else:
            changed, proof = strip_result_suffix(old, concept_proof=concept_proofs.get(old['id']))
            records.append(changed); changes.append(proof)
    report = validate_dataset(records=records + load_records([validation]), profile='demo', enforce_minimums=False)
    counts = {name: sum(c['kind'] == name for c in changes) for name in ['select_result_suffix', 'dml_result_suffix', 'create_unchanged']}
    if len(records) != 240 or len(plain_ids) != 40 or counts != {'select_result_suffix': 160, 'dml_result_suffix': 30, 'create_unchanged': 10}:
        raise ValueError('Unexpected training composition; no silent broad rewriting')
    for old, new in zip(old_records, records):
        if old['id'] in plain_ids and old != new:
            raise ValueError('Protected diverse plain explanation changed')
        for key in ['id', 'split', 'concept', 'problem_family_id', 'fixture', 'expected']:
            if old.get(key) != new.get(key):
                raise ValueError('Protected training computation changed: ' + key)
        if old['messages'][:-1] != new['messages'][:-1]:
            raise ValueError('Public question or system prompt changed')
    destination.mkdir(parents=True, exist_ok=True)
    for name, values in [('train.jsonl', records), ('changes.jsonl', changes)]:
        path = destination / name
        content = ''.join(dumps(value) + '\n' for value in values)
        if path.exists() and path.read_text(encoding='utf-8') != content:
            raise ValueError('Existing candidate differs; preserve it and use a new version')
        if not path.exists(): path.write_text(content, encoding='utf-8')
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != digest for path, digest in protected.items()):
        raise ValueError('Protected prior data or validation changed')
    report.update(status='CPU_PREPARED_NOT_TRAINED', train_records=240,
                  prior_candidate_sha256=protected[source], validation_sha256=protected[validation],
                  candidate_train_sha256=hashlib.sha256((destination / 'train.jsonl').read_bytes()).hexdigest(),
                  result_suffix_changes=counts, unchanged_diverse_plain_explanations=40,
                  fresh_isolated_select_checks=160, fresh_isolated_dml_checks=30,
                  no_final_read=True, no_family_schema_fixture_or_reference_sql_changes=True,
                  human_review='H_PENDING', data_change_bundle='Diverse40 plain explanations plus removal of exact result-array suffixes from160 SELECT and30 DML examples;10 CREATE unchanged.',
                  hypothesis='Redundant predicted result arrays may encourage numeric answer imitation, but causality and educational benefit are unproven.',
                  evaluation_caution='A reduction in emitted result arrays shrinks claim coverage. Fewer detected array contradictions must not be reported as accuracy improvement; retain SQL-result/counterexample checks and independent explanation review.')
    (destination / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True); args = parser.parse_args()
    print(dumps(build(Path(__file__).resolve().parents[3], Path(args.output))))
