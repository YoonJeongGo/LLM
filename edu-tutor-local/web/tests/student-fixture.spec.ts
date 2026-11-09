import { test, expect, type Page } from "@playwright/test";

// Program-flow fixtures only. The tone is not TTS or education-quality evidence.
const table = {
  type: "table",
  element_id: "source",
  table_name: "sample",
  slot: "main",
  columns: ["name", "value"],
  rows: [
    ["가", 4],
    ["나", 9],
  ],
  row_ids: ["r0", "r1"],
  column_ids: ["name", "value"],
  cell_ids: [
    ["r0-name", "r0-value"],
    ["r1-name", "r1-value"],
  ],
  caption: "개발 검증 전용 원본표",
  timing: { start: 0, end: 0 },
};
const plan: any = {
  schema_version: "1.0",
  lesson_id: "original",
  title: "개발 검증 수업",
  goal: "프로그램 흐름 검증",
  question_text: "검증용 질문",
  problem_source: "typed_user_input",
  provenance: "tool_derived",
  source_refs: [],
  problem_revision: 1,
  verification: {
    status: "calculation_checked",
    scope: "CPU UI fixture, 실제 모델 아님",
    limitations: ["인간 교육 품질 검토 미수행"],
  },
  final_summary: "검증 종료",
  steps: [
    {
      id: "source-step",
      title: "원본",
      speech: "개발 검증 대사",
      board_actions: [table],
      gesture: { kind: "point", target_element_id: "source" },
    },
    {
      id: "result-step",
      title: "결과",
      speech: "개발 검증 결과",
      board_actions: [
        {
          type: "text",
          element_id: "result",
          slot: "right",
          text: "검증용 결과 9",
          timing: { start: 0, end: 0 },
        },
      ],
      gesture: { kind: "point", target_element_id: "result" },
    },
  ],
};
function tone() {
  const samples = 32000,
    b = Buffer.alloc(44 + samples * 2);
  b.write("RIFF");
  b.writeUInt32LE(b.length - 8, 4);
  b.write("WAVE", 8);
  b.write("fmt ", 12);
  b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22);
  b.writeUInt32LE(8000, 24);
  b.writeUInt32LE(16000, 28);
  b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34);
  b.write("data", 36);
  b.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++)
    b.writeInt16LE(Math.round(Math.sin((i * Math.PI) / 20) * 1000), 44 + i * 2);
  return b;
}
async function setup(
  page: Page,
  options: {
    missing?: boolean;
    blocked?: boolean;
    delayed?: boolean;
    quota?: number;
    vision?: boolean;
    delayedPlan?: boolean;
    wideHighlight?: boolean;
    oversizedCell?: boolean;
    lateNext?: boolean;
    lateCurrent?: boolean;
    lateSupplement?: boolean;
    lateReturn?: boolean;
    missingNext?: boolean;
    missingThird?: boolean;
    nextJobDelayed?: boolean;
    nextJobFailed?: boolean;
    generationBlocked?: boolean;
    corruptCurrent?: boolean;
    corruptNext?: boolean;
    threeSteps?: boolean;
    queryReplay?: boolean;
    related?: boolean;
    unrelated?: boolean;
    storedFailure?: boolean;
    reprocessBlocked?: boolean;
    delayedReprocess?: boolean;
    unrelatedReprocess?: boolean;
    multiSupplement?: boolean;
    timedActions?: boolean;
    sharedSourceCellIds?: boolean;
  } = {},
) {
  const state = {
    sent: [] as any[],
    speech: [] as any[],
    manifestReads: [] as {lesson: string; step: string | null}[],
    cancelled: false,
    stopConfirmed: false,
    release: () => {},
    events: [] as any[],
    planRequested: false,
    planReady: false,
    waveReads: [] as string[],
    writes: [] as string[],
    binding: "b".repeat(64),
    planChanged: false,
    releaseNext: () => {},
    supplementReads: 0,
    supplementCompleted: false,
    inSupplement: false,
    returnReads: 0,
    nextJobComplete: !options.nextJobDelayed,
    nextJobStep: "result-step",
    reprocessPosts: [] as any[],
    releaseReprocess: () => {},
  };
  const delayed = new Promise<void>((resolve) => {
    state.release = resolve;
  });
  const lateNext = new Promise<void>((resolve) => { state.releaseNext = resolve; });
  const reprocessing = new Promise<void>((resolve) => { state.releaseReprocess = resolve; });
  const messages: any[] = [],
    plans: any = { original: plan };
  if (options.threeSteps) {
    plans.original = structuredClone(plan);
    plans.original.steps.push({ id: "third-step", title: "세 번째", speech: "세 번째 검증 대사",
      board_actions: [{ type: "text", element_id: "third-result", slot: "right", text: "검증용 세 번째 단계" }],
      gesture: { kind: "point", target_element_id: "third-result" } });
  }
  if (options.timedActions) {
    plans.original = structuredClone(plan);
    plans.original.steps = [plans.original.steps[0]];
    plans.original.steps[0].board_actions.push(
      {type: "text", element_id: "timed-text", slot: "right", text: "시간 경계 검증용 문구", timing: {start: .4, end: .4}},
      {type: "arrow", element_id: "timed-arrow", from_element_id: "source", to_element_id: "timed-text", timing: {start: .75, end: .75}},
    );
  }
  if (options.sharedSourceCellIds) {
    plans.original = structuredClone(plan);
    plans.original.steps[0].board_actions = [
      {...structuredClone(table),element_id:'result-copy',caption:'개발 검증용 결과표 · 원본 cell_id 공유'},
      structuredClone(table),
      {type:'highlight',target_element_id:'source',cell_ids:['r1-value'],style:'background',timing:{start:0,end:0}},
    ];
    plans.original.steps[1].board_actions = [
      {type:'text',element_id:'growth',slot:'right',text:'다음 단계에서 같은 원본 셀의 표 소속을 구분합니다.',timing:{start:0,end:0}},
      {type:'highlight',target_element_id:'result-copy',cell_ids:['r0-value'],style:'background',timing:{start:0,end:0}},
    ];
    plans.original.steps[1].gesture={kind:'point',target_element_id:'result-copy'};
  }
  if (options.wideHighlight) {
    const wide = structuredClone(plan);
    wide.steps[0].board_actions = [
      {
        ...structuredClone(table),
        columns: ["student", "team", "score", "attended"],
        column_ids: ["student", "team", "score", "attended"],
        rows: [
          [
            options.oversizedCell ? "longDevelopmentCell".repeat(8) : "하린",
            "청",
            35,
            1,
          ],
          ["도윤", "청", 25, 1],
        ],
        cell_ids: [
          ["r0-student", "r0-team", "r0-score", "r0-attended"],
          ["r1-student", "r1-team", "r1-score", "r1-attended"],
        ],
      },
      {
        type: "highlight",
        target_element_id: "source",
        cell_ids: [options.oversizedCell ? "r0-student" : "r0-attended"],
        style: "background",
        timing: { start: 0, end: 0 },
      },
    ];
    wide.steps[1].board_actions = [
      {
        type: "highlight",
        target_element_id: "source",
        cell_ids: ["r0-student"],
        style: "background",
        timing: { start: 0, end: 0 },
      },
    ];
    wide.steps[1].gesture = { kind: "point", target_element_id: "source" };
    plans.original = wide;
  }
  if (options.related) {
    const supplementary = structuredClone(plan);
    supplementary.lesson_id = "savedSupplement";
    supplementary.steps = supplementary.steps.slice(0, 1);
    plans.savedSupplement = supplementary;
  }
  let ready = !options.missing;
  let nextReady = !options.missingNext;
  let thirdReady = !options.missingThird;
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem("edu-session", "session");
    localStorage.setItem("edu-lesson", "original");
    localStorage.setItem("edu-tab", "classroom");
    (window as any).lessonEvents = [];
    window.addEventListener("edu:lesson", (event: Event) =>
      (window as any).lessonEvents.push((event as CustomEvent).detail),
    );
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.slice(4),
      method = route.request().method();
    if (method !== "GET") state.writes.push(`${method} ${path}`);
    let body: any = {};
    try {
      body = route.request().postDataJSON();
    } catch {}
    let value: any = {};
    if (path === "/capabilities")
      value = {
        fixture: true,
        text: { available: true },
        speech: { available: true },
        vision: { available: !!options.vision },
      };
    else if (path === "/models")
      value = { model_id: "CPU UI fixture", modules: [] };
    else if (path === "/sessions")
      value = [{ id: "session", title: "CPU UI fixture", generation_epoch: 0 }];
    else if (path === "/resources/budget")
      value = { enabled: true, new_audio_remaining: options.quota ?? 8 };
    else if (path === "/sessions/session/budget")
      value = { session_id: "session", exists: true, state: "active",
        limits: {seconds: 600, text_requests: 8, new_audio_clips: options.quota ?? 8, vision_requests: options.vision ? 2 : 0},
        effective_remaining: {seconds: 600, text_requests: 8, new_audio_clips: options.quota ?? 8, vision_requests: options.vision ? 2 : 0},
        parent_remaining: {seconds: 600, text_requests: 8, new_audio_clips: options.quota ?? 8, vision_requests: options.vision ? 2 : 0},
        used: {seconds: 0, text_requests: 0, new_audio_clips: 0, vision_requests: 0} };
    else if (path === "/sessions/session/messages") {
      if (method === "POST") {
        state.sent.push(body);
        const n = state.sent.length;
        messages.push(
          { id: "u" + n, role: "user", content: body.content },
          { id: "a" + n, role: "assistant", content: "CPU fixture 검증 대사", session_id: "session", lesson_context: body.lesson_context },
        );
        value = { job_id: "chat" + n };
      } else value = messages;
    } else if (path.startsWith("/jobs/chat"))
      value = {
        id: path.split("/")[2],
        state: "succeeded",
        result: { message_id: "a" + state.sent.length },
      };
    else if (path === "/lessons" && method === "POST") {
      const id = state.sent.length > 1 ? "supplement" : "student";
      const next = structuredClone(plans.original);
      next.lesson_id = id;
      if (id === "supplement") {
        next.steps = options.multiSupplement ? next.steps : next.steps.slice(0, 1);
        next.steps[0].board_actions.push({
          type: "highlight",
          target_element_id: "source",
          cell_ids: ["r1-value"],
          style: "background",
          timing: { start: 0, end: 0 },
        });
      }
      plans[id] = next;
      if (id === "supplement" && options.delayedPlan) ready = false;
      value = {
        id,
        source_message_id: body.message_id,
        plan:
          options.blocked || (id === "supplement" && options.delayedPlan)
            ? null
            : next,
        valid: true,
        speech_allowed: !options.blocked,
        status: options.blocked ? "verification_stopped" : "ready",
        fallback_text: "검증 실패 fixture",
      };
    } else if (path === "/lessons/original/reprocess" && method === "POST") {
      state.reprocessPosts.push(body);
      if (options.delayedReprocess) await reprocessing;
      const next = structuredClone(plans.original);
      next.lesson_id = "reprocessed";
      plans.reprocessed = next;
      value = { id: "reprocessed", plan: options.reprocessBlocked ? null : next, valid: true,
        status: options.reprocessBlocked ? "verification_stopped" : "ready",
        speech_allowed: !options.reprocessBlocked,
        reason: options.reprocessBlocked ? "조건식 설명을 검증하지 못했습니다." : undefined,
        reprocessing: { source_lesson_id: options.unrelatedReprocess ? "other" : "original", new_text_inference: false } };
    } else if (path === "/lessons/supplement/generate") {
      state.planRequested = true;
      value = { job_id: "plan" };
    } else if (path === "/jobs/plan") {
      value = { id: "plan", state: state.planReady ? "succeeded" : "running" };
    } else if (/^\/lessons\/[^/]+\/speech$/.test(path)) {
      const id = path.split("/")[2];
      if (method === "POST") {
        state.speech.push(body);
        if (options.delayed) await delayed;
        ready = true;
        if (body.step_id === "result-step" || body.step_id === "third-step") {
          state.nextJobStep = body.step_id;
          value = { job_id: "next-voice" };
        } else {
          if (!body.step_id) nextReady = thirdReady = true;
          value = { job_id: "voice" };
        }
      } else {
        state.manifestReads.push({lesson: id, step: new URL(route.request().url()).searchParams.get("step_id")});
        value = {
          available: true,
          generation_available: !options.generationBlocked,
          replay_only: true,
          binding_fingerprint: state.binding,
          steps: ready
            ? plans[id].steps.filter((s: any) => (s.id !== "result-step" || nextReady) && (s.id !== "third-step" || thirdReady)).map((s: any) => ({
                step_id: s.id,
                audio_id: "d".repeat(64),
                binding_fingerprint: state.binding,
                cache_hit: true,
                audio_url: `/api/lessons/${id}/speech/${s.id}/audio?voice=Sohee&binding=${state.binding}`,
              }))
            : [],
          cache_misses: plans[id].steps.filter((s: any) => !ready || (s.id === "result-step" && !nextReady) || (s.id === "third-step" && !thirdReady))
            .map((s: any) => ({ step_id: s.id, code: (options.corruptNext && s.id === "result-step") || (options.corruptCurrent && s.id === "source-step") ? "cache_checksum_mismatch" : "cache_missing", reason: "No matching fixture clip" })),
        };
      }
    } else if (path === "/jobs/voice/cancel" || path === "/jobs/next-voice/cancel") {
      state.cancelled = true;
      // The API cannot move an already failed job back into an active state.
      value = { state: path === "/jobs/next-voice/cancel" && options.nextJobFailed ? "failed" : "cancelling" };
    } else if (path === "/jobs/next-voice") {
      if (!state.cancelled && state.nextJobComplete && !options.nextJobFailed) {
        if (state.nextJobStep === "result-step") nextReady = true;
        else thirdReady = true;
      }
      value = { id: "next-voice", state: options.nextJobFailed ? "failed" : state.cancelled ? state.stopConfirmed ? "cancelled" : "cancelling"
        : state.nextJobComplete ? "succeeded" : "running",
        result: { steps: [{ step_id: state.nextJobStep, cache_hit: false }] } };
    } else if (path === "/jobs/voice")
      value = {
        id: "voice",
        state: state.cancelled
          ? state.stopConfirmed
            ? "cancelled"
            : "cancelling"
          : "running",
      };
    else if (/^\/lessons\/[^/]+\/speech\/[^/]+\/audio$/.test(path)) {
      const stepId = path.split("/")[4];
      state.waveReads.push(stepId);
      if ((options.lateNext && stepId === "result-step") || (options.lateCurrent && stepId === "source-step")) await lateNext;
      await route.fulfill({ contentType: "audio/wav", body: tone() }).catch(() => {});
      return;
    } else if (path.startsWith("/lessons/")) {
      const id = path.split("/")[2];
      if (id === "original" && options.lateReturn && state.inSupplement) {
        state.returnReads++;
        await lateNext;
      }
      if (id === "savedSupplement") state.inSupplement = true;
      if (id === "savedSupplement" && options.lateSupplement) {
        state.supplementReads++;
        await lateNext;
        state.supplementCompleted = true;
      }
      value = { id, plan: state.planChanged ? { ...plans[id], steps: plans[id].steps.map((step: any) => ({ ...step, speech: "서버에서 변경된 설명" })) } : plans[id], valid: true, speech_allowed: true,
        source_message_id: id === "supplement" ? "a2" : "a1",
        speech_binding_fingerprint: state.binding,
        source_session_id: "session",
        problem: { id: "problem-fixture", revision: 1 },
        evidence: { problem_id: "problem-fixture", problem_revision: 1 },
        source_lesson_context: id === "savedSupplement" ? { lesson_id: options.unrelated ? "other" : "original", problem_revision: 1 } : null,
      };
      if (options.storedFailure && id === "original")
        value = { ...value, plan: null, speech_allowed: false, status: "verification_stopped",
          fallback_text: "보존된 실패 모델 원문 fixture", reason: "이전 검증 중단 fixture" };
    } else if (path.startsWith("/audio/")) {
      await route.fulfill({ contentType: "audio/wav", body: tone() });
      return;
    } else if (path === "/jobs") value = [];
    await route.fulfill({ json: value });
  });
  await page.goto(options.queryReplay ? `/?lesson=original${options.related ? "&supplement=savedSupplement" : ""}` : "/");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page
    .getByLabel("관리 토큰", { exact: true })
    .fill("CPU_UI_FIXTURE_ONLY");
  await page.getByRole("button", { name: "연결", exact: true }).click();
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible();
  if (options.storedFailure && !options.queryReplay) await nav(page, "강의실");
  return state;
}
async function nav(page: Page, label: string) {
  await page
    .getByRole("navigation")
    .getByRole("button", { name: label, exact: true })
    .click();
}
async function start(page: Page) {
  await nav(page, "대화");
  await page.getByLabel("질문 입력").fill("CPU UI fixture 질문");
  await page.getByRole("button", { name: "수업 시작", exact: true }).click();
}
async function finishClip(page: Page) {
  await page.locator("audio").evaluate((audio: HTMLAudioElement) => {
    audio.currentTime = audio.duration - 0.05;
  });
}

