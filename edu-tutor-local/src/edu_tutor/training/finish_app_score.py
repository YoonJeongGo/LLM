"""Offline saved-answer appraisal through the current app verification path.

This is not a new live conversation or a browser/audio verification. Private
expected answers are accessed only after the app has constructed its evidence.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter

from edu_tutor.evaluation.sql_sandbox import compare_results
from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.problems.evidence import display_answer
from edu_tutor.problems.app_correction import verify_with_app_correction as verify_answer
from edu_tutor.problems.models import normalize_problem


def support_outcome(evidence, lesson):
    """Report what the app actually established; a safe stop is not an answer."""
    if evidence.get('status') == 'verified':
        return 'verified_lesson' if lesson.get('plan') is not None else 'verified_no_plan'
    declared = evidence.get('support_status')
    if declared:
        return declared
    if evidence.get('status') in {'needs_input', 'input_missing'}:
        return 'needs_input'
    if evidence.get('intent', {}).get('status') in {'unsupported', 'unverified'}:
        return 'unsupported_intent'
    return 'invalid_candidate_or_mismatch'


def public_problem(record):
    """Only the student-visible question and original table enter the app."""
    question = '\n'.join(m['content'] for m in record['messages'] if m['role'] == 'user')
    return normalize_problem({
        'task_kind': 'write_sql', 'dialect': record.get('sql_dialect', 'sqlite'),
        'raw_text': question, 'confirmed': True, 'source': {'kind': 'typed'},
        'tables': deepcopy(record.get('fixture', {}).get('tables', [])),
    })


def app_score_response(record, text, finish_reason):
    result = {'id': record['id'], 'finish_reason': finish_reason,
              'mode': 'saved_raw_answer_through_current_app_cpu',
              'new_model_calls': 0, 'new_audio_calls': 0,
              'accepted': False, 'plan_generated': False,
              'accepted_result_correct': False if 'expected' in record else None,
              'human_review': 'H_PENDING', 'overall_education_pass': None}
    if finish_reason != 'eos' or not text or not text.strip():
        return {**result, 'failure': 'incomplete_or_empty_generation'}
    if 'expected' not in record:
        return {**result, 'status': 'concept_not_automatically_graded',
                'notice': 'DDL/DML and concept explanations need separate claim and human review. No pass assigned.'}
    problem = public_problem(record)
    question = problem['raw_text']
    evidence = verify_answer(problem, text, question)
    content = display_answer(evidence)
    message = {'id': 'offline-' + record['id'], 'problem': problem, 'evidence': evidence,
               'content': content, 'raw_model_response': text}
    lesson = generate_verified_plan(message, question, 'offline-lesson-' + record['id'])
    accepted = evidence['status'] == 'verified' and lesson.get('plan') is not None
    # Only now read the private reference answer. Never pass it to the app.
    expected = record['expected']
    actual = evidence.get('execution', {})
    comparable = {**actual, 'columns': expected['columns']} if len(actual.get('columns', [])) == len(expected['columns']) else actual
    result.update(accepted=accepted, plan_generated=lesson.get('plan') is not None,
                  accepted_result_correct=accepted and compare_results(comparable, expected),
                  support_status=support_outcome(evidence, lesson),
                  raw_model_claim_check=deepcopy(evidence.get('raw_model_explanation') or evidence.get('model_claim_check')),
                  free_model_prose_approved=False,
                  status=evidence['status'], public_problem=problem,
                  displayed_answer=content, evidence=evidence, lesson=lesson,
                  notice='Safe stops and unsupported cases are not correct answers. App-derived numeric speech is separate from raw model prose; no listening or browser review performed.')
    return result


def summarize_app(items):
    sql = [i for i in items if i['accepted_result_correct'] is not None]
    accepted = [i for i in sql if i['accepted']]
    correct = sum(i['accepted_result_correct'] for i in sql)
    return {'total': len(items), 'sql_total': len(sql), 'accepted': len(accepted),
            'support_outcomes': dict(Counter(i.get('support_status', i.get('failure', i.get('status', 'unknown'))) for i in sql)),
            'substantive_response_rate': {'numerator': len(accepted), 'denominator': len(sql)},
            'correct_among_answered': {'numerator': correct, 'denominator': len(accepted),
                                      'value': correct / len(accepted) if accepted else None},
            'overall_result_match_rate': {'numerator': correct, 'denominator': len(sql)},
            'app_corrected_model_sql': sum(bool(i.get('evidence',{}).get('app_correction')) for i in accepted),
            'accepted_result_correct': correct,
            'accepted_result_wrong': len(accepted) - correct,
            'stopped_or_unsupported': len(sql) - len(accepted),
            'concept_review_pending': len(items) - len(sql),
            'overall_education_pass': None, 'human_review': 'H_PENDING',
            'browser_audio_review': 'NOT_RUN'}
