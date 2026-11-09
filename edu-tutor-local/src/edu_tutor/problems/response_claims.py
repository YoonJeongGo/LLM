"""Flag explicit machine-readable result claims; never approve all prose."""
import json
import math
import re

import sqlglot
from sqlglot import exp

from edu_tutor.evaluation.sql_sandbox import compare_results
from edu_tutor.problems.sql_response import parse_json_response

PROTOCOL = 'v021_explicit_result_array_and_scalar_claims_v2'
_IDENT = r'[A-Za-z_][A-Za-z_0-9]{0,63}'
_AGGREGATE = re.compile(r'\b(?:COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(?:DISTINCT\s+)?(?:'+_IDENT+r'(?:\.'+_IDENT+r')?|\*)\s*\)', re.I)
_NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def _explanation_parts(raw):
    value, suffix = parse_json_response(raw, require_sql=False)
    parts = []
    if isinstance(value.get('explanation'), str):
        parts.append(('json_explanation', value['explanation']))
    if suffix.strip():
        parts.append(('plain_text_suffix', suffix))
    return parts


def _aggregate_key(node):
    node = node.this if isinstance(node, exp.Alias) else node
    if not isinstance(node, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)):
        return None
    value = node.copy()
    for column in value.find_all(exp.Column):
        column.set('table', None)
    return value.sql(dialect='sqlite', normalize=True)


def _scalar_aggregate_claims(explanation, source, item, actual):
    """Compare explicit final scalars, not arbitrary arithmetic or group prose."""
    if len(actual.get('rows', [])) != 1:
        return []
    try:
        queries = sqlglot.parse(item.get('sql', ''), read='sqlite')
        query = queries[0] if len(queries) == 1 else None
        if (not isinstance(query, exp.Select) or query.args.get('group')
                or len(query.expressions) != len(actual['rows'][0])):
            return []
        locations = {}
        for index, expression in enumerate(query.expressions):
            key = _aggregate_key(expression)
            if key is not None:
                locations.setdefault(key, []).append(index)
        mentions = list(_AGGREGATE.finditer(explanation))
        claims = []
        for index, mention in enumerate(mentions):
            key = _aggregate_key(sqlglot.parse_one(mention[0], read='sqlite'))
            if len(locations.get(key, [])) != 1:
                continue
            end = mentions[index+1].start() if index+1 < len(mentions) else len(explanation)
            # A single explicit equation/direct-value clause, with no guessed
            # mapping of a later sentence or an arbitrary group's result.
            fragment = explanation[mention.end():end].split('\n', 1)[0].split(',', 1)[0].strip().lstrip('`').strip()
            binding = re.match(r'^(?:는|은|:|=)\s*(.*)$', fragment)
            if not binding:
                continue
            body = re.sub(r'(?:개\s*)?(?:입니다|이다|이에요|예요)\s*[.!]?\s*$', '', binding[1]).strip().rstrip('.,; ').strip()
            if not body or not re.fullmatch(r'(?:[0-9eE.+*/()=\-\s]|NULL)+', body, re.I):
                continue
            final = body.rsplit('=', 1)[-1].strip()
            if final.upper() == 'NULL':
                claimed = None
            elif re.fullmatch(_NUMBER, final):
                claimed = float(final)
                if not math.isfinite(claimed):
                    continue
            else:
                continue
            position = locations[key][0]
            observed = actual['rows'][0][position]
            matches = compare_results({'status':'executed', 'columns':['value'], 'rows':[[observed]]},
                {'columns':['value'], 'rows':[[claimed]], 'row_order':'ordered', 'numeric_abs_tolerance':1e-9})
            claims.append({'status':'checked_explicit_aggregate_scalar_against_candidate_sql',
                'source':source, 'fragment':mention[0]+fragment, 'expression':key,
                'projection_index':position, 'claimed_value':claimed, 'actual_value':observed,
                'matches_sql_execution':matches, 'arithmetic_steps_checked':False})
        return claims
    except (ValueError, KeyError, TypeError, sqlglot.errors.ParseError):
        return []


