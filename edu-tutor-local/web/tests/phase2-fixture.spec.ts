import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
const fixtureOutput =
  process.env.EDU_UI_ARTIFACT_DIR ?? "test-results-phase2-fixture";
const token = "PHASE2_UI_FIXTURE_ONLY",
  audioId = "d".repeat(64);
const table = {
  type: "table",
  element_id: "stable-original",
  table_name: "exam_result",
  slot: "main",
  columns: ["name", "score"],
  rows: [
    ["박강열", 80],
    ["유성재", null],
    ["김현수", 100],
  ],
  row_ids: ["r0", "r1", "r2"],
  column_ids: ["name", "score"],
  cell_ids: [
    ["r0-name", "r0-score"],
    ["r1-name", "r1-score"],
    ["r2-name", "r2-score"],
  ],
  caption: "UI fixture 원본",
  timing: { start: 0, end: 0 },
};
const original: any = {
  schema_version: "1.0",
  lesson_id: "original",
  title: "UI fixture · COUNT",
  goal: "상호작용 시험",
  question_text: "시험용 문제",
  problem_source: "typed_user_input",
  provenance: "tool_derived",
  source_refs: [],
  problem_revision: 1,
  verification: {
    status: "calculation_checked",
    scope: "명시적 UI fixture, 모델 미실행",
    limitations: ["교육 품질 검증 아님"],
  },
  final_summary: "시험 종료",
  steps: [
    {
      id: "count",
      title: "전체 세 행",
      speech: "UI fixture 오디오",
      board_actions: [
        table,
        {
          type: "highlight",
          target_element_id: "stable-original",
          row_indices: [0, 1, 2],
          style: "background",
          timing: { start: 0, end: 0 },
        },
      ],
      gesture: { kind: "point", target_element_id: "stable-original" },
    },
    {
      id: "shape",
      title: "같은 경로로 쓰기",
      speech: "UI fixture 경로",
      board_actions: [
        {
          type: "line",
          element_id: "line",
          geometry: { x1: 0.1, y1: 0.8, x2: 0.7, y2: 0.8 },
          timing: { start: 0, end: 1 },
        },
      ],
      gesture: { kind: "write", target_element_id: "line" },
    },
    {
      id: "look",
      title: "칠판 보기",
      speech: "보기",
      board_actions: [],
      gesture: { kind: "look_board", target_element_id: "stable-original" },
    },
    {
      id: "explain",
      title: "설명",
      speech: "설명",
      board_actions: [],
      gesture: { kind: "explain", target_element_id: "stable-original" },
    },
    {
      id: "idle",
      title: "학생 보기",
      speech: "보기",
      board_actions: [],
      gesture: { kind: "idle", target_element_id: null },
    },
  ],
};
function wave() {
  const rate = 8000,
    length = rate * 8,
    b = Buffer.alloc(44 + length * 2);
  b.write("RIFF");
  b.writeUInt32LE(b.length - 8, 4);
  b.write("WAVE", 8);
  b.write("fmt ", 12);
  b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22);
  b.writeUInt32LE(rate, 24);
  b.writeUInt32LE(rate * 2, 28);
  b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34);
  b.write("data", 36);
  b.writeUInt32LE(length * 2, 40);
  for (let i = 0; i < length; i++)
    b.writeInt16LE(
      Math.round(Math.sin((i / rate) * Math.PI * 440) * 3000),
      44 + i * 2,
    );
  return b;
}
async function setup(page: Page, { batch = false, compact = false } = {}) {
  let sent: any[] = [],
    messages: any[] = [],
    busy = false,
    voiceStarted = false,
    cancelled = false,
    invalid = false;
  const plans: any = { original: structuredClone(original) };
  if (compact) plans.original.steps = plans.original.steps.slice(0, 3);
  const voiceRequests: any[] = [];
  const session = { id: "session", title: "UI fixture", generation_epoch: 0 };
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem("edu-session", "session");
    localStorage.setItem("edu-lesson", "original");
    localStorage.setItem("edu-tab", "classroom");
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api", ""),
      method = route.request().method();
    let body: any = {};
    try {
      body = route.request().postDataJSON() || {};
    } catch {}
    let value: any = {};
    if (path === "/capabilities")
      value = {
        fixture: true,
        text: { available: true },
        speech: { available: true },
        vision: { available: false },
        training: { available: false },
      };
    else if (path === "/models")
      value = { model_id: "UI fixture", modules: [] };
    else if (path === "/doctor") value = {};
    else if (path === "/sessions")
      value = method === "POST" ? session : [session];
    else if (path === "/sessions/session/messages") {
      if (method === "POST") {
        if (busy) {
          await route.fulfill({
            status: 409,
            json: { detail: "UI fixture GPU busy" },
          });
          return;
        }
        sent.push(body);
        const n = sent.length;
        messages.push(
          { id: "u" + n, role: "user", content: body.content },
          {
            id: "a" + n,
            role: "assistant",
            content: "UI fixture 보충 설명 " + n,
          },
        );
        value = { job_id: "chat" + n };
      } else value = messages;
    } else if (path.startsWith("/jobs/chat"))
      value = {
        id: path.split("/")[2],
        state: "succeeded",
        result: { message_id: "a" + sent.length },
      };
    else if (path === "/lessons" && method === "POST") {
      const n = Number(body.message_id.slice(1));
      const plan = structuredClone(original);
      plan.lesson_id = "supplement" + n;
      plan.title = "UI fixture 보충 " + n;
      plan.steps = plan.steps.slice(0, 1);
      plan.steps[0].speech = "UI fixture 보충 설명";
      if (n === 2) {
        plan.steps[0].board_actions[0].rows = [
          ["박강열", null],
          ["유성재", null],
          ["김현수", null],
        ];
        plan.steps[0].board_actions[0].caption = "별도 가정 · UI fixture";
      }
      plans[plan.lesson_id] = plan;
      value = { id: plan.lesson_id, plan, valid: true };
    } else if (path.match(/^\/lessons\/[^/]+\/speech$/)) {
      const id = path.split("/")[2];
      if (method === "POST") {
        voiceRequests.push(body);
        voiceStarted = true;
        value = { job_id: "voice" };
      } else
        value = {
          available: true,
          steps:
            !batch || voiceStarted
              ? plans[id].steps.map((step: any) => ({
                  step_id: step.id,
                  audio_url: "/api/audio/" + audioId,
                  duration: 8,
                }))
              : [],
        };
    } else if (path === "/jobs/voice/cancel") {
      cancelled = true;
      value = { state: "cancelled" };
    } else if (path === "/jobs/voice")
      value = { id: "voice", state: cancelled ? "cancelled" : "running" };
    else if (path.startsWith("/audio/")) {
      await route.fulfill({ contentType: "audio/wav", body: wave() });
      return;
    } else if (path.startsWith("/lessons/")) {
      const id = path.split("/")[2];
      value = {
        id,
        plan: plans[id],
        valid: !invalid,
        invalidated_reason: invalid ? "사진 원문 수정 fixture" : undefined,
      };
    } else if (path === "/jobs") value = [];
    await route.fulfill({ json: value });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page.getByLabel("관리 토큰", { exact: true }).fill(token);
  await page.getByRole("button", { name: "연결", exact: true }).click();
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible();
  await nav(page, "강의실");
  return {
    sent: () => sent,
    setBusy: (value: boolean) => (busy = value),
    invalidate: () => (invalid = true),
    voiceStarted: () => voiceStarted,
    voiceRequests: () => voiceRequests,
  };
}
async function nav(page: Page, name: string) {
  const menu = page.getByRole("button", { name: "메뉴 열기" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name, exact: true })
    .click();
}
async function board(page: Page) {
  return page.locator(".chalk-board").evaluate((element) => ({
    tables: Array.from(element.querySelectorAll("[data-board-element]")).map(
      (e) => ({
        id: (e as HTMLElement).dataset.boardElement,
        text: e.textContent,
      }),
    ),
    cells: Array.from(element.querySelectorAll("[data-cell-id]")).map((e) => ({
      id: (e as HTMLElement).dataset.cellId,
      text: e.textContent,
      class: e.className,
    })),
    rows: Array.from(element.querySelectorAll("[data-row-id]")).map((e) => ({
      id: (e as HTMLElement).dataset.rowId,
      class: e.className,
    })),
  }));
}

