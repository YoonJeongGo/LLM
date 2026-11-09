"""Reproducible original demo authoring; expected rows are authored, not model output.

Running this script only writes this project's demo data. It does not promote review.
"""
import json
from pathlib import Path


def table(name, columns, rows):
    return {"name": name, "columns": [{"name": n, "type": t} for n, t in columns], "rows": rows}


P = table("products", [("id", "INTEGER"), ("category", "TEXT"), ("price", "REAL"), ("stock", "INTEGER")],
          [[1, "책", 12, 4], [2, "책", 18, 0], [3, "펜", 3, 10], [4, "펜", None, 2]])
E = table("staff", [("id", "INTEGER"), ("team", "TEXT"), ("pay", "REAL"), ("manager_id", "INTEGER")],
          [[1, "가", 100, None], [2, "가", 160, 1], [3, "나", 90, 1], [4, "나", None, 3]])
C = table("customers", [("id", "INTEGER"), ("name", "TEXT")], [[1, "하늘"], [2, "바다"], [3, "숲"]])
O = table("orders", [("id", "INTEGER"), ("customer_id", "INTEGER"), ("amount", "REAL")], [[10, 1, 8], [11, 1, 12], [12, 2, 5]])
N = table("notes", [("id", "INTEGER"), ("text", "TEXT")], [[1, "SQL 연습"], [2, "SQL 입문"], [3, "자료 모음"]])
A = table("a", [("v", "INTEGER")], [[1], [1], [2]])
B = table("b", [("v", "INTEGER")], [[2], [3]])
records = []


def add(split, family, concept, question, answer, tables=None, sql=None, columns=None, rows=None, ordered=False):
    if tables:
        detail = " ".join(t["name"] + "(" + ",".join(c["name"] for c in t["columns"]) + ")=" +
                          json.dumps(t["rows"], ensure_ascii=False, separators=(",", ":")) for t in tables)
        question = "SQLite. " + detail + ". " + question
        answer = json.dumps({"sql": sql, "explanation": answer}, ensure_ascii=False)
    record = {
        "id": f"demo_v1_{family}", "subject": "SQL·관계형 데이터베이스 기초", "concept": concept,
        "difficulty": 2 if split != "test" else 3, "problem_family_id": family, "split": split,
        "messages": [{"role": "user", "content": question}, {"role": "assistant", "content": answer}],
        "source": {"kind": "self_authored_demo", "title": "새로 작성한 로컬 SQL 교육 데모 v1",
                   "rights_note": "이 프로젝트를 위해 새로 작성한 합성 예제. 기출·유료 교재를 복제하지 않음. 사람의 교육 검토 전이며 데모에만 사용.",
                   "created_by": "Codex_generated_original_demo"},
        "review_status": "generated_unreviewed", "demo_only": True, "sql_dialect": "sqlite" if tables else "none",
        "verification_notes": ["사람의 설명 검토: not_reviewed. SQL 실행 검증은 별도 보고서에 기록하며 검토 상태를 승격하지 않음."]}
    if tables:
        record["fixture"] = {"tables": tables}
        record["expected"] = {"sql": sql, "columns": columns, "rows": rows,
                              "row_order": "ordered" if ordered else "multiset", "numeric_abs_tolerance": 1e-9}
    records.append(record)


