import pytest

from edu_tutor.lessons.verified import concept_plan
from edu_tutor.problems.ddl_examples import build_ddl_example
from edu_tutor.problems.models import normalize_problem
from edu_tutor.problems.pipeline import model_messages


def example(command):
    return build_ddl_example("설명용 새 예시:\n```sql\nCREATE TABLE inventory (id INTEGER, units INTEGER, note TEXT); "
        "INSERT INTO inventory VALUES (7, 0, NULL), (8, 5, 'kept'); " + command + "\n```")


@pytest.mark.parametrize("command,rows,changed", [
    ("UPDATE inventory SET units = -3 WHERE id = 7;", [[7,-3,None],[8,5,"kept"]], [[0,1]]),
    ("UPDATE inventory SET note = 'checked' WHERE note IS NULL;", [[7,0,"checked"],[8,5,"kept"]], [[0,2]]),
    ("UPDATE inventory SET units = NULL;", [[7,None,None],[8,None,"kept"]], [[0,1],[1,1]]),
    ("UPDATE inventory SET units = 0 WHERE id = 7;", [[7,0,None],[8,5,"kept"]], []),
    ("UPDATE inventory SET units = 9 WHERE id = 999;", [[7,0,None],[8,5,"kept"]], []),
])
def test_literal_update_records_actual_before_after_and_changed_cells(command, rows, changed):
    result=example(command)
    assert result['status']=='verified', result
    stage=result['steps'][-1]
    assert stage['operation']=='update_values'
    assert stage['before'][0]['rows']==[[7,0,None],[8,5,'kept']]
    assert stage['after'][0]['rows']==rows
    assert stage['effects']['changed_cells']==changed
    assert stage['effects']['rows_before']==stage['effects']['rows_after']==2
    assert stage['effects']['columns_before']==stage['effects']['columns_after']==3
    assert 'UPDATE' in stage['narration']
    assert '바뀐 값은 999' not in stage['narration']


@pytest.mark.parametrize("command", ["UPDATE inventory SET units=units+1;",
    "UPDATE inventory SET units=(SELECT 3);", "UPDATE inventory SET units=3 WHERE id>1;",
    "UPDATE inventory SET missing=3;", "UPDATE inventory SET units=3 RETURNING *;",
    "UPDATE inventory SET units=3 FROM other;", "UPDATE inventory SET units=3, units=4;",
    "UPDATE inventory SET note=readfile('secret');"])
def test_unproved_update_extensions_are_blocked(command):
    result=example(command)
    assert result['status']=='blocked' and not result['steps']


def test_primary_key_change_is_not_published_with_false_row_identity():
    result=build_ddl_example('```sql\nCREATE TABLE x(id INTEGER PRIMARY KEY, val INTEGER); '
        'INSERT INTO x VALUES(2,7),(1,4); UPDATE x SET id=3 WHERE id=1;\n```')
    assert result['status']=='blocked' and '기본키' in result['reason']


def test_sql_like_update_string_stays_literal_and_plan_points_at_real_changed_cell():
    p=normalize_problem({'task_kind':'concept','raw_text':'UPDATE와 열 추가의 차이는 무엇인가요?',
                         'confirmed':True,'dialect':'sqlite'})
    raw="설명용 새 예시\n```sql\nCREATE TABLE notebook(note TEXT); INSERT INTO notebook VALUES('old'); UPDATE notebook SET note='DROP TABLE notebook;';\n```"
    msg={'id':'cpu-update','content':raw,'raw_model_response':raw,'problem':p,'evidence':{},'sources':[]}
    result=concept_plan(msg,p['raw_text'],'cpu-update-lesson')
    assert result['speech_allowed']
    last=result['plan']['steps'][-1]
    after=next(a for a in last['board_actions'] if a['type']=='table' and a['caption'].endswith('실행 후'))
    highlight=next(a for a in last['board_actions'] if a['type']=='highlight')
    assert after['rows']==[['DROP TABLE notebook;']]
    assert highlight['cell_ids']==[after['cell_ids'][0][0]]
    assert last['gesture']['target_element_id']==after['element_id']
    assert '1개 칸' in last['speech']
    assert 'UPDATE SET' in model_messages(p['raw_text'],p,[])[0]['content']
