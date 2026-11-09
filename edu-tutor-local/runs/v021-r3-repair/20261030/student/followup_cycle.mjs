// Pure harness evidence helpers. No browser/API/model calls.
export function questionPlan(spec, {repeatCase = null, controlled = false} = {}) {
  const rows = [{ordinal: 1, kind: 'initial', cohort: 'primary', question: spec.question}];
  if (!controlled && spec.followup) rows.push({ordinal: 2, kind: 'followup', cohort: 'primary', question: spec.followup.question});
  if (spec.cancel_question) rows.unshift({ordinal: 0, kind: 'deliberate_cancel', cohort: 'primary', question: spec.cancel_question});
  if (repeatCase === spec.id) {
    if (controlled || !spec.followup) throw Error('Repeated interruption requires an ordinary followup journey');
    rows.push({ordinal: 3, kind: 'repeat_followup', cohort: 'repeat_stability_only', question: spec.followup.question,
      start_condition: 'First supplement naturally finished and original nonempty board/cell/audio position restored'});
  }
  return rows;
}

export function cycleEvidence({events, nativeMedia, originalId, supplement}) {
  const submitted = events.find(e => e.type === 'interruption_submitted' && e.lesson_record_id === originalId);
  const resumed = events.find(e => submitted && e.type === 'lesson_resumed' && e.lesson_record_id === originalId && e.at_ms > submitted.at_ms);
  const playing = events.find(e => resumed && e.type === 'audio_playing' && e.lesson_record_id === originalId && e.at_ms > resumed.at_ms);
  const before = submitted?.media || {}, after = playing?.media || {};
  const oldPause = nativeMedia.find(e => submitted && e.type === 'pause' && e.lesson_id === originalId && e.media_id === before.media_id
    && e.epoch === before.epoch && e.current_src === before.current_src && e.at_ms >= submitted.at_ms && (!resumed || e.at_ms < resumed.at_ms));
  const endedSteps = (supplement?.plan?.steps || []).map(step => ({step_id: step.id, native_ended: nativeMedia.find(e =>
    submitted && resumed && e.type === 'ended' && e.lesson_id === supplement.id && e.step_id === step.id
    && e.at_ms > submitted.at_ms && e.at_ms < resumed.at_ms)}));
  const checks = {
    original_step_restored: !!playing && playing.step_id === submitted?.step_id,
    nonempty_board_restored: !!submitted?.board_content?.length && JSON.stringify(playing?.board_content) === JSON.stringify(submitted.board_content),
    selected_cell_restored: !!submitted?.selected_cell_id && !!playing?.cells?.some(c => c.selected && c.id === submitted.selected_cell_id),
    audio_position_restored: Number.isFinite(before.currentTime) && Number.isFinite(after.currentTime) && Math.abs(before.currentTime - after.currentTime) <= .35,
    new_audio_element: before.media_id != null && after.media_id != null && before.media_id !== after.media_id,
    original_native_pause: !!oldPause,
    no_cancelled_audio_replayed: !!submitted && !nativeMedia.some(e => e.type === 'playing' && e.media_id === before.media_id && e.at_ms > submitted.at_ms),
    all_supplement_steps_naturally_ended: endedSteps.length > 0 && endedSteps.every(e => !!e.native_ended),
  };
  return {status: Object.values(checks).every(Boolean) ? 'COMPLETED_AND_RESTORED' : 'FAILED_CYCLE_EVIDENCE', checks,
    interruption: submitted || null, resumed: resumed || null, resumed_playing: playing || null, original_native_pause: oldPause || null,
    supplement_id: supplement?.id, supplement_ended_steps: endedSteps, audio_position_tolerance_seconds: .35,
    scope: 'Mechanical playback/restoration evidence; speech fingerprint and semantic quality are checked separately. H_PENDING.'};
}
