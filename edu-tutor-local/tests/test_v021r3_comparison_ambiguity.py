"""Development regressions after disclosure of independent CPU boundary C01.

The original independent 5/6 result is preserved; these are not new holdouts.
"""
import pytest

from test_v021r3_explanation_repair import source, ask, words


def multiple_targets(rows=None):
    return source(rows=rows or [["chosen",-4,0],["first",None,1],["last",None,0],
                               ["zero-a",0,1],["zero-b",0,0]],
        query="SELECT label, reading FROM observations WHERE reading<0 OR priority=1 ORDER BY priority DESC")


@pytest.mark.parametrize("target", ["NULL인 그 행", "NULL인 해당 행", "그 NULL 행", "해당 널인 행", "0인 그 행", "그 0인 행"])
def test_singular_deictic_multiple_value_targets_asks_which_original_row(target):
    m,lesson=multiple_targets()
    before=m["evidence"]["result"]
    result=ask(m,lesson,f"선택한 chosen과 {target}을 비교해 줘.")
    assert not result["speech_allowed"],result
    assert result["plan"] is None and result["explanation_fulfillment"]["status"]=="unmet"
    assert "어느 행" in result["reason"] and "원본" in result["reason"]
    assert "없습니다" not in result["reason"]
    assert m["evidence"]["result"] == before


@pytest.mark.parametrize("target", ["NULL인 행들을", "NULL인 행들을 모두", "널인 행들과"])
def test_explicit_plural_comparison_still_explains_each_real_truth(target):
    m,lesson=multiple_targets()
    result=ask(m,lesson,f"선택한 chosen과 {target} 비교해 줘.")
    assert result["speech_allowed"],result
    text=words(result)
    assert "원본 2행" in text and "원본 3행" in text
    assert "TRUE" in text and "UNKNOWN" in text
    item=next(i for i in result["explanation_fulfillment"]["items"] if i["kind"]=="null_comparison")
    assert len(item["evidence"]["comparison_row_ids"]) == 2


@pytest.mark.parametrize("reference", ["원본 2행", "'first'"])
def test_explicit_unique_reference_resolves_singular_null_target(reference):
    m,lesson=multiple_targets()
    result=ask(m,lesson,f"선택한 chosen과 NULL인 그 행, {reference}을 비교해 줘.")
    assert result["speech_allowed"],result
    item=next(i for i in result["explanation_fulfillment"]["items"] if i["kind"]=="null_comparison")
    assert item["evidence"]["comparison_row_ids"] == [m["evidence"]["working_tables"][0]["row_ids"][1]]


def test_one_actual_null_target_is_not_ambiguous():
    m,lesson=multiple_targets([["chosen",-4,0],["only-null",None,1]])
    result=ask(m,lesson,"선택한 chosen과 NULL인 그 행을 비교해 줘.")
    assert result["speech_allowed"],result
    assert "원본 2행" in words(result)


def test_missing_null_target_stays_explicitly_absent_without_invention():
    m,lesson=multiple_targets([["chosen",-4,0],["present",9,1]])
    result=ask(m,lesson,"선택한 chosen과 NULL인 그 행을 비교해 줘.")
    assert result["speech_allowed"],result
    assert "NULL인 행이 없습니다" in words(result)


def test_singular_null_explicitly_bound_to_current_selection_remains_resolved():
    m,lesson=multiple_targets()
    result=ask(m,lesson,"선택한 그 NULL 행은 왜 포함돼? 0인 행들과 비교해 줘.",row=1)
    assert result["speech_allowed"],result
    item=next(i for i in result["explanation_fulfillment"]["items"] if i["kind"]=="null_comparison")
    assert item["evidence"]["comparison_row_ids"] == [m["evidence"]["working_tables"][0]["row_ids"][1]]


def test_selected_null_anchor_does_not_silently_identify_a_separate_null_target():
    m,lesson=multiple_targets()
    result=ask(m,lesson,"선택한 행과 NULL인 그 행을 비교해 줘.",row=1)
    assert not result["speech_allowed"] and "어느 행" in result["reason"]
