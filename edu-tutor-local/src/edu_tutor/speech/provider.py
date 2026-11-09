from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import re
import time
import wave
from pathlib import Path
from edu_tutor.paths import initialize, project_root

VOICES = {"Sohee", "Vivian", "Serena", "Ryan", "Aiden", "Ono_Anna", "Uncle_Fu", "Dylan", "Eric"}


def pronunciation(text):
    text = re.sub(r"COUNT\s*\(\s*\*\s*\)", "카운트 별표", text, flags=re.I)
    return re.sub(r"\bNULL\b", "널", text, flags=re.I)


def status(root=None):
    from .windows_sapi import settings, status as windows_status
    if settings(project_root(root)).get("provider") == "windows_sapi_local":
        return windows_status(project_root(root))
    folder = project_root(root) / ".local/models/tts"
    installed = (folder / "model-manifest.json").exists()
    ready = installed and importlib.util.find_spec("qwen_tts") is not None
    return {"installed": installed, "ready": ready, "provider": "qwen3_tts_local", "voice": "Sohee",
            "reason": None if ready else "음성 사용 불가: 로컬 TTS 모델 또는 패키지가 없습니다.", "listening_review": "not_run"}


def prepare(text, root=None, voice="Sohee", cancel_event=None, job_id=None, session_key=None):
    return prepare_batch([{"id": "answer", "text": text}], root=root, voice=voice,
                         cancel_event=cancel_event, job_id=job_id, session_key=session_key)[0]["audio"]


def _spec(text, root, voice):
    from .windows_sapi import resolve_voice, spec as windows_spec, VOICE_PREFIX
    voice = resolve_voice(root, voice)
    if voice.startswith(VOICE_PREFIX):
        return windows_spec(text, root, voice)
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError("음성은 비어 있지 않은 1,000자 이하 문장만 지원합니다.")
    manifest = json.loads((root / ".local/models/tts/model-manifest.json").read_text(encoding="utf-8"))
    spec = {"text": pronunciation(text), "display_text": text, "voice": voice,
            "revision": manifest["revision"], "language": "Korean", "max_new_tokens": 768,
            "dictionary_version": 1, "completion_check_version": 2}
    key = hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return key, spec