test("T0 UI: two supplements restore populated table IDs, values, highlights and paused audio position", async ({
  page,
}) => {
  const state = await setup(page);
  await page
    .getByRole("button", { name: "score, 2행: NULL", exact: true })
    .click();
  await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect
    .poll(() =>
      page.locator("audio").evaluate((a: HTMLAudioElement) => a.currentTime),
    )
    .toBeGreaterThan(0.3);
  await page
    .getByLabel("강의 중 질문")
    .fill("점수가 없는데 왜 사람 수에는 들어가?");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  const before = await board(page),
    position = state.sent()[0].lesson_context.audio_position;
  expect(state.sent()[0].lesson_context.selected_cell.cell_id).toBe("r1-score");
  expect(state.sent()[0].lesson_context.board_snapshot.highlights).toHaveLength(
    1,
  );
  await nav(page, "대화");
  await page
    .getByRole("button", { name: "강의 보기", exact: true })
    .last()
    .click();
  await page
    .getByRole("button", { name: "score, 2행: NULL", exact: true })
    .click();
  await page.getByLabel("별도 가정: 이 열의 값을 모두 NULL로 보기").check();
  await page.getByLabel("강의 중 질문").fill("그럼 셋 다 점수가 없으면?");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  await nav(page, "대화");
  await page
    .getByRole("button", { name: "강의 보기", exact: true })
    .last()
    .click();
  expect(state.sent()[1].hypothesis).toEqual({
    kind: "all_null",
    table: "exam_result",
    column: "score",
  });
  await expect(
    page.getByText("별도 가정 · UI fixture", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "원래 강의로 돌아가기", exact: true })
    .click();
  // Returning validates the saved source with the server before committing
  // the restored plan. Wait for that commit rather than the click dispatch.
  await expect.poll(() => board(page)).toEqual(before);
  await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
  await expect(page.locator("audio")).toHaveCount(1);
  await expect
    .poll(() =>
      page.locator("audio").evaluate((a: HTMLAudioElement) => a.currentTime),
    )
    .toBeCloseTo(position, 1);
  expect(
    await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused),
  ).toBe(true);
  mkdirSync(fixtureOutput, { recursive: true });
  writeFileSync(
    `${fixtureOutput}/two-questions.json`,
    JSON.stringify(
      {
        tier: "T0_UI_fixture",
        model_inference: "not_run",
        before,
        after: await board(page),
        position,
        requests: state.sent(),
      },
      null,
      2,
    ),
  );
});

