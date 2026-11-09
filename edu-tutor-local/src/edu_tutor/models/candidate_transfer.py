"""PROPOSAL ONLY: owned native curl transfers with parent-enforced deadlines."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import urlparse, urljoin
from email.parser import BytesHeaderParser

CURL = Path("C:/Windows/System32/curl.exe")
CURL_SHA256 = "73d24149ff289afc49ec41f08918ef9faa727d39ad993e929757dc2ddafab805"
MAX_REDIRECTS = 5
MAX_HEADER_BYTES = 262144


def official_url(value):
    if any(ord(char)<32 or ord(char)==127 for char in value):
        raise ValueError("Control characters are not allowed in an official URL")
    url = urlparse(value)
    host = url.hostname or ""
    if (url.scheme != "https" or url.username or url.password or url.port not in {None,443}
            or not (host in {"huggingface.co","hf.co"} or host.endswith(".huggingface.co") or host.endswith(".hf.co"))):
        raise ValueError("Redirect is outside reviewed public model hosting")
    return value


def curl_binary():
    if not CURL.is_file() or hashlib.sha256(CURL.read_bytes()).hexdigest() != CURL_SHA256:
        raise RuntimeError("Installed reviewed curl identity changed; no install or implicit alternative")
    return str(CURL)


def receive(root, url, target, *, maximum, transfer_maximum, deadline, cancel, prefix):
    from edu_tutor.jobs.owned_process import OwnedWindowsJob
    root, target, prefix = Path(root).resolve(), Path(target), Path(prefix)
    if (not target.resolve().is_relative_to(root) or not prefix.resolve().is_relative_to(root)
            or target.exists() or maximum <= 0 or transfer_maximum < maximum):
        raise ValueError("Unsafe transfer destination or limit")
    exe = curl_binary()
    transferred = 0
    hops = []
    current = official_url(url)
    def guard():
        if cancel.is_set():raise RuntimeError("Candidate transfer cancelled")
        if time.monotonic() >= deadline:raise TimeoutError("Candidate transfer absolute deadline reached")
    for index in range(MAX_REDIRECTS+1):
        guard()
        remaining = deadline-time.monotonic()
        available = transfer_maximum-transferred
        if available <= 0:raise RuntimeError("Candidate transfer byte envelope exhausted")
        body = prefix.with_name(prefix.name+f".hop-{index}.body")
        headers = prefix.with_name(prefix.name+f".hop-{index}.headers")
        errors = prefix.with_name(prefix.name+f".hop-{index}.stderr")
        if any(p.exists() for p in (body,headers,errors)):raise ValueError("Preserve prior transfer artifacts")
        argv = [exe,"--disable","--globoff","--silent","--show-error","--fail","--retry","0",
            "--noproxy","*","--proto","=https","--max-time",str(max(.001,remaining)),
            "--connect-timeout",str(min(15,max(.001,remaining))),"--max-filesize",str(available),
            "--dump-header",str(headers),"--output",str(body),"--write-out","%{http_code} %{size_download}",
            "--config","-"]
        process = owner = None
        started = time.monotonic()
        entry = {"index":index,"url":current,"remaining_deadline_seconds":remaining}
        hops.append(entry)
        try:
            with errors.open("xb") as stderr:
                process = subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,
                    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                entry["pid"] = process.pid
                owner = OwnedWindowsJob(process)
                # No URL is in argv: owner death before Job attachment gives
                # curl EOF with no target, so it cannot start an orphan transfer.
                # Deliver the reviewed URL only after kill-on-close ownership.
                guard()
                config_url=current.replace("\\","\\\\").replace('"','\\"')
                process.stdin.write(('url = "'+config_url+'"\n').encode("utf-8"))
                process.stdin.close()
                process.stdin = None
                while process.poll() is None:
                    guard()
                    if headers.exists() and headers.stat().st_size > MAX_HEADER_BYTES:
                        raise RuntimeError("HTTP header size exceeded")
                    if body.exists() and body.stat().st_size > available:
                        raise RuntimeError("Transfer body exceeded reserved bytes")
                    cancel.wait(min(.05,max(.001,deadline-time.monotonic())))
                guard()
                output,_ = process.communicate(timeout=1)
                entry.update(exit_code=process.returncode, wall_seconds=time.monotonic()-started)
                if process.returncode != 0:raise RuntimeError(f"Owned curl failed (exit={process.returncode}); no retry")
                parts=output.decode("ascii").strip().split()
                if len(parts)!=2 or not all(v.isdigit() for v in parts):raise RuntimeError("Invalid curl transfer receipt")
                code,count=map(int,parts)
                if not body.is_file() or body.stat().st_size != count or count > available:
                    raise RuntimeError("Curl byte receipt/file/reservation mismatch")
                transferred+=count;entry.update(http_status=code,body_bytes=count)
                if headers.stat().st_size > MAX_HEADER_BYTES:raise RuntimeError("HTTP headers exceeded limit")
                if code==200:
                    if count>maximum:raise RuntimeError("Downloaded file exceeds pinned body size")
                    target.parent.mkdir(parents=True,exist_ok=True)
                    body.rename(target)
                    return {"body_bytes":count,"transferred_bytes":transferred,"hops":hops}
                if code not in {301,302,303,307,308} or index==MAX_REDIRECTS:
                    raise RuntimeError("Unexpected status or redirect limit reached")
                raw=headers.read_bytes().replace(b"\r\n",b"\n")
                blocks=[b for b in raw.split(b"\n\n") if b.startswith(b"HTTP/")]
                if not blocks:raise RuntimeError("Missing HTTP status headers")
                fields=BytesHeaderParser().parsebytes(blocks[-1].split(b"\n",1)[1])
                locations=fields.get_all("Location",[])
                if len(locations)!=1:raise RuntimeError("Missing or ambiguous redirect target")
                current=official_url(urljoin(current,locations[0]))
        finally:
            # Direct native child: Popen is the real transfer process, with no
            # venv redirector. Job handle also bounds abrupt API-owner death.
            if owner is not None:owner.close()
            if process is not None:
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
                entry.update(exit_code=process.returncode,process_exit_confirmed=process.poll() is not None)
                if process.stdout is not None:process.stdout.close()
                if process.stdin is not None:process.stdin.close()
            prefix.with_name(prefix.name+".receipt.json").write_text(json.dumps({"hops":hops,"transferred_body_bytes":transferred},indent=2),encoding="utf-8")
    raise RuntimeError("Redirect limit reached")
