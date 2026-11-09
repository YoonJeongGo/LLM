"""Read-only collection of fresh student-journey evidence; never runs a model.

Usage: python scripts/finish_collect_journeys.py --version final01
Each invocation creates a new report directory and preserves failed attempts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import html
import os
from pathlib import Path
import re
import sqlite3
import statistics
import hashlib
import array
import io
import math
import sys
import wave

from finish_binding_evidence import binding_evidence

from student_experience_report import (
    digest, explicit_ids, latencies, message_export, playback_records,
    read, write, lesson_at, clip_at, iso,
)


def measured_stats(values):
    valid=[value for value in values if isinstance(value,(int,float)) and not isinstance(value,bool)]
    return {"measured_count":len(valid),"median_ms":statistics.median(valid) if valid else None,
            "max_ms":max(valid) if valid else None}


def assert_frozen_record(record,frozen,version):
    if record.get("version")!=version or record.get("source_hashes")!=frozen["source_hashes"] or record.get("source_unchanged_at_end") is not True:
        raise ValueError("Mixed execution versions: "+str(record.get("id")))


def native_interruptions(record, timing):
    """Prefer actual media pause events, never a timer or narrative assertion."""
    for index, row in enumerate(timing["interruptions"]):
        submitted=row["submission_event"]
        end=min([event["at_ms"] for event in record.get("events",[]) if event.get("type")=="lesson_resumed"
                 and event.get("lesson_record_id")==submitted.get("lesson_record_id") and event["at_ms"]>submitted["at_ms"]]
                +[timing["interruptions"][index+1]["submission_event"]["at_ms"] if index+1<len(timing["interruptions"]) else float("inf")])
        media=submitted.get("media") or {}
        pause=next((event for event in record.get("native_media",[])
                    if event.get("type")=="pause" and event.get("lesson_id")==submitted.get("lesson_record_id")
                     and media.get("media_id") is not None and event.get("media_id")==media["media_id"]
                     and event.get("epoch")==media.get("epoch") and event.get("current_src")==media.get("current_src")
                    and submitted["at_ms"]<=event["at_ms"]<end),None)
        row["native_pause_event"]=pause
        row["old_audio_stopped_ms"]=pause["at_ms"]-submitted["at_ms"] if pause else None
        row["old_audio_stop_evidence"]="native_media_pause_event" if pause else "NOT_MEASURED_native_pause_absent"
    return timing


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def lesson_binding(lesson):
    return fingerprint({key:lesson.get(key) for key in (
        "id","plan","problem","generation_epoch","source_message_id","speech_allowed","fallback_text")})


def board_binding(event, lesson, step, equation_renderings=None, expected_scene=None):
    """Check the actual visible cells/text against the exact lesson plan, not an oracle screenshot."""
    actions=[]
    for unit in lesson.get("plan",{}).get("steps",[]):
        actions.extend(unit.get("board_actions",[]))
        if unit.get("id")==step.get("id"):break
    errors=[]
    visible=event.get("board_content") or []
    if expected_scene is not None:
        expected=expected_scene["elements"]
        actual_ids=[e.get("id") for e in visible]
        if len(actual_ids)!=len(set(actual_ids)) or set(actual_ids)!=set(expected):
            errors.append("missing_or_extra_visible_elements")
    for element in visible:
        possibilities=[a for a in actions if a.get("element_id")==element.get("id") and a.get("type") in {"table","text","code","equation"}]
        action=expected_scene["elements"].get(element.get("id"),{}) if expected_scene is not None else possibilities[-1] if possibilities else {}
        if not action:errors.append("unknown_visible_element:"+str(element.get("id")));continue
        if action["type"]=="table":
            expected=action.get("rows",[])
            actual=[[cell.get("text") for cell in row] for row in element.get("rows",[])]
            def same(value,text):
                if isinstance(value,(int,float)) and not isinstance(value,bool):
                    try:return float(text)==value
                    except (ValueError,TypeError):return False
                return text==("NULL" if value is None else str(value))
            if (len(expected)!=len(actual) or any(len(a)!=len(b) or not all(same(v,t) for v,t in zip(a,b)) for a,b in zip(expected,actual))
                    or action.get("columns")!=element.get("columns")):errors.append("visible_table_values_mismatch:"+element["id"])
            if action.get("cell_ids") is not None and action["cell_ids"]!=[[cell.get("id") for cell in row] for row in element.get("rows",[])]:
                errors.append("visible_table_cell_identity_mismatch:"+element["id"])
        elif action["type"] in {"text","code"}:
            key=action["type"]
            actual=element.get(key)
            if actual is None or action.get(key,"").rstrip("\n")!=actual.rstrip("\n"):errors.append("visible_"+key+"_mismatch:"+element["id"])
        else:
            expected=(equation_renderings or {}).get(action.get("latex"))
            if not expected or element.get("equation_html")!=expected:errors.append("visible_equation_mismatch:"+element["id"])
    if not visible and (expected_scene is None or expected_scene["elements"]):errors.append("visible_board_absent")
    if event.get("caption")!=step.get("speech"):errors.append("caption_script_mismatch")
    return {"pass":not errors,"errors":errors,"board_fingerprint":fingerprint(visible)}


def active_scene(lesson, step_id, progress):
    """Independent reconstruction of the existing action timing/clear contract."""
    elements={};arrows={}
    for step in lesson.get("plan",{}).get("steps",[]):
        actions=step.get("board_actions",[])
        for index,action in enumerate(actions):
            if step.get("id")==step_id:
                timing=action.get("timing") or {"start":index/len(actions),"end":(index+1)/len(actions)}
                if progress<timing["start"] or progress==timing["start"] and timing["end"]>timing["start"]:continue
            kind=action.get("type")
            if kind=="clear":
                target=action.get("target")
                if target=="all":elements={};arrows={}
                else:
                    elements.pop(target,None)
                    arrows={k:v for k,v in arrows.items() if target not in (k,v.get("from_element_id"),v.get("to_element_id"))}
            elif kind=="highlight":continue
            elif kind=="arrow" and not action.get("geometry"):arrows[action["element_id"]]=action
            else:elements[action["element_id"]]=action
        if step.get("id")==step_id:break
    return {"elements":elements,"arrows":arrows}


def arrow_binding(sample,scene):
    actual=sample.get("arrows") or []
    if not isinstance(actual,list):return {"pass":False,"reason":"No arrow identity snapshot"}
    if {a.get("id") for a in actual}!=set(scene["arrows"]):return {"pass":False,"reason":"Missing/extra diagram arrows"}
    stage=sample.get("stage_rect") or {};elements={e["id"]:e.get("rect") for e in sample.get("elements",[])}
    for arrow in actual:
        action=scene["arrows"][arrow["id"]];origin=elements.get(action["from_element_id"]);target=elements.get(action["to_element_id"])
        if not origin or not target or not stage:return {"pass":False,"reason":"Arrow endpoint bounds absent"}
        expected={"x1":origin["x"]+origin["width"]-stage["x"],"y1":origin["y"]+origin["height"]/2-stage["y"],
                  "x2":target["x"]-stage["x"],"y2":target["y"]+target["height"]/2-stage["y"]}
        if any(not isinstance(arrow.get(k),(int,float)) or abs(arrow[k]-v)>4 for k,v in expected.items()):
            return {"pass":False,"reason":"Arrow does not connect its actual source and target bounds"}
    return {"pass":True,"checked_arrows":len(actual),"tolerance_css_px":4}


def scene_binding_checks(record,lesson_map,played):
    """Board correctness is an independent requirement, not first-audio timing.

    Ignore samples within 75ms of an action boundary because the UI's audio-clock
    rendering tick can follow the media clock. Record those exclusions explicitly.
    Every played step still needs a stable late snapshot of its complete scene.
    """
    checks=[]
    for ident,step_id in sorted({(p["lesson_id"],p["step_id"]) for p in played if p["valid_explanation_by_record_linkage"]}):
        lesson=lesson_map.get(ident,{})
        step=next((s for s in lesson.get("plan",{}).get("steps",[]) if s.get("id")==step_id),{})
        audios=[p for p in played if p["lesson_id"]==ident and p["step_id"]==step_id and p["valid_explanation_by_record_linkage"]]
        final=active_scene(lesson,step_id,1)
        samples=[]
        for sample in record.get("scene_samples",[]):
            media=sample.get("media") or {}
            if (sample.get("lesson_record_id")!=ident or sample.get("step_id")!=step_id or not any(
                    media.get("media_id")==p["event"].get("media",{}).get("media_id") and media.get("epoch")==p["event"].get("epoch")
                    for p in audios)):continue
            time,duration=media.get("currentTime"),media.get("duration")
            if not isinstance(time,(int,float)) or not isinstance(duration,(int,float)) or duration<=0:continue
            progress=min(1,max(0,time/duration));scene=active_scene(lesson,step_id,progress)
            before=active_scene(lesson,step_id,max(0,(time-.075)/duration));after=active_scene(lesson,step_id,min(1,(time+.075)/duration))
            stable=before==after
            if not stable:
                samples.append({"status":"SKIPPED_ACTION_BOUNDARY","at_ms":sample.get("at_ms"),"progress":progress});continue
            board=board_binding(sample,lesson,step,record.get("equation_renderings"),scene)
            pointer=pointer_binding(sample,step) if step.get("gesture",{}).get("target_element_id") in scene["elements"] else {"status":"TARGET_NOT_YET_VISIBLE"}
            arrows=arrow_binding(sample,scene)
            valid=(sample.get("dom_lesson_record_id")==ident and sample.get("dom_step_id")==step_id and board["pass"] and arrows["pass"]
                   and pointer["status"] in {"PASS","NOT_APPLICABLE","TARGET_NOT_YET_VISIBLE"})
            samples.append({"status":"PASS" if valid else "FAIL","at_ms":sample.get("at_ms"),"progress":progress,
                "complete_late_scene":progress>=.8 and scene==final and bool(final["elements"]),
                "board":board,"pointer":pointer,"arrows":arrows})
        stable=[s for s in samples if s["status"]!="SKIPPED_ACTION_BOUNDARY"]
        late=[s for s in stable if s.get("complete_late_scene")]
        pointer_required=step.get("gesture",{}).get("kind") in {"point","write"}
        passed=bool(stable and late and all(s["status"]=="PASS" for s in stable)
                    and (not pointer_required or any(s["pointer"]["status"]=="PASS" for s in late)))
        checks.append({"lesson_id":ident,"step_id":step_id,"pass":passed,"samples":samples,
            "stable_sample_count":len(stable),"complete_late_sample_count":len(late),"action_boundary_tolerance_seconds":.075})
    return checks


def pointer_binding(event, step):
    gesture=step.get("gesture") or {}
    if gesture.get("kind") not in {"point","write"}:return {"status":"NOT_APPLICABLE"}
    selected=next((cell for cell in event.get("cells",[]) if cell.get("selected")),None)
    target=selected or next((element for element in event.get("elements",[]) if element.get("id")==gesture.get("target_element_id")),None)
    point=event.get("pointer_end");rect=(target or {}).get("rect")
    equation=not selected and ((target or {}).get("equation_html") is not None or any(
        action.get("type")=="equation" and action.get("element_id")==gesture.get("target_element_id")
        for action in step.get("board_actions",[])))
    if equation:
        glyphs=(target or {}).get("equation_glyph_rects")
        measured=isinstance(glyphs,list) and bool(glyphs)
        good=bool(point and measured and any(isinstance(glyph,dict)
            and all(isinstance(glyph.get(key),(int,float)) and math.isfinite(glyph[key]) for key in ("x","y","width","height"))
            and glyph["width"]>0 and glyph["height"]>0
            and glyph["x"]-4<=point["x"]<=glyph["x"]+glyph["width"]+4
            and glyph["y"]-4<=point["y"]<=glyph["y"]+glyph["height"]+4 for glyph in glyphs))
        return {"status":"PASS" if good else "FAIL" if measured else "NOT_MEASURED",
            "reason":"Pointer must intersect an actual rendered equation glyph; wrapper bounds are insufficient",
            "target_id":(target or {}).get("id"),"pointer_end":point,"target_rect":rect,
            "equation_glyph_rects":glyphs,"tolerance_css_px":4}
    good=bool(point and rect and rect["x"]-4<=point["x"]<=rect["x"]+rect["width"]+4
              and rect["y"]-4<=point["y"]<=rect["y"]+rect["height"]+4)
    return {"status":"PASS" if good else "FAIL","target_id":(target or {}).get("id"),"pointer_end":point,"target_rect":rect,"tolerance_css_px":4}


def pcm_non_silent(data):
    with wave.open(io.BytesIO(data),"rb") as stream:
        if stream.getnchannels()!=1 or stream.getsampwidth()!=2 or stream.getcomptype()!="NONE":return False
        raw=stream.readframes(stream.getnframes())
        if len(raw)!=stream.getnframes()*2 or not .1<=stream.getnframes()/stream.getframerate()<=35:return False
    values=array.array("h",raw)
    if sys.byteorder!="little":values.byteswap()
    return bool(values and max(abs(v) for v in values)>=2 and math.sqrt(sum(v*v for v in values)/len(values))/32768>=.00001)


def validate_playbacks(root,record,lesson_map,played,audio_exports):
    sys.path.insert(0,str(root/"src"))
    from edu_tutor.speech.provider import cached_audio
    for entry in played:
        event=entry["event"];media=event.get("media") or {}
        lesson,_=lesson_at(record,lesson_map,event)
        step=next((s for s in lesson.get("plan",{}).get("steps",[]) if s.get("id")==entry["step_id"]),{})
        clip,_=clip_at(record,lesson_map,event,entry["audio_id"])
        exported=audio_exports.get(entry["audio_id"],{});meta=exported.get("generation_metadata",{})
        voice=meta.get("voice","")
        if meta.get("provider")=="windows_sapi_local":voice="windows_sapi:"+voice
        checked=cached_audio(step.get("speech",""),root=root,voice=voice)
        native=next((item for item in record.get("native_media",[]) if item.get("type")=="playing"
            and item.get("lesson_id")==entry["lesson_id"] and item.get("step_id")==entry["step_id"]
            and item.get("media_id") is not None and item.get("media_id")==media.get("media_id")
            and item.get("epoch")==event.get("epoch")==media.get("epoch")
            and item.get("current_src")==media.get("current_src") and abs(item["at_ms"]-event["at_ms"])<100),None)
        blob=record.get("blob_bytes",{}).get(media.get("current_src"),{})
        entry["native_playing_event"]=native
        entry["board_binding"]=board_binding(event,lesson,step,record.get("equation_renderings"))
        entry["pointer_binding"]=pointer_binding(event,step)
        entry["lesson_binding_evidence_v2"] = binding_evidence(record, lesson_map.get(entry["lesson_id"], {}), lesson, event, entry["audio_id"])
        validations={"provider_cache_and_script":checked.get("hit") is True and checked.get("audio",{}).get("audio_id")==entry["audio_id"],
            "lesson_board_script_fingerprint":entry["lesson_binding_evidence_v2"]["pass"],
            "file_hash":exported.get("metadata_checksum_matches_wav") is True,
            "duration":exported.get("metadata_duration_matches_wav") is True,
            "actual_browser_blob_hash":bool(blob.get("sha256") and blob.get("sha256")==exported.get("wav_sha256")),
            "native_playing_identity":native is not None,
            "actual_dom_lesson_step":event.get("dom_lesson_record_id")==entry["lesson_id"] and event.get("dom_step_id")==entry["step_id"],
            "audible_media_settings":bool(native and not native.get("muted") and native.get("volume",0)>0 and native.get("playbackRate")==1),
            "caption_script":event.get("caption")==step.get("speech")}
        try:validations["non_silent_complete_pcm"]=bool(checked.get("hit") and pcm_non_silent(checked["wave_bytes"]))
        except (OSError,ValueError,KeyError,wave.Error,EOFError,ZeroDivisionError):validations["non_silent_complete_pcm"]=False
        entry["validation"]=validations
        entry["valid_explanation_by_record_linkage"]=entry["valid_explanation_by_record_linkage"] and all(validations.values())
        if meta.get("provider")=="windows_sapi_local":
            entry["tts_load_regime"]="cached_system_voice_clip" if entry.get("tts_clip_cache_hit") else "local_system_voice_no_neural_model_load"
    return played


def bound_latencies(record,played,messages,lesson_map):
    result=latencies(record,played,messages)
    for question_index,row in enumerate(result["question_to_first_valid_explanation"]):
        next_index=result["question_to_first_valid_explanation"][question_index+1]["event_index"] if question_index+1<len(result["question_to_first_valid_explanation"]) else len(record.get("events",[]))
        answer=next((m for m in messages if row.get("request_id") and m.get("role")=="assistant" and m.get("request_id")==row["request_id"]),{})
        audio=next((p for p in played if p["valid_explanation_by_record_linkage"] and row["event_index"]<p["event_index"]<next_index
            and lesson_map.get(p["lesson_id"],{}).get("source_message_id")==answer.get("id") and answer.get("id")
            and bool(p["event"].get("supplement"))==(row["input_kind"]=="followup")),None)
        row.update(status="MEASURED" if audio else "NO_VALID_EXPLANATION_AUDIO_RECORDED",
            first_valid_explanation_ms=audio["event"]["at_ms"]-row["submission_event"]["at_ms"] if audio else None,
            audio_id=audio.get("audio_id") if audio else None,
            linkage="request_id -> assistant message -> lesson.source_message_id -> step/epoch/media/blob/PCM")
    result=native_interruptions(record,result)
    for row in result["interruptions"]:
        question=next((q for q in result["question_to_first_valid_explanation"] if q["input_kind"]=="followup" and q["submission_event"]["at_ms"]>=row["submission_event"]["at_ms"]),None)
        row["supplement_started_ms"]=(question["submission_event"]["at_ms"]+question["first_valid_explanation_ms"]-row["submission_event"]["at_ms"]) if question and question["first_valid_explanation_ms"] is not None else None
        row["supplement_status"]="MEASURED" if row["supplement_started_ms"] is not None else "NOT_RECORDED"
    return result


def restoration_checks(record):
    checks=[]
    events=record.get("events",[])
    for interrupted in (e for e in events if e.get("type")=="interruption_submitted"):
        ident=interrupted.get("lesson_record_id");old=interrupted.get("media") or {}
        resumed=next((e for e in events if e.get("type")=="lesson_resumed" and e.get("lesson_record_id")==ident and e["at_ms"]>interrupted["at_ms"]),None)
        playing=next((e for e in events if resumed and e.get("type")=="audio_playing" and e.get("lesson_record_id")==ident and e["at_ms"]>resumed["at_ms"]),None)
        media=(playing or {}).get("media") or {}
        late=[e for e in record.get("native_media",[]) if e.get("type")=="playing" and e["at_ms"]>interrupted["at_ms"]
              and e.get("media_id")==old.get("media_id") and old.get("media_id") is not None]
        values={"original_lesson":bool(playing),"original_step":bool(playing and playing.get("step_id")==interrupted.get("step_id")),
            "board_fingerprint_restored":bool(playing and interrupted.get("board_content") and fingerprint(playing.get("board_content"))==fingerprint(interrupted["board_content"])),
            "audio_position_restored":bool(playing and isinstance(media.get("currentTime"),(int,float)) and isinstance(old.get("currentTime"),(int,float)) and abs(media["currentTime"]-old["currentTime"])<=.35),
            "new_audio_element":bool(playing and media.get("media_id") is not None and media.get("media_id")!=old.get("media_id")),
            "selected_cell_restored":bool(playing and interrupted.get("selected_cell_id") and any(c.get("selected") and c.get("id")==interrupted["selected_cell_id"] for c in playing.get("cells",[]))),
            "cancelled_audio_never_replayed":not late}
        checks.append({"pass":all(values.values()),"checks":values,"interruption_event":interrupted,"resumed_playing_event":playing,"cancelled_late_playing":late,"audio_position_tolerance_seconds":.35})
    return checks


def model_evidence(record,messages,ledger):
    """Request-linked reservations, including repair attempts, are distinct from browser submissions."""
    evidence=[]
    for answer in (m for m in messages if m.get("role")=="assistant"):
        response=next((r for r in record.get("responses",[]) if r.get("method")=="POST"
            and isinstance(r.get("value"),dict) and r["value"].get("request_id")==answer.get("request_id") and answer.get("request_id")),{})
        job_id=response.get("value",{}).get("job_id")
        rows=[r for r in ledger.get("requests",[]) if job_id and r.get("job_id")==job_id and r.get("kind") in {"text","text_batch"}]
        snapshot=answer.get("generation_snapshot") or {}
        passed=bool(rows and all(r.get("status")=="completed" and r.get("execution_allowance_id")==record.get("before",{}).get("budget",{}).get("accounting_scope") for r in rows)
            and snapshot.get("source")=="worker_metadata" and snapshot.get("revision") and snapshot.get("output_tokens",0)>0 and answer.get("raw_model_response"))
        evidence.append({"message_id":answer.get("id"),"request_id":answer.get("request_id"),"job_id":job_id,
            "pass":passed,"reservations":rows,"reservation_count":len(rows),"recorded_model_attempt_count":len(answer.get("model_attempts") or []),
            "snapshot":snapshot,"worker_identity_recorded":bool(snapshot.get("worker_pid")),
            "identity_boundary":"A missing per-request PID is not evidence of resident reuse; actual response requires request-linked completed model reservations and worker token/revision metadata."})
    return evidence


def selected_row_checks(record,lessons,messages,spec):
    if not spec.get("followup"):return {"status":"NOT_APPLICABLE"}
    interrupted=next((e for e in record.get("events",[]) if e.get("type")=="interruption_submitted"),{})
    selected=next((c for c in interrupted.get("cells",[]) if c.get("id")==interrupted.get("selected_cell_id") and c.get("selected")),{})
    follow=spec["followup"]
    source_row=False
    for element in interrupted.get("board_content",[]):
        if follow["column"] not in element.get("columns",[]):continue
        ri=follow["row_index"];ci=element["columns"].index(follow["column"])
        rows=element.get("rows",[])
        if len(rows)>ri and len(rows[ri])>ci and rows[ri][ci].get("id")==selected.get("id") and rows[ri][ci].get("text")==str(follow["value"]):source_row=True
    contexts=[m for m in messages if m.get("role")=="assistant" and ((m.get("lesson_context") or {}).get("selected_cell") or {}).get("cell_id")==selected.get("id") and selected.get("id")]
    context_ids={m["id"] for m in contexts}
    highlighted=any(selected.get("id") in action.get("cell_ids",[]) for lesson in lessons if lesson.get("source_message_id") in context_ids
        for step in (lesson.get("plan") or {}).get("steps",[]) for action in step.get("board_actions",[]) if action.get("type")=="highlight")
    return {"status":"PASS" if source_row and contexts and highlighted else "FAIL","selected_cell_matches_requested_nonempty_row":source_row,
        "supplement_message_retained_selected_cell":bool(contexts),"supplement_plan_highlights_selected_cell":highlighted,
        "semantic_explanation_review":"H_PENDING"}


def transition_measurements(record,lesson_map,played):
    rows=[]
    valid=[p for p in played if p["valid_explanation_by_record_linkage"]]
    for ident,lesson in lesson_map.items():
        if not any(p["lesson_id"]==ident for p in played):continue
        steps=lesson.get("plan",{}).get("steps",[])
        for before,after in zip(steps,steps[1:]):
            ended=next((e for e in record.get("native_media",[]) if e.get("type")=="ended" and e.get("lesson_id")==ident and e.get("step_id")==before["id"]),None)
            following=next((p for p in valid if ended and p["lesson_id"]==ident and p["step_id"]==after["id"] and p["event"]["at_ms"]>=ended["at_ms"]),None)
            rows.append({"lesson_id":ident,"from_step":before["id"],"to_step":after["id"],"status":"MEASURED" if following else "NOT_MEASURED",
                "gap_ms":following["event"]["at_ms"]-ended["at_ms"] if following else None,"clock":"same-browser native ended to bound native playing"})
    return rows


def completed_steps(record,lesson_map,played):
    rows=[]
    for ident,lesson in lesson_map.items():
        if not any(p["lesson_id"]==ident for p in played):continue
        for step in lesson.get("plan",{}).get("steps",[]):
            candidates=[p for p in played if p["lesson_id"]==ident and p["step_id"]==step["id"] and p["valid_explanation_by_record_linkage"]]
            ended=next((e for e in record.get("native_media",[]) if e.get("type")=="ended" and e.get("lesson_id")==ident and e.get("step_id")==step["id"] and any(
                e.get("media_id")==p["event"].get("media",{}).get("media_id") and e.get("epoch")==p["event"].get("epoch") and e["at_ms"]>p["event"]["at_ms"] for p in candidates)),None)
            rows.append({"lesson_id":ident,"step_id":step["id"],"pass":ended is not None,"native_ended":ended})
    return rows


def write_gallery(report, cases, audio_exports):
    """Local review index populated from actual records, including failures."""
    preferred=["J01","J03","J04","J06","J07"]
    selected=[case for ident in preferred for case in cases if case["id"]==ident]
    esc=lambda value:html.escape(str(value),quote=True)
    href=lambda path:esc(os.path.relpath(path,report).replace("\\","/"))
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>실제 수업 증거 검토</title><style>body{font:16px/1.6 system-ui;margin:24px auto;padding:0 16px;max-width:1100px;background:#f7f8f5;color:#24332c}section{background:white;border:1px solid #ddd;padding:18px;margin:22px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%;border:1px solid #ddd}audio{max-width:100%}summary{cursor:pointer;font-weight:600}.pending{color:#865400}h1{font-size:1.7rem}</style>',
        '<h1>실제 수업 증거 검토</h1><p class="pending">H_PENDING · 사람이 교육 정확도·발음·사용성을 검토하지 않았습니다. 실제 실행 기록을 연결한 검토 화면이며, 실패와 미측정을 성공으로 바꾸지 않습니다.</p>',
        '<p>직접 작성한 개발 검증 질문·사진입니다. 실제 학생 업로드와 독립 final80 평가가 아닙니다. <a href="summary.json">전체 수치·누락 분모</a></p>']
    parts.append('<h2>모든 실행 결과</h2><ul>')
    for case in cases:
        parts.append('<li><a href="'+esc(case['id']+'.json')+'">'+esc(case['id'])+'</a> · '
            +esc(case['status'])+' · '+esc(case.get('failure') or '기술적 실행 기록이며 교육 검토는 대기 중')+'</li>')
    parts.append('</ul><p>아래는 대표 화면입니다. 나머지 수업의 질문·화면·음성 경로도 위 전체 기록에서 확인할 수 있습니다.</p>')
    if not selected:parts.append('<p>이 버전에는 선택된 대표 수업의 실제 실행 기록이 없습니다.</p>')
    for case in selected:
        parts.append('<section><h2>'+esc(case["id"])+': '+esc(case["status"])+'</h2><p>'+esc(case["spec"].get("question","사진 문제"))+'</p>')
        if case.get("failure"):parts.append('<p class="pending">실패: '+esc(case["failure"])+'</p>')
        parts.append('<p><a href="'+esc(case["id"]+'.json')+'">전체 질문·답변·계획·측정 JSON</a></p>')
        for answer in case["answers"]:
            if answer.get("role")!="assistant":continue
            parts.append('<details><summary>실제 원시 모델 답변</summary><pre>'+esc(answer.get("raw_model",{}).get("response"))+'</pre></details>')
            parts.append('<details open><summary>앱이 표시한 답변</summary><pre>'+esc(answer.get("app_display",{}).get("content"))+'</pre></details>')
        if case.get("photo"):
            parts.append('<details><summary>실제 사진 인식 후보 · 수정 전</summary><pre>'+esc(json.dumps(case["photo"],ensure_ascii=False,indent=2))+'</pre></details>')
        seen=set()
        for entry in case["playback"]:
            ident=entry.get("audio_id")
            if ident in seen:continue
            seen.add(ident)
            audio=audio_exports.get(ident,{})
            parts.append('<h3>실제 재생 대사 · '+esc(entry.get("step_id"))+'</h3><p>'+esc(entry.get("speech"))+'</p>')
            if audio.get("status")=="COPIED":
                parts.append('<audio controls preload="metadata" src="'+href(audio["wav"])+'"></audio><p><a href="'+href(audio["json"])+'">음성 설정·합성 기록</a></p>')
            else:parts.append('<p>연결된 실제 WAV를 확인하지 못했습니다.</p>')
        if not seen:parts.append('<p>실제 설명 음성 재생 기록 없음.</p>')
        parts.append('<details><summary>판서 계획·단계별 대사</summary><pre>'+esc(json.dumps(case["lessons"],ensure_ascii=False,indent=2))+'</pre></details>')
        parts.append('<details open><summary>실제 브라우저 측정</summary><pre>'+esc(json.dumps(case["timings"],ensure_ascii=False,indent=2))+'</pre></details>')
        screens=case["screenshots"]
        important=[item for item in screens if any(label in Path(item["path"]).stem for label in ("interruption-before","interruption-stopped","supplement-playing","original-resumed","completed","failure"))]
        if not important:important=screens[-2:]
        for item in important[:5]:parts.append('<figure><figcaption>'+esc(Path(item["path"]).name)+'</figcaption><a href="'+href(item["path"])+'"><img loading="lazy" src="'+href(item["path"])+'"></a></figure>')
        parts.append('</section>')
    parts.append('</html>')
    (report/'gallery.html').write_text('\n'.join(parts),encoding='utf-8')


def collect(root, version):
    base=root/"runs/finish-v2/20261029/student"
    source=base/version
    frozen=read(source/"execution-version.json")
    input_path=source/"journeys.json"
    if not input_path.is_file():
        input_path=base/"journeys.json"
    specs=read(input_path)
    if frozen["input_sha256"]!=digest(input_path):
        raise ValueError("Prepared questions changed after version freeze")
    report=source/("report-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    report.mkdir(exist_ok=False)
    audio_exports={}
    exported_cases=[]
    cases=[]
    questions=[]
    interruptions=[]
    gaps=[]
    ledger=read(root/"runs/phase2/current/resource-budget.json")
    with sqlite3.connect((root/".local/tutor.sqlite3").as_uri()+"?mode=ro",uri=True,timeout=15) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for spec in specs["journeys"]:
            path=source/spec["id"]/"actual.json"
            expected_count=2 if spec.get("followup") else 1
            if not path.is_file():
                cases.append({"id":spec["id"],"status":"NOT_RUN","human_review":"H_PENDING"})
                questions.extend({"case":spec["id"],"input_kind":"followup" if i else spec["kind"],
                                  "status":"NOT_RUN","first_valid_explanation_ms":None}
                                 for i in range(expected_count))
                continue
            record=read(path)
            if record.get("status")=="RUNNING" or not record.get("completed_at"):
                raise ValueError("Do not collect an active or incomplete browser attempt: "+spec["id"])
            assert_frozen_record(record,frozen,version)
            ids,job_ids=explicit_ids(record)
            records={}
            for table in ("messages","lessons"):
                records[table]=[]
                for ident in ids[table]:
                    found=db.execute(f"SELECT payload FROM {table} WHERE id=?",(ident,)).fetchone()
                    if found:records[table].append(json.loads(found[0]))
            lesson_map={item["id"]:item for item in records["lessons"]}
            # Explicit lesson references only; do not sweep unrelated session rows.
            for lesson in lesson_map.values():
                source_id=lesson.get("source_message_id")
                if source_id and not any(m.get("id")==source_id for m in records["messages"]):
                    found=db.execute("SELECT payload FROM messages WHERE id=?",(source_id,)).fetchone()
                    if found:records["messages"].append(json.loads(found[0]))
            played=playback_records(root,record,lesson_map,report/"audio",audio_exports)
            played=validate_playbacks(root,record,lesson_map,played,audio_exports)
            actual_models=model_evidence(record,records["messages"],ledger)
            verified_sources={item["message_id"] for item in actual_models if item["pass"]}
            for entry in played:
                entry["validation"]["actual_model_request_reservation"]=lesson_map.get(entry["lesson_id"],{}).get("source_message_id") in verified_sources
                entry["valid_explanation_by_record_linkage"]=entry["valid_explanation_by_record_linkage"] and entry["validation"]["actual_model_request_reservation"]
            timing=bound_latencies(record,played,records["messages"],lesson_map)
            timing["stage_gaps"]=transition_measurements(record,lesson_map,played)
            restored=restoration_checks(record)
            completed=completed_steps(record,lesson_map,played)
            scene_checks=scene_binding_checks(record,lesson_map,played)
            row_checks=selected_row_checks(record,records["lessons"],records["messages"],spec)
            evidence_requirements={"valid_bound_playback":bool(played) and all(p["valid_explanation_by_record_linkage"] for p in played),
                "board_values_clears_diagram_and_pointer_during_playback":bool(scene_checks) and all(s["pass"] for s in scene_checks),
                "browser_launch_not_muted":record.get("browser_launch",{}).get("no_browser_mute_flag") is True
                    and "--mute-audio" not in record.get("browser_launch",{}).get("actual",{}).get("argv",["--mute-audio"]),
                "restoration":not spec.get("followup") or bool(restored) and all(c["pass"] for c in restored),
                "selected_row_context":row_checks["status"] in {"PASS","NOT_APPLICABLE"},
                "all_steps_naturally_ended":bool(completed) and all(c["pass"] for c in completed),
                "no_browser_or_cleanup_errors":not record.get("errors") and not record.get("blocked_requests")}
            collected_status=record["status"]
            if collected_status.startswith("COMPLETED") and not all(evidence_requirements.values()):collected_status="COMPLETED_WITH_EVIDENCE_FAILURES"
            case_reservations=[r for r in ledger.get("requests",[]) if r.get("job_id") in job_ids]
            safe_stop=None
            if spec.get("must_not_invent"):
                safe_stop={"missing_condition_reported":bool((record.get("photo") or {}).get("missing_conditions")),
                    "no_text_or_speech_reservations":not any(r.get("kind") in {"text","text_batch","speech","speech_batch"} for r in case_reservations),
                    "no_explanation_played":not played,
                    "explicit_block":(record.get("safe_stop_response") or {}).get("status") in {409,"UI_DISABLED"}}
                if not all(safe_stop.values()):collected_status="FAILED_MISSING_CONDITION_SAFETY_EVIDENCE"
            for row in timing["question_to_first_valid_explanation"]:
                row["case"]=spec["id"]
                # Retain explicit cold/warm worker counters; never infer warm from
                # browser order, a shorter wall time, or the prior case's state.
                meta=row.get("text_model_generation") or {}
                row["text_worker_evidence"]={k:meta.get(k) for k in (
                    "worker_pid","model_instance_id","model_load_count","model_load_seconds","generation_seconds")}
            current=timing["question_to_first_valid_explanation"]
            if len(current)>expected_count:raise ValueError("Unexpected duplicate question events: "+spec["id"])
            for index in range(len(current),expected_count):
                current.append({"case":spec["id"],"input_kind":"followup" if index else spec["kind"],
                    "question_text":spec.get("followup",{}).get("question") if index else spec.get("question"),
                    "status":"NO_VALID_EXPLANATION_AUDIO_RECORDED", "first_valid_explanation_ms":None,
                    "reason":record.get("failure") or record.get("status")})
            questions.extend(current)
            interruptions.extend({"case":spec["id"],**row} for row in timing["interruptions"])
            gaps.extend({"case":spec["id"],**row} for row in timing["stage_gaps"])
            if spec["kind"]=="photo":
                first=next((entry["event"]["at_ms"] for entry in played if entry["valid_explanation_by_record_linkage"]),None)
                timing["photo"]={"recognition_ms":record.get("ocr_candidate_at_ms",0)-record.get("ocr_submit_at_ms",0)
                    if record.get("ocr_candidate_at_ms") is not None and record.get("ocr_submit_at_ms") is not None else None,
                    "upload_to_first_valid_explanation_ms":first-record["photo_upload_at_ms"]
                    if first is not None and record.get("photo_upload_at_ms") is not None else None,
                    "boundary":"Includes OCR and automated authored-source confirmation time; this is not a human review duration."}
            exported_case={"id":spec["id"],"status":collected_status,"harness_status":record["status"],"failure":record.get("failure"),
                "actual_json":str(path),"actual_sha256":digest(path),"spec":spec,"requirements":record.get("requirements"),
                "quality":record.get("quality"),"photo":record.get("photo"),"photo_check":record.get("photo_check"),
                "safe_stop_response":record.get("safe_stop_response"),"source_unchanged_at_end":record.get("source_unchanged_at_end"),
                "answers":[message_export(m) for m in records["messages"]],"lessons":records["lessons"],
                "playback":played,"timings":timing,"screenshots":[{"path":str(root/name),"sha256":digest(root/name)}
                    for name in record.get("screenshots",[]) if (root/name).is_file()],
                "samples":record.get("samples"),"human_review":"H_PENDING","evidence_requirements":evidence_requirements,
                "scene_binding_checks":scene_checks,"scene_samples":record.get("scene_samples"),"browser_launch":record.get("browser_launch"),
                "restoration_checks":restored,"completed_steps":completed,"selected_row_checks":row_checks,"actual_model_evidence":actual_models,
                "case_reservations":case_reservations,"missing_condition_safety":safe_stop,
                "source_fidelity_human_review":"H_PENDING" if spec.get("must_not_invent") else None}
            write(report/(spec["id"]+".json"),exported_case)
            exported_cases.append(exported_case)
            cases.append({"id":spec["id"],"status":collected_status,"failure":record.get("failure"),
                          "evidence":str(report/(spec["id"]+".json")),"requirements":record.get("requirements")})
    summary={"version":version,"human_review":"H_PENDING","readiness":"NOT_READY",
        "provenance":specs["provenance"],"frozen_execution":frozen,"cases":cases,"question_events":questions,
        "interruptions":interruptions,"stage_gaps":gaps,"audio":list(audio_exports.values()),
        "latency_denominator":specs["provenance"]["planned_question_events"],
        "question_to_audio":measured_stats(q.get("first_valid_explanation_ms") for q in questions),
        "interrupt_to_native_pause":measured_stats(q.get("old_audio_stopped_ms") for q in interruptions),
        "interrupt_to_supplement":measured_stats(q.get("supplement_started_ms") for q in interruptions),
        "stage_gap":measured_stats(q.get("gap_ms") for q in gaps),
         "stage_gap_denominator":len(gaps),
         "question_to_audio_by_input_and_text_load_regime":{kind+"/"+regime:measured_stats(q.get("first_valid_explanation_ms") for q in questions if q.get("input_kind")==kind and q.get("text_model_load_regime","NOT_MEASURED")==regime)
             for kind,regime in sorted({(q.get("input_kind","unknown"),q.get("text_model_load_regime","NOT_MEASURED")) for q in questions})},
        "interpretation":"Measured latency statistics exclude missing measurements but retain every planned question in the denominator. Missing-condition safe-stop is not a successful explanation. No human accuracy or listening verdict is inferred."}
    write(report/"summary.json",summary)
    write_gallery(report,exported_cases,audio_exports)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--version",required=True)
    args=parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}",args.version):parser.error("Invalid version")
    print(collect(Path(__file__).resolve().parents[1],args.version))