test("cache-first repair: ordinary initial and resumed clips avoid all-step manifest reads", async ({page}) => {
  const state = await setup(page);
  await start(page);
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement) => !a.paused)).toBe(true);
  expect(state.manifestReads.length).toBeGreaterThan(0);
  expect(state.manifestReads.every(read => read.step !== null)).toBe(true);
  await page.getByRole('button',{name:'value, 2행: 9',exact:true}).click();
  await page.getByLabel('강의 중 질문').fill('왜 이 행이 포함돼?');
  await page.getByRole('button',{name:'강의 멈추고 질문'}).click();
  await expect(page.locator('.classroom[data-lesson-record-id="supplement"]')).toBeVisible();
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement) => !a.paused)).toBe(true);
  await finishClip(page); // CPU fixture seek only; not an actual latency measurement.
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e:any) => e.type === 'lesson_resumed'))).toBe(true);
  await expect(page.locator('.classroom[data-lesson-record-id="student"]')).toBeVisible();
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement) => !a.paused)).toBe(true);
  expect(state.manifestReads.every(read => read.step !== null)).toBe(true);
  expect(state.speech).toHaveLength(0);
});

test("cache-first repair: stored replay remains scoped and cannot generate", async ({page}) => {
  const state = await setup(page,{queryReplay:true});
  await page.getByRole('button',{name:'저장된 수업 이어 재생',exact:true}).click();
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement) => !a.paused)).toBe(true);
  expect(state.manifestReads.length).toBeGreaterThan(0);
  expect(state.manifestReads.every(read => read.step !== null)).toBe(true);
  expect(state.speech).toHaveLength(0);
});

