"""Installed Windows SAPI speech. No neural package imports or network clients.

The existing authenticated speech job reserves the attempt and owns the GPU
dispatch slot even though this adapter uses CPU. The small owned PowerShell
child also watches its Python parent's identity and the shared cancel file.
"""
from __future__ import annotations

import array
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import wave

PROVIDER = "windows_sapi_local"
VOICE_PREFIX = "windows_sapi:"
DICTIONARY_VERSION = 2
SAMPLE_RATE = 22050


from edu_tutor.jobs.owned_process import OwnedWindowsJob as _OwnedProcessJob


def settings(root):
    path = Path(root) / ".local/speech-provider.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if value.get("provider", "qwen3_tts_local") not in {"qwen3_tts_local", PROVIDER}:
        raise ValueError("Unknown speech provider")
    return value


def resolve_voice(root, voice):
    if voice != "default":
        return voice
    config = settings(root)
    if config.get("provider") == PROVIDER:
        return VOICE_PREFIX + config["windows_sapi"]["voice_id"]
    return "Sohee"


def sapi_binary():
    return Path(os.environ.get("WINDIR", "C:/Windows")) / "System32/Speech/Common/sapi.dll"


def status(root):
    config = settings(root).get("windows_sapi", {})
    ready, reason = False, "설치된 한국어 Windows 음성 설정을 확인하지 못했습니다."
    if os.name == "nt" and config.get("voice_id") and config.get("language") == "ko-KR":
        try:
            import winreg
            prefix = "HKEY_LOCAL_MACHINE\\"
            ident = config["voice_id"]
            if not ident.startswith(prefix + "SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\"):
                raise ValueError("Not an installed SAPI voice token")
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ident[len(prefix):] + "\\Attributes") as key:
                languages = winreg.QueryValueEx(key, "Language")[0].lower().split(";")
                if "412" not in languages:
                    raise ValueError("Selected installed voice is not Korean")
            if hashlib.sha256(sapi_binary().read_bytes()).hexdigest() != config["sapi_binary_sha256"]:
                raise ValueError("SAPI engine version changed; revalidate its configuration")
            host = Path(config["powershell_executable"])
            if host.name.lower() != "pwsh.exe" or hashlib.sha256(host.read_bytes()).hexdigest() != config["powershell_sha256"]:
                raise ValueError("Recorded PowerShell host changed; revalidate configuration")
            ready, reason = True, None
        except (OSError, ValueError, KeyError) as exc:
            reason = f"Windows 음성 설정 재확인 필요: {exc}"
    return {"installed": ready, "ready": ready, "provider": PROVIDER,
        "voice": config.get("voice_id"), "voice_name": config.get("voice_name"),
        "revision": config.get("sapi_binary_sha256"), "reason": reason,
        "listening_review": "not_run", "device": "cpu", "network": "no network API; installed local SAPI engine"}


def spoken_text(text):
    result = re.sub(r"COUNT\s*\(\s*\*\s*\)", "카운트 별표", text, flags=re.I)
    result = re.sub(r"(?<![A-Za-z0-9_])NULL(?![A-Za-z0-9_])", "널", result, flags=re.I)
    result = re.sub(r"(?<![A-Za-z0-9_])SQL(?![A-Za-z0-9_])", "에스 큐 엘", result, flags=re.I)
    # Numeric normalization remains with the installed Korean engine. Do not
    # invent a context-insensitive digit conversion (row 10 != decimal 1.0).
    return result


def spec(text, root, voice):
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError("음성은 비어 있지 않은 1,000자 이하 문장만 지원합니다.")
    config = settings(root).get("windows_sapi", {})
    ident = voice.removeprefix(VOICE_PREFIX)
    if voice != VOICE_PREFIX + config.get("voice_id", "") or config.get("language") != "ko-KR":
        raise ValueError("검증 대상으로 등록된 한국어 Windows 화자만 사용할 수 있습니다.")
    value = {"provider": PROVIDER, "text": spoken_text(text), "spoken_text": spoken_text(text),
        "display_text": text, "voice": ident, "voice_name": config["voice_name"],
        "language": "ko-KR", "revision": config["sapi_binary_sha256"],
        "engine_version": config["engine_version"], "os_build": config["os_build"],
        "rate": 0, "volume": 100, "sample_rate": SAMPLE_RATE, "channels": 1,
        "sample_width": 2, "dictionary_version": DICTIONARY_VERSION,
        "completion_check_version": 1, "number_pronunciation": "installed_Korean_engine"}
    key = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return key, value


