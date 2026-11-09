"""Saved SELECT candidates versus reference SQL on bounded counterfactual data.

Finding a mismatch disproves equivalence. Not finding one does not prove the
SQL intent or explanation correct. References stay inside this offline grader.
"""
from copy import deepcopy

from edu_tutor.evaluation.sql_sandbox import compare_results, execute_sql
from edu_tutor.problems.sql_response import extract_sql_candidate

PROTOCOL = 'saved_select_numeric_counterexamples_v1'


def fixtures(record):
    original = record['fixture']
    for table_index, table in enumerate(original['tables']):
        # Keep ID/link keys stable. Value perturbations do not rewrite joins or
        # table structure and never modify a real student/app database.
        for column_index, column in enumerate(table['columns']):
            if column['type'] not in {'INTEGER', 'REAL', 'NUMERIC'} or column['name'].lower() in {'id', 'rowid'} or column['name'].lower().endswith('_id'):
                continue
            values = [row[column_index] for row in table['rows']]
            if not values:
                continue
            known = [v for v in values if v is not None]
            duplicate = known[0] if known else 1
            transforms = {
                'duplicate_nonnull': [None if v is None else duplicate for v in values],
                'all_null': [None] * len(values),
                'all_zero': [0] * len(values),
                'alternating_null_zero': [None if i % 2 else 0 for i in range(len(values))],
                'negate_nonnull': [None if v is None else -v for v in values],
                'reverse_values': list(reversed(values)),
            }
            for kind, changed in transforms.items():
                if changed == values:
                    continue
                value = deepcopy(original)
                for row, replacement in zip(value['tables'][table_index]['rows'], changed):
                    row[column_index] = replacement
                yield {'kind': kind, 'table': table['name'], 'column': column['name'],
                       'original_values': values, 'changed_values': changed, 'fixture': value}


def check_saved_sql(record, text, finish_reason):
    result = {'id': record['id'], 'protocol': PROTOCOL, 'new_model_calls': 0,
              'semantic_pass': None, 'human_review': 'H_PENDING', 'counterexample_found': None,
              'notice': 'Counterfactual data, not fresh model answers. No counterexample is not a proof of SQL intent or explanation quality.'}
    if 'expected' not in record or finish_reason != 'eos':
        return {**result, 'status': 'not_applicable_or_incomplete', 'probes': []}
    try:
        sql = extract_sql_candidate(text)
    except ValueError as exc:
        return {**result, 'status': 'candidate_not_extracted', 'reason': str(exc), 'probes': []}
    probes = []
    for probe in fixtures(record):
        reference = execute_sql(record['expected']['sql'], probe['fixture'], dialect='sqlite')
        actual = execute_sql(sql, probe['fixture'], dialect='sqlite')
        if reference['status'] != 'executed':
            probes.append({**probe, 'status': 'reference_failed', 'reference': reference, 'actual': actual, 'matches': None})
            continue
        expected = {**record['expected'], 'columns': reference['columns'], 'rows': reference['rows']}
        comparable = {**actual, 'columns': expected['columns']} if len(actual.get('columns', [])) == len(expected['columns']) else actual
        probes.append({**probe, 'status': 'checked', 'reference': reference, 'actual': actual,
                       'matches': compare_results(comparable, expected)})
    mismatch = any(p['matches'] is False for p in probes)
    return {**result, 'status': 'counterexample_found' if mismatch else 'no_counterexample_in_bounded_probes',
            'counterexample_found': mismatch, 'sql': sql, 'probes': probes,
            'checked_probes': sum(p['matches'] is not None for p in probes),
            'failed_probes': sum(p['matches'] is False for p in probes)}
