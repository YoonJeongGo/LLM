import hashlib
import json
import wave
import pytest
from types import SimpleNamespace
from edu_tutor.models.budget import reserve, finish, ResourceBudgetExceeded
from edu_tutor.speech import provider


def enable(root, **overrides):
    (root / '.local').mkdir(exist_ok=True)
    limits = dict(enabled=True, gpu_seconds=5400, new_audio_clips=12, vision_requests=4,
                  min_C_free_bytes=0, system_volume=str(root))
    limits.update(overrides)
    (root / '.local/phase2-policy.json').write_text(json.dumps(limits))


def test_crash_reservation_survives_restart_and_caps_total(tmp_path):
    enable(tmp_path, gpu_seconds=301)
    first, duration = reserve(tmp_path, {'kind': 'text'}, 900)
    assert duration == 300
    second, duration = reserve(tmp_path, {'kind': 'text'}, 300)
    assert duration == 1
    with pytest.raises(ResourceBudgetExceeded):
        reserve(tmp_path, {'kind': 'text'}, 300)
    finish(first, False)
    third, duration = reserve(tmp_path, {'kind': 'text'}, 300)
    assert duration > 290
    finish(second, True)
    finish(third, True)


def test_clip_attempts_and_photos_do_not_reset_on_failure(tmp_path):
    enable(tmp_path, new_audio_clips=2, vision_requests=1)
    r, _ = reserve(tmp_path, {'kind':'speech_batch','items':[{},{}]}, 300)
    finish(r, False)
    with pytest.raises(ResourceBudgetExceeded):
        reserve(tmp_path, {'kind':'speech'}, 300)
    r, _ = reserve(tmp_path, {'kind':'vision'}, 300)
    finish(r, False)
    with pytest.raises(ResourceBudgetExceeded):
        reserve(tmp_path, {'kind':'vision'}, 300)


def test_disk_floors_block_without_deleting_files(tmp_path):
    enable(tmp_path, min_C_free_bytes=10**30)
    marker = tmp_path / '.local' / 'preserve.txt'
    marker.write_text('keep')
    with pytest.raises(ResourceBudgetExceeded, match='C 드라이브'):
        reserve(tmp_path, {'kind':'text'}, 300)
    enable(tmp_path, fixed_storage_upper_bound_bytes=50_000_000_000,
           max_project_bytes=50_000_000_000, warning_project_bytes=40_000_000_000)
    with pytest.raises(ResourceBudgetExceeded, match='50GB'):
        reserve(tmp_path, {'kind':'text'}, 300)
    assert marker.read_text() == 'keep'


