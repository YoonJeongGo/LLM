"""Owned local process tests; no external network, model, GPU or live ledger."""
import io
import os
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import pytest
from candidate_support import load


def fake_transfer(monkeypatch, tmp_path, replies):
    from edu_tutor.jobs import owned_process
    d=load(monkeypatch,'candidate_transfer'); calls=[]; owned=[]
    monkeypatch.setattr(d,'curl_binary',lambda:'reviewed-curl')
    class Gate(io.BytesIO):
        def close(self):
            assert owned[-1]=='attached'
            owned.append('released');super().close()
    class Process:
        def __init__(self,argv,**kwargs):
            calls.append(argv);self.pid=42;self.returncode=0;self.stdin=Gate();self.stdout=io.BytesIO()
            assert '--globoff' in argv
            assert argv[1]=='--disable' and argv[-2:]==['--config','-']
            assert not any(arg.startswith('https://') for arg in argv)
            assert kwargs['stdin']==subprocess.PIPE and '-L' not in argv and '--location' not in argv
            assert argv[argv.index('--retry')+1]=='0'
            code,body,location=replies[len(calls)-1]
            Path(argv[argv.index('--output')+1]).write_bytes(body)
            Path(argv[argv.index('--dump-header')+1]).write_bytes(
                f'HTTP/1.1 {code} Status\r\n'.encode()+(f'Location: {location}\r\n'.encode() if location else b'')+b'\r\n')
            self.output=f'{code} {len(body)}'.encode()
        def poll(self):return self.returncode
        def communicate(self,timeout):return self.output,None
        def wait(self,timeout):return self.returncode
    class Owner:
        def __init__(self,p):owned.append('attached')
        def close(self):pass
    monkeypatch.setattr(owned_process,'OwnedWindowsJob',Owner)
    monkeypatch.setattr(d,'subprocess',SimpleNamespace(Popen=Process,PIPE=subprocess.PIPE,TimeoutExpired=subprocess.TimeoutExpired))
    return d,calls,owned


def test_manual_redirect_counts_all_bodies_and_releases_only_after_ownership(monkeypatch,tmp_path):
    d,calls,owned=fake_transfer(monkeypatch,tmp_path,[(302,b'go','https://cdn-lfs.hf.co/fixed'),(200,b'payload',None)])
    got=d.receive(tmp_path,'https://huggingface.co/fixed',tmp_path/'target',maximum=7,transfer_maximum=9,
                  deadline=time.monotonic()+10,cancel=threading.Event(),prefix=tmp_path/'hop')
    assert got['body_bytes']==7 and got['transferred_bytes']==9 and len(calls)==2
    assert owned==['attached','released','attached','released']
    assert all(h['process_exit_confirmed'] for h in got['hops'])
    assert (tmp_path/'target').read_bytes()==b'payload'


def test_offsite_redirect_stops_before_second_process(monkeypatch,tmp_path):
    d,calls,_=fake_transfer(monkeypatch,tmp_path,[(302,b'go','https://evil.example/weights')])
    with pytest.raises(ValueError,match='outside'):
        d.receive(tmp_path,'https://huggingface.co/fixed',tmp_path/'target',maximum=7,transfer_maximum=9,
                  deadline=time.monotonic()+10,cancel=threading.Event(),prefix=tmp_path/'hop')
    assert len(calls)==1 and not (tmp_path/'target').exists()
    assert json.loads((tmp_path/'hop.receipt.json').read_text())['transferred_body_bytes']==2


@pytest.mark.skipif(os.name!='nt',reason='Actual Windows owned-process boundary')
@pytest.mark.parametrize('mode',['slow_headers','slow_body','cancel'])
def test_owned_native_child_stops_at_parent_deadline_or_cancel(monkeypatch,tmp_path,mode):
    d=load(monkeypatch,'candidate_transfer');children=[];cancel=threading.Event()
    monkeypatch.setattr(d,'curl_binary',lambda:'stub-native-transfer')
    # A local native child blocks on config EOF, then mimics header/body drip.
    # The production parent loop and actual Windows Job ownership are unchanged.
    script="""import sys,time
from pathlib import Path
sys.stdin.buffer.read()
with Path(sys.argv[1]).open('wb',buffering=0) as stream:
 while True:
  stream.write(b'x');time.sleep(.01)
"""
    def launch(argv,**kwargs):
        file=argv[argv.index('--dump-header' if mode=='slow_headers' else '--output')+1]
        p=subprocess.Popen([sys._base_executable,'-u','-c',script,file],**kwargs);children.append(p)
        return p
    monkeypatch.setattr(d,'subprocess',SimpleNamespace(Popen=launch,PIPE=subprocess.PIPE,
        CREATE_NO_WINDOW=subprocess.CREATE_NO_WINDOW,TimeoutExpired=subprocess.TimeoutExpired))
    timer=threading.Timer(.5,cancel.set) if mode=='cancel' else None
    started=time.monotonic()
    if timer:timer.start()
    try:
        with pytest.raises(RuntimeError if mode=='cancel' else TimeoutError):
            d.receive(tmp_path,'https://huggingface.co/fixed',tmp_path/'target',maximum=1024,transfer_maximum=1024,
                deadline=started+1,cancel=cancel,prefix=tmp_path/'hop')
    finally:
        if timer:timer.cancel()
    assert time.monotonic()-started<3
    assert len(children)==1 and children[0].poll() is not None
    path=tmp_path/('hop.hop-0.headers' if mode=='slow_headers' else 'hop.hop-0.body')
    assert path.stat().st_size>0
    receipt=json.loads((tmp_path/'hop.receipt.json').read_text())
    assert receipt['hops'][0]['process_exit_confirmed']
    assert not (tmp_path/'target').exists()


@pytest.mark.skipif(os.name!='nt',reason='Actual Windows owned-process boundary')
def test_ownership_failure_never_releases_stdin_and_kills_child(monkeypatch,tmp_path):
    from edu_tutor.jobs import owned_process
    d=load(monkeypatch,'candidate_transfer');children=[]
    monkeypatch.setattr(d,'curl_binary',lambda:'stub-native-transfer')
    marker=tmp_path/'must-not-exist'
    script="import sys;from pathlib import Path;sys.stdin.buffer.read();Path(sys.argv[1]).write_text('started')"
    def launch(argv,**kwargs):
        p=subprocess.Popen([sys._base_executable,'-u','-c',script,str(marker)],**kwargs);children.append(p);return p
    monkeypatch.setattr(d,'subprocess',SimpleNamespace(Popen=launch,PIPE=subprocess.PIPE,
        CREATE_NO_WINDOW=subprocess.CREATE_NO_WINDOW,TimeoutExpired=subprocess.TimeoutExpired))
    def fail_owner(process):raise RuntimeError('synthetic ownership failure')
    monkeypatch.setattr(owned_process,'OwnedWindowsJob',fail_owner)
    with pytest.raises(RuntimeError,match='ownership'):
        d.receive(tmp_path,'https://huggingface.co/fixed',tmp_path/'target',maximum=2,transfer_maximum=2,
            deadline=time.monotonic()+2,cancel=threading.Event(),prefix=tmp_path/'hop')
    assert children[0].poll() is not None and not marker.exists()
