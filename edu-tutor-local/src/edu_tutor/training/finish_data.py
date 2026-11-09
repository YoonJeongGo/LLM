"""Original, deterministic SQLite exercises with independent Python calculations.

Training data authoring only: this module is never imported by student inference.
Names and numeric variants stay inside one problem family and one split.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .data import validate_dataset


TRAIN = ('project', 'positive', 'null', 'nonnull', 'zero', 'distinct_group',
         'descending', 'count_all', 'count_value', 'sum', 'average', 'minmax',
         'boolean_sum', 'group_count', 'group_sum', 'having_sum', 'inner', 'left',
         'and', 'or', 'create', 'insert', 'update', 'delete')
VALIDATION = ('between', 'distinct_pair', 'count_distinct', 'group_average',
              'having_count', 'join_positive', 'left_missing', 'notnull_constraint')
FINAL = ('multikey', 'filter_order', 'not_zero', 'empty_aggregate',
         'null_average', 'filtered_minmax', 'group_filtered_sum', 'group_nonnull_count',
         'left_count', 'join_on_filter', 'left_where_filter', 'join_multiplicity',
         'alter', 'primary_key', 'foreign_key', 'missing_schema')
SYSTEM = ('한국어 SQLite 기초 튜터입니다. 주어진 데이터만 사용하고 NULL과 0을 구분합니다. '
          'SQL이 필요하면 sql과 explanation 키의 JSON으로 답하세요. 설명은 짧고 정확하게 씁니다.')


def dumps(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def make_table(name, columns, rows):
    return {'name': name, 'columns': [{'name': n, 'type': t} for n, t in columns], 'rows': rows}


def database(tables):
    con = sqlite3.connect(':memory:')
    con.execute('PRAGMA foreign_keys=ON')
    for table in tables:
        definitions = ','.join('"'+c['name']+'" '+c['type'] for c in table['columns'])
        con.execute('CREATE TABLE "'+table['name']+'" ('+definitions+')')
        con.executemany('INSERT INTO "'+table['name']+'" VALUES ('+','.join('?' for _ in table['columns'])+')', table['rows'])
    return con


def aggregate(values, operation):
    known = [v for v in values if v is not None]
    if operation == 'count': return len(known)
    if not known: return None
    if operation == 'sum': return sum(known)
    if operation == 'average': return sum(known)/len(known)
    return (min if operation == 'min' else max)(known)


def exercise(family, index, split):
    n = index + 2
    name = f'item_{index+1}'
    other = f'label_{index+1}'
    rows = [[1, '가', n], [2, '가', None], [3, '나', 0], [4, '나', -n], [5, '나', n+1]]
    labels = [[1, '하늘'], [3, '바다'], [6, '숲']]
    if family == 'join_multiplicity': labels.insert(1, [1, '별'])
    tables = [make_table(name, [('id', 'INTEGER'), ('grp', 'TEXT'), ('val', 'INTEGER')], rows)]
    values = [r[2] for r in rows]
    positive = [r for r in rows if r[2] is not None and r[2] > 0]
    groups = defaultdict(list)
    for r in rows: groups[r[1]].append(r)
    ordered = True
    sql = question = rule = None
    expected = []
    selected = rows
    concept_result = None
    if family == 'project':
        sql=f'SELECT id, val FROM {name} ORDER BY id'; question='id와 val을 id 순서로 조회하세요.'
        expected=[[r[0],r[2]] for r in rows]; rule='SELECT는 열을 고릅니다. 원본 값과 NULL을 그대로 유지합니다.'
    elif family in {'positive','null','nonnull','zero','and','or','between','not_zero'}:
        predicates={
            'positive':('val > 0',lambda r:r[2] is not None and r[2]>0,'val이 양수인 행'),
            'null':('val IS NULL',lambda r:r[2] is None,'val이 NULL인 행'),
            'nonnull':('val IS NOT NULL',lambda r:r[2] is not None,'val이 NULL이 아닌 행'),
            'zero':('val = 0',lambda r:r[2]==0,'val이 0인 행'),
            'and':("grp = '나' AND val > 0",lambda r:r[1]=='나' and r[2] is not None and r[2]>0,'grp가 나이고 val이 양수인 행'),
            'or':('val = 0 OR val IS NULL',lambda r:r[2] is None or r[2]==0,'val이 0이거나 NULL인 행'),
            'between':(f'val BETWEEN {-n} AND 0',lambda r:r[2] is not None and -n<=r[2]<=0,f'val이 {-n} 이상 0 이하인 행'),
            'not_zero':('NOT (val = 0)',lambda r:r[2] is not None and r[2]!=0,'val이 0이 아닌 행(NULL 제외)')}
        predicate, test, words=predicates[family];selected=[r for r in rows if test(r)]
        sql=f'SELECT id FROM {name} WHERE {predicate} ORDER BY id';question=words+'의 id를 오름차순으로 조회하고 선택 이유를 설명하세요.'
        expected=[[r[0]] for r in selected]; rule=f'WHERE {predicate}가 참인 행만 남깁니다. NULL 비교의 UNKNOWN은 선택되지 않습니다.'
    elif family in {'distinct_group','distinct_pair'}:
        column='grp' if family=='distinct_group' else 'grp, val'
        sql=f'SELECT DISTINCT {column} FROM {name}';question=f'{column} 결과 행을 중복 없이 조회하세요.'
        expected=[list(v) for v in dict.fromkeys((r[1],) if family=='distinct_group' else (r[1],r[2]) for r in rows)];ordered=False
        rule='DISTINCT는 같은 결과 값을 하나로 줄입니다. NULL도 결과에 있으면 하나만 남습니다.'
    elif family in {'descending','multikey','filter_order'}:
        if family=='descending':
            sql=f'SELECT id, val FROM {name} ORDER BY val DESC, id';question='val 내림차순, 동점이면 id 오름차순으로 id와 val을 보여 주세요.'
            selected=sorted(rows,key=lambda r:(r[2] is None,-(r[2] or 0),r[0]))
        elif family=='multikey':
            sql=f'SELECT id, grp, val FROM {name} ORDER BY grp DESC, val ASC, id';question='grp 내림차순, 같은 그룹은 val 오름차순, 같은 val은 id 순서로 세 열을 보여 주세요.'
            selected=sorted(rows,key=lambda r:(-ord(r[1]),r[2] is not None,r[2] or 0,r[0]))
        else:
            sql=f'SELECT id, val FROM {name} WHERE val IS NOT NULL ORDER BY val ASC, id';question='NULL을 제외하고 val 오름차순, 동점은 id 순서로 id와 val을 보여 주세요.'
            selected=sorted([r for r in rows if r[2] is not None],key=lambda r:(r[2],r[0]))
        expected=[r[:] if family=='multikey' else [r[0],r[2]] for r in selected]
        rule='WHERE가 있으면 먼저 걸러낸 뒤 ORDER BY의 우선순위대로 정렬합니다. SQLite에서 NULL은 작은 값으로 정렬됩니다.'
    elif family in {'count_all','count_value','sum','average','minmax','boolean_sum','count_distinct','empty_aggregate','null_average','filtered_minmax'}:
        if family=='count_all':
            sql=f'SELECT COUNT(*) AS n FROM {name}'; expected=[[len(rows)]];question='NULL을 가진 행도 포함해 전체 행 수를 구하세요.';rule='COUNT(*)는 값이 아니라 행을 셉니다.'
        elif family=='count_value':
            sql=f'SELECT COUNT(val) AS n FROM {name}';expected=[[aggregate(values,'count')]];question='val이 입력된 행 수를 구하세요.';rule='COUNT(val)은 NULL만 제외합니다. 0과 음수도 셉니다.'
        elif family in {'sum','average'}:
            fn='SUM' if family=='sum' else 'AVG';sql=f'SELECT {fn}(val) AS result FROM {name}';expected=[[aggregate(values,family)]];question='입력된 val의 '+('합계' if family=='sum' else '평균')+'를 구하세요.'
            rule='NULL을 제외한 값으로 계산합니다. '+('합계를 구합니다.' if family=='sum' else '합계를 NULL 아닌 값의 개수로 나눕니다.')
        elif family=='minmax':
            sql=f'SELECT MIN(val) AS low, MAX(val) AS high FROM {name}';expected=[[aggregate(values,'min'),aggregate(values,'max')]];question='입력된 val의 최솟값과 최댓값을 구하세요.';rule='MIN과 MAX는 NULL을 제외합니다.'
        elif family=='boolean_sum':
            sql=f'SELECT SUM(val IS NOT NULL) AS n FROM {name}';expected=[[sum(v is not None for v in values)]];question='각 행의 val IS NOT NULL 결과를 SUM으로 더하세요.';rule='IS NOT NULL은 NULL이면 0, 아니면 1입니다. 이 표는 비어 있지 않아 그 값을 더합니다.'
        elif family=='count_distinct':
            sql=f'SELECT COUNT(DISTINCT val) AS n FROM {name}';expected=[[len({v for v in values if v is not None})]];question='NULL을 제외한 서로 다른 val의 개수를 구하세요.';rule='중복 값과 NULL을 제외한 뒤 셉니다.'
        elif family=='empty_aggregate':
            sql=f'SELECT COUNT(*) AS n, SUM(val) AS total FROM {name} WHERE id < 0';expected=[[0,None]];selected=[];question='id가 음수인 행만 대상으로 행 수와 val 합계를 구하세요.';rule='입력이 비어도 GROUP BY 없는 집계는 한 행입니다. COUNT는 0이고 SUM은 NULL입니다.'
        elif family=='null_average':
            sql=f'SELECT COUNT(val) AS n, AVG(val) AS mean FROM {name} WHERE val IS NULL';expected=[[0,None]];selected=[r for r in rows if r[2] is None];question='val이 NULL인 행만 대상으로 COUNT(val)과 AVG(val)을 구하세요.';rule='집계에 사용할 NULL 아닌 값이 없어서 COUNT(val)은 0, AVG(val)은 NULL입니다.'
        else:
            sql=f'SELECT MIN(val) AS low, MAX(val) AS high FROM {name} WHERE val >= 0';selected=[r for r in rows if r[2] is not None and r[2]>=0];v=[r[2] for r in selected];expected=[[min(v),max(v)]];question='val이 0 이상인 행만 대상으로 최솟값과 최댓값을 구하세요.';rule='행을 거른 뒤 남은 값의 최솟값과 최댓값을 계산합니다.'
    elif family in {'group_count','group_sum','having_sum','group_average','having_count','group_filtered_sum','group_nonnull_count'}:
        if family=='group_filtered_sum':
            selected=[r for r in rows if r[2] is not None and r[2]>=0];groups=defaultdict(list)
            for r in selected:groups[r[1]].append(r)
        operation='count' if family in {'group_count','having_count','group_nonnull_count'} else 'average' if family=='group_average' else 'sum'
        arg='*' if family in {'group_count','having_count'} else 'val'
        fn={'count':'COUNT','sum':'SUM','average':'AVG'}[operation]
        where=' WHERE val >= 0' if family=='group_filtered_sum' else ''
        having=' HAVING SUM(val) > 1' if family=='having_sum' else ' HAVING COUNT(*) >= 3' if family=='having_count' else ''
        sql=f'SELECT grp, {fn}({arg}) AS result FROM {name}{where} GROUP BY grp{having} ORDER BY grp'
        for g,rr in sorted(groups.items()):
            result=len(rr) if arg=='*' else aggregate([r[2] for r in rr],operation)
            if family=='having_sum' and not(result is not None and result>1):continue
            if family=='having_count' and result<3:continue
            expected.append([g,result])
        question={'group_count':'grp별 전체 행 수','group_sum':'grp별 val 합계','having_sum':'grp별 val 합계를 구하고 합계가 1보다 큰 그룹','group_average':'grp별 NULL을 제외한 val 평균','having_count':'grp별 행 수를 구하고 3행 이상인 그룹','group_filtered_sum':'val이 0 이상인 행만 대상으로 grp별 val 합계','group_nonnull_count':'grp별 NULL이 아닌 val의 개수'}[family]+'를 grp 순서로 보여 주세요.'
        rule='WHERE로 행 선택 → GROUP BY로 묶기 → 집계 → HAVING이 있으면 그룹 선택 순서입니다.'
    elif family in {'inner','left','join_positive','left_missing','left_count','join_on_filter','left_where_filter','join_multiplicity'}:
        tables.append(make_table(other,[('id','INTEGER'),('label','TEXT')],labels))
        pairs=[]
        for r in rows:
            matches=[l for l in labels if l[0]==r[0] and (family!='join_on_filter' or (r[2] is not None and r[2]>0))]
            pairs.extend((r,l) for l in matches)
            if not matches and family not in {'inner','join_positive','join_multiplicity'}:pairs.append((r,None))
        join='JOIN' if family in {'inner','join_positive','join_multiplicity'} else 'LEFT JOIN'
        on=' AND a.val > 0' if family=='join_on_filter' else ''
        where=' WHERE a.val > 0' if family in {'join_positive','left_where_filter'} else ' WHERE b.id IS NULL' if family=='left_missing' else ''
        if family in {'join_positive','left_where_filter'}:pairs=[(r,l) for r,l in pairs if r[2] is not None and r[2]>0]
        if family=='left_missing':pairs=[(r,l) for r,l in pairs if l is None]
        if family=='join_multiplicity':
            sql=f'SELECT a.id, COUNT(*) AS n FROM {name} a JOIN {other} b ON a.id = b.id GROUP BY a.id ORDER BY a.id'
            expected=[[r[0],sum(l[0]==r[0] for l in labels)] for r in rows if any(l[0]==r[0] for l in labels)]
            question='id로 INNER JOIN한 결과를 왼쪽 id별로 묶어 연결된 행 수를 구하세요. 오른쪽 중복 id도 세고 연결 없는 id는 제외하세요.'
        elif family=='left_count':
            sql=f'SELECT a.id, COUNT(b.id) AS n FROM {name} a LEFT JOIN {other} b ON a.id = b.id GROUP BY a.id ORDER BY a.id';expected=[[r[0],sum(l[0]==r[0] for l in labels)] for r in rows]
            question='왼쪽 모든 id별 연결된 label 행 수를 구하세요. 연결이 없으면 0입니다.'
        else:
            sql=f'SELECT a.id, b.label FROM {name} a {join} {other} b ON a.id = b.id{on}{where} ORDER BY a.id, b.label'
            expected=sorted([[r[0],l[1] if l else None] for r,l in pairs],key=lambda x:(x[0],x[1] or ''))
            question={'inner':'id가 같은 행만 연결해 왼쪽 id와 label을 구하세요.','left':'왼쪽 모든 행을 보존해 id와 연결된 label을 구하세요.','join_positive':'id가 같은 행을 연결하고 val이 양수인 행의 id와 label을 구하세요.','left_missing':'LEFT JOIN 뒤 연결이 없는 왼쪽 id와 label을 구하세요.','join_on_filter':'LEFT JOIN의 ON에 id 일치와 왼쪽 val > 0 조건을 넣고 모든 왼쪽 id와 label을 구하세요.','left_where_filter':'id로 LEFT JOIN한 다음 WHERE에서 왼쪽 val > 0을 적용해 id와 label을 구하세요.','join_multiplicity':'id로 INNER JOIN해 id와 label을 구하세요. 오른쪽 같은 id의 여러 행도 유지하세요.'}[family]+' id와 label 순서로 정렬하세요.'
        rule='각 왼쪽 행마다 ON에 맞는 오른쪽 행을 연결합니다. LEFT JOIN은 연결이 없어도 왼쪽 행을 NULL 확장해 보존합니다. WHERE는 연결 후 적용합니다.'
    else:
        question, answer, concept_result=concept(family,n,name)
        rule=answer
    description=' '.join(t['name']+'('+','.join(c['name'] for c in t['columns'])+')='+dumps(t['rows']) for t in tables)
    prefix='SQLite. '+description+'. ' if sql else 'SQLite. '
    if sql:
        with database(tables) as con:
            cur=con.execute(sql);actual=[list(r) for r in cur.fetchall()];columns=[c[0] for c in cur.description]
        compare=lambda v:sorted(dumps(r) for r in v) if not ordered else v
        if compare(actual)!=compare(expected):raise AssertionError((family,index,actual,expected))
        intermediate={'input_values':values,'selected_ids':[r[0] for r in selected], 'group_ids':{k:[r[0] for r in v] for k,v in sorted(groups.items())} if family.startswith('group') or family.startswith('having') else None}
        answer=rule+' 결과 '+dumps(expected)+'입니다.'
        if family in {'sum','average','boolean_sum'}:
            middle=[int(v is not None) for v in values] if family=='boolean_sum' else [v for v in values if v is not None]
            answer=rule+' 중간값 '+dumps(middle)+', 결과 '+dumps(expected)+'입니다.'
        target=dumps({'sql':sql,'explanation':answer})
    else:
        intermediate=concept_result;columns=[];actual=[];target=rule
    record={'id':f'finish_v2_{family}_{index+1:02d}','subject':'SQL·관계형 데이터베이스 기초',
        'concept':family,'difficulty':2 if split=='train' else 3,'problem_family_id':'finish_v2_'+family,'split':split,
        'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':prefix+question},{'role':'assistant','content':target}],
        'source':{'kind':'self_authored_demo','title':'프로젝트용 독립 계산 규칙 기반 SQLite 예제 v2',
          'rights_note':'이 프로젝트에서 새로 작성한 생성 규칙과 합성 데이터. 외부 교재·기출·모델 답변 수집 없음. 사용자 승인 범위의 로컬 실험용. 사람 검토 전.',
          'created_by':'project_procedural_sqlite_authoring'},'review_status':'generated_unreviewed','demo_only':True,'sql_dialect':'sqlite',
        'verification_notes':['실제 SQLite와 독립 Python 계산을 대조. 생성 규칙의 자연어 적합성은 사람 검토 대기.','이름·값 변형은 같은 problem_family_id와 같은 split에만 배치.']}
    if sql:record.update(fixture={'tables':tables},expected={'sql':sql,'columns':columns,'rows':expected,'row_order':'ordered' if ordered else 'multiset','numeric_abs_tolerance':1e-9})
    evidence={'id':record['id'],'family':family,'split':split,'method':'sqlite_vs_independent_python' if sql else 'sqlite_schema_mutation_or_missing_input_rule',
              'actual_rows':actual,'expected_rows':expected,'intermediate':intermediate,'passed':True,'human_review':'H_PENDING'}
    return record,evidence


def concept(family,n,name):
    """Execute authored DDL/DML examples in a fresh disposable database only."""
    with sqlite3.connect(':memory:') as db:
        db.execute('PRAGMA foreign_keys=ON')
        if family=='create':
            sql=f'CREATE TABLE {name}(id INTEGER PRIMARY KEY, val INTEGER)';db.execute(sql)
            cols=[r[1] for r in db.execute(f'PRAGMA table_info({name})')];count=db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
            assert cols==['id','val'] and count==0
            return f'새 표 {name}에 id 기본키와 val 정수 열을 만들려면? 구조와 행의 차이도 설명하세요.',f'{sql}; CREATE는 DDL로 표 구조를 만듭니다. 열은 id와 val이고 아직 행은 {count}개입니다. 기본키는 행을 식별합니다.',{'columns':cols,'row_count':count}
        if family=='missing_schema':
            return f'{name}의 좋은 기록 {n}개를 뽑아 주세요. 열 정의와 좋은 기록의 기준은 아직 없습니다.',f'{name}의 열 이름, 좋은 기록의 판단 기준, 정렬 기준과 동점 처리 방법을 알려 주세요. 지금은 정보가 부족해 {n}개를 임의로 선택하거나 없는 열을 만들 수 없습니다.',{'missing':['columns','criterion','order','ties'],'invented_schema':False}
        if family=='foreign_key':
            db.execute('CREATE TABLE p(id INTEGER PRIMARY KEY)');db.execute('CREATE TABLE c(pid INTEGER REFERENCES p(id))');db.execute('INSERT INTO p VALUES (?)',(n,))
            try:db.execute('INSERT INTO c VALUES (?)',(n+1,));raise AssertionError('foreign key accepted')
            except sqlite3.IntegrityError:pass
            return f'외래키 검사를 켠 SQLite에서 부모 id는 {n}뿐입니다. 자식 외래키에 {n+1}을 넣어도 되나요?',f'안 됩니다. 참조할 부모 id {n+1}이 없으므로 외래키 제약 오류입니다. 먼저 그 부모를 만들거나 존재하는 id {n}을 사용해야 합니다. 외래키가 부모 행을 자동 생성하지 않습니다.',{'parent_ids':[n],'attempt':n+1,'integrity_error':True}
        definition='id INTEGER PRIMARY KEY, val INTEGER NOT NULL' if family=='notnull_constraint' else 'id INTEGER PRIMARY KEY, val INTEGER'
        db.execute(f'CREATE TABLE {name}({definition})');db.execute(f'INSERT INTO {name} VALUES(?,?)',(n,n*2))
        if family=='primary_key':
            try:db.execute(f'INSERT INTO {name} VALUES(?,?)',(n,n*3));raise AssertionError('duplicate accepted')
            except sqlite3.IntegrityError:pass
            return f'{name}의 INTEGER PRIMARY KEY id={n}이 이미 있습니다. 같은 id로 다른 값을 INSERT하면?',f'{name}에서 id {n}이 중복되므로 기본키 제약 오류입니다. 다른 val 값이어도 같은 기본키를 새 행에 다시 쓸 수 없습니다. 기존 행이 자동 수정되지는 않습니다.',{'key':n,'integrity_error':True,'rows':[list(r) for r in db.execute(f'SELECT * FROM {name}')]}
        if family=='notnull_constraint':
            try:db.execute(f'INSERT INTO {name} VALUES(?,NULL)',(n+1,));raise AssertionError('null accepted')
            except sqlite3.IntegrityError:pass
            return f'{name}.val은 NOT NULL입니다. id={n+1}, val=NULL을 INSERT할 수 있나요?',f'불가능합니다. {name}.val의 NOT NULL 제약 때문에 오류가 납니다. NULL은 값이 없음을 나타내며 0과 다릅니다. id {n+1}이 새 값이라는 사실만으로 이 제약을 통과하지 못합니다.',{'new_id':n+1,'integrity_error':True}
        before=[list(r) for r in db.execute(f'SELECT * FROM {name}')]
        if family=='insert':
            sql=f'INSERT INTO {name}(id,val) VALUES({n+1},{n*3})';question=f'{name}(id,val)에 {dumps(before)}가 있습니다. ({n+1},{n*3}) 행을 추가하고 전후를 설명하세요.';rule='INSERT는 DML로 행을 추가합니다. 기존 열 구조는 그대로입니다.'
        elif family=='update':
            sql=f'UPDATE {name} SET val={n*3} WHERE id={n}';question=f'{name}(id,val)에 {dumps(before)}가 있습니다. id {n}의 val만 {n*3}으로 바꾸고 전후를 설명하세요.';rule='UPDATE는 DML로 선택한 행의 값을 바꿉니다. 열을 새로 만드는 DDL이 아닙니다.'
        elif family=='delete':
            sql=f'DELETE FROM {name} WHERE id={n}';question=f'{name}(id,val)에 {dumps(before)}가 있습니다. id {n}인 행을 지우면 표 자체도 없어지나요? SQL과 전후를 설명하세요.';rule='DELETE는 DML로 행을 지웁니다. 표 구조는 남습니다. 표 자체를 없애는 DROP과 다릅니다.'
        elif family=='alter':
            sql=f'ALTER TABLE {name} ADD COLUMN note TEXT';question=f'{name}(id,val)에 {dumps(before)}가 있습니다. note TEXT 열을 추가하면 기존 행의 note는? SQL도 쓰세요.';rule='ALTER TABLE은 DDL로 열 구조를 바꿉니다. DEFAULT 없는 새 열의 기존 행 값은 NULL입니다.'
        else:raise ValueError(family)
        db.execute(sql);after=[list(r) for r in db.execute(f'SELECT * FROM {name}')];cols=[r[1] for r in db.execute(f'PRAGMA table_info({name})')]
        expected={'insert':[[n,n*2],[n+1,n*3]],'update':[[n,n*3]],'delete':[],'alter':[[n,n*2,None]]}[family]
        assert after==expected and cols==(['id','val','note'] if family=='alter' else ['id','val'])
        return question,f'{sql}; {rule} 결과 행은 {dumps(after)}입니다.',{'before':before,'after':after,'columns':cols,'sql':sql}


def build(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    all_records=[];all_evidence=[]
    for split,families,count in [('train',TRAIN,10),('validation',VALIDATION,5),('test',FINAL,5)]:
        records=[];evidence=[]
        for family in families:
            for i in range(count):
                record, proof=exercise(family,i,split);records.append(record);evidence.append(proof)
        folder=destination/'final' if split=='test' else destination/'development';folder.mkdir(exist_ok=True)
        for suffix,items in [('.jsonl',records),('-claims.jsonl',evidence)]:
            path=folder/(split+suffix);content=''.join(dumps(r)+'\n' for r in items)
            if path.exists() and path.read_text(encoding='utf-8')!=content:
                raise ValueError('Existing frozen dataset differs; use a new explicit dataset version: '+str(path))
            if not path.exists():path.write_text(content,encoding='utf-8')
        all_records.extend(records);all_evidence.extend(evidence)
    report=validate_dataset(records=all_records,profile='demo')
    assert report['counts']=={'train':240,'validation':40,'test':80}
    report.update(sqlite_checks=sum(e['family']!='missing_schema' for e in all_evidence),
        missing_input_rule_checks=sum(e['family']=='missing_schema' for e in all_evidence),sqlite_version=sqlite3.sqlite_version,
        independently_calculated_selects=sum('expected' in r for r in all_records),
        concept_execution_or_missing_input_checks=sum('expected' not in r for r in all_records),
        family_allocation={'train':list(TRAIN),'validation':list(VALIDATION),'test':list(FINAL)},
        final_policy='Frozen holdout. Do not load final into training, retrieval, product cache, or prompts. Inspect results only after validation-driven selection is frozen.',
        final_automatic_scoring_scope='SQL result checks for 60/80;20 concept cases require claim rubric plus human education review. Missing/hallucinated explanations are not SQL-pass evidence.',
        generated_at='2026-10-28',human_review='H_PENDING',source='project-authored procedural generator; no externally collected model answers or copyrighted lessons')
    report['files']={str(p.relative_to(destination)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in destination.rglob('*.jsonl')}
    (destination/'dataset-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    print(dumps(build(args.output)))
