"""Author fresh development inputs; no model, OCR, audio or network calls.

Expected values stay in a separate harness file and never enter model prompts.
These examples are development journeys, not the frozen independent final set.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/finish-v2/20261029/student"


def table(name, columns, rows):
    return {"name": name, "columns": [{"name": n, "type": t} for n, t in columns], "rows": rows}


def execute(tables, query):
    with sqlite3.connect(":memory:") as db:
        for item in tables:
            columns = ", ".join('"' + c["name"] + '" ' + c["type"] for c in item["columns"])
            db.execute('CREATE TABLE "' + item["name"] + '" (' + columns + ')')
            placeholders = ",".join("?" for _ in item["columns"])
            db.executemany('INSERT INTO "' + item["name"] + '" VALUES (' + placeholders + ')', item["rows"])
        cursor = db.execute(query)
        return {"columns": [c[0] for c in cursor.description], "rows": [list(r) for r in cursor.fetchall()]}


def image_page(path, title, tab, sql_lines, *, crop_y=None, rotate=False):
    font_path = Path("C:/Windows/Fonts/malgun.ttf")
    font = ImageFont.truetype(str(font_path), 29)
    mono = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 24)
    image = Image.new("RGB", (1240, 730), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 18), "직접 작성한 개발 검증 문제 · 실제 학생 업로드 아님", font=font, fill="#333333")
    draw.text((30, 64), title, font=font, fill="black")
    draw.text((30, 112), "테이블: " + tab["name"], font=font, fill="black")
    x, y, width, height = 30, 160, 280, 54
    visible = [[c["name"] for c in tab["columns"]], *tab["rows"]]
    for row_number, row in enumerate(visible):
        for column_number, cell in enumerate(row):
            box = (x + column_number * width, y + row_number * height,
                   x + (column_number + 1) * width, y + (row_number + 1) * height)
            draw.rectangle(box, outline="black", width=2)
            draw.text((box[0] + 12, box[1] + 9), "NULL" if cell is None else str(cell), font=font, fill="black")
    sql_y = y + len(visible) * height + 30
    for index, line in enumerate(sql_lines):
        draw.text((30, sql_y + 40 * index), line, font=mono, fill="black")
    if crop_y is not None:
        image = image.crop((0, 0, image.width, sql_y + crop_y))
    if rotate:
        image = image.rotate(2, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
        image = image.filter(ImageFilter.GaussianBlur(.35))
    image.save(path)
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "width": image.width, "height": image.height, "authoring": "Procedural PIL text/table drawing",
            "font": str(font_path), "rights": "Original development question and data authored for this project; no textbook/student data",
            "human_review": "H_PENDING", "rotated_degrees": 2 if rotate else 0, "blur_radius": .35 if rotate else 0,
            "critical_condition_cropped": crop_y is not None}


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "journeys.json").exists():
        raise RuntimeError("Inputs already frozen; do not overwrite existing journeys")
    images = OUT / "images"
    images.mkdir(exist_ok=True)
    readings = table("reading_log", [("topic", "TEXT"), ("minutes", "INTEGER")],
                     [["정규화", 18], ["조인", None], ["키", 0], ["정렬", 12]])
    visits = table("visits", [("branch", "TEXT"), ("tickets", "INTEGER"), ("open", "INTEGER")],
                   [["동", 4, 1], ["동", 7, 1], ["동", 30, 0], ["서", 5, 1], ["서", None, 1], ["남", 9, 1]])
    deliveries = table("delivery", [("zone", "TEXT"), ("boxes", "INTEGER"), ("paid", "INTEGER")],
                       [["A", 3, 1], ["A", 8, 1], ["B", 2, 1], ["B", 20, 0], ["C", 12, 1]])
    stock = table("stock", [("item", "TEXT"), ("qty", "INTEGER")],
                  [["지우개", 7], ["연필", None], ["종이", 0], ["풀", 2]])
    bills = table("bills", [("label", "TEXT"), ("amount", "INTEGER")],
                  [["가", 12], ["나", None], ["다", 6], ["라", 0]])
    sq1 = "SELECT COUNT(*) AS all_rows, COUNT(qty) AS present_rows FROM stock;"
    sq2 = "SELECT SUM(amount) AS total, AVG(amount) AS average FROM bills;"
    cropped_source = "SELECT item FROM stock WHERE qty >= 2 ORDER BY item;"
    photo1 = image_page(images / "normal-stock.png", "다음 SQL의 두 결과 값은 무엇인가요?", stock,
                        ["SELECT COUNT(*) AS all_rows, COUNT(qty) AS present_rows", "FROM stock;"])
    photo2 = image_page(images / "rotated-bills.png", "다음 합계와 평균이 왜 이렇게 계산되나요?", bills,
                        ["SELECT SUM(amount) AS total, AVG(amount) AS average", "FROM bills;"], rotate=True)
    source_image = image_page(images / "missing-source-private.png", "다음 SQL에서 선택되는 물건은 무엇인가요?", stock,
                              ["SELECT item FROM stock", "WHERE qty >=", "2 ORDER BY item;"])
    photo3 = image_page(images / "cropped-condition.png", "다음 SQL에서 선택되는 물건은 무엇인가요?", stock,
                        ["SELECT item FROM stock", "WHERE qty >=", "2 ORDER BY item;"], crop_y=78)
    journeys = [
        {"id": "J01", "kind": "concept", "question": "DDL과 DML이 헷갈려. 작은 book 테이블을 만들고 행 하나를 넣는 예시로 구조와 데이터의 차이를 설명해 줘.", "expected_scope": "Executed model-authored CREATE/INSERT example; raw concept prose remains separately reviewable"},
        {"id": "J02", "kind": "concept", "question": "테이블에 열을 추가하는 것과 기존 행의 값을 바꾸는 것은 어떻게 달라? SQLite에서 간단한 도서 목록 예시로 보여 줘.", "expected_scope": "Executed model-authored structure/value change; no invented student source table"},
        {"id": "J03", "kind": "table", "task_kind": "query_result", "tables": [readings],
         "query": "SELECT COUNT(*) AS entries, COUNT(minutes) AS recorded, SUM(minutes) AS total FROM reading_log;",
         "question": "직접 작성한 개발 검증 표야. 전체 행 수, 기록된 시간 개수, 총 시간을 원본에서 결과까지 차례대로 설명해 줘. NULL과 0을 구분해 줘."},
        {"id": "J04", "kind": "table", "task_kind": "query_result", "tables": [visits],
         "query": "SELECT branch, COUNT(*) AS visits, SUM(tickets) AS tickets FROM visits WHERE open = 1 GROUP BY branch HAVING SUM(tickets) >= 9 ORDER BY branch;",
         "question": "직접 작성한 개발 검증 표야. 문을 연 기록만 묶은 다음 합계가 9 이상인 지점을 남기는 과정을 원본·중간 표·최종 표로 보여 줘.",
         "followup": {"question": "선택한 이 행은 왜 조건을 통과해서 포함되는 거야?", "column": "open", "row_index": 0, "value": 1}},
        {"id": "J05", "kind": "group_diagram", "task_kind": "query_result", "tables": [deliveries],
         "query": "SELECT zone, SUM(boxes) AS boxes FROM delivery WHERE paid = 1 GROUP BY zone HAVING SUM(boxes) >= 10 ORDER BY zone;",
         "question": "직접 만든 개발 예시야. 결제가 끝난 배송을 구역별로 합칠 때 WHERE와 HAVING의 차이를 표로 설명하고, 원본에서 그룹과 결과로 가는 간단한 화살표 그림도 보여 줘.",
         "followup": {"question": "이 행이 결과를 만드는 데 남아 있는 이유를 다시 알려 줘.", "column": "paid", "row_index": 1, "value": 1},
         "requires_simple_diagram": True},
        {"id": "J06", "kind": "photo", "photo": photo1, "expected_condition": "normal"},
        {"id": "J07", "kind": "photo", "photo": photo2, "expected_condition": "complete_slight_rotation_and_blur"},
        {"id": "J08", "kind": "photo", "photo": photo3, "expected_condition": "missing_critical_threshold", "must_not_invent": True},
    ]
    expected = {j["id"]: {"result": execute(j["tables"], j["query"]), "question": j["question"]}
                for j in journeys if "query" in j}
    expected.update(J06={"tables": [stock], "query": sq1, "result": execute([stock], sq1)},
                    J07={"tables": [bills], "query": sq2, "result": execute([bills], sq2)},
                    J08={"source_tables": [stock], "hidden_source_query": cropped_source,
                         "source_image": source_image, "expected": "ask_for_missing_condition_without_inventing_threshold"})
    provenance = {"purpose": "New original development journeys, separate from independent final80",
                  "source": "Original procedural test authoring; no actual student upload",
                  "data_rights": "Project-authored synthetic data; no third-party course content",
                  "human_review": "H_PENDING", "model_calls": 0, "tts_calls": 0, "ocr_calls": 0,
                  "expected_answers_sent_to_model": False,
                  "planned_question_events": 10, "planned_journeys": 8,
                  "latency_note": "Missing-condition failure/safe-stop remains in denominator; not averaged as successful explanation",
                  "timing_targets_seconds": {"first_valid_warm": 10, "supplement_warm": 10, "step_gap": 2, "local_stop": .5}}
    (OUT / "journeys.json").write_text(json.dumps({"provenance": provenance, "journeys": journeys}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "private-oracle.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"journeys": len(journeys), "question_events_planned": 10, "model_calls": 0,
                      "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    prepare()
