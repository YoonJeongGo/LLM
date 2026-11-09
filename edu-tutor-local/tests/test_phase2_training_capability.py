"""Policy availability must match the existing POST guard; CPU-only fixtures."""
import json

from fastapi.testclient import TestClient

from edu_tutor.api import create_app


def test_enabled_phase2_policy_disables_training_even_when_runtime_is_ready(tmp_path,monkeypatch):
    import edu_tutor.models.runtime as runtime
    import edu_tutor.api.app as app_module
    monkeypatch.setattr(runtime,'model_status',lambda **kwargs:{'ready':True,'reason':None})
    monkeypatch.setattr(app_module.importlib.util,'find_spec',lambda name:object())
    app=create_app(tmp_path)
    (tmp_path/'.local/phase2-policy.json').write_text(json.dumps({'enabled':True,'no_new_training':True}),encoding='utf-8')
    token=(tmp_path/'.local/auth-token').read_text()
    with TestClient(app,base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+token}) as client:
        training=client.get('/api/capabilities').json()['training']
        assert training['runtime_ready'] is True
        assert training['available'] is False and training['policy_blocked'] is True
        assert '사용할 수 있는 학습 예산이 없습니다' in training['reason']
        result=client.post('/api/train',json={'profile':'smoke','request_id':'policy-contract-fixture'})
        assert result.status_code==409 and client.app.state.store.list('jobs')==[]
