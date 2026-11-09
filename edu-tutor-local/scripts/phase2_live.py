"""Bounded actual localhost model/voice/photo scenarios; never inject OCR answers.

All expected answers below are test oracles and are only inspected after the
server response. The original query/tables are the student's problem input.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from phase2_snapshot import snapshot

OUT = ROOT / 'runs/phase2/current/live'


def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (name+'.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


class Live:
    def __init__(self):
        token = (ROOT / '.local/auth-token').read_text(encoding='utf-8').strip()
        self.client = httpx.Client(base_url='http://127.0.0.1:8000',
                                  headers={'Authorization':'Bearer '+token},timeout=30,trust_env=False)

    def call(self, method, path, **kwargs):
        response = self.client.request(method,path,**kwargs)
        if response.is_error:
            raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
        return response.json()

    def wait(self, job_id, on_poll=None):
        start=time.monotonic()
        while time.monotonic()-start < 340:
            job=self.call('GET',f'/api/jobs/{job_id}')
            if on_poll:on_poll(job)
            if job['state'] in {'succeeded','failed','cancelled','interrupted','blocked'}:
                write('job-'+job_id,job)
                if job['state']!='succeeded':
                    raise RuntimeError(f"job {job_id}: {job['state']} {job.get('error')}")
                return job
            time.sleep(.4)
        self.call('POST',f'/api/jobs/{job_id}/cancel')
        raise TimeoutError('Scenario requested cancellation after 340 seconds')

    def question(self,name,content,problem=None,use_rag=True):
        started=time.monotonic()
        session=self.call('POST','/api/sessions',json={'title':'v0.2 실제 검증 · '+name})
        body={'content':content,'request_id':uuid4().hex,'use_rag':use_rag,'adapter':'base'}
        if problem:body['problem']=problem
        sub=self.call('POST',f"/api/sessions/{session['id']}/messages",json=body)
        job=self.wait(sub['job_id'])
        messages=self.call('GET',f"/api/sessions/{session['id']}/messages")
        answer=next(m for m in messages if m['id']==job['result']['message_id'])
        value={'session_id':session['id'],'message_id':answer['id'],'request':body,
               'answer':answer,'job':job,'request_to_answer_seconds':time.monotonic()-started,
               'human_review':'not_reviewed','timestamp':datetime.now(timezone.utc).isoformat()}
        write(name,value)
        print(json.dumps({'scenario':name,'status':'answer_saved','seconds':value['request_to_answer_seconds']},ensure_ascii=False),flush=True)
        return value

    def lesson(self,name,answer,voice_steps=0):
        start=time.monotonic()
        lesson=self.call('POST','/api/lessons',json={'session_id':answer['session_id'],'message_id':answer['message_id']})
        sub=self.call('POST',f"/api/lessons/{lesson['id']}/generate")
        self.wait(sub['job_id'])
        lesson=self.call('GET',f"/api/lessons/{lesson['id']}")
        answer['lesson_ready_seconds']=time.monotonic()-start
        answer['lesson']=lesson
        write(name,answer)
        if voice_steps and not lesson.get('speech_allowed',False):
            answer['voice_validation']={'status':'not_run_blocked','reason':lesson.get('reason'),'request_was_not_sent':True}
        if voice_steps and lesson.get('plan') and lesson.get('speech_allowed',False):
            # Select individual steps only if requested. Preparing all units in
            # one request permits the shared sequential TTS worker to load once.
            steps=lesson['plan']['steps']
            if voice_steps>=len(steps):
                requests=[{}]
            else:
                requests=[{'step_id':step['id']} for step in steps[:voice_steps]]
            for request in requests:
                voice_start=time.monotonic()
                sub=self.call('POST',f"/api/lessons/{lesson['id']}/speech",json={**request,'request_id':uuid4().hex})
                timing={'job_id':sub['job_id'],'first_complete_clip_seconds':None}
                def poll_audio(job):
                    if timing['first_complete_clip_seconds'] is None:
                        ready=self.call('GET',f"/api/lessons/{lesson['id']}/speech")
                        if ready.get('steps'):
                            timing['first_complete_clip_seconds']=time.monotonic()-voice_start
                            timing['first_clip_observed_job_state']=job['state']
                self.wait(sub['job_id'],on_poll=poll_audio)
                timing['seconds']=time.monotonic()-voice_start
                answer.setdefault('voice_requests',[]).append(timing)
            answer['lesson']=self.call('GET',f"/api/lessons/{lesson['id']}")
        write(name,answer)
        return answer


def count_problem():
    question='COUNT(*)와 COUNT(score)는 각각 얼마이고, 왜 다른가?'
    return {'task_kind':'query_result','dialect':'sqlite','raw_text':question,'confirmed':True,
            'query':'SELECT COUNT(*) AS people, COUNT(score) AS scores FROM exam_result;',
            'tables':[{'name':'exam_result','columns':[{'name':'name','type':'TEXT','label':'이름'},
                       {'name':'score','type':'INTEGER','label':'점수'}],
                       'rows':[['박강열',80],['유성재',None],['김현수',100]]}]}


def count(live):
    problem=count_problem()
    result=live.question('T02-count',problem['raw_text'],problem)
    assert result['answer']['evidence']['result']['rows']==[[3,2]]
    live.lesson('T02-count',result,voice_steps=4)


def concepts(live,tag=''):
    for i,question in enumerate(['DDL이 뭐였지? 사람 추가하는 것과 칸 추가하는 게 헷갈려.',
                                  '기존 명단에 새 사람을 넣는 INSERT와 점수 열을 만드는 ALTER는 어떻게 달라?']):
        name=f'T01-concept-{i+1}'+('-'+tag if tag else '')
        result=live.question(name,question,use_rag=True)
        if i==0:live.lesson(name,result,voice_steps=1)


def grouping(live):
    question='아래 SQL의 결과와 WHERE, GROUP BY, HAVING의 학습용 논리 순서를 설명해 줘.'
    problem={'task_kind':'query_result','dialect':'sqlite','raw_text':question,'confirmed':True,
        'query':'SELECT dept, COUNT(*) AS people, SUM(score) AS total, AVG(score) AS average FROM results WHERE active = 1 GROUP BY dept HAVING COUNT(*) >= 2 ORDER BY dept;',
        'tables':[{'name':'results','columns':[{'name':'dept','type':'TEXT'},{'name':'score','type':'INTEGER'},{'name':'active','type':'INTEGER'}],
                   'rows':[['A',10,1],['A',None,1],['A',30,0],['B',40,1],['C',20,1],['C',60,1]]}]}
    result=live.question('T04-group',question,problem)
    assert result['answer']['evidence']['result']['rows']==[['A',2,10,10.0],['C',2,80,40.0]]
    live.lesson('T04-group',result,voice_steps=1)


def create_photos():
    from PIL import Image,ImageDraw,ImageFont
    folder=OUT/'photos';folder.mkdir(parents=True,exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',30)
    lines={
        'text':['SQLite 기초 문제','COUNT(*)와 COUNT(score)의 차이를 설명하세요.','NULL과 숫자 0은 같은가요?'],
        'table':['SQLite 표: exam_result(name TEXT, score INTEGER)','이름(name)                 점수(score)','박강열                         80','유성재                         NULL','김현수                         100','SELECT AVG(score) FROM exam_result;','이 SQL의 결과는 얼마인가요?'],
        'cut':['SQLite 표: exam_result(name TEXT, score INTEGER)','박강열 80 / 유성재 NULL / 김현수 100','SELECT COUNT(*) FROM exam_result','WHERE score >=']}
    result=[]
    for kind,content in lines.items():
        image=Image.new('RGB',(1100,520),'white');draw=ImageDraw.Draw(image)
        for i,line in enumerate(content):draw.text((30,25+62*i),line,font=font,fill='black')
        path=folder/(kind+'.png');image.save(path)
        result.append({'kind':kind,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                       'authorship':'New synthetic image created in this verification run; not a real student photo.',
                       'source_lines':content})
    write('T05-image-provenance',result)
    return result


def photos(live):
    for image in create_photos():
        with open(image['path'],'rb') as stream:
            photo=live.call('POST','/api/photos',files={'file':(image['kind']+'.png',stream,'image/png')})
        job=live.call('POST',f"/api/photos/{photo['id']}/transcribe",json={'request_id':uuid4().hex})
        live.wait(job['job_id'])
        recognized=live.call('GET',f"/api/photos/{photo['id']}")
        write('T05-'+image['kind'],{'image':image,'photo':recognized,'ocr':'actual_vision_worker','correction':'not_performed'})
        print(json.dumps({'photo':image['kind'],'status':'actual_OCR_saved','photo_id':photo['id']},ensure_ascii=False),flush=True)


def photo_edit(live):
    captured=json.loads((OUT/'T05-table.json').read_text(encoding='utf-8'))
    ident=captured['photo']['id']
    original=captured['photo']['original_text']
    problem=count_problem()
    correction={'question':'이 SQL의 평균 점수 결과는 얼마인가요?',
                'sql':'SELECT AVG(score) AS average_score FROM exam_result;',
                'tables':problem['tables'],'choices':[],'missing_conditions':[],'unreadable_regions':[]}
    report={'photo_id':ident,'actual_OCR':original,
            'correction_provenance':'Test harness explicitly corrected synthetic image transcription from its authored source. This is not OCR success or a real human review.',
            'human_review':'not_reviewed','revisions':[]}
    for index in range(2):
        edited=live.call('PATCH',f'/api/photos/{ident}',json=correction)
        assert edited['original_text']==original
        if index:
            previous=report['revisions'][0]['lesson']['id']
            invalid=live.call('GET',f'/api/lessons/{previous}')
            speech=live.client.post(f'/api/lessons/{previous}/speech',json={'request_id':uuid4().hex})
            report['old_lesson_invalidation']={'lesson':invalid,'speech_post_status':speech.status_code}
            write('T05-edit',report)
            assert invalid.get('valid') is False and speech.status_code==409
        live.call('POST',f'/api/photos/{ident}/confirm')
        session=live.call('POST','/api/sessions',json={'title':f'v0.2 사진 수동수정 검증 {index+1}'})
        started=time.monotonic()
        submitted=live.call('POST',f'/api/photos/{ident}/solve',json={'session_id':session['id'],'request_id':uuid4().hex})
        job=live.wait(submitted['job_id'])
        messages=live.call('GET',f"/api/sessions/{session['id']}/messages")
        answer=next(m for m in messages if m['id']==job['result']['message_id'])
        value={'session_id':session['id'],'message_id':answer['id'],'answer':answer,'job':job,
               'request_to_answer_seconds':time.monotonic()-started,'photo_revision':edited['revision']}
        live.lesson(f'T05-edit-{index+1}',value,voice_steps=1)
        report['revisions'].append(value)
        expected=90.0 if index==0 else 60.0
        report['revisions'][-1]['independent_expected']=[[expected]]
        write('T05-edit',report)
        assert answer['evidence']['result']['rows']==[[expected]]
        correction['tables'][0]['rows'][0][1]=20
    # An incomplete SQL condition must remain blocked even after confirm.
    cut=json.loads((OUT/'T05-cut.json').read_text(encoding='utf-8'))['photo']
    live.call('POST',f"/api/photos/{cut['id']}/confirm")
    result=live.client.post(f"/api/photos/{cut['id']}/solve",json={'session_id':session['id'],'request_id':uuid4().hex})
    report['cropped_photo']={'photo_id':cut['id'],'actual_OCR':cut['original_text'],'solve_status':result.status_code,
                            'response':result.json()}
    write('T05-edit',report)
    assert result.status_code==409


def short_supplements(live):
    previous=json.loads((ROOT/'web/test-results-phase2-live/evidence.json').read_text(encoding='utf-8'))
    repaired=[]
    for index in (1,2):
        captured=previous[f'supplement_{index}']
        answer=captured['answer']
        value={'session_id':answer['session_id'],'message_id':answer['id'],'answer':answer,
               'prior_actual_lesson_id':captured['lesson']['id'],
               'scope':'Same actual model response and computed evidence; new short narration and EOS-checked TTS. This is not a repeated model answer or end-to-end latency measurement.',
               'human_review':'not_reviewed'}
        live.lesson(f'T03-short-{index}',value,voice_steps=1)
        repaired.append({'index':index,'lesson_id':value['lesson']['id'],'source_message_id':answer['id'],
                         'speech':value['lesson']['plan']['steps'][0]['speech'],
                         'audio':value['lesson']['audio_steps'],'voice_requests':value['voice_requests']})
        write('T03-short-summary',repaired)
        print(json.dumps({'short_supplement':index,'lesson_id':value['lesson']['id'],
                          'duration':value['lesson']['audio_steps'][0]['duration']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['count','concepts','group','photos','photo-edit','short-supplements']);parser.add_argument('--tag',default='');args=parser.parse_args()
    if args.tag and not __import__('re').fullmatch('[A-Za-z0-9_-]{1,40}',args.tag):parser.error('tag must be a short safe artifact suffix')
    write('source-'+args.stage+('-'+args.tag if args.tag else ''),snapshot(ROOT))
    live=Live()
    if args.stage=='concepts':concepts(live,args.tag)
    else:{'count':count,'group':grouping,'photos':photos,'photo-edit':photo_edit,'short-supplements':short_supplements}[args.stage](live)
