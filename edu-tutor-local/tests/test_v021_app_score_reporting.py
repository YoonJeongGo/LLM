from edu_tutor.training.finish_app_score import support_outcome, summarize_app


def test_zero_answers_have_undefined_conditional_accuracy_and_no_safe_stop_credit():
    items = [{'accepted': False, 'accepted_result_correct': False,
              'support_status': kind} for kind in ('needs_input', 'unsupported_intent', 'invalid_candidate_or_mismatch')]
    result = summarize_app(items)
    assert result['substantive_response_rate'] == {'numerator': 0, 'denominator': 3}
    assert result['correct_among_answered'] == {'numerator': 0, 'denominator': 0, 'value': None}
    assert result['overall_result_match_rate'] == {'numerator': 0, 'denominator': 3}
    assert result['overall_education_pass'] is None


def test_verified_calculation_without_a_plan_is_not_a_verified_lesson():
    assert support_outcome({'status': 'verified'}, {'plan': None}) == 'verified_no_plan'
    assert support_outcome({'status': 'verified'}, {'plan': {'steps': []}}) == 'verified_lesson'
    assert support_outcome({'status': 'stopped', 'support_status': 'unsupported_intent'}, {'plan': None}) == 'unsupported_intent'


def test_answered_accuracy_and_all_questions_accuracy_keep_different_denominators():
    items = [
        {'accepted': True, 'accepted_result_correct': True, 'support_status': 'verified_lesson'},
        {'accepted': True, 'accepted_result_correct': False, 'support_status': 'verified_lesson'},
        {'accepted': False, 'accepted_result_correct': False, 'support_status': 'unsupported_intent'},
    ]
    result = summarize_app(items)
    assert result['correct_among_answered'] == {'numerator': 1, 'denominator': 2, 'value': .5}
    assert result['overall_result_match_rate'] == {'numerator': 1, 'denominator': 3}
    assert result['accepted_result_wrong'] == 1