add("train", "primary_key_identity", "기본키", "도서 대출표에서 대출번호를 기본키로 정한다는 뜻은 무엇인가요?", "기본키는 각 행을 구별하도록 선택한 열 또는 열의 조합입니다. 대출번호를 기본키로 정하면 같은 번호를 중복해 쓰거나 NULL로 비워 둘 수 없습니다. 한 사람이 여러 번 빌리는 것은 가능하므로 회원번호만으로 대출 행을 식별할 수는 없습니다.")
add("train", "foreign_key_reference", "외래키", "주문표의 고객번호가 고객표의 고객번호를 참조하는 외래키이면 무엇을 확인하나요?", "외래키는 주문의 고객번호가 참조 대상 고객에 연결되는지 제한합니다. NULL 허용 여부는 별도 제약이며, NULL을 허용하면 고객번호가 비어 있는 주문도 가능할 수 있습니다. 고객 삭제 시 주문을 함께 지울지 막을지는 설정된 참조 동작에 따라 다릅니다. 외래키가 주문의 중복을 없애 주는 것은 아닙니다.")
add("train", "projection_columns", "열 선택", "id와 price만 조회해 주세요.", "SELECT 뒤에 필요한 열만 적습니다. 가격이 없는 행도 남으며 해당 값은 NULL입니다.", [P], "SELECT id, price FROM products", ["id", "price"], [[1,12],[2,18],[3,3],[4,None]])
add("train", "numeric_where_filter", "WHERE", "가격이 10보다 큰 상품 id를 구해 주세요.", "12와 18이 조건을 만족합니다. NULL과의 비교는 참이 아니므로 id 4는 선택되지 않습니다.", [P], "SELECT id FROM products WHERE price > 10", ["id"], [[1],[2]])
add("train", "is_null_predicate", "NULL 검사", "가격이 입력되지 않은 상품 id를 구해 주세요.", "NULL 검사는 = NULL이 아니라 IS NULL로 표현합니다. id 4의 가격이 비어 있습니다.", [P], "SELECT id FROM products WHERE price IS NULL", ["id"], [[4]])
add("train", "count_rows_vs_values", "COUNT", "전체 행 수와 가격이 입력된 행 수를 함께 구해 주세요.", "COUNT(*)는 네 행을 모두 세고 COUNT(price)는 NULL 하나를 제외해 3을 반환합니다.", [P], "SELECT COUNT(*) AS total, COUNT(price) AS priced FROM products", ["total","priced"], [[4,3]])
add("train", "group_sum", "GROUP BY", "분류별 재고 합계를 구해 주세요.", "분류로 묶어 책은 4+0=4, 펜은 10+2=12가 됩니다.", [P], "SELECT category, SUM(stock) AS total_stock FROM products GROUP BY category", ["category","total_stock"], [["책",4],["펜",12]])
add("train", "having_sum_threshold", "HAVING", "재고 합계가 5보다 큰 분류만 구해 주세요.", "그룹의 합계는 HAVING에서 거릅니다. 펜의 합계 12만 5보다 큽니다.", [P], "SELECT category FROM products GROUP BY category HAVING SUM(stock) > 5", ["category"], [["펜"]])
add("train", "inner_join_parent", "INNER JOIN", "각 주문의 주문번호와 고객 이름을 구해 주세요.", "고객번호가 같은 행을 연결합니다. 하늘의 주문이 두 개라 이름도 두 행에 나옵니다.", [C,O], "SELECT o.id, c.name FROM orders o JOIN customers c ON o.customer_id = c.id", ["id","name"], [[10,"하늘"],[11,"하늘"],[12,"바다"]])
add("train", "left_join_preservation", "LEFT JOIN", "주문 없는 고객도 남겨 고객 이름과 주문번호를 조회해 주세요.", "LEFT JOIN은 왼쪽 고객을 모두 보존합니다. 주문 없는 숲의 주문번호는 NULL입니다.", [C,O], "SELECT c.name, o.id FROM customers c LEFT JOIN orders o ON c.id = o.customer_id", ["name","id"], [["하늘",10],["하늘",11],["바다",12],["숲",None]])
add("train", "distinct_projection", "DISTINCT", "상품 분류 목록을 중복 없이 구해 주세요.", "DISTINCT는 결과 행의 중복을 제거하여 책과 펜을 한 번씩 보여 줍니다.", [P], "SELECT DISTINCT category FROM products", ["category"], [["책"],["펜"]])
add("train", "multi_key_ordering", "정렬", "재고 내림차순, 같은 재고이면 id 오름차순으로 id를 조회해 주세요.", "정렬 기준을 순서대로 적습니다. 재고 10, 4, 2, 0에 해당하는 id는 3, 1, 4, 2입니다.", [P], "SELECT id FROM products ORDER BY stock DESC, id ASC", ["id"], [[3],[1],[4],[2]], True)
add("train", "between_inclusive", "BETWEEN", "가격이 3 이상 12 이하인 id를 구해 주세요.", "BETWEEN은 양쪽 경계값을 포함하므로 가격 3과 12가 모두 선택됩니다.", [P], "SELECT id FROM products WHERE price BETWEEN 3 AND 12", ["id"], [[1],[3]])
add("train", "in_membership", "IN", "id가 1 또는 4인 상품의 분류를 조회해 주세요.", "IN은 나열된 값 중 하나와 일치하는지 확인합니다. 결과는 책과 펜입니다.", [P], "SELECT category FROM products WHERE id IN (1, 4)", ["category"], [["책"],["펜"]])
add("train", "like_prefix", "LIKE", "text가 SQL로 시작하는 메모 id를 구해 주세요.", "퍼센트 기호는 뒤에 이어지는 0개 이상의 문자를 나타냅니다. 첫 두 메모가 해당합니다.", [N], "SELECT id FROM notes WHERE text LIKE 'SQL%'", ["id"], [[1],[2]])
add("train", "coalesce_display", "COALESCE", "가격이 비어 있으면 0으로 보여 주고 id와 표시 가격을 구해 주세요.", "COALESCE는 왼쪽부터 처음 NULL이 아닌 값을 선택합니다. 저장된 가격을 수정하는 쿼리는 아닙니다.", [P], "SELECT id, COALESCE(price, 0) AS shown_price FROM products", ["id","shown_price"], [[1,12],[2,18],[3,3],[4,0]])
add("train", "case_classification", "CASE", "재고가 0이면 품절, 아니면 판매로 표시해 주세요.", "CASE는 조건에 맞는 값을 결과 열로 만듭니다. id 2만 재고가 0입니다.", [P], "SELECT id, CASE WHEN stock = 0 THEN '품절' ELSE '판매' END AS state FROM products", ["id","state"], [[1,"판매"],[2,"품절"],[3,"판매"],[4,"판매"]])
add("train", "aggregate_expression", "계산식 집계", "가격과 재고를 곱한 값의 합계를 구해 주세요.", "입력된 가격 기준으로 12×4+18×0+3×10=78입니다. 마지막 행의 NULL 계산 결과는 SUM에서 제외되므로 실제 전체 가치라고 단정하면 안 됩니다.", [P], "SELECT SUM(price * stock) AS known_value FROM products", ["known_value"], [[78]])
add("train", "average_nonnull", "AVG와 NULL", "입력된 직원 급여의 평균을 구해 주세요.", "급여가 있는 세 명의 100+160+90을 3으로 나누므로 약 116.6667입니다. NULL을 0으로 간주해 네 명으로 나누지 않습니다.", [E], "SELECT AVG(pay) AS mean_pay FROM staff", ["mean_pay"], [[350/3]])
add("train", "min_max_range", "MIN·MAX", "입력된 가격 중 최저와 최고를 구해 주세요.", "MIN과 MAX는 NULL을 제외한 12, 18, 3 중에서 3과 18을 반환합니다.", [P], "SELECT MIN(price) AS lowest, MAX(price) AS highest FROM products", ["lowest","highest"], [[3,18]])
add("train", "pagination_offset", "LIMIT·OFFSET", "id 오름차순에서 첫 행을 건너뛰고 두 행의 id를 구해 주세요.", "ORDER BY로 순서를 고정한 뒤 OFFSET 1로 한 행을 건너뛰고 LIMIT 2로 두 행을 받습니다.", [P], "SELECT id FROM products ORDER BY id LIMIT 2 OFFSET 1", ["id"], [[2],[3]], True)
add("train", "text_concatenation", "문자열 결합", "각 고객 이름 뒤에 님을 붙여 label 열로 보여 주세요.", "SQLite의 문자열 결합 연산자는 ||입니다. 원본 이름은 바뀌지 않습니다.", [C], "SELECT name || '님' AS label FROM customers", ["label"], [["하늘님"],["바다님"],["숲님"]])
add("train", "unicode_length", "문자 수", "메모별 id와 text 문자 수를 구해 주세요.", "SQLite LENGTH는 이 텍스트에서 공백을 포함한 문자 수를 셉니다. 앞의 두 메모는 6자, 자료 모음은 5자입니다.", [N], "SELECT id, LENGTH(text) AS chars FROM notes", ["id","chars"], [[1,6],[2,6],[3,5]])
add("train", "numeric_rounding", "반올림", "입력된 가격 평균을 소수 첫째 자리까지 반올림해 주세요.", "평균은 33/3=11이므로 ROUND의 결과는 11.0입니다. 표시 형식의 자릿수 고정은 UI에서 별도로 할 수 있습니다.", [P], "SELECT ROUND(AVG(price), 1) AS rounded_mean FROM products", ["rounded_mean"], [[11.0]])
add("train", "and_predicates", "AND", "재고가 있고 가격이 10 미만인 상품 id를 구해 주세요.", "두 조건이 모두 참이어야 합니다. id 3은 재고 10, 가격 3이므로 해당합니다. NULL 가격은 참 판정을 받지 않습니다.", [P], "SELECT id FROM products WHERE stock > 0 AND price < 10", ["id"], [[3]])

