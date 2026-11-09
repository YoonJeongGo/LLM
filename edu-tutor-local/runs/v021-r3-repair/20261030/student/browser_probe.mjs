export async function installProbe(page) {
await page.addInitScript(() => {
  localStorage.setItem('edu-tab', 'settings');
  window.__finishEvents = [];
  window.__finishMedia = [];
  window.__finishSceneSamples = [];
  window.__finishBlobs = {};
  window.__finishBlobTasks = [];
  const originalObjectURL = URL.createObjectURL.bind(URL);
  URL.createObjectURL = blob => {
    const url = originalObjectURL(blob);
    if (blob instanceof Blob) window.__finishBlobTasks.push(blob.arrayBuffer().then(async bytes => {
      const hash = await crypto.subtle.digest('SHA-256', bytes);
      window.__finishBlobs[url] = { sha256: [...new Uint8Array(hash)].map(x => x.toString(16).padStart(2, '0')).join(''), size: bytes.byteLength };
    }).catch(error => { window.__finishBlobs[url] = { error: String(error) }; }));
    return url;
  };
  const mediaIds = new WeakMap(); let nextMediaId = 0;
  const mediaId = element => { if (!element) return null; if (!mediaIds.has(element)) mediaIds.set(element, ++nextMediaId); return mediaIds.get(element); };
  const media = element => ({ paused: element?.paused, currentTime: element?.currentTime, duration: element?.duration,
    playbackRate: element?.playbackRate, lesson_id: element?.dataset.lessonRecordId, step_id: element?.dataset.stepId,
    epoch: Number(element?.dataset.playbackEpoch), media_id: mediaId(element), current_src: element?.currentSrc || element?.src,
    muted: element?.muted, volume: element?.volume });
  const equationGlyphRects = element => {
    const content = element.querySelector('.equation .katex-html');
    if (!content) return undefined;
    const rectangles = [], walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.textContent?.trim() || !node.parentElement?.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
      const range = document.createRange(); range.selectNodeContents(node);
      rectangles.push(...[...range.getClientRects()].filter(rect => rect.width > 0 && rect.height > 0).map(rect => rect.toJSON()));
    }
    return rectangles;
  };
  window.__finishSnapshot = () => {
    const board = document.querySelector('.chalk-board');
    const elements = [...document.querySelectorAll('[data-board-element]')].map(e => ({ id: e.dataset.boardElement,
      text: e.querySelector(':scope > p')?.textContent,
      equation_html: e.querySelector('.equation')?.innerHTML,
      equation_glyph_rects: equationGlyphRects(e),
      code: [...e.querySelectorAll('.code-line')].map(line => [...line.childNodes].filter(n => !(n instanceof Element && n.classList.contains('line-number'))).map(n => n.textContent).join('')).join(''),
      columns: [...e.querySelectorAll('thead th')].map(c => c.textContent),
      rows: [...e.querySelectorAll('tbody tr')].map(row => [...row.querySelectorAll('[data-cell-id]')].map(c => ({ id: c.dataset.cellId, text: c.textContent }))),
      rect: e.getBoundingClientRect().toJSON() }));
    const content = elements.map(({ rect, equation_glyph_rects, ...rest }) => rest);
    const pointer = document.querySelector('[data-testid="avatar-pointer"]'), svg = pointer?.ownerSVGElement, point = svg?.createSVGPoint();
    if (point && pointer) { point.x = Number(pointer.getAttribute('x2')); point.y = Number(pointer.getAttribute('y2')); }
    const end = point && svg?.getScreenCTM() ? point.matrixTransform(svg.getScreenCTM()) : null;
    return { dom_lesson_record_id: document.querySelector('.classroom')?.dataset.lessonRecordId,
      dom_step_id: document.querySelector('.classroom')?.dataset.stepId,
      board_text: board?.innerText || '', board_content: content, board_content_serialized: JSON.stringify(content),
      stage_rect: document.querySelector('.chalk-stage')?.getBoundingClientRect().toJSON(),
      elements, cells: [...document.querySelectorAll('[data-cell-id]')].map(c => ({ id: c.dataset.cellId, text: c.textContent, selected: c.querySelector('button')?.getAttribute('aria-pressed') === 'true', rect: c.getBoundingClientRect().toJSON() })),
      caption: document.querySelector('.caption-box p')?.textContent,
      gesture: document.querySelector('[data-gesture]')?.getAttribute('data-gesture'), pointer_end: end ? { x: end.x, y: end.y } : null,
      arrows: [...document.querySelectorAll('.pointer-layer line[marker-end]')].map(e => ({ id: e.id,
        x1: Number(e.getAttribute('x1')), y1: Number(e.getAttribute('y1')), x2: Number(e.getAttribute('x2')), y2: Number(e.getAttribute('y2')) })),
      media: media(document.querySelector('audio')) };
  };
  const sampled = new Set();
  function sampleScene(kind, element = document.querySelector('audio')) {
    if (!(element instanceof HTMLAudioElement) || !Number.isFinite(element.duration) || element.duration <= 0) return;
    const progress = element.currentTime / element.duration;
    const key = `${mediaId(element)}:${element.dataset.playbackEpoch}:${Math.floor(progress * 10)}:${kind}`;
    if (kind !== 'native_ended' && (element.paused || progress < 0.05 || sampled.has(key))) return;
    sampled.add(key);
    window.__finishSceneSamples.push({ ...window.__finishSnapshot(), type: kind, at_ms: performance.now(),
      lesson_record_id: element.dataset.lessonRecordId, step_id: element.dataset.stepId,
      epoch: Number(element.dataset.playbackEpoch), media: media(element) });
  }
  setInterval(() => sampleScene('progress'), 100);
  window.addEventListener('edu:lesson', event => {
    const board = document.querySelector('.chalk-board');
    window.__finishEvents.push({ ...event.detail, ...window.__finishSnapshot(),
      board_html: ['audio_playing', 'interruption_submitted', 'interruption_stopped', 'lesson_resumed'].includes(event.detail.type) ? board?.outerHTML : undefined,
      media: media(document.querySelector('audio')) });
  });
  for (const type of ['play', 'playing', 'pause', 'ended', 'seeking', 'seeked'])
    document.addEventListener(type, event => { if (event.target instanceof HTMLAudioElement) {
      window.__finishMedia.push({ type, at_ms: performance.now(), ...media(event.target) });
      if (type === 'ended') sampleScene('native_ended', event.target);
    } }, true);
});
}