def grant_after_history(root, **caps):
    from edu_tutor.models.budget import policy
    ledger = root / 'runs/phase2/current/resource-budget.json'
    rows = json.loads(ledger.read_text())['requests'] if ledger.exists() else []
    limits = policy(root)
    limits['active_execution_allowance'] = {
        'id': 'explicit-one-lesson', 'baseline_request_count': len(rows),
        'baseline_requests_sha256': hashlib.sha256(json.dumps(rows, ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'limits': dict(text_requests=1, new_audio_clips=2, vision_requests=0, gpu_seconds=900, **caps)}
    (root/'.local/phase2-policy.json').write_text(json.dumps(limits))


def test_explicit_allowance_counts_failures_and_blocks_hidden_repair(tmp_path):
    enable(tmp_path, new_audio_clips=21, vision_requests=6)
    old, _ = reserve(tmp_path, {'kind':'speech_batch','items':[{}]*19}, 300)
    finish(old, True)
    historical = json.loads((tmp_path/'runs/phase2/current/resource-budget.json').read_text())['requests']
    grant_after_history(tmp_path)
    text, _ = reserve(tmp_path, {'kind':'text'}, 300)
    finish(text, False)
    with pytest.raises(ResourceBudgetExceeded, match='추가 승인 호출'):
        reserve(tmp_path, {'kind':'text'}, 300)
    for kind in ('vision', 'evaluation', 'training'):
        with pytest.raises(ResourceBudgetExceeded, match='추가 승인'):
            reserve(tmp_path, {'kind':kind}, 300)
    speech, _ = reserve(tmp_path, {'kind':'speech_batch','items':[{},{}]}, 300)
    finish(speech, False)
    with pytest.raises(ResourceBudgetExceeded, match='추가 승인 호출'):
        reserve(tmp_path, {'kind':'speech'}, 300)
    from edu_tutor.models.budget import status
    state = status(tmp_path)
    assert state['new_audio_attempts'] == 21
    assert state['active_execution_allowance']['text_remaining'] == 0
    assert state['active_execution_allowance']['audio_remaining'] == 0
    rows = json.loads((tmp_path/'runs/phase2/current/resource-budget.json').read_text())['requests']
    assert rows[:len(historical)] == historical
    assert all(r['execution_allowance_id'] == 'explicit-one-lesson' for r in rows[len(historical):])


def test_scoped_time_reservations_and_baseline_cannot_reset(tmp_path):
    enable(tmp_path, gpu_seconds=2000)
    grant_after_history(tmp_path)
    a, seconds = reserve(tmp_path, {'kind':'text'}, 9999)
    assert seconds == 300
    b, seconds = reserve(tmp_path, {'kind':'speech'}, 9999)
    assert seconds == 300
    c, seconds = reserve(tmp_path, {'kind':'speech'}, 9999)
    assert seconds == 300
    from edu_tutor.models.budget import status
    assert status(tmp_path)['active_execution_allowance']['seconds_remaining'] == 0
    assert status(tmp_path)['gpu_seconds_remaining'] == 1100
    # A persisted reservation remains charged after a parent crash/restart.
    with pytest.raises(ResourceBudgetExceeded):
        reserve(tmp_path, {'kind':'speech'}, 300)
    finish(a, False); finish(b, True); finish(c, True)
    grant_after_history(tmp_path)
    ledger = tmp_path/'runs/phase2/current/resource-budget.json'
    state = json.loads(ledger.read_text()); state['requests'][0]['charged_seconds'] = 0
    ledger.write_text(json.dumps(state))
    with pytest.raises(ResourceBudgetExceeded, match='기준 장부'):
        reserve(tmp_path, {'kind':'text'}, 300)


def test_shared_voice_worker_and_cache_integrity(tmp_path, monkeypatch):
    from edu_tutor.models import runtime
    folder = tmp_path / '.local/models/tts'
    folder.mkdir(parents=True)
    files=[]
    for name, config in [('config.json',{'talker_config':{'codec_eos_token_id':99}}),('generation_config.json',{})]:
        raw=json.dumps(config).encode();(folder/name).write_bytes(raw)
        files.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest()})
    (folder / 'model-manifest.json').write_text(json.dumps({'revision':'test','files':files}))
    monkeypatch.setattr(provider, 'status', lambda _root: {'ready':True})
    calls = []
    def worker(payload, **kwargs):
        calls.append(payload)
        for item in payload['items']:
            key = item['audio_id']; spec=item['spec']
            wav = tmp_path / '.local/audio' / (key+'.wav')
            # Synthetic PCM for integrity tests, never model-produced audio.
            with wave.open(str(wav),'wb') as stream:
                stream.setparams((1,2,24000,0,'NONE','not compressed'))
                stream.writeframes(b'\x10\x00'*12000)
            audio = {'audio_id':key,'checksum':hashlib.sha256(wav.read_bytes()).hexdigest(),
                     'provider':'qwen3_tts_local','voice':spec['voice'],'revision':spec['revision'],
                     'text_hash':hashlib.sha256(spec['text'].encode()).hexdigest(),'duration':.5,'sample_rate':24000,
                     'generation_settings':{'language':'Korean','do_sample':False,'max_new_tokens':768,
                                            'dictionary_version':1,'completion_check_version':2},
                     'completion':{'finish_reason':'eos','completion_check_version':2,'observed_eos_token_id':99,
                                   'last_generated_tokens':[4,99],'output_code_frames':2}}
            wav.with_suffix('.json').write_text(json.dumps(audio))
            yield {'type':'audio', **audio}
        yield {'type':'done'}
    monkeypatch.setattr(runtime, 'run_worker', worker)
    published=[]
    items=[{'id':'a','text':'세 행입니다.'},{'id':'b','text':'두 값입니다.'}]
    first=provider.prepare_batch(items,root=tmp_path,on_audio=lambda i,a:published.append(i))
    assert len(calls)==1 and len(calls[0]['items'])==2 and published==['a','b']
    assert all(not r['audio']['cache_hit'] for r in first)
    second=provider.prepare_batch(items,root=tmp_path)
    assert len(calls)==1 and all(r['audio']['cache_hit'] for r in second)
    # Modified or damaged media is regenerated; a metadata key alone is not a hit.
    (tmp_path/'.local/audio'/ (first[0]['audio']['audio_id']+'.wav')).write_bytes(b'broken')
    provider.prepare_batch(items,root=tmp_path)
    assert len(calls)==2 and len(calls[1]['items'])==1


@pytest.mark.parametrize('ended', [True,False])
def test_generated_wave_without_codec_eos_is_not_served(ended):
    import numpy as np
    # Hidden states lag the final generated token; only sequences includes EOS.
    frames=[np.array([[4,5]]),np.array([[8,5]])]
    def generate(**kwargs):
        return SimpleNamespace(hidden_states=[(None,frame) for frame in frames],
                               sequences=np.array([[4,99 if ended else 8]]))
    talker=SimpleNamespace(generate=generate)
    core=SimpleNamespace(talker=talker,config=SimpleNamespace(talker_config=SimpleNamespace(codec_eos_token_id=99)))
    class Model:
        model=core
        def generate_custom_voice(self,**kwargs):
            self.model.talker.generate()
            return [[.1,.2]],24000
    spec={'text':'시험','voice':'Sohee','max_new_tokens':768}
    if ended:
        _,_,completion=provider._checked_custom_voice(Model(),spec)
        assert completion['finish_reason']=='eos' and completion['output_code_frames']==2
    else:
        with pytest.raises(RuntimeError,match='종료 토큰'):
            provider._checked_custom_voice(Model(),spec)
    assert talker.generate is generate