add("validation", "count_distinct_values", "중복 제거 집계", "서로 다른 분류의 수를 구해 주세요.", "COUNT(DISTINCT category)는 중복을 제거한 NULL 아닌 분류의 수를 셉니다. 책과 펜으로 2개입니다.", [P], "SELECT COUNT(DISTINCT category) AS kinds FROM products", ["kinds"], [[2]])
add("validation", "null_or_truth", "3값 논리", "가격이 10보다 크거나 가격이 비어 있는 id를 구해 주세요.", "OR의 한쪽이 참이면 선택됩니다. 가격이 12와 18인 행, 그리고 IS NULL이 참인 id 4가 남습니다.", [P], "SELECT id FROM products WHERE price > 10 OR price IS NULL", ["id"], [[1],[2],[4]])
add("validation", "not_in_null_trap", "NOT IN과 NULL", "id NOT IN (2, NULL) 조건의 결과와 이유를 설명해 주세요.", "id 2는 비교가 거짓이고 나머지는 NULL과의 비교 때문에 UNKNOWN입니다. WHERE는 참만 남기므로 결과 행이 없습니다.", [P], "SELECT id FROM products WHERE id NOT IN (2, NULL)", ["id"], [])
add("validation", "filter_before_group", "WHERE와 집계", "재고가 양수인 행만 대상으로 분류별 상품 수를 구해 주세요.", "WHERE가 먼저 재고 0인 id 2를 제외합니다. 그 뒤 책 1개, 펜 2개로 집계합니다.", [P], "SELECT category, COUNT(*) AS n FROM products WHERE stock > 0 GROUP BY category", ["category","n"], [["책",1],["펜",2]])
add("validation", "empty_aggregate", "빈 집계", "id가 99인 행의 수와 가격 합계를 구해 주세요.", "대상 행이 없어도 GROUP BY 없는 집계는 한 행을 반환합니다. COUNT는 0이고 SUM은 NULL입니다.", [P], "SELECT COUNT(*) AS n, SUM(price) AS total FROM products WHERE id = 99", ["n","total"], [[0,None]])
add("validation", "self_join_manager", "셀프 조인", "상사가 있는 직원의 id와 상사 id를 실제 직원 행과 연결해 구해 주세요.", "같은 staff를 직원 e와 상사 m으로 구분합니다. 연결 결과는 2→1, 3→1, 4→3입니다.", [E], "SELECT e.id AS employee, m.id AS manager FROM staff e JOIN staff m ON e.manager_id = m.id", ["employee","manager"], [[2,1],[3,1],[4,3]])
add("validation", "union_all_duplicates", "UNION ALL", "a와 b의 v를 중복을 유지해 합쳐 주세요.", "UNION ALL은 중복 행을 제거하지 않습니다. 1이 두 번, 2가 두 번, 3이 한 번 나옵니다.", [A,B], "SELECT v FROM a UNION ALL SELECT v FROM b", ["v"], [[1],[1],[2],[2],[3]])
add("validation", "exists_semijoin", "EXISTS", "주문이 하나 이상 있는 고객 id를 한 번씩 구해 주세요.", "EXISTS는 해당 고객의 주문 존재 여부만 확인합니다. 주문이 두 개인 고객 1도 한 번만 나옵니다.", [C,O], "SELECT c.id FROM customers c WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id)", ["id"], [[1],[2]])