def check_explicit_result_claim(item):
    value = {'id': item['id'], 'protocol': PROTOCOL, 'claims': [],
             'full_explanation_quality': 'H_PENDING', 'human_review': 'H_PENDING',
             'new_model_calls': 0, 'explicit_numeric_mismatch': False}
    raw = item.get('actual_answer') or ''
    try:
        parts = _explanation_parts(raw)
    except ValueError:
        return {**value, 'status': 'structured_explanation_unavailable'}
    actual = item.get('actual') or {}
    if not parts or actual.get('status') != 'executed':
        return {**value, 'status': 'structured_explanation_or_executed_sql_unavailable'}
    for source, explanation in parts:
        for found in re.finditer(r'결과\s*(\[)', explanation):
            fragment = explanation[found.start(1):]
            try:
                rows, length = json.JSONDecoder().raw_decode(fragment)
                if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
                    raise ValueError('Expected an explicit array of result rows')
            except ValueError as exc:
                value['claims'].append({'status': 'not_machine_readable', 'source':source,
                    'fragment': fragment, 'reason': str(exc), 'matches_sql_execution': None})
                continue
            comparison = {'columns': actual['columns'], 'rows': rows,
                          'row_order': 'ordered' if re.search(r'\bORDER\s+BY\b', item.get('sql', ''), re.I) else 'unordered',
                          'numeric_abs_tolerance': 1e-9}
            matches = compare_results(actual, comparison)
            value['claims'].append({'status': 'checked_against_candidate_sql_execution', 'source':source,
                'fragment': fragment[:length], 'claimed_rows': rows, 'actual_rows': actual['rows'],
                'matches_sql_execution': matches})
        value['claims'].extend(_scalar_aggregate_claims(explanation, source, item, actual))
    mismatch = any(c['matches_sql_execution'] is False for c in value['claims'])
    return {**value, 'status': 'explicit_result_claim_mismatch' if mismatch else 'no_mismatch_found_in_parseable_claims',
            'explicit_numeric_mismatch': mismatch,
            'explanation_sources':[source for source, _ in parts],
            'notice': 'Checks explicit result arrays and direct single-row, ungrouped aggregate final values from JSON explanation and bounded plain suffix. Arithmetic steps, arbitrary prose and group-to-value meaning are not validated. Absence of a parseable contradiction is not an explanation, intent, educational or human pass.'}


def audit_model_explanation(raw, evidence):
    """Preserve and classify the draft separately from tool-derived speech."""
    claim = check_explicit_result_claim({'id': evidence.get('id', 'raw-draft'),
        'actual_answer': raw, 'sql': evidence.get('sql', ''),
        'actual': evidence.get('execution', {})})
    try:
        parts = _explanation_parts(raw)
    except ValueError:
        parts = []
    concepts = []
    for source, explanation in parts:
        if re.search(r'COUNT\s*\(\s*\*\s*\)\s*(?:는|은)?\s*(?:NULL|널)\s*'
                r'(?:(?:인\s*)?행|값)?\s*(?:을|를)?\s*제외(?:합니다|한다|해요|한다는)', explanation, re.I):
            concepts.append({'kind': 'count_star_excludes_null_incorrect',
                'rule': 'SQLite COUNT(*) counts input rows including rows with NULL values.',
                'source': source, 'verification_basis': 'app SQLite aggregate rule independently checked against fixture execution'})
    mismatch = claim['explicit_numeric_mismatch'] or bool(concepts)
    return {'status': 'detected_contradiction' if mismatch else 'unverified_free_explanation',
        'explicit_result_claims': claim, 'concept_contradictions': concepts,
        'raw_explanation_approved': False, 'used_as_student_speech': False,
        'student_speech_source': 'verified_intent_and_calculation_evidence_only',
        'human_review': 'H_PENDING',
        'explanation_sources':[source for source, _ in parts],
        'scope': 'Checks explicit result arrays, ungrouped single-row aggregate final scalars and a narrow COUNT(*)/NULL contradiction in JSON explanation and bounded plain suffix; no arithmetic-step or general prose truthfulness approval.'}
