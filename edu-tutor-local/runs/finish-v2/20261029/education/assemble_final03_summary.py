"""Read saved final03 evidence only; no model/API/final80 access."""
from pathlib import Path
from datetime import datetime, timezone
import difflib
import hashlib
import json

ROOT=Path(__file__).resolve().parents[4]
EDU=Path(__file__).resolve().parent
FOLDER=ROOT/'runs/finish-v2/20261029/student/final03'
REPORT=FOLDER/'report-binding-v2-20261029T054109464134Z'
ORIGINAL=FOLDER/'report-20261029T053248264000Z'
PROPOSAL=EDU/'collector-numeric-binding-v2'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

summary=read(REPORT/'summary.json');freeze=read(FOLDER/'execution-version.json')
original_script=ROOT/'scripts/finish_collect_journeys.py'
assert digest(original_script)==freeze['source_hashes']['scripts/finish_collect_journeys.py']
notes={
 'J01':'CREATE/INSERT 문장을 실제 실행한 예시에서 DDL/DML 분류를 각각 말함. 사람 교육·청취 검토는 없음.',
 'J02':'원시 예시는 기존 행이 없어 UPDATE 변화를 보이지 못함. 1회 보정은 CREATE에 이미 있는 rental_price를 ALTER로 다시 추가하여 duplicate column 오류. 음성 생성·재생 없음.',
 'J03':'제공된 SQL의 4/3/25를 원본→계산→표·수식·음성으로 연결. NULL 제외/0 포함. SQL 작성 정확도 평가가 아님.',
 'J04':'제공된 GROUP/HAVING SQL의 남1·12, 동2·14를 검증. 선택한 원본 행의 WHERE 설명, 본수업 위치 복귀. 보충 음성은 WHERE 중심이며 전체 GROUP/HAVING 맥락은 판서에 표시.',
 'J05':'원시 모델 설명은 A만 남는다고 잘못 썼지만 검증 앱은 A13/C14를 판서·대사로 구성. 원시 오답은 보존. 추가 질문과 복귀 확인.',
 'J06':'직접 작성한 정상 사진의 풀을 폴로 인식. 쿼리/수치는 같아도 원문 동일성 실패. 원본 정답으로 교체하거나 재추론하지 않고 중단.',
 'J07':'직접 작성한 기울어진 사진 원문과 인식 후보 일치. SUM18/AVG6.0, 실제 WAV2개, 수식 글리프 위치 확인. 수집기 숫자 표현/클립 선택 오류만 별도 CPU 재채점으로 해소.',
 'J08':'잘린 사진에서 숫자 조건을 발명하지 않았으나 구체적 누락 조건을 식별하지 못함(missing_conditions=[]). 확인 전 후보 상태이며 안전성 통과로 계산하지 않음. 저장 화면은 처리중 UI로 최종 상태 증거가 아님.'}
cases=[]
for ident in notes:
    actual=read(FOLDER/ident/'actual.json');case=read(REPORT/(ident+'.json'))
    before=actual['before']['budget']['active_execution_allowance'];after=actual['after']['active_execution_allowance']
    delta={k:before[k]-after[k] for k in ('text_remaining','audio_remaining','vision_remaining','seconds_remaining')}
    cases.append({'id':ident,'status':case['status'],'question':case['spec'].get('question'),
        'followup_question':case['spec'].get('followup',{}).get('question'),
        'input_kind':case['spec']['kind'],'educational_read_review':notes[ident],
        'human_review':'H_PENDING','evidence':str(REPORT/(ident+'.json')),
        'actual_sha256':digest(FOLDER/ident/'actual.json'),'new_text':delta['text_remaining'],
        'new_audio':delta['audio_remaining'],'new_vision':delta['vision_remaining'],
        'charged_seconds':delta['seconds_remaining'],'planned_followup':bool(case['spec'].get('followup')),
        'question_events':[{k:q.get(k) for k in ('input_kind','status','first_valid_explanation_ms','text_model_load_regime','text_worker_evidence')}
            for q in case['timings']['question_to_first_valid_explanation']],
        'photo_timing':case['timings'].get('photo'),'interruptions':case['timings']['interruptions'],
        'source_unchanged':actual['source_unchanged_at_end']})