def cached_audio(text, root=None, voice="Sohee"):
    """Read and validate an exact existing clip. Never initialize, write or generate.

    The legacy content key includes the displayed script and pinned model revision.
    A lesson/board binding is supplied separately by the authenticated API. Small
    pinned configuration files are checked without loading or hashing model weights.
    """
    root = project_root(root)
    def miss(code, reason):
        return {"hit": False, "code": code, "reason": reason}
    from .windows_sapi import resolve_voice, cached_audio as windows_cache, VOICE_PREFIX
    try:
        voice = resolve_voice(root, voice)
    except (OSError, ValueError, KeyError, TypeError):
        return miss("provider_settings_invalid", "현재 음성 제공자 설정을 확인할 수 없습니다.")
    if voice.startswith(VOICE_PREFIX):
        return windows_cache(text, root, voice)
    if voice not in VOICES:
        return miss("unsupported_voice", "지원하지 않는 제공 화자입니다.")
    try:
        folder = root / ".local/models/tts"
        manifest = json.loads((folder / "model-manifest.json").read_text(encoding="utf-8"))
        files = {item["path"]: item for item in manifest.get("files", [])}
        configs = {}
        for name in ("config.json", "generation_config.json"):
            data = (folder / name).read_bytes()
            if len(data) > 1024 * 1024 or hashlib.sha256(data).hexdigest() != files.get(name, {}).get("sha256"):
                return miss("model_settings_changed", "현재 음성 모델 설정이 저장된 revision과 일치하지 않습니다.")
            configs[name] = json.loads(data)
        key, spec = _spec(text, root, voice)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return miss("model_settings_unavailable", "저장 음성의 모델·설정 정보를 확인할 수 없습니다.")
    metadata = root / ".local/audio" / (key + ".json")
    wav = metadata.with_suffix(".wav")
    if not metadata.is_file() or not wav.is_file():
        return miss("cache_missing", "현재 대사와 설정에 일치하는 저장 음성이 없습니다. 새 음성을 자동 생성하지 않습니다.")
    try:
        audio_folder = (root / ".local/audio").resolve()
        if metadata.resolve().parent != audio_folder or wav.resolve().parent != audio_folder:
            return miss("cache_path_invalid", "저장 음성 경로가 허용된 폴더를 벗어납니다.")
        if metadata.stat().st_size > 1024 * 1024:
            raise ValueError("oversized metadata")
        cached = json.loads(metadata.read_text(encoding="utf-8"))
        settings = {"language": spec["language"], "do_sample": False,
                    "max_new_tokens": spec["max_new_tokens"], "dictionary_version": spec["dictionary_version"],
                    "completion_check_version": spec["completion_check_version"]}
        expected = {"audio_id": key, "provider": "qwen3_tts_local", "revision": spec["revision"],
                    "voice": voice, "text_hash": hashlib.sha256(spec["text"].encode()).hexdigest()}
        if any(cached.get(k) != v for k, v in expected.items()) or cached.get("generation_settings") != settings:
            return miss("cache_metadata_mismatch", "저장 음성의 대사·화자·모델·생성 설정이 일치하지 않습니다.")
        completion = cached.get("completion", {})
        eos = configs["config.json"]["talker_config"]["codec_eos_token_id"]
        if (completion.get("finish_reason") != "eos" or completion.get("completion_check_version") != 2
                or completion.get("observed_eos_token_id") != eos
                or eos not in completion.get("last_generated_tokens", [])
                or not 0 < completion.get("output_code_frames", 0) <= spec["max_new_tokens"]):
            return miss("cache_incomplete", "종료가 확인되지 않은 음성은 재생하지 않습니다.")
        # Keep the validated bytes for serving, so a concurrent replacement
        # cannot change the file between checksum validation and HTTP playback.
        with wav.open("rb") as stream:
            wave_bytes = stream.read(4 * 1024 * 1024 + 1)
        if len(wave_bytes) > 4 * 1024 * 1024:
            return miss("cache_wave_oversized", "저장 음성의 크기가 짧은 단위 제한을 넘었습니다.")
        checksum = hashlib.sha256(wave_bytes).hexdigest()
        if checksum != cached.get("checksum"):
            return miss("cache_checksum_mismatch", "저장 음성 파일의 무결성 검사를 통과하지 못했습니다.")
        with wave.open(io.BytesIO(wave_bytes), "rb") as stream:
            rate, frames = stream.getframerate(), stream.getnframes()
            duration = frames / rate
            if (stream.getnchannels() != 1 or stream.getsampwidth() != 2 or stream.getcomptype() != "NONE"
                    or not .1 <= duration <= 35 or cached.get("sample_rate") != rate
                    or abs(cached.get("duration", 0) - duration) > 1 / rate):
                return miss("cache_wave_mismatch", "저장 음성의 길이·샘플 정보가 일치하지 않습니다.")
        return {"hit": True, "audio": {**cached, "cache_hit": True}, "path": wav, "wave_bytes": wave_bytes}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, wave.Error, EOFError, ZeroDivisionError):
        return miss("cache_invalid", "저장 음성 정보를 검증할 수 없습니다. 새 음성을 자동 생성하지 않습니다.")


