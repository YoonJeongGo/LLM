from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from v021_eval_grade import intent_contract

TABLE = {"name": "records", "columns": [{"name": name, "type": kind} for name, kind in
    [("key", "INTEGER"), ("category", "TEXT"), ("amount", "INTEGER")]], "rows": []}


def test_alias_qualification_reversed_comparison_and_commuted_and_are_compared_by_ast():
    reference = "SELECT key,amount FROM records WHERE amount >= 2 AND key < 9 ORDER BY amount DESC,key ASC"
    candidate = "SELECT r.key AS k,r.amount AS v FROM records r WHERE 9 > r.key AND 2.0 <= r.amount ORDER BY v DESC,k"
    assert intent_contract(candidate, reference, TABLE)["matches"] is True


def test_sort_priority_and_direction_are_not_approved_by_equal_empty_results():
    reference = "SELECT key,amount FROM records WHERE amount >= 2 ORDER BY amount DESC,key ASC"
    for candidate in (
        "SELECT key,amount FROM records WHERE amount >= 2 ORDER BY key ASC,amount DESC",
        "SELECT key,amount FROM records WHERE amount >= 2 ORDER BY amount ASC,key ASC",
        "SELECT key,amount FROM records WHERE amount > 2 ORDER BY amount DESC,key ASC",
    ):
        assert intent_contract(candidate, reference, TABLE)["matches"] is False


def test_group_alias_in_having_and_order_preserves_aggregate_contract():
    reference = "SELECT category,COUNT(*),SUM(amount) FROM records GROUP BY category HAVING SUM(amount)>0 ORDER BY SUM(amount) DESC,category"
    candidate = "SELECT category AS c,COUNT(0) AS n,SUM(amount) AS total FROM records GROUP BY category HAVING total>0 ORDER BY total DESC,c"
    assert intent_contract(candidate, reference, TABLE)["matches"] is True


def test_count_column_and_sum_predicate_are_not_rewritten_to_count_star():
    reference = "SELECT COUNT(*) FROM records"
    assert intent_contract("SELECT COUNT(amount) FROM records", reference, TABLE)["matches"] is False
    assert intent_contract("SELECT SUM(amount IS NOT NULL) FROM records", "SELECT COUNT(amount) FROM records", TABLE)["matches"] is False


def test_unsupported_equivalence_is_reported_as_unproved_not_semantic_wrongness():
    result = intent_contract("SELECT key FROM records LIMIT 1", "SELECT key FROM records", TABLE)
    assert result["matches"] is None
    assert result["status"] == "not_automatically_comparable"