def generation_settings(value):
    return {k: value[k] for k in ("language", "rate", "volume", "sample_rate", "channels",
        "sample_width", "dictionary_version", "completion_check_version", "number_pronunciation")}


def inspect_pcm(data):
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("Wave exceeds the short-lesson byte limit")
    with wave.open(io.BytesIO(data), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
            raise ValueError("Expected mono 16-bit 22050Hz PCM")
        frames = stream.getnframes()
        raw = stream.readframes(frames)
    duration = frames / SAMPLE_RATE
    if len(raw) != frames * 2 or not .1 <= duration <= 35:
        raise ValueError("Invalid/incomplete wave or speech exceeds 35 seconds")
    samples = array.array("h", raw)
    if sys.byteorder != "little":
        samples.byteswap()
    rms = math.sqrt(sum(int(s) ** 2 for s in samples) / len(samples)) / 32768
    if max(abs(s) for s in samples) < 2 or rms < 0.00001:
        raise ValueError("Silent waveform")
    return {"duration": duration, "sample_rate": SAMPLE_RATE, "rms": rms,
        "checksum": hashlib.sha256(data).hexdigest(), "pcm_frames": frames}


def cached_audio(text, root, voice):
    def miss(code, reason):
        return {"hit": False, "code": code, "reason": reason}
    try:
        key, value = spec(text, root, voice)
        folder = (Path(root) / ".local/audio").resolve()
        wav = folder / (key + ".wav")
        meta = wav.with_suffix(".json")
        if not wav.is_file() or not meta.is_file():
            return miss("cache_missing", "현재 대사·Windows 화자 설정에 맞는 저장 음성이 없습니다.")
        if wav.resolve().parent != folder or meta.resolve().parent != folder or meta.stat().st_size > 1024 * 1024:
            raise ValueError("Invalid cache path/metadata size")
        saved = json.loads(meta.read_text(encoding="utf-8"))
        expected = {"audio_id": key, "provider": PROVIDER, "voice": value["voice"],
            "revision": value["revision"], "engine_version": value["engine_version"],
            "text_hash": hashlib.sha256(value["text"].encode()).hexdigest(),
            "display_text": value["display_text"], "spoken_text": value["spoken_text"],
            "generation_settings": generation_settings(value)}
        if any(saved.get(k) != v for k, v in expected.items()):
            raise ValueError("Speech identity/settings mismatch")
        completion = saved.get("completion", {})
        if completion.get("finish_reason") != "sapi_wait_until_done" or completion.get("exit_code") != 0 or completion.get("completion_check_version") != 1:
            raise ValueError("SAPI completion is unconfirmed")
        with wav.open("rb") as stream:
            data = stream.read(4 * 1024 * 1024 + 1)
        inspected = inspect_pcm(data)
        if any(saved.get(k) != inspected[k] for k in ("checksum", "sample_rate", "duration")):
            raise ValueError("PCM integrity mismatch")
        return {"hit": True, "audio": {**saved, "cache_hit": True}, "path": wav, "wave_bytes": data}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, EOFError, wave.Error):
        return miss("cache_invalid", "저장된 Windows 음성의 대사·완료·PCM 무결성 검사를 통과하지 못했습니다.")


