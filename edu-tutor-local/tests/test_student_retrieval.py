"""Technical retrieval ranking, not a model-answer correctness benchmark."""
from types import SimpleNamespace
import pytest
from edu_tutor.retrieval.index import DocumentIndex

@pytest.mark.parametrize('term',['DDL','DML','DCL','TCL','CREATE','ALTER','DROP','INSERT','UPDATE','DELETE','TRUNCATE','COMMIT','ROLLBACK'])
def test_named_technical_term_with_korean_particle_prefers_matching_approved_reference(term):
    docs=[{'id':'relevant','review_status':'approved'},{'id':'generic','review_status':'approved'}, {'id':'pending','review_status':'pending'}]
    chunks=[{'document_id':'relevant','text':term+'은 명령의 분류를 설명합니다. 기초 데이터베이스 학습 자료.'},
            {'document_id':'generic','text':'테이블 예시로 설명해 주는 다른 집계 수업입니다.'},
            {'document_id':'pending','text':term+'이 뭐였지? 테이블 예시로 설명해 줘.'}]
    index=DocumentIndex(SimpleNamespace(list=lambda table: docs if table=='documents' else chunks))
    hits=index.search(term+'이 뭐였지?',limit=2)
    assert hits[0]['document_id']=='relevant'
    assert not any(hit['document_id']=='pending' for hit in hits)
