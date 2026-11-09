/** Local UI restoration, never permission to generate or mutate a stored lesson. */
export type SavedPlaybackStatus = 'playing' | 'paused' | 'interrupted' | 'completed' | 'resume_requested';
export function restorePlaybackState(
  saved: any, total: number, studentMode: boolean, explicitReplay = false,
) {
  const count = Math.max(1, total);
  const step = Number.isInteger(saved?.step) ? Math.max(0, Math.min(count - 1, saved.step)) : 0;
  const progress = Number.isFinite(saved?.progress) ? Math.max(0, Math.min(1, saved.progress)) : studentMode ? 0 : 1;
  const audioPosition = Number.isFinite(saved?.audio_position) ? Math.max(0, saved.audio_position) : 0;
  // Older completed lessons did not save an explicit state. A final board by
  // itself is insufficient (manual inspection also has progress=1).
  const completed = saved?.playback_status === 'completed' ||
    (!saved?.playback_status && step === count - 1 && progress === 1 && audioPosition > 0);
  const explicitResume = saved?.playback_status === 'resume_requested';
  const autoStart = !completed && (explicitResume || (!saved && (studentMode || explicitReplay)));
  return {step, progress, audioPosition, completed, autoStart,
    selectedCell: saved?.selected_cell || null};
}