def prepare_batch(items, root=None, voice="Sohee", cancel_event=None, job_id=None, on_audio=None, session_key=None):
    """Prepare 1..4 short units with a single sequential TTS model load.

    on_audio(id, audio) publishes complete clips as they arrive; subsequent
    units can be generated while the first complete unit is already playable.
    """
    from edu_tutor.models.runtime import run_worker, ModelUnavailable
    from .windows_sapi import resolve_voice, VOICE_PREFIX, status as windows_status
    root = initialize(root)
    voice = resolve_voice(root, voice)
    system_voice = voice.startswith(VOICE_PREFIX)
    if not isinstance(items, list) or not 1 <= len(items) <= 4 or len({i["id"] for i in items}) != len(items):
        raise ValueError("한 번에 서로 다른 1~4개 음성 단위를 준비할 수 있습니다.")
    if voice not in VOICES and not system_voice:
        raise ValueError("지원하지 않는 제공 화자입니다.")
    specs = {i["id"]: _spec(i["text"], root, voice) for i in items}
    by_key = {}
    missing = {}
    for key, spec in specs.values():
        if key in by_key or key in missing:
            continue
        cached = cached_audio(spec["display_text"], root=root, voice=voice)
        if cached["hit"]:
            by_key[key] = cached["audio"]
            continue
        if system_voice and cached.get("code") != "cache_missing":
            # System-voice cache corruption needs explicit review. Do not spend
            # an attempt and only then discover that preserved bytes exist.
            raise ValueError(cached["reason"])
        missing[key] = {"spec": spec, "audio_id": key}
    def publish(key, audio):
        if on_audio:
            for ident, (audio_key, _) in specs.items():
                if key == audio_key:
                    on_audio(ident, audio)
    for key, audio in by_key.items():
        publish(key, audio)
    payload = {"kind": "speech_batch", "items": list(missing.values())}
    if system_voice:
        payload["speech_provider"] = "windows_sapi_local"
    if session_key and not system_voice:
        payload["tts_session_key"] = session_key
    if job_id:
        payload["job_id"] = job_id
    if missing:
        state = windows_status(root) if system_voice else status(root)
        if not state["ready"]:
            raise ModelUnavailable("TTS unavailable: " + state["reason"])
        for event in run_worker(payload, root=root, cancel_event=cancel_event):
            if event.get("type") == "audio":
                audio = {k: v for k, v in event.items() if k != "type"}
                by_key[audio["audio_id"]] = {**audio, "cache_hit": False}
                publish(audio["audio_id"], by_key[audio["audio_id"]])
    if any(key not in by_key for key, _ in specs.values()):
        raise RuntimeError("음성 생성이 중단되었습니다.")
    return [{"id": ident, "audio": by_key[key]} for ident, (key, _) in specs.items()]


def speech_batch_job(payload, emit):
    if payload.get("speech_provider") == "windows_sapi_local":
        from .windows_sapi import speech_job as windows_job
        if not 1 <= len(payload["items"]) <= 4:
            raise ValueError("Speech batch must contain 1..4 clips")
        for index, item in enumerate(payload["items"]):
            windows_job({**payload, **item}, emit, batch_index=index)
        return
    import torch
    from qwen_tts import Qwen3TTSModel
    if not 1 <= len(payload["items"]) <= 4:
        raise ValueError("Speech batch must contain 1..4 clips")
    started = time.monotonic()
    root = Path(payload["root"])
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    model = Qwen3TTSModel.from_pretrained(str(root / ".local/models/tts"),
        device_map="cuda:0", dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        attn_implementation="sdpa", local_files_only=True)
    load_seconds = time.monotonic() - started
    for index, item in enumerate(payload["items"]):
        if Path(payload["cancel_path"]).exists():
            raise RuntimeError("Speech cancelled")
        speech_job({**payload, **item}, emit, model=model,
                   model_load_seconds=load_seconds if index == 0 else 0, batch_index=index)