test("cache-first repair: ordinary explicit current cache miss retains bounded synthesis", async ({page}) => {
  const state = await setup(page,{missing:true,quota:1});
  await start(page);
  await expect.poll(() => state.speech.length).toBe(1);
  expect(state.speech[0].step_id).toBe('source-step');
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement) => !a.paused)).toBe(true);
  expect(state.manifestReads[0].step).toBe('source-step');
  expect(state.manifestReads.some(read => read.step === null)).toBe(true); // Existing generation fallback retained.
  state.stopConfirmed = true;
});

test("cache-first repair: corrupt current cache cannot enter synthesis fallback", async ({page}) => {
  const state = await setup(page,{missing:true,corruptCurrent:true,quota:2});
  await start(page);
  await expect(page.getByText(/저장된 수업의 현재 단계 음성을 사용할 수 없습니다/)).toBeVisible();
  expect(state.speech).toHaveLength(0);
  expect(state.manifestReads.every(read => read.step !== null)).toBe(true);
  await expect(page.locator('audio')).toHaveCount(0);
});

test("cache-first repair: changed current plan stops before any WAV or synthesis", async ({page}) => {
  const state = await setup(page);
  state.planChanged = true;
  await start(page);
  await expect(page.getByText(/화면의 판서·대사와 현재 저장 수업이 달라/)).toBeVisible();
  expect(state.speech).toHaveLength(0);
  expect(state.waveReads).toHaveLength(0);
  await expect(page.locator('audio')).toHaveCount(0);
});

test("next repair: completed student lesson remains completed after settings remount", async ({page}) => {
  const state = await setup(page);
  await start(page);
  await expect.poll(() => page.locator('audio').evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true);
  await finishClip(page);
  await expect(page.locator('audio')).toHaveAttribute('data-step-id', 'result-step');
  await expect.poll(() => page.locator('audio').evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true);
  await finishClip(page);
  await expect.poll(() => page.locator('audio').evaluate((a: HTMLAudioElement) => a.ended)).toBe(true);
  const events = await page.evaluate(() => (window as any).lessonEvents.filter((e:any) => e.type === 'audio_playing').length);
  const posts = state.speech.length;
  await nav(page, '설정');
  await page.getByLabel('화면 글자 크기').selectOption('2');
  await nav(page, '강의실');
  await page.waitForTimeout(900); // Observe absence across async remount/cache preparation.
  expect(await page.evaluate(() => (window as any).lessonEvents.filter((e:any) => e.type === 'audio_playing').length)).toBe(events);
  expect(state.speech).toHaveLength(posts);
  await expect(page.locator('audio')).toHaveCount(0);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('lecture:student') || '{}').playback_status)).toBe('completed');
});

test("next repair: paused student lesson never resumes just by leaving and returning", async ({page}) => {
  const state = await setup(page);
  await start(page);
  await expect.poll(() => page.locator('audio').evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(.15);
  await page.getByRole('button',{name:'일시정지',exact:true}).click();
  const events = await page.evaluate(() => (window as any).lessonEvents.filter((e:any) => e.type === 'audio_playing').length);
  const position = await page.locator('audio').evaluate((a:HTMLAudioElement) => a.currentTime);
  await nav(page,'설정'); await nav(page,'강의실');
  await page.waitForTimeout(900);
  expect(await page.evaluate(() => (window as any).lessonEvents.filter((e:any) => e.type === 'audio_playing').length)).toBe(events);
  await expect(page.locator('audio')).toHaveCount(0);
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('lecture:student') || '{}'));
  expect(saved.playback_status).toBe('paused'); expect(saved.audio_position).toBeGreaterThanOrEqual(position-.05);
  expect(state.speech).toHaveLength(0);
});

test("student opt-in: real playing events, selected-row interruption, supplement and automatic resume", async ({
  page,
}) => {
  const state = await setup(page);
  await start(page);
  await expect(
    page.locator('.classroom[data-lesson-record-id="student"]'),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as any).lessonEvents.filter(
            (e: any) => e.type === "audio_playing",
          ).length,
      ),
    )
    .toBe(1);
  await page
    .getByRole("button", { name: "value, 2행: 9", exact: true })
    .click();
  await page.getByLabel("강의 중 질문").fill("왜 이 행이 포함돼?");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  await expect(
    page.locator('.classroom[data-lesson-record-id="supplement"]'),
  ).toBeVisible();
  expect(state.sent[1].lesson_context.selected_cell.cell_id).toBe("r1-value");
  await expect
    .poll(() =>
      page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused),
    )
    .toBe(true);
  await finishClip(page);
  await expect(
    page.locator('.classroom[data-lesson-record-id="student"]'),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused),
    )
    .toBe(true);
  await finishClip(page);
  await expect(
    page.locator('.classroom[data-step-id="result-step"]'),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "value, 2행: 9", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as any).lessonEvents.filter(
            (e: any) => e.type === "stage_gap",
          ).length,
      ),
    )
    .toBe(1);
  expect(state.speech).toHaveLength(0); // Cached fixture audio never triggers new generation.
});

test("next repair: every supplementary stage finishes before the original selected cell resumes", async ({page}) => {
  const state = await setup(page, {multiSupplement: true});
  await start(page);
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement) => !a.paused)).toBe(true);
  await page.getByRole('button',{name:'value, 2행: 9',exact:true}).click();
  await page.getByLabel('강의 중 질문').fill('선택 행과 NULL행 차이, 정렬 순서를 설명해 줘.');
  await page.getByRole('button',{name:'강의 멈추고 질문',exact:true}).click();
  await expect(page.locator('.classroom[data-lesson-record-id="supplement"]')).toBeVisible();
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement) => !a.paused)).toBe(true);
  await finishClip(page);
  await expect(page.locator('.classroom[data-lesson-record-id="supplement"][data-step-id="result-step"]')).toBeVisible();
  expect(await page.evaluate(() => (window as any).lessonEvents.filter((e:any)=>e.type==='lesson_resumed').length)).toBe(0);
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement) => !a.paused)).toBe(true);
  await finishClip(page);
  await expect(page.locator('.classroom[data-lesson-record-id="student"][data-step-id="source-step"]')).toBeVisible();
  await expect(page.getByRole('button',{name:'value, 2행: 9',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement) => !a.paused)).toBe(true);
  expect(state.speech).toHaveLength(0);
});