add("test", "correlated_group_max", "상관 서브쿼리", "각 팀에서 입력된 급여가 가장 큰 직원 id를 모두 구해 주세요.", "직원이 속한 팀의 최대 급여와 자신의 급여를 비교합니다. 가 팀은 id 2, 나 팀은 id 3입니다. 동점이면 모두 반환합니다.", [E], "SELECT s.id FROM staff s WHERE s.pay = (SELECT MAX(t.pay) FROM staff t WHERE t.team = s.team)", ["id"], [[2],[3]])
add("test", "not_exists_antijoin", "미존재 조회", "주문이 전혀 없는 고객 이름을 구해 주세요.", "NOT EXISTS는 연결되는 주문이 없는 고객을 찾습니다. 숲만 주문이 없습니다.", [C,O], "SELECT c.name FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id)", ["name"], [["숲"]])
add("test", "cross_product_count", "교차 조인", "a와 b를 CROSS JOIN한 결과의 행 수를 구해 주세요.", "a의 세 행 각각이 b의 두 행과 결합하므로 3×2=6행입니다. 중복 원본 행도 별개로 셉니다.", [A,B], "SELECT COUNT(*) AS pairs FROM a CROSS JOIN b", ["pairs"], [[6]])
add("test", "union_distinct_set", "UNION", "a와 b의 v를 합치되 중복을 없애 주세요.", "UNION은 합친 결과의 중복 행을 제거합니다. 결과 값은 1, 2, 3이며 ORDER BY 없이는 순서를 보장하지 않습니다.", [A,B], "SELECT v FROM a UNION SELECT v FROM b", ["v"], [[1],[2],[3]])
add("test", "intersect_common_set", "INTERSECT", "a와 b에 모두 있는 v를 중복 없이 구해 주세요.", "INTERSECT는 두 결과에 공통인 행을 남깁니다. 공통 값은 2입니다.", [A,B], "SELECT v FROM a INTERSECT SELECT v FROM b", ["v"], [[2]])
add("test", "except_difference_set", "EXCEPT", "a에는 있고 b에는 없는 v를 중복 없이 구해 주세요.", "EXCEPT는 왼쪽 결과에서 오른쪽에도 있는 행을 제외하고 중복을 제거합니다. 값 1만 남습니다.", [A,B], "SELECT v FROM a EXCEPT SELECT v FROM b", ["v"], [[1]])
add("test", "outer_join_count_child", "외부 조인 집계", "주문 없는 고객을 0으로 포함해 고객별 주문 수를 구해 주세요.", "LEFT JOIN 뒤 COUNT(o.id)를 사용해야 주문 없는 고객의 NULL 확장 행을 세지 않습니다. COUNT(*)라면 숲도 1로 잘못 셉니다.", [C,O], "SELECT c.id, COUNT(o.id) AS order_count FROM customers c LEFT JOIN orders o ON c.id = o.customer_id GROUP BY c.id", ["id","order_count"], [[1,2],[2,1],[3,0]])
add("test", "having_count_multiple", "그룹 빈도 조건", "주문을 두 번 이상 한 고객번호를 구해 주세요.", "고객번호로 묶고 HAVING COUNT(*) >= 2로 그룹을 고릅니다. 고객 1은 두 주문이 있습니다.", [O], "SELECT customer_id FROM orders GROUP BY customer_id HAVING COUNT(*) >= 2", ["customer_id"], [[1]])
add("test", "real_division_percentage", "실수 나눗셈", "상품 중 재고가 0인 행의 비율을 백분율로 구해 주세요.", "네 행 중 한 행이므로 25%입니다. 100.0을 곱해 정수 나눗셈으로 소수 부분이 사라지는 것을 피합니다.", [P], "SELECT 100.0 * SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) / COUNT(*) AS pct FROM products", ["pct"], [[25.0]])
D = table("sales", [("day", "TEXT"), ("amount", "REAL")], [["2026-01-03",8],["2026-01-19",12],["2026-02-01",7]])
add("test", "date_month_bucket", "월별 집계", "YYYY-MM-DD 형식 day를 월별로 묶어 매출 합계를 구해 주세요.", "strftime의 %Y-%m으로 연도와 월을 함께 묶습니다. 1월 20, 2월 7입니다.", [D], "SELECT strftime('%Y-%m', day) AS month, SUM(amount) AS total FROM sales GROUP BY strftime('%Y-%m', day)", ["month","total"], [["2026-01",20],["2026-02",7]])
add("test", "scalar_subquery_average", "전체 평균 비교", "입력된 전체 급여 평균보다 많이 받는 직원 id를 구해 주세요.", "NULL을 제외한 평균은 약 116.67입니다. 급여 160인 직원 2만 평균보다 큽니다.", [E], "SELECT id FROM staff WHERE pay > (SELECT AVG(pay) FROM staff)", ["id"], [[2]])
add("test", "insufficient_schema_clarification", "조건 부족 확인", "매출이 가장 좋은 사람을 뽑는 SQL을 써 주세요. 표는 아직 보내지 않았습니다.", "정확한 SQL을 쓰려면 표 이름, 담당자 식별 열, 매출 금액 열, 집계 기간을 알려 주세요. 가장 좋다는 기준이 합계인지 평균인지, 동점자를 모두 포함할지도 필요합니다. 이 정보 없이 실제 열 이름이나 순위를 정답처럼 만들 수는 없습니다.")

if __name__ == "__main__":
    destination = Path(__file__).parent / "demo"
    destination.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation", "test"):
        selected = [r for r in records if r["split"] == split]
        (destination / f"{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in selected), encoding="utf-8")
        print(split, len(selected))
