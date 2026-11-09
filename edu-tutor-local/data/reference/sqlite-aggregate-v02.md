SQLite COUNT SUM AVG NULL

COUNT(*)는 행을 세며, 어떤 셀의 값이 NULL이어도 행 자체를 제외하지 않습니다. COUNT(열)는 해당 열이 NULL이 아닌 행만 셉니다. COUNT(DISTINCT 열)는 NULL을 제외한 서로 다른 값을 셉니다. 숫자 열의 SUM은 NULL 아닌 값의 합이며, AVG는 NULL 아닌 값들의 평균입니다. NULL은 숫자 0과 다릅니다. NULL 아닌 입력이 없을 때 COUNT는 0, SUM과 AVG는 NULL입니다. 수치 결과는 학생이 준 실제 행 값으로 계산해야 합니다.

공식 근거: https://www.sqlite.org/lang_aggfunc.html
작성: 공식 문서를 대조해 직접 작성한 한국어 요약. AI 검토이며 사람의 교육·문장 검토는 미실시.
