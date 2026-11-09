SQLite WHERE GROUP BY HAVING SELECT

학습용 논리 설명에서 FROM은 입력 표를 정하고 WHERE는 조건에 맞는 행을 남깁니다. GROUP BY는 남은 행을 그룹으로 묶고 집계식은 그룹별 값을 계산합니다. HAVING은 그룹 결과에 조건을 적용합니다. 최종 SELECT 출력 열과 설명에 쓰는 중간 표는 구분해야 합니다. 이 단계는 결과를 이해하기 위한 논리적 설명이며 엔진의 물리 실행 순서를 추적했다는 뜻이 아닙니다. ORDER BY가 없으면 출력 행 순서를 보장하지 않습니다.

공식 근거: https://www.sqlite.org/lang_select.html
작성: 공식 문서를 대조해 직접 작성한 한국어 요약. AI 검토이며 사람의 교육·문장 검토는 미실시.
