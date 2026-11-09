from pathlib import Path

import pytest
import yaml

from edu_tutor.training.runner import education_bounds, run_gpu_training, _matching_owned_processes, _remaining_work_seconds


def configuration():
    root=Path(__file__).resolve().parents[1]
    return yaml.safe_load((root/'configs/finish_education.yaml').read_text(encoding='utf-8'))


def test_three_epochs_is_stricter_than_six_hundred_step_cap():
    config=configuration()
    assert education_bounds(config,240)==(90,7200,3)
    config['budgets']['education_optimizer_steps']=20
    assert education_bounds(config,240)==(20,7200,3)


@pytest.mark.parametrize('field,value',[('education_optimizer_steps',601),('education_wall_seconds',7201)])
def test_training_limits_are_not_silently_expanded(field,value):
    config=configuration();config['budgets'][field]=value
    with pytest.raises(ValueError,match='600 steps or 7200'):
        education_bounds(config,240)


def test_no_active_scope_denies_education_before_model_or_provenance(tmp_path,monkeypatch):
    from edu_tutor.models import budget
    monkeypatch.setattr(budget,'training_allowed',lambda *_:False,raising=False)
    monkeypatch.setattr(budget,'active_scope_id',lambda *_:None,raising=False)
    root=Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError,match='explicitly active training allowance'):
        run_gpu_training(root/'configs/finish_education.yaml','missing-model',tmp_path/'unused',
            mode='education',scope_id='finish-local-tutor-20261028-v1')
    assert not (tmp_path/'unused').exists()


def test_education_config_excludes_final_data():
    config=configuration()
    paths=config['training']['dataset_paths']
    assert all('/development/' in p and '/final/' not in p for p in paths)
    assert config['training']['auto_promote_adapter'] is False


def test_recycled_pid_is_never_treated_as_owned_worker(monkeypatch):
    import psutil
    class Process:
        def __init__(self,pid):self.pid=pid
        def create_time(self):return {101:10.0,102:99.0}[self.pid]
        def is_running(self):return True
    monkeypatch.setattr(psutil,'Process',Process)
    found=_matching_owned_processes({101:10.0,102:20.0})
    assert [p.pid for p in found]==[101]


def test_training_and_reload_budget_keep_cleanup_inside_wall_cap():
    assert _remaining_work_seconds(100,7200,now=200)==7094
    assert _remaining_work_seconds(100,300,now=390)==4
    with pytest.raises(TimeoutError,match='cleanup margin'):
        _remaining_work_seconds(100,300,now=394)