test("T0 UI: 409 preserves question and only explicit retry submits", async ({
  page,
}) => {
  const state = await setup(page);
  state.setBusy(true);
  await nav(page, "대화");
  await page.getByLabel("질문 입력").fill("남겨 둘 질문");
  await page.getByRole("button", { name: "질문 전송" }).click();
  await expect(page.getByLabel("질문 입력")).toHaveValue("남겨 둘 질문");
  await expect(
    page.getByRole("button", { name: "보관한 질문 다시 전송" }),
  ).toBeVisible();
  expect(state.sent()).toHaveLength(0);
  state.setBusy(false);
  await page.waitForTimeout(600);
  expect(state.sent()).toHaveLength(0);
  await page.getByRole("button", { name: "보관한 질문 다시 전송" }).click();
  await expect.poll(() => state.sent().length).toBe(1);
});

test("T0 UI: first complete clip plays before job completion and pen matches drawing", async ({
  page,
}) => {
  const state = await setup(page, { batch: true });
  await page
    .getByRole("button", { name: "다음 단계", exact: true })
    .last()
    .click();
  await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
  await expect(
    page.getByRole("button", { name: "음성 재생", exact: true }),
  ).toBeVisible();
  expect(state.voiceStarted()).toBe(true);
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect(page.locator("[data-pen-tip]")).toBeVisible();
  await page.setViewportSize({ width: 900, height: 900 });
  const delta = await page.locator(".shape-layer").evaluate((svg) => {
    const points = svg
      .querySelector("polyline")!
      .getAttribute("points")!
      .split(" ")
      .at(-1)!
      .split(",")
      .map(Number);
    const pen = svg.querySelector("[data-pen-tip]")!;
    return Math.hypot(
      points[0] - Number(pen.getAttribute("data-tip-x")),
      points[1] - Number(pen.getAttribute("data-tip-y")),
    );
  });
  expect(delta).toBeLessThan(0.001);
  await page
    .getByRole("button", { name: "다음 단계", exact: true })
    .last()
    .click();
  await expect(page.locator(".avatar")).toHaveAttribute(
    "data-gesture",
    "look_board",
  );
  await page
    .getByRole("button", { name: "다음 단계", exact: true })
    .last()
    .click();
  await expect(page.locator(".avatar")).toHaveAttribute(
    "data-gesture",
    "explain",
  );
  await page
    .getByRole("button", { name: "다음 단계", exact: true })
    .last()
    .click();
  await expect(page.locator(".avatar")).toHaveAttribute("data-gesture", "idle");
});

test("T0 UI: a short plan requests one batch and exposes its first valid unit", async ({
  page,
}) => {
  const state = await setup(page, { batch: true, compact: true });
  await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
  await expect(
    page.getByRole("button", { name: "음성 재생", exact: true }),
  ).toBeVisible();
  expect(state.voiceRequests()).toHaveLength(1);
  expect(state.voiceRequests()[0]).not.toHaveProperty("step_id");
});

test("T0 UI: changed source cannot be replaced by old return snapshot", async ({
  page,
}) => {
  const state = await setup(page);
  await page.getByLabel("강의 중 질문").fill("추가 질문");
  await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
  await nav(page, "대화");
  await page
    .getByRole("button", { name: "강의 보기", exact: true })
    .last()
    .click();
  state.invalidate();
  await page
    .getByRole("button", { name: "원래 강의로 돌아가기", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "사진 원문 수정 fixture" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "UI fixture 보충 1", exact: true }),
  ).toBeVisible();
});
