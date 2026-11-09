import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync(new URL("../src/lesson.fixture.json", import.meta.url), "utf8"),
);
const token = "UI_TEST_FIXTURE_ONLY_NOT_A_REAL_SECRET";
const fixtureOutput = process.env.EDU_UI_ARTIFACT_DIR ?? "test-results";
async function installFixture(page: Page, { completeAfterUserSnapshot = false } = {}) {
  let messages: any[] = [],
    sessions: any[] = [],
    job: any = {
      id: "j1",
      state: "running",
      kind: "chat",
      partial_text: "UI fixture: 응답을 생성하고 있습니다.",
    },
    photo: any = {
      id: "p1",
      question: "",
      sql: "",
      tables: [],
      choices: [],
      unreadable_regions: [],
      missing_conditions: [],
      confirmed: false,
      revision: 1,
      recognition_status: "not_run",
    };
  let sends = 0,
    jobReads = 0,
    messageReads = 0,
    completionSnapshotTaken = false;
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname.replace("/api", ""),
      method = req.method();
    let body: any = {};
    try {
      body = req.postDataJSON() || {};
    } catch {}
    if (
      req.headers().authorization !== `Bearer ${token}` &&
      path != "/health"
    ) {
      await route.fulfill({
        status: 401,
        json: { detail: "UI fixture 인증 필요" },
      });
      return;
    }
    let value: any;
    if (path === "/capabilities")
      value = {
        fixture: true,
        text: { available: true, reason: "명시적 UI fixture" },
        speech: { available: false, reason: "fixture 음성 미준비" },
        vision: { available: false },
        training: { available: false },
        validation: { T0: "fixture_only", T2: "not_run" },
      };
    else if (path === "/models")
      value = {
        installed: false,
        ready: false,
        model_id: "UI-fixture/no-real-model",
        reason: "실제 모델이 아닌 UI 시험 상태",
        modules: [],
      };
    else if (path === "/doctor")
      value = {
        gpu: { status: "N/A", reason: "UI fixture에서는 수집하지 않음" },
      };
    else if (path === "/sessions" && method === "GET") value = sessions;
    else if (path === "/sessions" && method === "POST") {
      value = { id: "s1", title: body.title, generation_epoch: 0 };
      sessions = [value];
    } else if (path === "/sessions/s1/messages" && method === "GET") {
      messageReads++;
      value = structuredClone(messages);
      if (completeAfterUserSnapshot && messages.some((m) => m.role === "user") && !completionSnapshotTaken) {
        // Deterministic boundary: snapshot has only the user, but the very next
        // job read is terminal and must trigger a final messages refresh.
        completionSnapshotTaken = true;
        job = { ...job, state: "completed", partial_text: "" };
        messages.push({ id: "a1", role: "assistant", content: "완료 경계 fixture 최종 답변", sources: [] });
      }
    } else if (path === "/sessions/s1/messages" && method === "POST") {
      sends++;
      messages.push({ id: `u${sends}`, role: "user", content: body.content });
      job = {
        id: "j1",
        state: "running",
        kind: "chat",
        partial_text: "UI fixture: 응답을 생성하고 있습니다.",
      };
      jobReads = 0;
      value = { job_id: "j1", request_id: "test", generation_epoch: 0 };
    } else if (path === "/jobs/j1/cancel") {
      job = {
        ...job,
        state: "cancelled",
        cancel_requested: true,
        partial_text: "늦게 도착한 이전 응답",
      };
      value = job;
    } else if (path === "/jobs/j1") {
      jobReads++;
      value = job;
    } else if (path === "/jobs") value = [];
    else if (path === "/documents") value = [];
    else if (path === "/datasets")
      value = {
        datasets: [
          {
            id: "demo",
            valid: true,
            record_count: 44,
            counts: { train: 24, validation: 8, test: 12 },
            human_review: "not_reviewed",
          },
        ],
      };
    else if (path === "/adapters")
      value = { adapters: [], active_adapter: null, history: [] };
    else if (path === "/evaluations")
      value = { reports: [], notice: "UI fixture · 실제 평가 미실행" };
    else if (path === "/evaluations/reviews") value = { reviews: [] };
    else if (path === "/training/config")
      value = {
        profile: "demo",
        production_supported: false,
        training: {
          bnb_4bit_quant_type: "nf4",
          lora_r: 8,
          lora_alpha: 16,
          batch_size: 1,
          gradient_accumulation_steps: 8,
          learning_rate: 0.0001,
          max_sequence_length: 512,
          target_modules: ["q_proj", "v_proj"],
        },
        budgets: {},
      };
    else if (path === "/lessons/demo" || path === "/lessons/demo-count-null")
      value = {
        id: "demo-count-null",
        plan: fixture,
        is_demo: true,
        status: "demo_fixture",
      };
    else if (path === "/lessons" && method === "POST")
      value = {
        id: "generated-fixture",
        plan: null,
        fallback_text: messages.find((m) => m.id === body.message_id)?.content,
        status: "text_fallback",
        is_demo: false,
      };
    else if (path === "/photos" && method === "POST") value = photo;
    else if (path === "/photos/p1" && method === "PATCH") {
      photo = {
        ...photo,
        ...body,
        confirmed: false,
        revision: photo.revision + 1,
      };
      value = photo;
    } else if (path === "/photos/p1/confirm") {
      photo = {
        ...photo,
        confirmed: true,
        confirmed_at: "fixture",
        confirmed_by: "local_user",
      };
      value = photo;
    } else if (path === "/photos/p1/solve") {
      if (!photo.confirmed) {
        await route.fulfill({ status: 409, json: { detail: "원문 미확정" } });
        return;
      }
      value = { job_id: "j1", session_id: "s1" };
    } else {
      await route.fulfill({
        status: 404,
        json: { detail: `UI fixture 미정의: ${method} ${path}` },
      });
      return;
    }
    await route.fulfill({ json: value });
  });
  return {
    sends: () => sends,
    messageReads: () => messageReads,
    completionSnapshotTaken: () => completionSnapshotTaken,
    finish: () => {
      job = { ...job, state: "completed", partial_text: "" };
      messages.push({
        id: "a1",
        role: "assistant",
        content: 'UI fixture 응답. <img src=x onerror="window.__xss=1">',
        sources: [],
      });
    },
    jobReads: () => jobReads,
  };
}
async function connect(page: Page) {
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page.getByLabel("관리 토큰", { exact: true }).fill(token);
  await page.getByRole("button", { name: "연결", exact: true }).click();
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible();
}
async function nav(page: Page, name: string) {
  const mobile = page.getByRole("button", { name: "메뉴 열기" });
  if (await mobile.isVisible()) await mobile.click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name, exact: true })
    .click();
}
async function demo(page: Page) {
  await nav(page, "강의실");
  await page.getByRole("button", { name: "설명용 예시 열기" }).click();
  await expect(
    page.getByText("데모 데이터 재생", { exact: true }),
  ).toBeVisible();
}
test("UI fixture: Korean IME, streamed partial, cancel and stale display guard", async ({
  page,
}) => {
  const server = await installFixture(page);
  await page.goto("/");
  await connect(page);
  await nav(page, "대화");
  const input = page.getByLabel("질문 입력");
  await input.fill("한글 입력 검증");
  await input.dispatchEvent("compositionstart");
  await input.press("Enter");
  expect(server.sends()).toBe(0);
  await input.dispatchEvent("compositionend");
  await input.press("Shift+Enter");
  expect(server.sends()).toBe(0);
  await input.press("Enter");
  await expect(page.getByRole("button", { name: "생성 중지" })).toBeVisible();
  await expect(
    page.getByText("UI fixture: 응답을 생성하고 있습니다.", { exact: true }),
  ).toBeVisible();
  expect(server.sends()).toBe(1);
  await page.getByRole("button", { name: "생성 중지" }).click();
  await expect(page.getByRole("button", { name: "질문 전송" })).toBeVisible();
  await expect(page.getByText("늦게 도착한 이전 응답")).toHaveCount(0);
});
test("UI fixture: generated output stays text and stored draft survives reconnect", async ({
  page,
}) => {
  const server = await installFixture(page);
  await page.goto("/");
  await connect(page);
  await nav(page, "대화");
  await page.getByLabel("질문 입력").fill("안전한 출력 확인");
  await page.getByRole("button", { name: "질문 전송" }).click();
  await expect.poll(server.sends).toBe(1);
  server.finish();
  await expect(
    page.getByText("UI fixture 응답.", { exact: false }),
  ).toBeVisible();
  expect(await page.evaluate(() => Boolean((window as any).__xss))).toBe(false);
  await expect(page.locator(".message-content img")).toHaveCount(0);
  await page.getByLabel("질문 입력").fill("새로고침해도 남아야 할 초안");
  await page.reload();
  await expect(page.getByLabel("질문 입력")).toHaveValue(
    "새로고침해도 남아야 할 초안",
  );
  await expect(
    page.getByRole("button", { name: "서버 연결 필요" }),
  ).toBeVisible();
  await connect(page);
  await nav(page, "대화");
  await expect(
    page.getByText("UI fixture 응답.", { exact: false }),
  ).toBeVisible();
});
for (const size of [
  { width: 1440, height: 900 },
  { width: 1280, height: 720 },
  { width: 390, height: 844 },
]) {
  test(`UI fixture: board replay, pointer and responsive layout ${size.width}x${size.height}`, async ({
    page,
  }, info) => {
    await page.setViewportSize(size);
    await installFixture(page);
    await page.goto("/");
    await page.screenshot({
      path: `${fixtureOutput}/chat-${size.width}.png`,
      fullPage: true,
    });
    await connect(page);
    await demo(page);
    await expect(page.getByRole("table")).toBeVisible();
    await page.locator('button[aria-label="다음 단계"]').click();
    await expect(page.locator('[data-board-element="query"]')).toBeVisible();
    await page.locator('button[aria-label="다음 단계"]').click();
    await expect(page.locator('[data-board-element="dev_avg"]')).toBeVisible();
    await page.getByRole("button", { name: "이전 단계", exact: true }).click();
    await expect(page.locator('[data-board-element="dev_avg"]')).toHaveCount(0);
    await expect(page.locator('[data-board-element="query"]')).toBeVisible();
    const pointer = await page.evaluate(() => {
      const line = document.querySelector('[data-testid="avatar-pointer"]')!,
        target = document
          .querySelector('[data-board-element="query"]')!
          .getBoundingClientRect(),
        root = document.querySelector(".chalk-stage")!.getBoundingClientRect();
      return {
        x: Number(line.getAttribute("x2")),
        expected: target.right - root.left - 14,
        overflow: document.documentElement.scrollWidth > window.innerWidth,
      };
    });
    expect(Math.abs(pointer.x - pointer.expected)).toBeLessThan(1);
    expect(pointer.overflow).toBe(false);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: `${fixtureOutput}/lecture-${size.width}.png`,
      fullPage: true,
    });
    await info.attach("fixture screenshot", {
      path: `${fixtureOutput}/lecture-${size.width}.png`,
      contentType: "image/png",
    });
    await page.reload();
    await connect(page);
    await nav(page, "강의실");
    await expect(page.locator('[data-board-element="query"]')).toBeVisible();
    await expect(page.locator('[data-board-element="dev_avg"]')).toHaveCount(0);
  });
}
test("UI fixture: manual photo correction cannot solve before save and confirmation", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/");
  await connect(page);
  await nav(page, "대화");
  await page.getByRole("button", { name: "문제 사진 첨부" }).click();
  await page.getByLabel("문제 사진 업로드").setInputFiles({
    name: "self-authored-pixel.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/mXcAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  const solve = page.getByRole("button", { name: "확정한 문제 풀이" });
  await expect(solve).toBeDisabled();
  await page
    .getByLabel("문제 본문")
    .fill("직접 작성한 문제: 2 + 3은 얼마인가요?");
  await expect(
    page.getByRole("button", { name: "이 원문으로 확정" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "교정 저장" }).click();
  await page.getByRole("button", { name: "이 원문으로 확정" }).click();
  await expect(solve).toBeEnabled();
  await page.getByLabel("문제 본문").fill("숫자 교정: 2 + 4는 얼마인가요?");
  await expect(solve).toBeDisabled();
  await expect(page.getByText("자동 인식 미실행 · 직접 입력")).toBeVisible();
});
test("UI fixture: admin no invented metrics and all six sections are usable", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/");
  await connect(page);
  await nav(page, "교육자료");
  await expect(page.getByText("아직 등록한 자료가 없습니다")).toBeVisible();
  await nav(page, "학습·평가");
  await expect(page.getByText("아직 실행 기록이 없습니다")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "예산 확인 후 학습" }),
  ).toBeDisabled();
  await nav(page, "모델 분석");
  await expect(page.getByText("로드된 모듈 정보가 없습니다")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "모델 구조도" }),
  ).toBeVisible();
  await nav(page, "설정");
  await expect(
    page.getByText("토큰은 현재 브라우저 메모리에만 보관합니다.", {
      exact: false,
    }),
  ).toBeVisible();
});
test("UI fixture: 200 percent text preserves narrow layout and keyboard controls", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installFixture(page);
  await page.goto("/");
  await connect(page);
  await page.getByLabel("화면 글자 크기").selectOption("2");
  await demo(page);
  await expect(
    page.getByRole("button", { name: "이전 단계", exact: true }),
  ).toBeDisabled();
  await page.locator('button[aria-label="다음 단계"]').click();
  await expect(page.locator('[data-board-element="query"]')).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `${fixtureOutput}/lecture-390-text200.png`,
    fullPage: true,
  });
});
test("UI audio fixture: playback pause resume interruption uses actual audio clock", async ({
  page,
}) => {
  await installFixture(page);
  const sampleRate = 8000,
    length = sampleRate * 5,
    data = Buffer.alloc(44 + length * 2);
  data.write("RIFF");
  data.writeUInt32LE(data.length - 8, 4);
  data.write("WAVE", 8);
  data.write("fmt ", 12);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(1, 22);
  data.writeUInt32LE(sampleRate, 24);
  data.writeUInt32LE(sampleRate * 2, 28);
  data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(length * 2, 40);
  for (let i = 0; i < length; i++)
    data.writeInt16LE(
      Math.round(Math.sin((i / sampleRate) * Math.PI * 440) * 5000),
      44 + i * 2,
    );
  const audioId = "a".repeat(64);
  await page.route("**/api/capabilities", (route) =>
    route.fulfill({
      json: {
        fixture: true,
        text: { available: true },
        speech: { available: true },
        vision: { available: false },
        training: { available: false },
      },
    }),
  );
  await page.route("**/api/lessons/demo-count-null/speech", (route) =>
    route.fulfill({
      json: {
        available: true,
        steps: [
          { step_id: "s1", audio_url: `/api/audio/${audioId}`, duration: 5 },
        ],
      },
    }),
  );
  await page.route(`**/api/audio/${audioId}`, (route) =>
    route.fulfill({ contentType: "audio/wav", body: data }),
  );
  await page.goto("/");
  await connect(page);
  await demo(page);
  await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.currentTime),
    )
    .toBeGreaterThan(0.2);
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  expect(
    await page
      .locator("audio")
      .evaluate((audio: HTMLAudioElement) => audio.paused),
  ).toBe(true);
  const pausedAt = await page
    .locator("audio")
    .evaluate((audio: HTMLAudioElement) => audio.currentTime);
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.currentTime),
    )
    .toBeGreaterThan(pausedAt + 0.1);
  await page.getByLabel("강의 중 질문").fill("지금 단계가 궁금합니다");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  await expect(
    page.getByText("강의를 멈추고 현재 칠판을 보존했습니다."),
  ).toBeVisible();
  expect(
    await page
      .locator("audio")
      .evaluate((audio: HTMLAudioElement) => audio.paused),
  ).toBe(true);
  await expect(page.getByRole("table")).toBeVisible();
  await page.getByRole("button", { name: "원래 강의로 돌아가기" }).click();
  await expect(page.getByRole("table")).toBeVisible();
});
test("UI fixture: return from interruption explanation restores the original board", async ({
  page,
}) => {
  const server = await installFixture(page);
  await page.goto("/");
  await connect(page);
  await demo(page);
  await page.locator('button[aria-label="다음 단계"]').click();
  await page.getByLabel("강의 중 질문").fill("이 SQL을 더 쉽게 설명해 주세요");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  await expect.poll(server.sends).toBe(1);
  server.finish();
  await nav(page, "대화");
  await expect(
    page.getByText("UI fixture 응답.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "강의 보기", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "설명 텍스트" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "원래 강의로 돌아가기", exact: true })
    .click();
  await expect(page.locator('[data-board-element="query"]')).toBeVisible();
  await expect(page.locator('[data-board-element="dev_avg"]')).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: fixture.title }),
  ).toBeVisible();
});

