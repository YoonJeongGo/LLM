import {describe,it,expect} from 'vitest';
import {restorePlaybackState} from './playbackSession';
describe('persistent playback intent across remount',()=>{
  it('auto-starts a new student lesson but never a completed one',()=>{
    expect(restorePlaybackState(null,3,true).autoStart).toBe(true);
    expect(restorePlaybackState({step:2,progress:1,audio_position:8,playback_status:'completed'},3,true)).toMatchObject({completed:true,autoStart:false,step:2});
  });
  it('restores legacy final audio to completed without treating manual final boards as completed',()=>{
    expect(restorePlaybackState({step:2,progress:1,audio_position:8},3,true).completed).toBe(true);
    expect(restorePlaybackState({step:2,progress:1,audio_position:0},3,false).completed).toBe(false);
  });
  it.each(['playing','paused','interrupted'])('does not replay %s merely on navigation return',(playback_status)=>{
    expect(restorePlaybackState({step:1,progress:.3,audio_position:2,playback_status},3,true).autoStart).toBe(false);
  });
  it('accepts an explicit original-lesson resume without losing its selected cell',()=>{
    const selected_cell={cell_id:'original-r2-value',value:0};
    expect(restorePlaybackState({step:1,progress:.3,audio_position:2,playback_status:'resume_requested',selected_cell},3,true))
      .toMatchObject({autoStart:true,step:1,progress:.3,audioPosition:2,selectedCell:selected_cell});
  });
  it('clamps malformed saved positions',()=>{
    expect(restorePlaybackState({step:999,progress:Infinity,audio_position:NaN},2,true)).toMatchObject({step:1,progress:0,audioPosition:0,autoStart:false});
  });
});
