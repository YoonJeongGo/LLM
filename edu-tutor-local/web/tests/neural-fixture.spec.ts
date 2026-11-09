import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const token = "CPU_UI_FIXTURE_NOT_REAL_AUTH";
const root = "test-results-neural";
const nodes = [
  { path: "model.embed_tokens", role: "embedding", type: "FixtureEmbedding" },
  ...Array.from({ length: 5 }, (_, i) => ({
    path: `model.layers.${i}`,
    role: "block",
    type: "FixtureBlock",
    verified_flow: [
      "input_layernorm",
      "self_attn",
      "residual_add",
      "post_attention_layernorm",
      "mlp",
      "residual_add",
    ],
    components: [
      { path: `model.layers.${i}.self_attn`, type: "FixtureAttention" },
    ],
  })),
  { path: "model.norm", role: "normalization", type: "FixtureNorm" },
  { path: "lm_head", role: "output_scores", type: "FixtureLinear" },
];
const structure = {
  nodes,
  edges: nodes.slice(0, -1).map((node, i) => ({
    from: node.path,
    to: nodes[i + 1].path,
    kind: "verified_block_path",
  })),
  layer_count: 5,
  hidden_size: 32,
  model_id: "UI-fixture/no-actual-model",
  revision: "CPU-fixture-revision",
  adapter: null,
  device: "cpu",
  dtype: "torch.float32",
  source: "cpu_fixture",
  resident: false,
  graph_notice: "CPU 합성 UI fixture · 실제 GPU 구조가 아님",
  wrapper_type: "FixtureWrapper",
  base_type: "FixtureModel",
  parameter_counts: { total: 100, base: 100, adapter: 0, trainable: 0 },
  parameter_count_notice: "CPU fixture 집계 기준",
  forward_evidence: {
    implementation: "CPU fixture",
    transformers_version: "fixture",
    sha256: "fixture",
  },
};
function makeRun(state = "running") {
  return {
    run_id: "fixture-run",
    request_id: "fixture-request",
    job_id: "fixture-job",
    generation_epoch: 7,
    model_id: structure.model_id,
    revision: structure.revision,
    state,
    observer_enabled: true,
    observation_mode: "detail",
    resident: state === "running",
    structure,
    metadata: {},
    output_text: "",
    dropped_events: 2,
    worker_dropped_events: 3,
    sequence_no: 0,
    created_at: "2026-10-26T00:00:00Z",
    updated_at: "2026-10-26T00:00:00Z",
  };
}
function envelope(
  sequence: number,
  type: string,
  payload: any,
  options: any = {},
) {
  return {
    run_id: "fixture-run",
    request_id: "fixture-request",
    generation_epoch: 7,
    sequence_no: sequence,
    event_type: type,
    observed_at: new Date().toISOString(),
    source: "live_worker",
    phase: "prefill",
    timing_kind: "host_call",
    payload,
    ...options,
  };
}
async function fixture(page: Page, active = true, cachedAdapter?: string) {
  let run: any = makeRun(active ? "running" : "completed");
  const requests: { path: string; method: string; body: any }[] = [];
  let record: any = {
    id: "fixture-record",
    run_id: run.run_id,
    created_at: "2026-10-25T13:00:00Z",
    include_sensitive: false,
    run: { ...run, state: "completed", output_text: "" },
    structure,
    events: [
      envelope(1, "input_tokens", { redacted: true }),
      envelope(
        2,
        "activation_sample",
        { redacted: true },
        { module_path: "model.layers.0" },
      ),
    ],
  };
  await page.addInitScript(
    ({ run, structure }) => {
      const original = window.fetch.bind(window);
      const state: any = {
        controller: null,
        headers: null,
        url: null,
        aborts: 0,
        run,
      };
      (window as any).__neuralFixture = state;
      window.fetch = async (input, init) => {
        const url = String(input);
        if (!url.includes("/neural/runs/") || !url.includes("/events?"))
          return original(input, init);
        state.headers = Object.fromEntries(new Headers(init?.headers));
        state.url = url;
        const stream = new ReadableStream({
          start(controller) {
            state.controller = controller;
            const snapshot = {
              run_id: state.run.run_id,
              request_id: state.run.request_id,
              generation_epoch: state.run.generation_epoch,
              event_type: "snapshot",
              sequence_no: 99,
              payload: {
                run: state.run,
                structure,
                server_instance: "fixture-instance",
              },
            };
            controller.enqueue(
              new TextEncoder().encode(
                `event: snapshot\ndata: ${JSON.stringify(snapshot)}\n\n`,
              ),
            );
            init?.signal?.addEventListener(
              "abort",
              () => {
                state.aborts++;
                try {
                  controller.close();
                } catch {}
              },
              { once: true },
            );
          },
        });
        return new Response(stream, {
          headers: { "content-type": "text/event-stream" },
        });
      };
    },
    { run, structure },
  );
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname.replace("/api", ""),
      method = request.method();
    let body: any = {};
    try {
      body = request.postDataJSON() ?? {};
    } catch {}
    requests.push({ path, method, body });
    if (request.headers().authorization !== `Bearer ${token}`)
      return route.fulfill({ status: 401, json: { detail: "fixture auth" } });
    let value: any = {};
    if (path === "/capabilities")
      value = {
        fixture: true,
        text: { available: true },
        training: { available: false },
        speech: { available: false },
        vision: { available: false },
      };
    else if (path === "/models")
      value = {
        ready: true,
        installed: true,
        model_id: structure.model_id,
        modules: [],
      };
    else if (path === "/sessions" || path === "/jobs") value = [];
    else if (path === "/adapters")
      value = { adapters: [{ id: "fixture-adapter" }] };
    else if (path === "/neural/state")
      value = {
        fixture: true,
        server_instance: "fixture-instance",
        structure: cachedAdapter
          ? { ...structure, adapter: cachedAdapter }
          : structure,
        mode: active ? "LIVE" : "STATIC",
        active_run:
          active && ["running", "loading"].includes(run.state) ? run : null,
        model: { model_id: structure.model_id },
        training: {
          current: [],
          history: [
            {
              id: "historical-fixture-50",
              state: "completed",
              metrics: [
                {
                  step: 50,
                  loss: 0.65,
                  actual_microbatches: 400,
                  elapsed_seconds: 25,
                },
              ],
              created_at: "2026-10-25T00:00:00Z",
            },
          ],
        },
        records: [
          {
            ...record,
            events: undefined,
            structure: undefined,
            run: undefined,
          },
        ],
      };
    else if (path === "/neural/runs" && method === "POST") {
      run = {
        ...makeRun("completed"),
        generation_epoch: body.generation_epoch,
        request_id: body.request_id,
      };
      value = run;
    } else if (path === "/neural/runs/fixture-run/observation") {
      run = { ...run, observer_enabled: body.enabled };
      value = run;
    } else if (path === "/neural/runs/fixture-run/cancel") {
      run = { ...run, state: "cancelled", observer_enabled: false };
      value = run;
    } else if (path === "/neural/runs/fixture-run/save")
      value = {
        id: "saved-fixture",
        include_sensitive: body.include_sensitive,
      };
    else if (path === "/neural/runs/fixture-run") value = run;
    else if (path === "/neural/records") value = { records: [record] };
    else if (path === "/neural/records/fixture-record") value = record;
    await route.fulfill({ json: value });
  });
  await page.goto("/#neural");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page.getByLabel("관리 토큰", { exact: true }).fill(token);
  await page.getByRole("button", { name: "연결", exact: true }).click();
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible();
  await page.evaluate(() => {
    window.location.hash = "neural";
  });
  await expect(
    page.getByRole("heading", { name: "신경망 보기", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("CPU 합성 UI fixture · 실제 GPU 계측 증거가 아닙니다."),
  ).toBeVisible();
  return {
    requests,
    finish: () => {
      run = {
        ...run,
        state: "completed",
        observer_enabled: false,
        metadata: { finish_reason: "length_or_timeout" },
      };
    },
    record: (next: any) => {
      record = next;
    },
  };
}
async function emit(page: Page, events: any[], close = false) {
  await page.waitForFunction(
    () => !!(window as any).__neuralFixture?.controller,
  );
  await page.evaluate(
    ({ events, close }) => {
      const controller = (window as any).__neuralFixture.controller;
      for (const event of events)
        controller.enqueue(
          new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`),
        );
      if (close) controller.close();
    },
    { events, close },
  );
}

test("CPU UI fixture: live contract, bounds, stale guards, pause and terminal modes", async ({
  page,
}) => {
  const server = await fixture(page);
  expect(
    server.requests.filter(
      (r) => r.path === "/neural/runs" && r.method === "POST",
    ),
  ).toHaveLength(0);
  await emit(page, [
    envelope(1, "input_tokens", {
      token_ids: [11, 12],
      special_tokens: [false, true],
      token_count: 2,
    }),
    envelope(2, "forward", {
      step: 0,
      input_sequence_length: 1,
      cache_length_before: 0,
      cache_reused: false,
    }),
    envelope(
      3,
      "block_call",
      {
        input: { shape: [1, 1, 32], dtype: "torch.float32", device: "cpu" },
        output: { shape: [1, 1, 32], dtype: "torch.float32", device: "cpu" },
        step: 0,
        call_count: 1,
        host_elapsed_ms: 0.1,
        gpu_elapsed_ms: null,
      },
      { module_path: "model.layers.0" },
    ),
    envelope(4, "token", {
      token_ids: [41],
      special_tokens: [false],
      output_token_count: 1,
      cumulative_text: "UI fixture 한글 응답�",
    }),
    envelope(5, "output", { text: "UI fixture 한글 응답" }),
  ]);
  await expect(page.getByTestId("neural-mode")).toHaveText("LIVE");
  await expect(page.getByTestId("neural-output")).toHaveText(
    "UI fixture 한글 응답",
  );
  await expect(page.getByTestId("neural-event-count")).toContainText("5개");
  await expect(page.getByTestId("neural-layer-detail")).toContainText(
    "[1 × 1 × 32]",
  );
  expect(
    await page
      .getByTestId("neural-graph")
      .getByRole("button", { name: /블록 .* 선택/ })
      .count(),
  ).toBe(5);
  const security = await page.evaluate(() => ({
    url: (window as any).__neuralFixture.url,
    headers: (window as any).__neuralFixture.headers,
  }));
  expect(security.headers.authorization).toBe(`Bearer ${token}`);
  expect(security.url).not.toContain(token);
  await page.getByRole("button", { name: "화면만 일시정지" }).click();
  await emit(page, [
    envelope(6, "token", {
      token_ids: [42],
      output_token_count: 2,
      cumulative_text: 'UI fixture incomplete bytes �',
    }),
    envelope(7, "output", { text: '<img src=x onerror="window.__xss=1"> UI fixture' }),
    envelope(
      8,
      "token",
      { cumulative_text: "OLD EPOCH" },
      { generation_epoch: 6 },
    ),
    envelope(7, "token", { cumulative_text: "DUPLICATE" }),
  ]);
  await page.waitForTimeout(350);
  await expect(page.getByTestId("neural-mode")).toHaveText("STALE");
  await expect(page.getByTestId("neural-output")).toHaveText(
    "UI fixture 한글 응답",
  );
  await page.getByRole("button", { name: "화면만 계속 보기" }).click();
  await expect(page.getByTestId("neural-output")).toHaveText(
    '<img src=x onerror="window.__xss=1"> UI fixture',
  );
  expect(await page.evaluate(() => (window as any).__xss)).toBeUndefined();
  expect(
    server.requests.filter((r) => r.path.endsWith("/cancel")),
  ).toHaveLength(0);
  await page.getByRole("button", { name: "관측 끄기", exact: true }).click();
  expect(
    server.requests.find((r) => r.path.endsWith("/observation"))?.body,
  ).toMatchObject({ enabled: false, generation_epoch: 7 });
  expect(
    server.requests.find((r) => r.path.endsWith("/observation"))?.body.mode,
  ).toBeUndefined();
  await expect(page.getByTestId("neural-mode")).toHaveText("STALE");
  server.finish();
  await emit(
    page,
    [envelope(8, "run_state", { state: "completed", resident: false })],
    true,
  );
  await expect(page.getByTestId("neural-mode")).toHaveText("STATIC");
  await expect(page.getByTestId("neural-finish")).toContainText(
    "토큰·시간 제한으로 중단 · 부분 출력",
  );
  expect(
    server.requests.filter(
      (r) => r.path === "/neural/runs" && r.method === "POST",
    ),
  ).toHaveLength(0);
});

test("CPU UI fixture: actual-shape selection, sample values, mobile/desktop and no implicit save", async ({
  page,
}) => {
  const server = await fixture(page);
  await emit(page, [
    envelope(
      1,
      "activation_sample",
      {
        values: [-5, -0.5, 0, 0.5, 5],
        sample_mean: 0,
        step: 0,
        sample_cpu_transfer_and_stats_ms: 0.2,
      },
      {
        module_path: "model.layers.0",
        sampling_info: {
          batch_index: 0,
          token_index: 4,
          sequence_token_index: 4,
          component_indices: [0, 1, 2, 3, 4],
          method: "last_valid_token_first_components",
          every_steps: 16,
        },
      },
    ),
  ]);
  await expect(page.getByTestId("neural-layer-detail")).toContainText(
    "토큰 index 4",
  );
  await expect(page.locator(".neural-samples > div")).toHaveCount(5);
  await page.getByText("확인된 블록 내부 경로", { exact: true }).click();
  await expect(
    page.getByText("Attention · 문맥 계산", { exact: true }),
  ).toBeVisible();
  mkdirSync(root, { recursive: true });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByRole("button", { name: "화면 맞춤", exact: true }).click();
    await page.screenshot({
      path: `${root}/neural-fixture-${width}.png`,
      fullPage: true,
    });
    const sizes = await page.evaluate(() => ({
      width: innerWidth,
      body: document.body.scrollWidth,
    }));
    expect(sizes.body).toBeLessThanOrEqual(sizes.width + 1);
  }
  expect(server.requests.filter((r) => r.path.endsWith("/save"))).toHaveLength(
    0,
  );
  await page
    .getByRole("button", { name: "현재 기록 저장", exact: true })
    .click();
  await expect
    .poll(() => server.requests.filter((r) => r.path.endsWith("/save")).length)
    .toBe(1);
  expect(server.requests.find((r) => r.path.endsWith("/save"))?.body).toEqual({
    include_sensitive: false,
  });
  server.finish();
  await emit(page, [envelope(2, "run_state", { state: "completed" })], true);
  await expect(page.getByTestId("neural-mode")).toHaveText("STATIC");
  await page.getByRole("tab", { name: "학습 지표", exact: true }).click();
  await expect(
    page.getByText("현재 학습 작업 없음", { exact: true }),
  ).toBeVisible();
  await page.getByText(/과거 학습 기록 · historical-fixture-50/).click();
  await expect(
    page.getByText("층별 활성값 / gradient", { exact: true }),
  ).toBeVisible();
  expect(
    server.requests.some(
      (r) => r.path.includes("/training") && r.method === "POST",
    ),
  ).toBe(false);
  writeFileSync(
    `${root}/evidence.json`,
    JSON.stringify(
      {
        source: "CPU synthetic browser fixture, not actual GPU",
        widths: [1440, 390],
        autoInferenceRequests: server.requests.filter(
          (r) => r.path === "/neural/runs" && r.method === "POST",
        ).length,
        tests:
          "auth-header, dynamic-five-block-graph, actual-fixture-values, no-XSS, epoch/seq, pause-vs-cancel, save opt-in, no-training",
      },
      null,
      2,
    ),
  );
});

test("CPU UI fixture: redacted replay has no invented values, subscription cleanup", async ({
  page,
}) => {
  const server = await fixture(page, false);
  await expect(page.getByTestId("neural-mode")).toHaveText("STATIC");
  await page
    .getByLabel("저장 기록 선택", { exact: true })
    .selectOption("fixture-record");
  await expect(page.getByTestId("neural-mode")).toHaveText("REPLAY");
  await page.getByLabel("재생 속도", { exact: true }).selectOption("0.25");
  await page.getByRole("button", { name: "기록 재생", exact: true }).click();
  await expect(page.getByTestId("neural-event-count")).toContainText("2개");
  await expect(page.locator(".neural-samples > div")).toHaveCount(0);
  await expect(page.getByTestId("neural-output")).toContainText(
    "아직 표시할 생성 원문이 없습니다",
  );
  await expect(page.getByTestId("neural-mode")).toHaveText("REPLAY");
  await page
    .getByRole("button", { name: "현재 상태로 돌아가기", exact: true })
    .click();
  await expect(page.getByTestId("neural-mode")).toHaveText("STATIC");
  expect(server.requests.filter((r) => r.method === "POST")).toHaveLength(0);
});

test("CPU UI fixture: tab exit aborts only this subscription, without global hook disable", async ({
  page,
}) => {
  const server = await fixture(page);
  await emit(page, [envelope(1, "forward", { step: 0 })]);
  await expect(page.getByTestId("neural-mode")).toHaveText("LIVE");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "대화", exact: true })
    .click();
  await expect
    .poll(() => page.evaluate(() => (window as any).__neuralFixture.aborts))
    .toBe(1);
  expect(
    server.requests.filter(
      (r) => r.path.endsWith("/observation") || r.path.endsWith("/cancel"),
    ),
  ).toHaveLength(0);
});

test("CPU UI fixture: detail is opt-in and a single explicit request retains the 128-token cap", async ({
  page,
}) => {
  const server = await fixture(page, false);
  await expect(page.getByLabel("계측 수준", { exact: true })).toHaveValue(
    "light",
  );
  await page.getByLabel("계측 수준", { exact: true }).selectOption("detail");
  await page
    .getByRole("button", { name: "블록 0 · model.layers.0 선택", exact: true })
    .click();
  await page.getByLabel("상세 표본 대상에 포함 (최대 2개 층)").check();
  await page
    .getByRole("button", { name: "블록 1 · model.layers.1 선택", exact: true })
    .click();
  await page.getByLabel("상세 표본 대상에 포함 (최대 2개 층)").check();
  await page
    .getByRole("button", { name: "블록 2 · model.layers.2 선택", exact: true })
    .click();
  await expect(
    page.getByLabel("상세 표본 대상에 포함 (최대 2개 층)"),
  ).toBeDisabled();
  await page
    .getByLabel("관찰할 질문", { exact: true })
    .fill("CPU fixture 질문: 실제 모델을 호출하지 않습니다.");
  await page.getByLabel("최대 새 토큰", { exact: true }).fill("999");
  await expect(page.getByLabel("최대 새 토큰", { exact: true })).toHaveValue(
    "128",
  );
  await page
    .getByRole("button", { name: "질문 보내고 관찰", exact: true })
    .click();
  await expect
    .poll(
      () =>
        server.requests.filter(
          (request) =>
            request.path === "/neural/runs" && request.method === "POST",
        ).length,
    )
    .toBe(1);
  const request = server.requests.find(
    (request) => request.path === "/neural/runs" && request.method === "POST",
  )!;
  expect(request.body).toMatchObject({
    observation_mode: "detail",
    max_new_tokens: 128,
    selected_layers: ["model.layers.0", "model.layers.1"],
    sample_every_steps: 16,
    adapter_id: "base",
    update_interval_ms: 250,
  });
  expect(request.body.save_trace).toBeUndefined();
  expect(request.body.include_sensitive).toBeUndefined();
});

test("CPU UI fixture: old backlog cannot claim LIVE and 200 percent text remains inside 390px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  await emit(page, [
    envelope(
      1,
      "forward",
      { step: 0 },
      { observed_at: "2000-01-01T00:00:00Z" },
    ),
  ]);
  await expect(page.getByTestId("neural-event-count")).toContainText("1개");
  await expect(page.getByTestId("neural-mode")).toHaveText("STALE");
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "28px";
  });
  const sizes = await page.evaluate(() => ({
    width: innerWidth,
    body: document.documentElement.scrollWidth,
  }));
  expect(sizes.body).toBeLessThanOrEqual(sizes.width + 1);
  await page.screenshot({
    path: `${root}/neural-fixture-390-text200.png`,
    fullPage: true,
  });
  await emit(page, [envelope(2, "forward", { step: 1 })]);
  await expect(page.getByTestId("neural-mode")).toHaveText("LIVE");
});

test("CPU UI fixture: cached adapter provenance does not become the default base selection", async ({
  page,
}) => {
  await fixture(page, false, "D:/fixture/runs/preserved-adapter");
  await expect(page.getByTestId("neural-mode")).toHaveText("STATIC");
  await expect(page.locator(".neural-status")).toContainText(
    "D:/fixture/runs/preserved-adapter",
  );
  await expect(page.locator(".neural-status")).toContainText(
    "마지막 확인 구조의 어댑터",
  );
  await expect(page.getByLabel("관측 어댑터", { exact: true })).toHaveValue(
    "base",
  );
});
