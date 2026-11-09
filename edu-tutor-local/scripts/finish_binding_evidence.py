"""CPU-only report repair. Production lesson/audio binding is unchanged.

Require the server payload's exact Python fingerprint, the captured lesson's
server fingerprint and a pre-playback speech response for this lesson/step.
Only finite JS-safe integral floats may lose their numeric type in browser JSON.
"""
import hashlib
import json
import math
from datetime import datetime

KEYS = ('id','plan','problem','generation_epoch','source_message_id','speech_allowed','fallback_text')

def bound(value):
    return {key:value.get(key) for key in KEYS}

def fingerprint(value):
    return hashlib.sha256(json.dumps(bound(value), ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()

def equivalent(server, browser, path=''):
    """Return exact or safe integer/float representation differences; fail closed."""
    if type(server) is not type(browser):
        good = (type(server) is float and type(browser) is int and math.isfinite(server)
                and server.is_integer() and abs(server) <= 2**53-1 and server == browser
                and not (server == 0 and math.copysign(1, server) < 0))
        return good, ([{'path':path, 'server':server, 'browser':browser,
            'server_type':'float', 'browser_type':'int'}] if good else [])
    if isinstance(server, dict):
        if server.keys() != browser.keys(): return False, []
        results = [equivalent(server[k], browser[k], path+'/'+k) for k in server]
    elif isinstance(server, list):
        if len(server) != len(browser): return False, []
        results = [equivalent(a,b,path+'/'+str(i)) for i,(a,b) in enumerate(zip(server,browser))]
    else:
        if isinstance(server,float) and not math.isfinite(server): return False, []
        return server == browser, []
    return all(ok for ok,_ in results), [d for _,diffs in results for d in diffs]

def moment(value):
    try: return datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError, AttributeError, TypeError): return None

def binding_evidence(record, server, captured, event, audio_id):
    ident=event.get('lesson_record_id') or event.get('lesson_id')
    step_id=event.get('step_id'); at=moment(event.get('at_iso'))
    source_hash=fingerprint(server)
    good,diffs=equivalent(bound(server),bound(captured))
    checks={'lesson_identity':bool(ident and server.get('id')==captured.get('id')==ident),
        'captured_payload_matches_server':good,
        'captured_server_fingerprint_matches_db':captured.get('speech_binding_fingerprint')==source_hash,
        'pre_playback_bound_speech_response':False}
    candidates=[]
    for response in record.get('responses',[]):
        when=moment(response.get('at'))
        if not at or not when or when>at or response.get('status')!=200: continue
        if response.get('path')!=f'/api/lessons/{ident}/speech': continue
        value=response.get('value')
        if not isinstance(value,dict): continue
        for clip in value.get('steps',[]):
            if not isinstance(clip,dict) or clip.get('audio_id')!=audio_id or clip.get('step_id')!=step_id:continue
            # Do not skip a later mismatching bound response in favour of an older good one.
            candidates.append((when,response,clip,value.get('binding_fingerprint')))
    chosen=max(candidates,key=lambda item:item[0]) if candidates else None
    if chosen:
        _,response,clip,response_hash=chosen
        checks['pre_playback_bound_speech_response']=(clip.get('binding_fingerprint')==response_hash==source_hash)
    return {'pass':all(checks.values()),'checks':checks,'server_binding_fingerprint':source_hash,
        'captured_python_rehash':fingerprint(captured),'representation_differences':diffs,
        'binding_response':({'at':chosen[1]['at'],'path':chosen[1]['path'],
            'audio_id':audio_id,'step_id':step_id,'binding_fingerprint':chosen[2].get('binding_fingerprint')}
            if chosen else None),
        'boundary':'Read-only evidence correction; exact server binding retained. No product state or original event changed.'}