test("next repair: text and arrow DOM commits follow the same native media clock within 75ms", async ({page}, testInfo) => {
  await setup(page, {timedActions: true});
  await page.evaluate(() => {
    const samples:any[] = []; (window as any).timelineSamples = samples;
    const sample = () => {
      const a = document.querySelector('audio');
      if (a && !a.paused) samples.push({at_ms:performance.now(),time:a.currentTime,duration:a.duration,
        text:!!document.querySelector('[data-board-element="timed-text"]'),
        arrow:!!document.querySelector('[data-board-arrow="timed-arrow"]')});
      if (samples.length < 1000) requestAnimationFrame(sample);
    }; requestAnimationFrame(sample);
  });
  await start(page);
  await expect.poll(() => page.locator('audio').evaluate((a:HTMLAudioElement)=>a.ended), {timeout:10000}).toBe(true);
  const captured = await page.evaluate(() => ({samples:(window as any).timelineSamples,
    commits:(window as any).lessonEvents.filter((e:any)=>e.type==='scene_commit')}));
  const bounds = ['text','arrow'].map((kind,index) => {
    const due = captured.samples[0].duration * [0.4,0.75][index];
    const absent = captured.samples.filter((s:any)=>!s[kind]).at(-1);
    const visible = captured.samples.find((s:any)=>s[kind]);
    return {kind,due,last_absent:absent?.time,first_visible:visible?.time,
      delay_lower_ms:Math.max(0,((absent?.time??0)-due)*1000),
      delay_upper_ms:visible ? (visible.time-due)*1000 : null};
  });
  await testInfo.attach('cpu-media-clock-bounds',{body:JSON.stringify({scope:'CPU UI fixture tone; no actual TTS or human review',threshold_ms:75,bounds,...captured},null,2),contentType:'application/json'});
  for (const bound of bounds) { expect(bound.delay_upper_ms).not.toBeNull(); expect(bound.delay_upper_ms!).toBeLessThanOrEqual(75); }
  expect(captured.commits.some((e:any)=>e.arrow_ids.includes('timed-arrow'))).toBe(true);
});

test("late speech POST is cancelled and follow-up waits for confirmed server stop", async ({
  page,
}) => {
  const state = await setup(page, { missing: true, delayed: true, quota: 1 });
  await nav(page, "강의실");
  await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
  await expect.poll(() => state.speech.length).toBe(1);
  expect(state.speech[0].step_id).toBe("source-step");
  await page.getByLabel("강의 중 질문").fill("왜 이 행이 포함돼?");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  expect(state.sent).toHaveLength(0);
  state.release();
  await expect.poll(() => state.cancelled).toBe(true);
  expect(state.sent).toHaveLength(0);
  state.stopConfirmed = true;
  await expect.poll(() => state.sent.length).toBe(1);
  await expect(page.locator("audio")).toHaveCount(0);
});

test("delayed supplementary plan preserves the original board and starts new speech after atomic commit", async ({
  page,
}) => {
  const state = await setup(page, { delayedPlan: true });
  await start(page);
  await expect
    .poll(() =>
      page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused),
    )
    .toBe(true);
  await page
    .getByRole("button", { name: "value, 2행: 9", exact: true })
    .click();
  await page.getByLabel("강의 중 질문").fill("왜 이 행이 포함돼?");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  await expect.poll(() => state.planRequested).toBe(true);
  await expect(
    page.locator('.classroom[data-lesson-record-id="student"]'),
  ).toBeVisible();
  await expect(
    page.locator('.classroom[data-lesson-record-id="supplement"]'),
  ).toHaveCount(0);
  state.planReady = true;
  await expect(
    page.locator(
      '.classroom[data-lesson-record-id="supplement"][data-student-mode="true"]',
    ),
  ).toBeVisible();
  await expect.poll(() => state.speech.length).toBe(1);
  expect(state.speech[0].step_id).toBe("source-step");
  await expect
    .poll(() =>
      page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused),
    )
    .toBe(true);
});

test("saved failure reprocessing commits a new student lesson and prepares its two steps without a new text request", async ({ page }) => {
  const state = await setup(page, { storedFailure: true, missing: true, missingNext: true, quota: 2 });
  await expect(page.getByText("보존된 실패 모델 원문 fixture", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "저장 답변으로 다시 검증", exact: true }).click();
  await expect(page.locator('.classroom[data-lesson-record-id="reprocessed"][data-student-mode="true"][data-replay-only="false"]')).toBeVisible();
  await expect(page.getByRole("link", { name: "이전 검증 기록", exact: true })).toHaveAttribute("href", "/?lesson=original");
  await expect.poll(() => state.speech.map(s => s.step_id)).toEqual(["source-step", "result-step"]);
  expect(state.reprocessPosts).toHaveLength(1);
  expect(state.reprocessPosts[0].request_id).toMatch(/^[a-f0-9-]{36}$/);
  expect(state.sent).toHaveLength(0);
  expect(state.writes.some(path => path.endsWith("/generate"))).toBe(false);
  expect(await page.evaluate(() => localStorage.getItem("edu-lesson"))).toBe("reprocessed");
  await finishClip(page);
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "audio_playing" && e.step_id === "result-step"))).toBe(true);
  expect(state.speech).toHaveLength(2);
  const old = await page.evaluate(async () => await (await fetch("/api/lessons/original")).json());
  expect(old.status).toBe("verification_stopped");
  expect(old.plan).toBeNull();
  expect(old.fallback_text).toBe("보존된 실패 모델 원문 fixture");
  await test.info().attach("saved-failure-reprocess-fixture-events.json", { body: JSON.stringify(await page.evaluate(() => (window as any).lessonEvents)), contentType: "application/json" });
});

test("saved failure reprocessing cannot start speech when the new verification is still blocked", async ({ page }) => {
  const state = await setup(page, { storedFailure: true, reprocessBlocked: true, quota: 2 });
  await page.getByRole("button", { name: "저장 답변으로 다시 검증", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "조건식 설명을 검증하지 못했습니다." })).toBeVisible();
  await expect(page.getByText("보존된 실패 모델 원문 fixture", { exact: true })).toBeVisible();
  expect(state.speech).toHaveLength(0);
  expect(state.sent).toHaveLength(0);
  expect(await page.evaluate(() => localStorage.getItem("edu-lesson"))).toBe("original");
});

test("saved failure reprocessing rejects a plan linked to a different original lesson", async ({ page }) => {
  const state = await setup(page, { storedFailure: true, unrelatedReprocess: true, quota: 2 });
  await page.getByRole("button", { name: "저장 답변으로 다시 검증", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "이전 실패 기록을 보존합니다." })).toBeVisible();
  expect(state.speech).toHaveLength(0);
  expect(await page.evaluate(() => localStorage.getItem("edu-lesson"))).toBe("original");
});

test("saved failure reprocessing ignores a late response after leaving the classroom", async ({ page }) => {
  const state = await setup(page, { storedFailure: true, delayedReprocess: true });
  await page.getByRole("button", { name: "저장 답변으로 다시 검증", exact: true }).click();
  await expect.poll(() => state.reprocessPosts.length).toBe(1);
  await nav(page, "대화");
  const completed = page.waitForResponse(response => new URL(response.url()).pathname === "/api/lessons/original/reprocess");
  state.releaseReprocess();
  await completed;
  await expect(page.getByLabel("질문 입력")).toBeVisible();
  expect(state.speech).toHaveLength(0);
  expect(await page.evaluate(() => localStorage.getItem("edu-lesson"))).toBe("original");
});

test("saved failure reprocessing stop preserves the old record and does not apply a late result", async ({ page }) => {
  const state = await setup(page, { storedFailure: true, delayedReprocess: true });
  await page.getByRole("button", { name: "저장 답변으로 다시 검증", exact: true }).click();
  await expect.poll(() => state.reprocessPosts.length).toBe(1);
  const failed = page.waitForEvent("requestfailed", request => new URL(request.url()).pathname === "/api/lessons/original/reprocess");
  await page.getByRole("button", { name: "생성 중지", exact: true }).click();
  state.releaseReprocess();
  await failed;
  await expect(page.getByText("보존된 실패 모델 원문 fixture", { exact: true })).toBeVisible();
  expect(state.speech).toHaveLength(0);
  expect(await page.evaluate(() => localStorage.getItem("edu-lesson"))).toBe("original");
});

test("saved failure query review remains GET-only and does not expose reprocessing", async ({ page }) => {
  const state = await setup(page, { storedFailure: true, queryReplay: true, quota: 2 });
  await expect(page.getByText("보존된 실패 모델 원문 fixture", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "저장 답변으로 다시 검증", exact: true })).toHaveCount(0);
  expect(state.writes).toEqual([]);
  expect(state.speech).toEqual([]);
});