def _checked_custom_voice(model, spec, report_path=None, phase_timings=None):
    """Observe the installed qwen-tts 0.1.1 codec stop marker without patching it.

    The public helper returns WAVs even when its code budget is exhausted.
    Observe the generated token sequence, not lagging hidden-state audio codes
    (the last EOS token need not have a following hidden state).
    """
    talker = model.model.talker
    original = talker.generate
    completion = {"finish_reason": "not_observed", "output_code_frames": 0}
    def observe(*args, **kwargs):
        output = original(*args, **kwargs)
        first_codes = output.sequences[0].tolist()
        eos = model.model.config.talker_config.codec_eos_token_id
        completion.update(finish_reason="eos" if eos in first_codes else "length_or_timeout",
                          output_code_frames=len(first_codes), completion_check_version=2,
                          observed_eos_token_id=eos, last_generated_tokens=first_codes[-5:])
        if report_path:
            Path(report_path).write_text(json.dumps(completion, indent=2), encoding="utf-8")
        return output
    talker.generate = observe
    wrapped = []
    if phase_timings is not None:
        import torch
        # A handful of API boundaries, never one synchronization per token.
        # These are synchronized host intervals, not CUDA kernel timings.
        def wrap(owner, name, key):
            original_method = getattr(owner, name)
            def timed(*args, **kwargs):
                torch.cuda.synchronize()
                started = time.monotonic()
                try:
                    return original_method(*args, **kwargs)
                finally:
                    torch.cuda.synchronize()
                    phase_timings[key] = phase_timings.get(key, 0.0) + time.monotonic() - started
                    phase_timings[key.replace("_seconds", "_calls")] = phase_timings.get(key.replace("_seconds", "_calls"), 0) + 1
            setattr(owner, name, timed)
            wrapped.append((owner, name, original_method))
        wrap(model, "_tokenize_texts", "tokenize_and_input_transfer_seconds")
        wrap(model.model, "generate", "speech_code_generation_api_seconds")
        wrap(model.model.speech_tokenizer, "decode", "codec_decode_and_cpu_transfer_api_seconds")
        wrap(model.model.speech_tokenizer.model, "decode", "codec_network_decode_seconds")
        phase_timings.update(clock="worker_monotonic", timing_kind="synchronized_host_api_boundaries",
            gpu_kernel_seconds=None, cpu_transfer_seconds=None,
            cpu_transfer_scope="Included in speech_tokenizer.decode together with input normalization, waveform conversion and device-to-CPU copy; not separately measured.",
            nested_intervals_notice="codec_network_decode_seconds is inside codec_decode_and_cpu_transfer_api_seconds; do not add them.")
    try:
        wavs, sample_rate = model.generate_custom_voice(text=spec["text"], language="Korean",
            speaker=spec["voice"], max_new_tokens=spec["max_new_tokens"], do_sample=False)
    finally:
        for owner, name, original_method in reversed(wrapped):
            setattr(owner, name, original_method)
        talker.generate = original
    if completion["finish_reason"] != "eos":
        raise RuntimeError("음성 종료 토큰을 확인하지 못했습니다. 잘린 음성은 재생하지 않습니다. 대사를 더 짧게 나눠 주세요.")
    return wavs, sample_rate, completion