test("UI fixture: matching report comparison requires user's rubric choices and retains actual module metadata", async ({
  page,
}) => {
  await installFixture(page);
  const reports = ["baseline-fixture", "adapter-fixture"].map((id, index) => ({
    run_id: id,
    artifact: "evaluation.json",
    report: {
      status: "completed",
      dataset_sha256: "UI_FIXTURE_TEST_HASH",
      protocol: {
        version: 1,
        max_new_tokens: 256,
        do_sample: false,
        rag: false,
      },
      adapter: index ? "fixture-adapter" : null,
      items: [
        {
          id: "same-fixture-question",
          question: "UI fixture 공통 질문: COUNT는 무엇인가요?",
          text: index ? "UI fixture 어댑터 답변" : "UI fixture 기반 답변",
          finish_reason: "eos",
          sql_result: { status: "executed", match: index === 0 },
        },
      ],
    },
  }));
  const reviews: any[] = [];
  await page.route("**/api/evaluations", (route) =>
    route.fulfill({
      json: { reports, notice: "UI fixture 비교 · 실제 모델 평가 아님" },
    }),
  );
  await page.route("**/api/evaluations/reviews", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      reviews.push({
        ...body,
        id: "fixture-review",
        reviewed_at: "2026-10-25T00:00:00Z",
        report_sha256: "FIXTURE_HASH",
      });
      await route.fulfill({ status: 201, json: reviews[0] });
    } else await route.fulfill({ json: { reviews } });
  });
  await page.route("**/api/models", (route) =>
    route.fulfill({
      json: {
        installed: true,
        ready: true,
        model_id: "UI-fixture-model",
        active_adapter: "next-selected-fixture",
        last_loaded_adapter: "historical-fixture",
        last_loaded_at: "2026-10-25T00:00:00Z",
        resident: false,
        modules: [
          {
            name: "layer.q_proj.lora_A",
            type: "Linear",
            parameters: 16,
            lora: true,
            tensors: [
              {
                name: "weight",
                shape: [2, 8],
                dtype: "torch.float32",
                device: "cuda:0",
                trainable: false,
              },
            ],
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await connect(page);
  await nav(page, "학습·평가");
  const comparison = page.locator(".evaluation-comparison");
  await expect(comparison).toContainText("UI fixture 공통 질문");
  await comparison
    .getByText("직접 검토 점수 입력 · 저장 기록 0개", { exact: true })
    .first()
    .click();
  const save = comparison.getByRole("button", { name: "내 검토 저장" }).first();
  await expect(save).toBeDisabled();
  expect(reviews).toHaveLength(0);
  for (const [label, score] of [
    ["정확성", "2"],
    ["명료성", "3"],
    ["근거성", "1"],
  ])
    await page
      .getByLabel(`baseline-fixture ${label}`, { exact: true })
      .selectOption(score);
  await page
    .getByLabel("baseline-fixture 검토 메모")
    .fill("UI fixture만 검토. 실제 모델 사람 평가가 아님.");
  await save.click();
  await expect(comparison).toContainText("사용자 검토 기록");
  expect(reviews[0].scores).toEqual({
    correctness: 2,
    clarity: 3,
    grounding: 1,
  });
  await page.getByLabel("오른쪽 평가").selectOption("baseline-fixture");
  await expect(comparison).toContainText("공통 문항이 없습니다");
  await expect(comparison.locator(".comparison-answer")).toHaveCount(0);
  await nav(page, "모델 분석");
  await expect(
    page.getByText("next-selected-fixture", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("historical-fixture", { exact: true }),
  ).toBeVisible();
  await page.locator(".module-layer > summary").click();
  await page.locator(".module-children summary").click();
  await expect(page.getByRole("table")).toContainText("2 × 8");
  await expect(page.getByRole("table")).toContainText("torch.float32");
  await expect(page.getByRole("table")).toContainText("cuda:0");
});


test("terminal job after an earlier user-only snapshot still displays its final answer", async ({ page }) => {
  const server = await installFixture(page, { completeAfterUserSnapshot: true });
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem("edu-session", "s1");
    localStorage.setItem("edu-tab", "chat");
  });
  await page.goto("/");
  const initialRead = page.waitForResponse((r) => r.url().endsWith("/api/sessions/s1/messages") && r.request().method() === "GET");
  await connect(page);
  await (await initialRead).finished();
  await expect.poll(server.messageReads).toBe(1);
  await nav(page, "대화");
  await page.getByLabel("질문 입력").fill("완료 경계 검증");
  await page.getByRole("button", { name: "질문 전송", exact: true }).click();
  await expect(page.getByText("완료 경계 fixture 최종 답변", { exact: true })).toBeVisible();
  expect(server.completionSnapshotTaken()).toBe(true);
  expect(server.jobReads()).toBe(1);
  expect(server.messageReads()).toBeGreaterThanOrEqual(3);
});