test("unsafe answer stops before speech", async ({ page }) => {
  const state = await setup(page, { blocked: true });
  await start(page);
  await expect(
    page.getByText("검증 실패 fixture", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("audio")).toHaveCount(0);
  expect(state.speech).toHaveLength(0);
});

test("cancelled student request cannot apply a late lesson response", async ({
  page,
}) => {
  await setup(page);
  let release = () => {},
    requested = false;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/lessons", async (route) => {
    requested = true;
    await pending;
    await route.fulfill({
      json: {
        id: "stale",
        valid: true,
        speech_allowed: true,
        plan: { ...plan, lesson_id: "stale" },
      },
    });
  });
  await start(page);
  await expect.poll(() => requested).toBe(true);
  await page.getByRole("button", { name: "생성 중지" }).click();
  release();
  await expect(page.getByLabel("질문 입력")).toBeVisible();
  await expect(
    page.locator('.classroom[data-lesson-record-id="stale"]'),
  ).toHaveCount(0);
  await expect(page.locator("audio")).toHaveCount(0);
  expect(
    await page.evaluate(() =>
      (window as any).lessonEvents.some((e: any) => e.type === "plan_ready"),
    ),
  ).toBe(false);
});

async function chatCancellationFixture(page: Page, options: {failedPost?: boolean; delayedPost?: boolean} = {}) {
  const state = await setup(page);
  const observed = {cancelPosted:false, oldGets:0, newGets:0, release:()=>{}};
  const pending = new Promise<void>(resolve => {observed.release=resolve;});
  await page.route(/\/api\/jobs\/chat[^/]+(?:\/cancel)?$/, async route => {
    const path=new URL(route.request().url()).pathname, id=path.split('/')[3];
    if (path.endsWith('/cancel')) {
      observed.cancelPosted=true;
      if(options.delayedPost)await pending;
      await route.fulfill(options.failedPost ? {status:500,json:{detail:'CPU cancellation transport failure'}}
        : {json:{id,state:'running',cancel_requested:true}});
    } else {
      if(id==='chat1')observed.oldGets++;else observed.newGets++;
      await route.fulfill({json:{id,state:id==='chat1' && observed.cancelPosted?'cancelled':'running',
        ...(id==='chat1' && observed.cancelPosted?{error:'CPU terminal cancellation'}:{})}});
    }
  });
  await nav(page,'대화');
  await page.getByLabel('질문 입력',{exact:true}).fill('CPU cancellation first request');
  await page.getByRole('button',{name:'질문 전송',exact:true}).click();
  await expect.poll(()=>observed.oldGets).toBeGreaterThan(0);
  await expect(page.getByRole('button',{name:'생성 중지',exact:true})).toBeVisible();
  return {state,observed};
}

test('cancel repair: same running cancellation response still observes terminal GET and enables next question', async ({page}) => {
  const {state,observed}=await chatCancellationFixture(page);
  await page.getByRole('button',{name:'생성 중지',exact:true}).click();
  await expect.poll(()=>observed.cancelPosted).toBe(true);
  await expect(page.getByRole('button',{name:'수업 시작',exact:true})).toBeVisible({timeout:4000});
  await page.getByLabel('질문 입력',{exact:true}).fill('CPU next question');
  await page.getByRole('button',{name:'질문 전송',exact:true}).click();
  await expect.poll(()=>state.sent.length).toBe(2);
});

test('cancel repair: failed cancellation POST does not stop terminal-state polling', async ({page}) => {
  const {observed}=await chatCancellationFixture(page,{failedPost:true});
  await page.getByRole('button',{name:'생성 중지',exact:true}).click();
  await expect.poll(()=>observed.cancelPosted).toBe(true);
  await expect(page.getByRole('button',{name:'수업 시작',exact:true})).toBeVisible({timeout:4000});
  expect(observed.oldGets).toBeGreaterThan(1);
});

test('cancel repair: late cancellation response cannot replace a newer running request', async ({page}) => {
  const {state,observed}=await chatCancellationFixture(page,{delayedPost:true});
  await page.getByRole('button',{name:'생성 중지',exact:true}).click();
  await expect(page.getByRole('button',{name:'수업 시작',exact:true})).toBeVisible({timeout:4000});
  await page.getByLabel('질문 입력',{exact:true}).fill('CPU newer request');
  await page.getByRole('button',{name:'질문 전송',exact:true}).click();
  await expect.poll(()=>state.sent.length).toBe(2);
  const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/jobs/chat1/cancel');
  observed.release();await response;
  await expect.poll(()=>observed.newGets).toBeGreaterThan(1);
  await expect(page.getByText('취소 요청됨 · 실제 중지를 기다리는 중',{exact:true})).toHaveCount(0);
});

test('cancel repair: late cancellation response cannot restore an old job after changing conversation', async ({page}) => {
  const {observed}=await chatCancellationFixture(page,{delayedPost:true});
  await page.getByRole('button',{name:'생성 중지',exact:true}).click();
  await expect(page.getByRole('button',{name:'수업 시작',exact:true})).toBeVisible({timeout:4000});
  await page.getByRole('button',{name:'새로운 대화',exact:true}).click();
  const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/jobs/chat1/cancel');
  observed.release();await response;
  await expect(page.getByRole('button',{name:'생성 중지',exact:true})).toHaveCount(0);
  await expect(page.getByText('취소 요청됨 · 실제 중지를 기다리는 중',{exact:true})).toHaveCount(0);
});

test('cancel repair: late original message POST cannot steal ownership from the newer job poll', async ({page}) => {
  await setup(page);
  let posts=0,newGets=0,oldCancelled=false,release=()=>{};
  const pending=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/sessions/session/messages',async route=>{
    if(route.request().method()!=='POST'){await route.fallback();return;}
    const ordinal=++posts;if(ordinal===1)await pending;
    await route.fulfill({json:{job_id:'chat'+ordinal}});
  });
  await page.route(/\/api\/jobs\/chat[^/]+(?:\/cancel)?$/,async route=>{
    const path=new URL(route.request().url()).pathname,id=path.split('/')[3];
    if(path.endsWith('/cancel')){oldCancelled=id==='chat1';await route.fulfill({json:{id,state:'cancelled'}});}
    else{if(id==='chat2')newGets++;await route.fulfill({json:{id,state:'running'}});}
  });
  await nav(page,'대화');
  await page.getByLabel('질문 입력',{exact:true}).fill('CPU old delayed POST');
  await page.getByRole('button',{name:'질문 전송',exact:true}).click();
  await expect.poll(()=>posts).toBe(1);
  await page.getByRole('button',{name:'생성 중지',exact:true}).click();
  expect(posts).toBe(1); // Stopping a pending POST must never submit the draft again.
  await expect(page.getByRole('button',{name:'수업 시작',exact:true})).toBeVisible();
  await page.getByLabel('질문 입력',{exact:true}).fill('CPU newer accepted POST');
  await page.getByRole('button',{name:'질문 전송',exact:true}).click();
  await expect.poll(()=>newGets).toBeGreaterThan(0);
  release();
  await expect.poll(()=>oldCancelled).toBe(true);
  await expect.poll(()=>newGets).toBeGreaterThan(1);
  await expect(page.getByRole('button',{name:'생성 중지',exact:true})).toBeVisible();
});

test('pointer repair: shared source cell IDs remain scoped to the actual gesture table across steps', async ({page}) => {
  await setup(page,{sharedSourceCellIds:true});
  await start(page);
  const source=page.locator('[data-board-element="source"]');
  await source.getByRole('button',{name:'value, 2행: 9',exact:true}).click();
  const pointerInside=async (elementId:string,cellId:string)=>page.evaluate(({elementId,cellId})=>{
    const target=[...document.querySelectorAll<HTMLElement>('[data-board-element]')].find(e=>e.dataset.boardElement===elementId);
    const cell=[...target?.querySelectorAll<HTMLElement>('[data-cell-id]')||[]].find(e=>e.dataset.cellId===cellId);
    const pointer=document.querySelector<SVGLineElement>('[data-testid="avatar-pointer"]'),svg=pointer?.ownerSVGElement;
    if(!cell||!pointer||!svg)return false;
    const point=svg.createSVGPoint();point.x=Number(pointer.getAttribute('x2'));point.y=Number(pointer.getAttribute('y2'));
    const end=point.matrixTransform(svg.getScreenCTM()!),rect=cell.getBoundingClientRect();
    return end.x>=rect.left&&end.x<=rect.right&&end.y>=rect.top&&end.y<=rect.bottom;
  },{elementId,cellId});
  await expect.poll(()=>pointerInside('source','r1-value'),{timeout:2000}).toBe(true);
  await expect(page.locator('[data-board-element="result-copy"] [data-cell-id="r1-value"]')).not.toHaveAttribute('aria-pressed','true');
  await expect(page.locator('audio')).toHaveAttribute('data-step-id','result-step',{timeout:8000});
  await expect.poll(()=>pointerInside('result-copy','r0-value')).toBe(true);
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>{document.documentElement.style.fontSize='28px';});
  await expect.poll(()=>pointerInside('result-copy','r0-value')).toBe(true);
});

