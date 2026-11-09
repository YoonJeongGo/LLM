"""Read only the terminal J08 JSON; no database or model execution."""
from pathlib import Path
from datetime import datetime
import json
OUT=Path(__file__).resolve().parent
path=OUT.parent/'student/repair-cancel-final07/J08/actual.json'
a=json.loads(path.read_text(encoding='utf-8'))
assert a.get('completed_at') and a['status']!='RUNNING'
cancel=a['cancel_exercise'];submitted=[e for e in a['events'] if e['type']=='question_submitted']
req=next(r for r in a['requests'] if r.get('path')=='/api/jobs/'+cancel['accepted']['job_id']+'/cancel')
iso=lambda v:datetime.fromisoformat(v.replace('Z','+00:00'))
terminal_delay=(iso(cancel['terminal_job']['updated_at'])-iso(req['at'])).total_seconds()
native=next(e for e in a['native_media'] if e['type']=='playing')
message=next(m for m in a['actual_messages'] if m.get('generation_snapshot'))
meta=message['generation_snapshot']
collected=json.loads((OUT.parent/'student/repair-cancel-final07/report-20261030T144127912846Z/J08.json').read_text(encoding='utf-8'))
result={'actual_path':str(path),'status':a['status'],'cancel_observed_state':cancel['running_job']['state'],
 'cancel_observed_progress':cancel['running_job']['progress'],'terminal_state':cancel['terminal_job']['state'],
 'terminal_error':cancel['terminal_job']['error'],'cancel_POST_to_server_terminal_seconds':terminal_delay,
 'cancel_POST_to_server_terminal_boundary':'Harness wall request timestamp to DB updated_at. Not local audio stop, not UI terminal-render latency.',
 'cancel_button_to_next_submission_seconds':(submitted[1]['at_ms']-cancel['submit_at_ms'])/1000,
 'next_question_button_to_native_speech_seconds':(native['at_ms']-submitted[1]['at_ms'])/1000,
 'next_text_identity':{k:meta.get(k) for k in ('worker_pid','instance_id','model_instance_id','model_python_id','request_model_load_count','cumulative_model_load_count')},
 'next_generation_seconds':meta['generation_seconds'],'next_dispatch_timing':meta['dispatch_timing'],
 'cancelled_no_late_commit':cancel['no_late_cancelled_assistant'],
 'completed_remount_no_autoplay':a['requirements']['no_completed_remount_autoplay'],
 'new_lesson_audio_ended':a['requirements']['final_audio_ended'],
 'student_used':a['student_budget_before_close']['used'],
 'limits':'Deliberate cancel happened before any voice in this attempt; local old-audio-stop latency is NOT_APPLICABLE. No selected-row/followup/resume claim is inferred from J08 harness default booleans.',
 'writer_commit':collected['recording_commit'],'human_review':'H_PENDING'}
(OUT/'cancel-data.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'CANCEL_KO.md').write_text('''# 최종07 취소 후 새 수업 복구

J08은 실제 완료했다. 취소 대상은 running/progress0 상태로 관측됐고, 최종 cancelled 및 `Request cancelled during preflight; no model worker started`를 기록했다. queued 상태로 관측했다는 주장은 하지 않는다.

취소 POST부터 서버 terminal 기록까지 %.3f초다. 이는 아직 음성이 없던 텍스트 preflight 취소이며, 기존 음성 정지 시간이나 UI terminal 렌더 지연과 다르다. 취소 버튼 이후 다음 질문 제출까지 %.3f초였고, 다음 질문 버튼부터 첫 native 설명 음성은 %.3f초다.

다음 질문은 PID%s/session%s/model%s 및 request load%s였다. 생성 %.3f초, 저장 검사 %.3f초를 기록했다. 취소 뒤 늦은 assistant 추가 없음, 새 수업 음성 최종 종료, 완료 수업 재진입 자동재생 없음이 저장된 actual에서 확인된다. 장부는 텍스트2회(취소 예약 포함), 새음성0개다.

final04의 UI waiting 고착 실패는 보존하며 이번 성공과 분리한다. J08에는 선택행 보충 질문을 하지 않았으므로 generic harness의 다른 true 값으로 중간 질문/복귀 성공을 확대 해석하지 않는다. 교육·청취 H_PENDING 유지.
'''%(terminal_delay,result['cancel_button_to_next_submission_seconds'],result['next_question_button_to_native_speech_seconds'],meta['worker_pid'],meta['instance_id'],meta['model_instance_id'],meta['request_model_load_count'],meta['generation_seconds'],meta['dispatch_timing']['storage_check_seconds']),encoding='utf-8')
print(json.dumps({k:result[k] for k in ('status','cancel_POST_to_server_terminal_seconds','next_question_button_to_native_speech_seconds')},ensure_ascii=False))