def speech_job(payload, emit, *, batch_index=0, progress=None):
    root = Path(payload["root"])
    value = payload["spec"]
    voice = VOICE_PREFIX + value["voice"]
    key, checked = spec(value["display_text"], root, voice)
    if checked != value or key != payload["audio_id"] or not status(root)["ready"]:
        raise ValueError("Windows speech settings changed or voice unavailable")
    if Path(payload["cancel_path"]).exists():
        raise RuntimeError("Speech cancelled before SAPI initialization")
    run = Path(payload["run_dir"])
    temporary = run / ("sapi-" + key + ".wav")
    report = run / ("sapi-" + key + ".json")
    request = run / ("sapi-" + key + "-request.json")
    progress_path = run / ("sapi-" + key + "-progress.jsonl")
    ownership_ready = run / ("sapi-" + key + "-owned.ready")
    if any(p.exists() for p in (temporary, report, request, ownership_ready)):
        raise ValueError("SAPI request artifacts already exist; no retry/overwrite")
    import psutil  # process identity only; no numerical/model packages
    parent = psutil.Process(os.getpid())
    request.write_text(json.dumps({"spec": value, "output": str(temporary), "report": str(report),
        "cancel_path": payload["cancel_path"], "parent_pid": os.getpid(),
        "parent_create_time": parent.create_time(), "max_seconds": 280,
        "ownership_ready": str(ownership_ready), "progress_path": str(progress_path),
        "job_id": payload.get("job_id")}, ensure_ascii=False), encoding="utf-8")
    executable = Path(settings(root)["windows_sapi"]["powershell_executable"])
    script = Path(__file__).with_name("windows_sapi_worker.ps1")
    started = time.perf_counter()
    if progress:
        progress("synth_started", provider=PROVIDER, item_index=batch_index)
    with (run / ("sapi-"+key+".stdout.log")).open("wb") as stdout, (run / ("sapi-"+key+".stderr.log")).open("wb") as stderr:
        child = subprocess.Popen([str(executable), "-NoProfile", "-NonInteractive", "-File", str(script), "-RequestPath", str(request)],
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, cwd=root,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        owned_job = None
        try:
            owned_job = _OwnedProcessJob(child)
            ownership_ready.touch(exist_ok=False)
            while child.poll() is None:
                if Path(payload["cancel_path"]).exists():
                    raise RuntimeError("Speech cancelled during SAPI synthesis")
                if time.perf_counter()-started > 285:
                    raise TimeoutError("Windows speech exceeded bounded synthesis deadline")
                time.sleep(.05)
            if child.returncode != 0:
                raise RuntimeError(f"Windows speech child failed (exit={child.returncode}); see {run.name}/{report.stem}.stderr.log")
        finally:
            if owned_job is not None:
                owned_job.close()
            if child.poll() is None:
                if owned_job is None:
                    child.terminate()
                child.wait(timeout=5)
    synthesized = time.perf_counter()
    completion = json.loads(report.read_text(encoding="utf-8-sig"))
    if completion.get("finish_reason") != "sapi_wait_until_done" or completion.get("voice_id") != value["voice"]:
        raise RuntimeError("Windows speech completion/voice identity is unconfirmed")
    completion.update(exit_code=child.returncode, completion_check_version=1,
        ownership="exact_Popen_handle_in_Windows_kill_on_job_close_job")
    data = temporary.read_bytes()
    inspected = inspect_pcm(data)
    if Path(payload["cancel_path"]).exists():
        raise RuntimeError("Speech cancelled before publishing audio")
    folder = root / ".local/audio"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (key + ".wav")
    # A valid immutable cache was already reused by prepare_batch. Preserve
    # damaged legacy entries for diagnosis rather than overwriting their bytes.
    if target.exists() or target.with_suffix(".json").exists():
        raise ValueError("Existing Windows speech cache entry must be reviewed; refusing overwrite")
    target.write_bytes(data)
    result = {"audio_id": key, "url": f"/api/audio/{key}", **inspected,
        "provider": PROVIDER, "voice": value["voice"], "voice_name": value["voice_name"],
        "revision": value["revision"], "engine_version": value["engine_version"],
        "display_text": value["display_text"], "spoken_text": value["spoken_text"],
        "text_hash": hashlib.sha256(value["text"].encode()).hexdigest(),
        "generation_settings": generation_settings(value), "completion": completion,
        "elapsed_seconds": time.perf_counter()-started, "model_load_seconds": None, "model_load_count": 0,
        "device": "cpu", "peak_vram_bytes": 0, "batch_index": batch_index,
        "batch_mode": "isolated_system_voice", "cache_hit": False, "tier": "T2",
        "listening_review": "not_run", "alignment": "waveform-driven mouth; no phoneme alignment",
        "host_timing": {"clock": "worker_perf_counter", "resolution_seconds": time.get_clock_info("perf_counter").resolution, "origin": "SAPI_child_start",
            "voice_api_seconds": completion["synthesis_seconds"], "child_start_to_close_seconds": synthesized-started,
            "wave_validation_and_publish_seconds": time.perf_counter()-synthesized,
            "voice_api_to_audio_duration_ratio": completion["synthesis_seconds"]/inspected["duration"]}}
    target.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if progress:
        progress("synth_finished", provider=PROVIDER, item_index=batch_index)
        progress("wav_saved", output_path=str(target), checksum=result["checksum"], duration_seconds=result["duration"])
    emit("audio", **result)
    return result
