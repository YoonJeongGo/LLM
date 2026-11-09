"""Prepare a train-only mixed-format hypothesis, never train or read holdout.

Existing examples, families, rows, reference SQL and validation are retained.
Only five prompts/labels in each of eight training families are restated as a
student misconception or a short explanation, derived from the same values.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .data import load_records, validate_dataset
from .finish_data import database, dumps

ALLOWED = {'count_all', 'count_value', 'boolean_sum', 'null', 'nonnull', 'zero', 'sum', 'average'}


def restate(record):
    value = deepcopy(record)
    family = value['concept']
    if value['split'] != 'train' or family not in ALLOWED:
        raise ValueError('Only the explicitly retained training families can be restated')
    table = value['fixture']['tables'][0]
    name = table['name']
    column_index, column = next((i, c) for i, c in enumerate(table['columns'])
                               if c['type'] in {'INTEGER', 'REAL', 'NUMERIC'} and c['name'].lower() != 'id')
    col = column['name']
    rows = table['rows']
    values = [r[column_index] for r in rows]
    known = [v for v in values if v is not None]
    included = [i + 1 for i, v in enumerate(values) if v is not None]
    null_rows = [i + 1 for i, v in enumerate(values) if v is None]
    zero_rows = [i + 1 for i, v in enumerate(values) if v == 0]
    conn = database(value['fixture']['tables'])
    try:
        sql_rows = [list(r) for r in conn.execute(value['expected']['sql'])]
    finally:
        conn.close()
    if sql_rows != value['expected']['rows']:
        raise ValueError('Original training reference no longer executes as recorded')
    if family == 'count_all':
        question = f'{name}에서 {col}에 NULL이 있으면 COUNT(*)에서도 그 행을 빼나요? 전체 행 수를 어떻게 세는지 평문으로 설명하세요.'
        answer = f'빼지 않습니다. {name}의 COUNT(*)는 값이 아니라 전체 행 {len(rows)}개를 셉니다. {col}의 NULL인 행도 실제 행이므로 포함합니다.'
        independent = [[len(rows)]]
        claims = {'all_rows': len(rows), 'included_row_numbers': list(range(1, len(rows) + 1)), 'null_rows_included': null_rows}
    elif family == 'count_value':
        question = f'{name}에서 COUNT({col})은 NULL인 행만 세는 건가요? 0과 음수는 어떻게 세는지도 평문으로 설명하세요.'
        answer = f'아니요. {name}의 COUNT({col})은 NULL이 아닌 값 {len(known)}개를 셉니다. NULL {len(null_rows)}개만 제외하고 0과 음수도 값이므로 포함합니다. 포함하는 원본 행 번호는 {dumps(included)}입니다.'
        independent = [[len(known)]]
        claims = {'nonnull_count': len(known), 'excluded_null_count': len(null_rows), 'included_row_numbers': included, 'zero_rows_included': zero_rows}
    elif family == 'boolean_sum':
        indicators = [int(v is not None) for v in values]
        total = sum(indicators) if indicators else None
        question = f'{name}에서 SUM({col} IS NOT NULL)은 {col} 값 자체를 더하나요? 원본 행마다 먼저 계산할 값과 그 합계를 평문으로 설명하세요.'
        answer = f'값 자체를 더하지 않습니다. {name}의 각 행에서 {col} IS NOT NULL을 계산해 NULL이면 0, 아니면 1로 바꿉니다. 원본 행 순서의 조건값은 {dumps(indicators)}이고 합계는 {total}입니다.'
        independent = [[total]]
        claims = {'indicators': indicators, 'indicator_sum': total, 'input_rows': len(rows)}
    elif family in {'null', 'nonnull', 'zero'}:
        predicate = {'null': lambda v: v is None, 'nonnull': lambda v: v is not None, 'zero': lambda v: v == 0}[family]
        positions = [i + 1 for i, v in enumerate(values) if predicate(v)]
        # The original source family queries its existing identifier column.
        ids = sorted(rows[i - 1][0] for i in positions)
        independent = [[ident] for ident in ids]
        condition = {'null': f'{col} IS NULL', 'nonnull': f'{col} IS NOT NULL', 'zero': f'{col} = 0'}[family]
        question = f'{name}에서 {condition} 조건의 결과를 설명하세요. NULL과 0을 같은 값으로 봐도 되나요? 선택된 원본 행과 이유를 평문으로 알려 주세요.'
        rule = {'null': 'IS NULL은 값이 NULL인 행만 고릅니다. 0은 NULL이 아니므로 고르지 않습니다.',
                'nonnull': 'IS NOT NULL은 NULL만 제외합니다. 0과 음수도 NULL이 아니므로 포함합니다.',
                'zero': '= 0은 실제 값이 0인 행만 고릅니다. NULL과의 등호 비교는 참이 아니므로 NULL 행은 제외합니다.'}[family]
        answer = f'{name}에서 NULL과 0은 다릅니다. {rule} 선택한 원본 행 번호는 {dumps(positions)}이고 결과 식별자는 {dumps(ids)}입니다.'
        claims = {'predicate': condition, 'selected_row_numbers': positions, 'selected_identifiers': ids}
    else:
        total = sum(known) if known else None
        result = total if family == 'sum' else total / len(known) if known else None
        independent = [[result]]
        if family == 'sum':
            question = f'{name}에서 {col}의 합계를 구할 때 NULL을 더해야 하나요? 0과 음수의 처리와 계산 결과를 평문으로 설명하세요.'
            answer = f'{name}의 SUM({col})은 NULL을 제외한 값 {dumps(known)}을 더합니다. 0과 음수는 값 그대로 포함하므로 합계는 {result}입니다.'
        else:
            question = f'{name}에서 AVG({col})의 분모는 항상 전체 행 수인가요? NULL과 0을 구분해 평균의 계산 과정을 평문으로 설명하세요.'
            answer = f'항상 전체 행 수가 아닙니다. {name}의 AVG({col})는 NULL을 제외한 값 {dumps(known)}의 합계 {total}을 그 값의 개수 {len(known)}로 나눕니다. 0도 분모에 포함하므로 평균은 {result}입니다.'
        claims = {'nonnull_values': known, 'sum': total, 'nonnull_count': len(known), 'result': result}
    if independent != sql_rows:
        raise ValueError('Independent explanation calculation and SQL reference disagree')
    declaration = f"SQLite. {name}({','.join(c['name'] for c in table['columns'])})={dumps(rows)}. "
    value['messages'] = [m for m in value['messages'] if m['role'] == 'system'] + [
        {'role': 'user', 'content': declaration + question}, {'role': 'assistant', 'content': answer}]
    value['source']['title'] += ' / train-only plain-explanation hypothesis'
    value['verification_notes'].append('Same original training family/fixture/reference SQL. Question format and assistant prose restated from independent calculation, SQLite checked; no model answer collection or human review.')
    return value, {'id': value['id'], 'family': value['problem_family_id'], 'claims': claims,
                   'independent_rows': independent, 'sqlite_rows': sql_rows,
                   'human_review': 'H_PENDING', 'source_reference_unchanged': True}


def diversify(record, variant):
    """Nonempty row subsets/duplicates of this training record only.

    This changes data, not SQL structure or schema. Duplicate identifiers are
    allowed in the existing unconstrained table and retain ORDER BY semantics.
    No heldout inputs, all-empty input, new value or extra query is introduced.
    """
    value = deepcopy(record)
    rows = value['fixture']['tables'][0]['rows']
    if len(rows) != 5:
        raise ValueError('This candidate transformation requires the frozen five-row training source')
    layouts = [(0,), (1, 2), (0, 1, 2), (0, 2, 2, 3, 4, 1), (1, 1, 1, 2, 2, 3, 4, 0)]
    selected = layouts[variant]
    value['fixture']['tables'][0]['rows'] = [deepcopy(rows[i]) for i in selected]
    conn = database(value['fixture']['tables'])
    try:
        actual = conn.execute(value['expected']['sql'])
        value['expected']['columns'] = [item[0] for item in actual.description]
        value['expected']['rows'] = [list(row) for row in actual]
    finally:
        conn.close()
    return value, list(selected)


def build(root, destination, *, diverse=False):
    root, destination = Path(root), Path(destination)
    original = root / 'runs/finish-v2/20261028/education/development/train.jsonl'
    validation = root / 'runs/finish-v2/20261028/education/development/validation.jsonl'
    source = load_records([original]); records = []; proofs = []; counts = Counter()
    for record in source:
        counts[record['concept']] += 1
        if record['concept'] in ALLOWED and counts[record['concept']] > 5:
            staged, layout = diversify(record, counts[record['concept']] - 6) if diverse else (record, None)
            changed, proof = restate(staged)
            if diverse:
                proof.update(source_reference_unchanged=False, reference_sql_structure_unchanged=True,
                             source_row_indices=layout, source_rows_unchanged_values=True)
                changed['verification_notes'].append('Nonempty subset/duplicates of this same training source row pool; SQL structure/schema retained, expected rows recomputed and independently checked.')
            records.append(changed); proofs.append(proof)
        else:
            records.append(deepcopy(record))
    report = validate_dataset(records=records + load_records([validation]), profile='demo', enforce_minimums=False)
    if len(records) != 240 or len(proofs) != 40:
        raise ValueError('Expected original240 with exactly40 format replacements')
    # No final reference needs to be opened: all SQL structures, identities and
    # fixtures are byte-for-byte equal to the already frozen training records.
    for old, new in zip(source, records):
        for field in ['id', 'split', 'concept', 'problem_family_id'] + ([] if diverse else ['fixture', 'expected']):
            if old.get(field) != new.get(field):
                raise ValueError('Training family or reference computation changed: ' + field)
        if diverse and 'expected' in old:
            if old['expected']['sql'] != new['expected']['sql']:
                raise ValueError('Reference SQL changed')
            for original_table, new_table in zip(old['fixture']['tables'], new['fixture']['tables']):
                if original_table['name'] != new_table['name'] or original_table['columns'] != new_table['columns'] or not new_table['rows']:
                    raise ValueError('Original schema/nonempty restriction changed')
                if any(row not in original_table['rows'] for row in new_table['rows']):
                    raise ValueError('Row values outside the original training record')
    destination.mkdir(parents=True, exist_ok=True)
    for filename, items in [('train.jsonl', records), ('claims.jsonl', proofs)]:
        path = destination / filename
        content = ''.join(dumps(item) + '\n' for item in items)
        if path.exists() and path.read_text(encoding='utf-8') != content:
            raise ValueError('Existing training candidate differs; preserve it and choose a new version')
        if not path.exists(): path.write_text(content, encoding='utf-8')
    changed_ids = {p['id'] for p in proofs}
    varied = [r for r in records if r['id'] in changed_ids]
    report.update(status='CPU_PREPARED_NOT_TRAINED', train_records=240, restated_plain_explanations=40,
                  unchanged_records=200, sqlite_and_independent_claim_checks=40,
                  original_train_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
                  validation_sha256=hashlib.sha256(validation.read_bytes()).hexdigest(),
                  candidate_train_sha256=hashlib.sha256((destination / 'train.jsonl').read_bytes()).hexdigest(),
                  final_read=False, final_family_or_structure_added=False, human_review='H_PENDING',
                  hypothesis='Task-format and same-family nonempty data diversity' if diverse else 'Task-format coverage, not verified educational improvement',
                  diverse_nonempty_training_rows=diverse,
                  changed_row_count_distribution=dict(Counter(len(r['fixture']['tables'][0]['rows']) for r in varied)),
                  changed_numeric_results_by_family={family: [r['expected']['rows'] for r in varied if r['concept'] == family] for family in sorted(ALLOWED)})
    (destination / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True); parser.add_argument('--diverse', action='store_true'); args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    print(dumps(build(root, Path(args.output), diverse=args.diverse)))