totals={key:sum(c[key] for c in cases) for key in ('new_text','new_audio','new_vision','charged_seconds')}
assert (totals['new_text'],totals['new_audio'],totals['new_vision'])==(9,5,3)
assert all(c['source_unchanged'] for c in cases)
combined={'recorded_at':datetime.now(timezone.utc).isoformat(),'readiness':'NOT_READY','human_review':'H_PENDING',
    'interpretation':'5/8 is technical journey completion, not educational accuracy, product readiness, or a requirement-gate pass rate.',
    'source_version':'r10/final03','collector_only_regrade':True,'original_report':str(ORIGINAL),
    'regraded_report':str(REPORT),'gallery':str(REPORT/'gallery.html'),
    'original_collector_unchanged_sha256':digest(original_script),'source_freeze':str(FOLDER/'execution-version.json'),
    'authoring_provenance_label':'final03_proposal_not_applied is the preserved authored-input label; actual application/freeze and per-run hashes govern execution provenance.',
    'cases':cases,'actual_attempted':8,'technical_completed_human_pending':5,
    'audio_question_event_denominator':10,'valid_explanation_events':7,
    'latency':{k:summary[k] for k in ('question_to_audio','interrupt_to_native_pause','interrupt_to_supplement','stage_gap','stage_gap_denominator','question_to_audio_by_input_and_text_load_regime')},
    'totals':totals,'ending_scope_snapshot':read(FOLDER/'J08/actual.json')['after']['active_execution_allowance'],
    'boundaries':[
        'Native HTML audio playing plus exact WAV/script/blob binding is measured; human hearing and pedagogic quality remain unreviewed.',
        'tts_clip_cache_hit can include a newly generated clip prefetched earlier in this same journey. New synthesis counts come from budget reservations (5), not playback cache flags.',
        'All first text explanation clips were reused from existing exact-text WAVs; J07 first photo explanation was newly synthesized. This is not an all-new-TTS benchmark.',
        '7/10 includes 2 followups; photo question event starts after source confirmation. J07 upload-to-audio is separately 50.5965 seconds including OCR and automated authored-source confirmation.',
        'J04/J05 pause is measured from interruption_submitted. Followup question_submitted occurs a few milliseconds later; report both clock boundaries without conflation.',
        'J08 saved images show processing UI, not settled missing-condition UX. Terminal raw response proves missing_conditions empty; no final UI claim is made.',
        'J06/J07/J08 images are authored development fixtures, not real student uploads. Automatic source comparison is not human confirmation.',
        'NOT_APPLICABLE followup assertions in non-followup harness cases do not establish interruption coverage; only J04 and J05 do.',
        'Final80 remains unopened and unexecuted. These fresh journeys are separate development examples.'
    ]}
write(EDU/'final03-execution-education-summary.json',combined)

runs=['validation-base-v1','validation-adapter-v1','validation-base-bf16-v1','validation-adapter1-bf16-v1','validation-candidate4b-nf4-v1']
grades=[]
for name in runs:
    path=EDU/name/'result-app-offline-final-source-r10-v1.json';result=read(path)
    grades.append({'run':name,'path':str(path),'sha256':digest(path),'summary':result['summary'],
        'source_result_sha256':result['source_result_sha256'],'source_hashes':result['source_hashes']})
assert all(g['source_hashes']==grades[0]['source_hashes'] for g in grades)
write(EDU/'validation-app-final-source-r10-comparison.json',{'grading_version':'final-source-r10-v1',
    'all_source_hashes_identical':True,'new_inference':False,'final80_access':False,'conditions':grades,
    'interpretation':'Every condition accepts 5/35 SQL answers and safely stops/does not support 30. Concepts5 remain H_PENDING. App acceptance is not raw-model accuracy.'})

# An inert review patch, not an applied change. Use the same helper tested above.
target=original_script.read_text(encoding='utf-8')
target=target.replace('from student_experience_report import (','from finish_binding_evidence import binding_evidence\n\nfrom student_experience_report import (',1)
target=target.replace('validations={"provider_cache_and_script":','entry["lesson_binding_evidence_v2"] = binding_evidence(record, lesson_map.get(entry["lesson_id"], {}), lesson, event, entry["audio_id"])\n        validations={"provider_cache_and_script":',1)
target=target.replace('"lesson_board_script_fingerprint":clip.get("binding_fingerprint")==lesson_binding(lesson),','"lesson_board_script_fingerprint":entry["lesson_binding_evidence_v2"]["pass"],',1)
patch=''.join(difflib.unified_diff(original_script.read_text(encoding='utf-8').splitlines(keepends=True),target.splitlines(keepends=True),
    fromfile='a/scripts/finish_collect_journeys.py',tofile='b/scripts/finish_collect_journeys.py'))
helper=(PROPOSAL/'binding_evidence.py').read_text(encoding='utf-8')
patch+=''.join(difflib.unified_diff([],helper.splitlines(keepends=True),fromfile='/dev/null',tofile='b/scripts/finish_binding_evidence.py'))
(PROPOSAL/'collector-only-unapplied.patch').write_text(patch,encoding='utf-8')
write(PROPOSAL/'regrade-receipt.json',{'recorded_at':datetime.now(timezone.utc).isoformat(),
    'production_changed':False,'source_script_changed':False,'collector_original_hash':digest(original_script),
    'copy_hash':digest(PROPOSAL/'finish_collect_journeys_v2.py'),'helper_hash':digest(PROPOSAL/'binding_evidence.py'),
    'test_artifact':str(PROPOSAL/'cpu-tests-24.xml'),'tests':'24 passed, 0.85s',
    'original_report':str(ORIGINAL),'new_report':str(REPORT),'patch_applied':False,
    'changes':['Exact server DB binding checked against captured server hash and latest pre-playback same-lesson same-step speech response.',
        'Browser payload must match every bound field, allowing only finite JS-safe float-to-int numeric representation.',
        'Reject late/wrong response, changed value/speech, wrong lesson/step, changed server fingerprint; no arbitrary fallback.']})
print(EDU/'final03-execution-education-summary.json')
print(EDU/'validation-app-final-source-r10-comparison.json')
print(PROPOSAL/'collector-only-unapplied.patch')