test("late OCR POST is cancelled without clearing a newer recognition request", async ({
  page,
}) => {
  await setup(page, { vision: true });
  let release = () => {},
    started = 0,
    lateCancelled = false;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/photos**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/transcribe")) {
      const n = ++started;
      if (n === 1) await pending;
      await route.fulfill({ json: { job_id: "ocr" + n } });
    } else
      await route.fulfill({
        json: {
          id: "photo",
          question: "CPU fixture 원문",
          tables: [],
          recognition_status: "not_run",
          revision: 1,
        },
      });
  });
  await page.route("**/api/jobs/ocr**", async (route) => {
    if (route.request().url().endsWith("/ocr1/cancel")) lateCancelled = true;
    await route.fulfill({
      json: {
        id: "ocr2",
        state: route.request().url().endsWith("/cancel")
          ? "cancelled"
          : "running",
      },
    });
  });
  await nav(page, "대화");
  await page.getByRole("button", { name: "문제 사진 첨부" }).click();
  await page.getByLabel("문제 사진 업로드").setInputFiles({
    name: "cpu-fixture-pixel.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/mXcAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  await page.getByRole("button", { name: "로컬 모델로 원문 인식" }).click();
  await expect.poll(() => started).toBe(1);
  await page.getByRole("button", { name: "인식 중지" }).click();
  await page.getByRole("button", { name: "로컬 모델로 원문 인식" }).click();
  await expect.poll(() => started).toBe(2);
  release();
  await expect.poll(() => lateCancelled).toBe(true);
  await expect(
    page.getByRole("button", { name: "로컬 모델로 원문 인식" }),
  ).toBeDisabled();
  await expect(page.getByRole("button", { name: "인식 중지" })).toBeVisible();
  await expect(page.getByLabel("문제 본문")).toHaveValue("CPU fixture 원문");
  await page.getByRole("button", { name: "인식 중지" }).click();
});

test("zero quota preserves board without starting a new speech job", async ({
  page,
}) => {
  const state = await setup(page, { missing: true, quota: 0 });
  await nav(page, "강의실");
  await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "새 음성 생성 한도를 모두 사용",
  );
  expect(state.speech).toHaveLength(0);
  await expect(
    page.getByRole("button", { name: "value, 2행: 9", exact: true }),
  ).toBeVisible();
});

test("stored photo can be reopened and restructured without OCR or automatic confirmation", async ({
  page,
}) => {
  await setup(page);
  let restructured = 0,
    recognized = 0,
    confirmed = 0,
    images = 0;
  let stored: any = {
    id: "saved-photo",
    created_at: "2026-10-27T03:00:00Z",
    question: "저장한 CPU 검증 문제",
    sql: "SELECT value FROM sample",
    tables: [],
    confirmed: true,
    revision: 1,
    recognition_status: "recognized",
    original_text: "name value\n가 4\n나 9",
  };
  await page.route("**/api/photos**", async (route) => {
    expect(route.request().headers().authorization).toBe(
      "Bearer CPU_UI_FIXTURE_ONLY",
    );
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/image")) {
      images++;
      await route.fulfill({
        contentType: "image/png",
        body: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/mXcAAAAASUVORK5CYII=",
          "base64",
        ),
      });
      return;
    }
    if (path.endsWith("/restructure")) {
      restructured++;
      stored = {
        ...stored,
        confirmed: false,
        revision: 2,
        tables: [
          {
            name: "sample",
            columns: ["name", "value"],
            rows: [
              ["가", 4],
              ["나", 9],
            ],
          },
        ],
        invalidated_lesson_ids: ["original"],
      };
    }
    if (path.endsWith("/transcribe")) recognized++;
    if (path.endsWith("/confirm")) confirmed++;
    await route.fulfill({ json: path === "/api/photos" ? [stored] : stored });
  });
  await nav(page, "대화");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "문제 사진 첨부" }).click();
  const selectBox = await page
    .getByLabel("저장한 사진", { exact: true })
    .boundingBox();
  expect(selectBox && selectBox.x + selectBox.width).toBeLessThanOrEqual(390);
  await page
    .getByLabel("저장한 사진", { exact: true })
    .selectOption("saved-photo");
  await expect(page.getByLabel("문제 본문")).toHaveValue(
    "저장한 CPU 검증 문제",
  );
  await expect(
    page.getByRole("img", { name: "업로드한 문제 원본" }),
  ).toBeVisible();
  expect(images).toBe(1);
  await page.getByRole("button", { name: "인식문에서 표 다시 정리" }).click();
  await expect(page.getByText("revision 2", { exact: false })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "확정한 문제 풀이" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "이 원문으로 확정" }),
  ).toBeEnabled();
  await page
    .getByText("표 · 읽지 못한 부분 · 누락 조건 편집", { exact: true })
    .click();
  expect(
    JSON.parse(await page.getByLabel("사진 표 JSON").inputValue())[0].rows,
  ).toEqual([
    ["가", 4],
    ["나", 9],
  ]);
  await page.getByLabel("문제 본문").fill("저장 전 수정 내용");
  await expect(
    page.getByRole("button", { name: "인식문에서 표 다시 정리" }),
  ).toBeDisabled();
  expect({ restructured, recognized, confirmed }).toEqual({
    restructured: 1,
    recognized: 0,
    confirmed: 0,
  });
});

test("narrow 200 percent highlighted cell is revealed locally while manual scroll and cancelled epochs are respected", async ({
  page,
}) => {
  const state = await setup(page, { wideHighlight: true });
  await nav(page, "강의실");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "28px";
  });
  const scroll = page.locator(".chalk-board .table-scroll");
  const targetVisible = (id: string) =>
    page.locator(`[data-cell-id="${id}"]`).evaluate((cell) => {
      const scroller = cell.closest(".table-scroll")!,
        clip = scroller.getBoundingClientRect(),
        rect = cell.getBoundingClientRect();
      return (
        rect.left >= clip.left - 1 &&
        rect.right <= clip.left + scroller.clientWidth + 1
      );
    });
  await expect.poll(() => targetVisible("r0-attended")).toBe(true);
  expect(await page.evaluate(() => scrollY)).toBe(0);
  const distance = await page
    .locator('[data-testid="avatar-pointer"]')
    .evaluate((pointer) => {
      const line = pointer as SVGLineElement;
      const point = new DOMPoint(
        line.x2.baseVal.value,
        line.y2.baseVal.value,
      ).matrixTransform(line.getScreenCTM()!);
      const cell = document
        .querySelector('[data-cell-id="r0-attended"]')!
        .getBoundingClientRect();
      return Math.hypot(
        point.x - cell.left - cell.width / 2,
        point.y - cell.top - cell.height / 2,
      );
    });
  expect(distance).toBeLessThanOrEqual(2);
  await scroll.evaluate((node) => {
    node.scrollLeft = 0;
  });
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  expect(await scroll.evaluate((node) => node.scrollLeft)).toBe(0);
  // A font/layout change reveals the current target again, without moving the page.
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "24px";
  });
  await expect.poll(() => targetVisible("r0-attended")).toBe(true);
  await page
    .getByRole("button", { name: "다음 단계", exact: true })
    .last()
    .click();
  await expect.poll(() => targetVisible("r0-student")).toBe(true);
  await page.getByRole("button", { name: "이전 단계", exact: true }).click();
  await expect.poll(() => targetVisible("r0-attended")).toBe(true);
  await page.getByLabel("강의 중 질문").fill("CPU fixture 중단 질문");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  await expect.poll(() => state.sent.length).toBe(1);
  await scroll.evaluate((node) => {
    node.scrollLeft = 0;
  });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "28px";
  });
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  expect(await scroll.evaluate((node) => node.scrollLeft)).toBe(0);
  await expect(page.locator('[data-testid="avatar-pointer"]')).toHaveCount(0);
});

