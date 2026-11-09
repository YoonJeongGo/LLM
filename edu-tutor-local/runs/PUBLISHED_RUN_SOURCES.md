# 개발 실행 코드와 회귀 입력

`PUBLISHED_SOURCE_MANIFEST.json`에는 공개한 파일의 상대 경로·종류·바이트 수·SHA-256과 로컬 전용 코퍼스의 건수·SHA-256이 있다. 이 폴더에는 모델 평가, 텍스트 worker와 저장 비용 측정, 수업·취소·재생 확인에 사용한 개발 도구가 있다. 로컬 실행 환경에 있었던 전체 실행 기록은 별도 보관한다.

N01·N02의 `student/repair-new-final02/*/actual.json`은 공개용 회귀 입력이다. 원래 개발자가 만든 표·질문, 당시 모델의 원시 답변, 보충 질문의 선택 행을 추출했다. 각 파일의 `_export`에 원본 기록의 SHA-256을 표시했다. 전체 세션 기록과 수업 재생 측정은 로컬에 있다. C04의 `evaluation/cpu-boundaries-development-final03.json`은 원래 질문을 그대로 보존한 발췌본이다. 이러한 발췌본의 해시는 원본과 다르다.

학생 사진을 대신해 개발자가 직접 만든 테스트 PNG 6개를 포함했다. 각 이미지의 작성 근거와 지문은 같은 버전의 `student/journeys.json`에서 확인할 수 있다. 공개용 복사본으로 N01·N02의 `reprocess_followups.run()`을 CPU에서 실행해 보충 계획을 생성했다. 이는 기록된 입력의 재처리 검사다.

## 로컬 데모 데이터 준비

`tests/test_finish_dataset_mapping.py`는 기존 세 훈련 설정에서 지정한 로컬 데이터 파일을 확인한다. 새 체크아웃에서 이 테스트를 실행하려면 프로젝트 루트에서 아래 자체 작성 생성기로 합성 데이터를 순서대로 준비한다. 설치한 프로젝트 Python을 사용한다. 각 명령은 SQLite 기반 데이터를 준비한다.

```powershell
python -m edu_tutor.training.finish_data --output runs/finish-v2/20261028/education
python -m edu_tutor.training.finish_remediation --diverse --output runs/finish-v2/20261029/education/candidate-diverse-v2
python -m edu_tutor.training.finish_reason_only --output runs/finish-v2/20261029/education/candidate-reason-v3
```

기존 로컬 코퍼스와 독립 평가 비공개 정답, SQLite 운영 DB·인증·사용량 장부·원음·브라우저 원시 네트워크 기록은 로컬에 보관한다. 저장된 실제 수업의 음성 일치 검사와 재시작 검사는 로컬 DB·WAV·당시 실행 영수증이 필요하다. `capture_state.py`는 실행 중인 로컬 API와 그 설치의 인증이 필요하다. 과거의 실측 결과는 공개 증거 보고서를 참고한다.
