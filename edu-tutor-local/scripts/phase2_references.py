"""Allow compact, attributed developer references for RAG, never test answers.

Approval here means retrieval enabled, not human educational-quality review.
Existing uploaded sources are preserved, and exact versions are reused.
"""
from pathlib import Path
import hashlib
import json
import httpx

root=Path(__file__).resolve().parents[1]
token=(root/'.local/auth-token').read_text(encoding='utf-8').strip()
report=[]
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+token},timeout=20,trust_env=False) as client:
    existing=client.get('/api/documents');existing.raise_for_status();existing=existing.json()
    for path in sorted((root/'data/reference').glob('*-v02.md')):
        raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        found=next((doc for doc in existing if doc.get('version')==digest),None)
        if found is None:
            response=client.post('/api/documents',files={'file':(path.name,raw,'text/markdown')},
                data={'title':path.read_text(encoding='utf-8').splitlines()[0]+' · 공식 문서 요약',
                      'rights':'공식 SQLite 문서를 대조한 자체 한국어 요약. AI가 작성·대조했으며 사람의 검토는 미실시. 수집 목적은 로컬 RAG이며 평가 정답은 포함하지 않음.',
                      'subject':'SQLite 기초'})
            response.raise_for_status();found=response.json()
        response=client.post('/api/documents/'+found['id']+'/review',json={'approved':True});response.raise_for_status()
        report.append({'document_id':found['id'],'version':digest,'source_path':str(path),
                       'retrieval_allowed':True,'reviewer':'assistant_official_document_crosscheck',
                       'human_review':'not_reviewed','evaluation_oracles_included':False})
out=root/'runs/phase2/current/rag-corpus-additions.json'
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'new_or_reused_reference_documents':len(report),'human_review':'not_reviewed'}))
