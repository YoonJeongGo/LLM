"""CPU tokenizer-only preparation. No torch import, model load or generation."""
from pathlib import Path
import hashlib
import json
import os
import sys

os.environ.update(USE_TORCH='0', USE_TF='0', USE_FLAX='0', CUDA_VISIBLE_DEVICES='',
                  HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
sys.stdout.reconfigure(encoding='utf-8')
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
from edu_tutor.training.data import load_records
from edu_tutor.training.masking import encode_response_only
from transformers import AutoTokenizer

folder=root/'runs/finish-v2/20261028/education'
tokenizer=AutoTokenizer.from_pretrained(root/'.local/models/text',local_files_only=True,trust_remote_code=False)
paths=[folder/'development/train.jsonl',folder/'development/validation.jsonl']
items=[]
for record in load_records(paths):
    try:
        encoded=encode_response_only(tokenizer,record['messages'],512)
        audit=encoded['audit']
        assert all(v==-100 for v in encoded['labels'][:audit['prefix_length']])
        assert tokenizer.eos_token_id in encoded['labels'][audit['prefix_length']:]
        assert '<think>' not in audit['target_decode']
        items.append({'id':record['id'],'split':record['split'],'status':'PASS',**audit})
    except ValueError as exc:items.append({'id':record['id'],'split':record['split'],'status':'FAIL','error':str(exc)})
assert 'torch' not in sys.modules
report={'status':'PASS' if all(i['status']=='PASS' for i in items) else 'FAIL',
    'scope':'Actual installed local tokenizer, CPU only; no torch/model/CUDA/generation; final holdout not read',
    'tokenizer_class':type(tokenizer).__name__,'template_sha256':hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
    'eos_token_id':tokenizer.eos_token_id,'pad_token_id':tokenizer.pad_token_id,'max_sequence_length':512,
    'items':items,'total':len(items),'passed':sum(i['status']=='PASS' for i in items),
    'max_tokens':max((i.get('valid_length',0) for i in items),default=0),'human_review':'H_PENDING'}
(folder/'token-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='items'},ensure_ascii=False))
if report['status']!='PASS':raise SystemExit(1)