def speech_job(payload, emit, model=None, model_load_seconds=0, batch_index=0,
               session_info=None, model_load_count=None, progress=None):
    if payload.get("spec", {}).get("provider") == "windows_sapi_local":
        from .windows_sapi import speech_job as windows_job
        return windows_job(payload, emit, batch_index=batch_index, progress=progress)
    import numpy as np
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel
    root = Path(payload["root"])
    spec = payload["spec"]
    started = time.monotonic()
    shared_model = model is not None
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    if model is None:
        model = Qwen3TTSModel.from_pretrained(str(root / ".local/models/tts"),
            device_map="cuda:0", dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
            attn_implementation="sdpa", local_files_only=True)
        model_load_seconds = time.monotonic() - started
    # This installed helper only merges configuration dictionaries; it performs
    # no model work and leaves the effective arguments passed below unchanged.
    effective_settings = model._merge_generate_kwargs(do_sample=False, max_new_tokens=spec["max_new_tokens"])
    if payload.get("seed") is not None:
        import random
        seed = payload["seed"]
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("Invalid fixed TTS seed")
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    detailed = bool(payload.get("detailed_timing"))
    phases = {} if detailed else None
    if detailed:
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    synthesis_started = time.monotonic()
    if progress is not None:
        progress("synth_started", item_index=batch_index)
    completion_path = Path(payload["run_dir"]) / ("completion-"+payload["audio_id"]+".json")
    if detailed:
        wavs, sample_rate, completion = _checked_custom_voice(model, spec, completion_path, phases)
        torch.cuda.synchronize()
    else:
        wavs, sample_rate, completion = _checked_custom_voice(model, spec, completion_path)
    synthesis_finished = time.monotonic()
    if progress is not None:
        progress("synth_finished", item_index=batch_index,
                 voice_api_seconds=synthesis_finished-synthesis_started)
    samples = np.asarray(wavs[0], dtype=np.float32)
    if samples.size < sample_rate / 10 or not np.isfinite(samples).all() or float(np.max(np.abs(samples))) < 0.00001:
        raise RuntimeError("Invalid or silent waveform")
    if len(samples) / sample_rate > 35:
        raise RuntimeError("짧은 강의 단위의 음성이 35초를 초과했습니다. 대사를 나눠 다시 준비하세요. 이 음성은 재생하지 않습니다.")
    if Path(payload["cancel_path"]).exists():
        raise RuntimeError("Speech cancelled")
    audio_id = payload["audio_id"]
    if not re.fullmatch(r"[a-f0-9]{64}", audio_id):
        raise ValueError("Invalid audio id")
    folder = root / ".local/audio"
    if payload.get("output_dir") is not None:
        folder = Path(payload["output_dir"]).resolve()
        if not payload.get("tts_benchmark") or not folder.is_relative_to((root / "runs").resolve()):
            raise ValueError("Benchmark audio output must stay within the project runs folder")
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / (audio_id + ".wav")
    if payload.get("tts_benchmark") and (file.exists() or file.with_suffix(".json").exists()):
        raise ValueError("Benchmark output already exists; never replace prior audio")
    validation_finished = time.monotonic()
    sf.write(file, samples, sample_rate, subtype="PCM_16")
    write_finished = time.monotonic()
    with file.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    hash_finished = time.monotonic()
    if progress is not None:
        progress("wav_saved", item_index=batch_index, output_path=str(file), checksum=digest,
                 duration_seconds=len(samples)/sample_rate, sample_rate=sample_rate)
    result = {"audio_id": audio_id, "url": f"/api/audio/{audio_id}", "duration": len(samples) / sample_rate,
              "sample_rate": sample_rate, "checksum": digest, "provider": "qwen3_tts_local", "voice": spec["voice"],
              "revision": spec["revision"], "text_hash": hashlib.sha256(spec["text"].encode()).hexdigest(),
              "generation_settings": {"language":spec["language"],"do_sample":False,"max_new_tokens":spec["max_new_tokens"],"dictionary_version":spec["dictionary_version"],"completion_check_version":spec.get("completion_check_version",2)},
              "effective_tts_generation_settings": effective_settings,
              "completion": completion,
              "elapsed_seconds": time.monotonic() - started, "peak_vram_bytes": torch.cuda.max_memory_allocated(),
              "model_load_seconds": model_load_seconds,
              "model_load_count": int(batch_index == 0) if model_load_count is None else model_load_count,
              "batch_index": batch_index, "batch_mode": "persistent_session" if session_info else "sequential_shared_model", "cache_hit": False,
              "host_timing": {"clock": "worker_monotonic", "version": 1,
                  "origin": "speech_job_entry", "not_gpu_kernel_time": True,
                  "model_load_scope": "before_clip_entry_shared_batch" if shared_model else "within_clip_entry",
                  "voice_api_scope": "full_codec_generation_decode_and_completion_check",
                  "voice_api_started_offset_seconds": synthesis_started - started,
                  "voice_api_finished_offset_seconds": synthesis_finished - started,
                  "voice_api_seconds": synthesis_finished - synthesis_started,
                  "wave_validation_seconds": validation_finished - synthesis_finished,
                  "wave_write_seconds": write_finished - validation_finished,
                  "checksum_seconds": hash_finished - write_finished,
                  "metadata_write_seconds": None,
                  "voice_api_to_audio_duration_ratio": (synthesis_finished - synthesis_started) / (len(samples) / sample_rate)},
              "rms": float(np.sqrt(np.mean(samples**2))), "tier": "T2", "listening_review": "not_run"}
    if session_info:
        result["session_info"] = {key: value for key, value in session_info.items() if not key.startswith("_")}
        result.update({key: session_info[key] for key in ("worker_pid", "process_start_time", "worker_instance_id",
            "model_instance_id", "cumulative_model_load_count", "request_model_load_count")})
        result["host_timing"]["worker_request_to_wave_seconds"] = hash_finished - session_info["_request_started_monotonic"]
        result["host_timing"]["worker_request_to_wave_scope"] = "Request receipt through imports/model loading (if any), synthesis, WAV validation/write and checksum; excludes result metadata write."
        result["host_timing"]["worker_request_to_audio_duration_ratio"] = result["host_timing"]["worker_request_to_wave_seconds"] / result["duration"]
    if detailed:
        from edu_tutor.speech.session_worker import memory_snapshot
        result.update(phase_timings=phases, memory=memory_snapshot(torch), seed=payload.get("seed"),
            deterministic_waveform_guaranteed=False)
    if payload.get("tts_benchmark"):
        result.update(url=None, output_path=str(file), metadata_path=str(file.with_suffix(".json")),
                      wav_cache_bypassed=True, not_attached_to_student_lesson=True)
    file.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (Path(payload["run_dir"]) / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    emit("audio", **result)
    return result
