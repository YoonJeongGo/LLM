"""Append final read-only screenshot and preservation receipts, no generation."""
from pathlib import Path
import shutil
import collect_journeys as collector
BASE=Path(__file__).resolve().parent;OUT=BASE/'final-v021-r3-combined'
read,write=collector.read,collector.write
backup=OUT/'before-final-readonly-reviews';backup.mkdir(exist_ok=False)
for name in ['summary.json','compact-results.json','gallery.html','J07.json']:shutil.copy2(OUT/name,backup/name)
summary=read(OUT/'summary.json');compact=read(OUT/'compact-results.json');j07=read(OUT/'J07.json')
receipt=BASE/'saved-J07-hydrated-screen/result.json';proof=read(receipt)
assert proof['status']=='SAVED_J07_HYDRATED_SCREEN_CONFIRMED_NO_GENERATION'
assert proof['hydrated_fields_match_saved_revision'] and proof['solve_disabled'] and proof['mutations']==0
j07['original_safe_stop_screenshot_status']='NOT_VALID_FOR_POST_OCR_SCREEN: capture preceded UI hydration; retained unchanged'
j07['read_only_followup_screen']={'receipt':str(receipt),'status':proof['status'],'revision':proof['saved_photo']['revision'],
    'scope':'Same saved photo read after original run; 0 models/TTS/OCR/mutations. Not a rerun or new latency sample.'}
for name in ['hydrated-missing-condition.png','hydrated-fields-and-disabled-solve.png']:
    path=receipt.parent/name;j07['screenshots'].append({'path':str(path),'sha256':collector.digest(path),'provenance':'Read-only follow-up hydrated-screen proof'})
write(OUT/'J07.json',j07)
for target in [summary,compact]:
    target['same_product_build_proof']['root_full_153_file_post_run_receipt']=str(BASE.parent/'final-preservation-review.json')
summary['read_only_followup_J07_screen']=j07['read_only_followup_screen']
summary['remaining_scene_and_lifecycle_review']=str(BASE/'evidence-agent-final-journey-review.json')
for row in compact['cases']:
    if row['id']=='J07':row['read_only_followup_screen']=j07['read_only_followup_screen'];row['original_safe_stop_screenshot_status']=j07['original_safe_stop_screenshot_status']
write(OUT/'summary.json',summary);write(OUT/'compact-results.json',compact)
proof=read(OUT/'same-product-build-proof.json');proof['root_full_153_file_post_run_receipt']=str(BASE.parent/'final-preservation-review.json');write(OUT/'same-product-build-proof.json',proof)
cases=[read(OUT/(f'J{i:02d}.json')) for i in range(1,9)]
collector.write_gallery(OUT,cases,{a['audio_id']:a for a in summary['audio']})
print('PASS: original J07 screenshot limitation and hydrated read-only proof linked; final preservation review linked')