test("narrow oversized highlighted cell keeps its pointer center in the table viewport", async ({
  page,
}) => {
  await setup(page, { wideHighlight: true, oversizedCell: true });
  await nav(page, "강의실");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "28px";
  });
  await expect
    .poll(() =>
      page.locator('[data-cell-id="r0-student"]').evaluate((cell) => {
        const scroller = cell.closest(".table-scroll")!,
          clip = scroller.getBoundingClientRect(),
          rect = cell.getBoundingClientRect();
        return (
          rect.width > scroller.clientWidth * 2 &&
          Math.abs(
            rect.left + rect.width / 2 - clip.left - scroller.clientWidth / 2,
          ) <= 2
        );
      }),
    )
    .toBe(true);
  expect(await page.evaluate(() => scrollY)).toBe(0);
});

// Cached browser program-flow tests use fixture tones and controlled delays.
// They are not actual generated speech, actual performance targets, or human review.
test("ordinary student prefetches exactly the next valid cached clip while current speech plays", async ({ page }) => {
  const state = await setup(page, { lateNext: true, threeSteps: true });
  await start(page);
  await expect(page.locator('.classroom[data-student-mode="true"][data-replay-only="false"]')).toBeVisible();
  await expect.poll(() => state.waveReads).toEqual(["source-step", "result-step"]);
  expect(await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(false);
  await expect(page.locator('.classroom[data-step-id="source-step"]')).toBeVisible();
  expect(state.speech).toEqual([]);
  state.releaseNext();
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "next_cache_prefetch_ready" && !e.replay_only))).toBe(true);
  expect(state.waveReads).toEqual(["source-step", "result-step"]);
  await finishClip(page); // Fixture-only seek; not measured real speech performance.
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "speech_ready" && e.step_id === "result-step" && e.prefetched && !e.replay_only))).toBe(true);
  await expect.poll(() => state.waveReads).toEqual(["source-step", "result-step", "third-step"]);
  expect(state.speech).toEqual([]);
});

test("ordinary student generates only the next verified step during current playback and reuses its prepared blob", async ({ page }) => {
  const state = await setup(page, { missingNext: true, missingThird: true, threeSteps: true, nextJobDelayed: true, quota: 2 });
  await start(page);
  await expect.poll(() => state.speech.length).toBe(1);
  expect(state.speech[0].step_id).toBe("result-step");
  await expect(page.locator('.classroom[data-step-id="source-step"]')).toBeVisible();
  expect(await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(false);
  expect(state.waveReads).toEqual(["source-step"]);
  state.nextJobComplete = true;
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "next_speech_generation_ready" && e.generated === true && e.cached === false))).toBe(true);
  expect(state.speech.map(s => s.step_id)).toEqual(["result-step"]);
  expect(state.waveReads).toEqual(["source-step", "result-step"]);
  await finishClip(page);
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "speech_ready" && e.step_id === "result-step" && e.prefetched && e.generated_ahead && e.cached === false))).toBe(true);
  await expect.poll(() => state.speech.map(s => s.step_id)).toEqual(["result-step", "third-step"]);
  expect(state.cancelled).toBe(false); // Routine advancement keeps the completed resident owner reusable.
  expect(state.waveReads.filter(s => s === "result-step")).toHaveLength(1);
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "next_speech_generation_ready" && e.step_id === "third-step"))).toBe(true);
  await finishClip(page);
  await expect(page.locator('.classroom[data-step-id="third-step"]')).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "audio_playing" && e.step_id === "third-step"))).toBe(true);
  expect(state.cancelled).toBe(false);
  state.stopConfirmed = true;
  await finishClip(page);
  await expect.poll(() => state.cancelled).toBe(true);
  expect(state.speech).toHaveLength(2);
  await test.info().attach("fixture-ahead-events.json", { body: JSON.stringify(await page.evaluate(() => (window as any).lessonEvents)), contentType: "application/json" });
});

test("ordinary student transition waits for the same future job without submitting a duplicate", async ({ page }) => {
  const state = await setup(page, { missingNext: true, nextJobDelayed: true, quota: 2 });
  await start(page);
  await expect.poll(() => state.speech.length).toBe(1);
  await finishClip(page);
  await expect(page.locator('.classroom[data-step-id="result-step"]')).toBeVisible();
  expect(state.speech).toHaveLength(1);
  expect(state.waveReads).toEqual(["source-step"]);
  state.nextJobComplete = true;
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "audio_playing" && e.step_id === "result-step"))).toBe(true);
  expect(state.speech).toHaveLength(1);
  expect(state.waveReads).toEqual(["source-step", "result-step"]);
});

test("ordinary student interruption cancels a late future POST before sending the follow-up", async ({ page }) => {
  const state = await setup(page, { missingNext: true, delayed: true, quota: 2 });
  await start(page);
  await expect.poll(() => state.speech.length).toBe(1);
  await page.getByLabel("강의 중 질문").fill("왜 이 행이 포함돼?");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  expect(await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  expect(state.sent).toHaveLength(1);
  state.release();
  await expect.poll(() => state.cancelled).toBe(true);
  expect(state.sent).toHaveLength(1);
  state.stopConfirmed = true;
  await expect.poll(() => state.sent.length).toBe(2);
  expect(state.speech).toHaveLength(1);
  expect(state.waveReads).not.toContain("result-step");
  await test.info().attach("fixture-cancel-events.json", { body: JSON.stringify(await page.evaluate(() => (window as any).lessonEvents)), contentType: "application/json" });
});

test("ordinary student pause cancels future generation and a resumed clip does not retry it", async ({ page }) => {
  const state = await setup(page, { missingNext: true, delayed: true, quota: 2 });
  await start(page);
  await expect.poll(() => state.speech.length).toBe(1);
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  state.stopConfirmed = true;
  state.release();
  await expect.poll(() => state.cancelled).toBe(true);
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await finishClip(page);
  expect(state.speech).toHaveLength(1);
  expect(state.waveReads).not.toContain("result-step");
});

test("ordinary student leaving the lesson cancels the late future job and ignores its audio", async ({ page }) => {
  const state = await setup(page, { missingNext: true, delayed: true, quota: 2 });
  await start(page);
  await expect.poll(() => state.speech.length).toBe(1);
  await nav(page, "대화");
  state.stopConfirmed = true;
  state.release();
  await expect.poll(() => state.cancelled).toBe(true);
  expect(state.waveReads).not.toContain("result-step");
  expect(state.speech).toHaveLength(1);
});

test("ordinary student leaving after completed future synthesis releases its owned session", async ({ page }) => {
  const state = await setup(page, { missingNext: true, nextJobDelayed: true, quota: 2 });
  await start(page);
  await expect.poll(() => state.speech.length).toBe(1);
  state.nextJobComplete = true;
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "next_speech_generation_ready"))).toBe(true);
  expect(state.cancelled).toBe(false);
  state.stopConfirmed = true;
  await nav(page, "대화");
  await expect.poll(() => state.cancelled).toBe(true);
  expect(state.speech).toHaveLength(1);
});

for (const scenario of [
  { label: "zero quota", quota: 0 },
  { label: "corrupt cache", quota: 2, corruptNext: true },
  { label: "generation unavailable", quota: 2, generationBlocked: true },
  { label: "failed job", quota: 2, nextJobFailed: true },
]) test(`ordinary student ${scenario.label} preserves the board without an automatic synthesis retry`, async ({ page }) => {
  const state = await setup(page, { missingNext: true, ...scenario });
  await start(page);
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "next_cache_prefetch_start"))).toBe(true);
  await finishClip(page);
  await expect(page.getByRole("alert")).toBeVisible();
  expect(state.speech).toHaveLength(scenario.nextJobFailed ? 1 : 0);
  expect(state.waveReads).toEqual(["source-step"]);
  await expect(page.getByRole("button", { name: "value, 2행: 9", exact: true })).toBeVisible();
});

test("ordinary student pause aborts a pending next cached clip and ignores its late response", async ({ page }) => {
  const state = await setup(page, { lateNext: true });
  await start(page);
  await expect.poll(() => state.waveReads).toEqual(["source-step", "result-step"]);
  const aborted = page.waitForEvent("requestfailed", (request) => new URL(request.url()).pathname.endsWith("/speech/result-step/audio"));
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  state.releaseNext();
  await aborted;
  await expect(page.locator('.classroom[data-step-id="source-step"]')).toBeVisible();
  expect(await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  expect(await page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "next_cache_prefetch_ready"))).toBe(false);
  expect(state.speech).toEqual([]);
});

test("ordinary student changed prefetched binding stops without generating or playing the next clip", async ({ page }) => {
  const state = await setup(page, { quota: 8 });
  await start(page);
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "next_cache_prefetch_ready"))).toBe(true);
  state.binding = "c".repeat(64);
  await finishClip(page);
  await expect(page.getByRole("alert")).toContainText("미리 준비한 음성을 폐기");
  expect(state.speech).toEqual([]);
  expect(await page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "audio_playing" && e.step_id === "result-step"))).toBe(false);
});

