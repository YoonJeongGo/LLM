"""CPU seams for candidate tests, always loaded from this checkout's src."""
import importlib.util
from pathlib import Path
import sys
from test_text_precision import fake_modules, Model

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/qwen3_4b_official_metadata.json'


def module(name,path,monkeypatch):
    source=(ROOT/path).resolve()
    assert source.is_relative_to(ROOT/'src') or source.is_relative_to(ROOT/'scripts')
    spec=importlib.util.spec_from_file_location(name,source)
    loaded=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,name,loaded)
    spec.loader.exec_module(loaded)
    assert Path(loaded.__file__).resolve()==source
    return loaded


def load(monkeypatch,name):
    if name=='candidate_download':load(monkeypatch,'candidate_transfer')
    return module('edu_tutor.models.'+name,'src/edu_tutor/models/'+name+'.py',monkeypatch)