test("stored replay prefetches only the next cached unit during playing and consumes it after ended", async ({ page }) => {
  const state = await setup(page, { lateNext: true, queryReplay: true });
  await expect(page.getByRole("status").filter({ hasText: "저장된 수업 재생" })).toBeVisible();
  await page.getByRole("button", { name: "저장된 수업 이어 재생", exact: true }).click();
  await expect.poll(() => state.waveReads).toEqual(["source-step", "result-step"]);
  await expect(page.locator('.classroom[data-step-id="source-step"]')).toBeVisible();
  expect(await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(false);
  state.releaseNext();
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.filter((e: any) => e.type === "next_cache_prefetch_ready").length)).toBe(1);
  await finishClip(page); // Fixture-only media seek, not a real timing measurement.
  await expect(page.locator('.classroom[data-step-id="result-step"]')).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "speech_ready" && e.step_id === "result-step" && e.prefetched))).toBe(true);
  expect(state.waveReads).toEqual(["source-step", "result-step"]);
  expect(state.writes).toEqual([]);
});

test("stored replay missing cache never generates even with a positive budget", async ({ page }) => {
  const state = await setup(page, { missing: true, quota: 8, queryReplay: true });
  await page.getByRole("button", { name: "저장된 수업 이어 재생", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("새 음성은 생성하지 않았습니다");
  expect(state.writes).toEqual([]);
  await expect(page.getByRole("button", { name: "value, 2행: 9", exact: true })).toBeVisible();
});

test("stored replay rechecks the binding before consuming prefetched audio", async ({ page }) => {
  const state = await setup(page, { queryReplay: true });
  await page.getByRole("button", { name: "저장된 수업 이어 재생", exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "next_cache_prefetch_ready"))).toBe(true);
  state.binding = "c".repeat(64);
  await finishClip(page);
  await expect(page.getByRole("alert")).toContainText("미리 준비한 음성을 폐기");
  expect(state.writes).toEqual([]);
  expect(await page.evaluate(() => (window as any).lessonEvents.filter((e: any) => e.type === "audio_playing" && e.step_id === "result-step").length)).toBe(0);
});

test("stored replay interrupt discards delayed future audio and preserves the typed question without inference", async ({ page }) => {
  const state = await setup(page, { lateNext: true, queryReplay: true });
  await page.getByRole("button", { name: "저장된 수업 이어 재생", exact: true }).click();
  await expect.poll(() => state.waveReads.length).toBe(2);
  await page.getByLabel("강의 중 질문").fill("왜 이 행이 포함돼?");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  await expect(page.getByRole("alert")).toContainText("새 답변이나 음성은 생성하지 않았습니다");
  state.releaseNext();
  await expect(page.getByLabel("강의 중 질문")).toHaveValue("왜 이 행이 포함돼?");
  await expect(page.locator('.classroom[data-step-id="source-step"]')).toBeVisible();
  expect(await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  expect(state.writes).toEqual([]);
});

test("matching stored supplement replays with GET only then restores the original selected cell and position", async ({ page }) => {
  const state = await setup(page, { queryReplay: true, related: true });
  await page.getByRole("button", { name: "저장된 수업 이어 재생", exact: true }).click();
  await expect.poll(() => page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true);
  await page.getByRole("button", { name: "value, 2행: 9", exact: true }).click();
  await page.getByRole("button", { name: "저장된 보충 설명 듣기", exact: true }).click();
  await expect(page.locator('.classroom[data-lesson-record-id="savedSupplement"][data-replay-only="true"]')).toBeVisible();
  await expect.poll(() => page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true);
  await finishClip(page);
  await expect(page.locator('.classroom[data-lesson-record-id="original"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "value, 2행: 9", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true);
  expect(state.writes).toEqual([]);
  expect(await page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "lesson_resumed" && e.audio_position > 0))).toBe(true);
});

test("unrelated stored supplement is blocked without a generation request", async ({ page }) => {
  const state = await setup(page, { queryReplay: true, related: true, unrelated: true });
  await page.getByRole("button", { name: "저장된 보충 설명 듣기", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("검증 조건이 일치하지");
  expect(state.writes).toEqual([]);
  await expect(page.locator('.classroom[data-lesson-record-id="original"]')).toBeVisible();
});

test("stopping current cached preparation prevents late autoplay and explicit replay can restart", async ({ page }) => {
  const state = await setup(page, { queryReplay: true, lateCurrent: true });
  await page.getByRole("button", { name: "저장된 수업 이어 재생", exact: true }).click();
  await expect.poll(() => state.waveReads).toEqual(["source-step"]);
  await page.getByRole("button", { name: "음성 준비 중지", exact: true }).click();
  state.releaseNext();
  await expect(page.locator("audio")).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).lessonEvents.filter((e: any) => e.type === "audio_playing").length)).toBe(0);
  await page.getByRole("button", { name: "저장된 수업 이어 재생", exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.filter((e: any) => e.type === "audio_playing").length)).toBe(1);
  expect(state.writes).toEqual([]);
});


for (const action of ["seek", "unmount"] as const) {
  test(`cancelled stored supplement GET cannot replace the original after ${action}`, async ({ page }) => {
    const state = await setup(page, { queryReplay: true, related: true, lateSupplement: true });
    await page.getByRole("button", { name: "저장된 보충 설명 듣기", exact: true }).click();
    await expect.poll(() => state.supplementReads).toBe(1);
    if (action === "seek") await page.getByRole("button", { name: "다음 단계", exact: true }).last().click();
    else await nav(page, "대화");
    state.releaseNext();
    await expect.poll(() => state.supplementCompleted).toBe(true);
    await expect(page.locator('.classroom[data-lesson-record-id="savedSupplement"]')).toHaveCount(0);
    if (action === "seek") await expect(page.locator('.classroom[data-lesson-record-id="original"][data-step-id="result-step"]')).toBeVisible();
    else await expect(page.getByLabel("질문 입력")).toBeVisible();
    expect(state.writes).toEqual([]);
    expect(await page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "saved_supplement_loaded"))).toBe(false);
  });
}

test("manual stored clip resumes after supplement without changing into continuous playback", async ({ page }) => {
  const state = await setup(page, { queryReplay: true, related: true });
  await page.getByRole("button", { name: "현재 단계 음성 준비", exact: true }).click();
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect.poll(() => page.locator("audio").evaluate((a: HTMLAudioElement) => a.currentTime > 0)).toBe(true);
  await page.getByRole("button", { name: "저장된 보충 설명 듣기", exact: true }).click();
  await expect(page.locator('.classroom[data-lesson-record-id="savedSupplement"]')).toBeVisible();
  await expect.poll(() => page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true);
  await finishClip(page);
  await expect(page.locator('.classroom[data-lesson-record-id="original"]')).toBeVisible();
  await expect.poll(() => page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true);
  await finishClip(page);
  await expect.poll(() => page.locator("audio").evaluate((a: HTMLAudioElement) => a.ended)).toBe(true);
  await expect(page.locator('.classroom[data-step-id="source-step"]')).toBeVisible();
  expect(state.writes).toEqual([]);
});

test("returning from saved supplement stops current audio before a delayed original GET", async ({ page }) => {
  const state = await setup(page, { queryReplay: true, related: true, lateReturn: true });
  await page.getByRole("button", { name: "저장된 보충 설명 듣기", exact: true }).click();
  await expect(page.locator('.classroom[data-lesson-record-id="savedSupplement"]')).toBeVisible();
  await expect.poll(() => page.locator("audio").evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true);
  await page.getByRole("button", { name: "원래 강의로 돌아가기", exact: true }).click();
  await expect.poll(() => state.returnReads).toBe(1);
  expect(await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  state.releaseNext();
  await expect(page.locator('.classroom[data-lesson-record-id="original"]')).toBeVisible();
  expect(state.writes).toEqual([]);
});

test("server plan change cannot play prefetched speech over the preserved old board", async ({ page }) => {
  const state = await setup(page, { queryReplay: true });
  await page.getByRole("button", { name: "저장된 수업 이어 재생", exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "next_cache_prefetch_ready"))).toBe(true);
  state.planChanged = true;
  await finishClip(page);
  await expect(page.getByRole("alert")).toBeVisible();
  expect(await page.evaluate(() => (window as any).lessonEvents.some((e: any) => e.type === "audio_playing" && e.step_id === "result-step"))).toBe(false);
  expect(state.writes).toEqual([]);
});
