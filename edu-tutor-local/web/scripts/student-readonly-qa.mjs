// Read-only witness for already generated local lessons. No model/TTS/OCR jobs.
// Run only after the real student GPU scenarios have finished.
// node scripts/student-readonly-qa.mjs [--lesson A=<id>] [--lesson D-normal=<id>] [--lesson C=<id>]
import { chromium } from "@playwright/test";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const runRoot = resolve(root, "runs/student-experience/20261027");
const liveRoot = resolve(runRoot, "live");
const runId = new Date().toISOString().replace(/[:.]/g, "-");
const output = resolve(runRoot, "ui-readonly", runId);
const explicit = new Map();
let base = "http://127.0.0.1:8000";
let layoutOnly = false;
for (let i = 2; i < process.argv.length; i++) {
  const arg = process.argv[i];
  if (arg === "--base") base = process.argv[++i];
  else if (arg === "--layout-only") layoutOnly = true;
  else if (arg === "--lesson") {
    const [role, id] = (process.argv[++i] || "").split("=");
    if (
      !["A", "D-normal", "C"].includes(role) ||
      !/^[a-z0-9_-]{1,80}$/.test(id || "")
    )
      throw new Error("Use --lesson A=<id>, D-normal=<id>, or C=<id>");
    explicit.set(role, id);
  } else throw new Error(`Unknown argument: ${arg}`);
}
const origin = new URL(base);
if (
  !["127.0.0.1", "localhost", "[::1]"].includes(origin.hostname) ||
  origin.protocol !== "http:"
)
  throw new Error("Only a local HTTP application is allowed");
base = origin.origin;
const tokenFile = resolve(root, ".local/auth-token");
const token = readFileSync(tokenFile, "utf8").trim();
mkdirSync(output, { recursive: true });
const evidence = {
  started_at: new Date().toISOString(),
  scope:
    "GET-only UI/media replay of previously generated real local lesson artifacts",
  human_listening_review: "NOT_RUN",
  human_education_review: "NOT_RUN",
  image_provenance:
    "Existing synthetic development test pictures; not new student uploads",
  new_model_requests_allowed: false,
  new_speech_requests_allowed: false,
  new_vision_requests_allowed: false,
  programmatic_audio_seeking: false,
  cached_audio_requested: !layoutOnly,
  api_reads: [],
  blocked_requests: [],
  page_errors: [],
  discovery: [],
  lessons: [],
  errors: [],
};
const save = () =>
  writeFileSync(
    resolve(output, "report.json"),
    JSON.stringify(evidence, null, 2),
  );
async function get(path) {
  if (!/^\/(lessons\/[a-z0-9_-]+|jobs|resources\/budget)$/.test(path))
    throw new Error(`Read helper disallows this endpoint: ${path}`);
  const response = await fetch(`${base}/api${path}`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(15000),
  });
  evidence.api_reads.push({
    method: "GET",
    path,
    status: response.status,
    at: new Date().toISOString(),
  });
  if (!response.ok) throw new Error(`GET ${path} failed (${response.status})`);
  return response.json();
}
function addCandidate(candidates, role, detail, file, time, priority = 0) {
  const id = detail?.lesson_record_id;
  if (id && /^[a-z0-9_-]{1,80}$/.test(id))
    candidates.push({
      role,
      id,
      file,
      at: detail.at_iso || time || "",
      evidence: detail.type || "first_playing",
      priority,
    });
}
function discover() {
  const candidates = [];
  for (const name of readdirSync(liveRoot).filter((file) =>
    file.endsWith(".json"),
  )) {
    let data;
    try {
      data = JSON.parse(readFileSync(resolve(liveRoot, name), "utf8"));
    } catch {
      evidence.discovery.push({
        file: name,
        status: "unreadable_or_in_progress",
      });
      continue;
    }
    const source = resolve(liveRoot, name),
      time = data.completed_at || data.started_at;
    if (["A", "A-final", "A-fixed", "A-rechecked"].includes(data.mode)) {
      const priority =
        data.mode === "A-final" || name === "A-final.json"
          ? 110
          : data.mode === "A-fixed" || name === "A-fixed.json"
            ? 100
            : data.mode === "A-rechecked" || name === "A-rechecked.json"
              ? 90
              : 0;
      addCandidate(candidates, "A", data.first_playing, source, time, priority);
      for (const event of data.events || [])
        if (event.type === "audio_playing")
          addCandidate(candidates, "A", event, source, time, priority);
    }
    if (data.mode === "D-normal-lesson") {
      addCandidate(candidates, "D-normal", data.first_playing, source, time);
      for (const event of data.events || [])
        if (event.type === "audio_playing")
          addCandidate(candidates, "D-normal", event, source, time);
    }
    if (
      String(data.mode).startsWith("BC") ||
      String(data.mode).startsWith("C")
    ) {
      addCandidate(candidates, "C", data.C_first, source, time);
      for (const event of data.events || [])
        if (event.type === "audio_playing" && event.supplement)
          addCandidate(candidates, "C", event, source, time);
    }
  }
  evidence.discovery = [...evidence.discovery, ...candidates];
  return candidates.sort(
    (a, b) => b.priority - a.priority || b.at.localeCompare(a.at),
  );
}
async function navigate(page, label) {
  const menu = page.getByRole("button", { name: "메뉴 열기", exact: true });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: label, exact: true })
    .click();
}
async function settle(page) {
  return page.evaluate(
    () =>
      new Promise((resolve, reject) => {
        const start = performance.now(),
          samples = [];
        let previous = "",
          stableFrames = 0;
        const sample = () => {
          const sidebar = document.querySelector(".sidebar"),
            board = document.querySelector(".chalk-board");
          const menu = document.querySelector(".mobile-menu");
          const mobile = !!menu?.getClientRects().length;
          const side = sidebar?.getBoundingClientRect(),
            target = board?.getBoundingClientRect();
          const style = sidebar ? getComputedStyle(sidebar) : null;
          const animations =
            sidebar
              ?.getAnimations()
              .filter((animation) => animation.playState === "running")
              .length || 0;
          const closed =
            !sidebar?.classList.contains("open") &&
            (!mobile || (side?.right ?? 0) <= 0.5);
          const verticalOverlap =
            side && target
              ? Math.max(
                  0,
                  Math.min(side.bottom, target.bottom) -
                    Math.max(side.top, target.top),
                )
              : 0;
          const overlap =
            side && target && verticalOverlap > 0
              ? Math.max(
                  0,
                  Math.min(side.right, target.right) -
                    Math.max(side.left, target.left),
                )
              : 0;
          const current = {
            at_ms: performance.now(),
            sidebar_left: style?.left,
            sidebar_transform: style?.transform,
            sidebar_rect: side?.toJSON(),
            board_rect: target?.toJSON(),
            running_sidebar_transitions: animations,
            sidebar_closed: closed,
            sidebar_board_overlap_width_px: overlap,
          };
          samples.push(current);
          const key = JSON.stringify([
            side?.left,
            side?.right,
            target?.x,
            target?.width,
            target?.height,
            style?.left,
            style?.transform,
          ]);
          stableFrames = key === previous ? stableFrames + 1 : 0;
          previous = key;
          if (closed && !animations && stableFrames >= 2 && overlap <= 0.5) {
            resolve({
              ...current,
              elapsed_ms: performance.now() - start,
              consecutive_stable_frames: stableFrames + 1,
              samples,
            });
            return;
          }
          if (performance.now() - start > 5000) {
            reject(
              new Error(
                "Sidebar/board geometry did not settle without occlusion",
              ),
            );
            return;
          }
          requestAnimationFrame(sample);
        };
        sample();
      }),
  );
}
async function geometry(page, step, label) {
  const settlement = await settle(page);
  return page.evaluate(
    ({ step, label, settlement }) => {
      const stage = document.querySelector(".chalk-stage"),
        board = document.querySelector(".chalk-board");
      const pointer = document.querySelector('[data-testid="avatar-pointer"]');
      const target = [
        ...document.querySelectorAll("[data-board-element]"),
      ].find(
        (node) => node.dataset.boardElement === step.gesture?.target_element_id,
      );
      const selected = document
        .querySelector('.board-cell-button[aria-pressed="true"]')
        ?.closest("[data-cell-id]");
      const highlight = step.board_actions.find(
        (action) =>
          action.type === "highlight" &&
          action.cell_ids?.length &&
          action.target_element_id === step.gesture?.target_element_id,
      );
      const highlighted = highlight
        ? [...document.querySelectorAll("[data-cell-id]")].find(
            (node) => node.dataset.cellId === highlight.cell_ids[0],
          )
        : null;
      const cell = selected || highlighted;
      const r = (node) => node?.getBoundingClientRect().toJSON() || null;
      const stageRect = r(stage),
        targetRect = r(target),
        cellRect = r(cell);
      const matrix = pointer?.getScreenCTM();
      const screenPoint = (x, y) => {
        if (!matrix) return null;
        const point = new DOMPoint(x, y).matrixTransform(matrix);
        return { x: point.x, y: point.y };
      };
      const endpoint = pointer
        ? screenPoint(
            Number(pointer.getAttribute("x2")),
            Number(pointer.getAttribute("y2")),
          )
        : null;
      const pointerOrigin = pointer
        ? screenPoint(
            Number(pointer.getAttribute("x1")),
            Number(pointer.getAttribute("y1")),
          )
        : null;
      const cellDistance =
        endpoint && cellRect
          ? Math.hypot(
              endpoint.x - cellRect.x - cellRect.width / 2,
              endpoint.y - cellRect.y - cellRect.height / 2,
            )
          : null;
      const targetContainsEndpoint =
        endpoint && targetRect
          ? endpoint.x >= targetRect.left - 2 &&
            endpoint.x <= targetRect.right + 2 &&
            endpoint.y >= targetRect.top - 2 &&
            endpoint.y <= targetRect.bottom + 2
          : null;
      const textSizes = [
        ...document.querySelectorAll(
          ".chalk-board td,.chalk-board th,.chalk-board p,.caption-box p",
        ),
      ].map((node) => ({
        tag: node.tagName,
        font_px: Number.parseFloat(getComputedStyle(node).fontSize),
      }));
      return {
        label,
        layout_settlement: settlement,
        step_id: step.id,
        gesture: step.gesture,
        pointer_present: !!pointer,
        pointer_expected: !!(target || cell),
        endpoint,
        pointer_origin: pointerOrigin,
        expected_target_kind: selected
          ? "selected_cell"
          : highlighted
            ? "highlighted_cell"
            : "gesture_element",
        stage_rect: stageRect,
        gesture_target_rect: targetRect,
        gesture_target_contains_endpoint: targetContainsEndpoint,
        selected_or_highlighted_cell_id: cell?.dataset.cellId || null,
        cell_rect: cellRect,
        cell_center_distance_px: cellDistance,
        cell_center_matches: cellDistance === null ? null : cellDistance <= 2,
        viewport: { width: innerWidth, height: innerHeight },
        root_font_px: Number.parseFloat(
          getComputedStyle(document.documentElement).fontSize,
        ),
        document_width: document.documentElement.scrollWidth,
        no_document_horizontal_overflow:
          document.documentElement.scrollWidth <= innerWidth + 1,
        board_text: board?.innerText || "",
        board_html: board?.outerHTML || "",
        text_sizes: textSizes,
        tables: [
          ...document.querySelectorAll(".chalk-board .table-scroll"),
        ].map((node) => ({
          rect: r(node),
          client_width: node.clientWidth,
          scroll_width: node.scrollWidth,
          overflow_x: getComputedStyle(node).overflowX,
        })),
        character: document.querySelector(".avatar")?.outerHTML || null,
      };
    },
    { step, label, settlement },
  );
}
async function openLesson(browser, item, viewport, textScale) {
  const context = await browser.newContext({
    viewport,
    serviceWorkers: "block",
  });
  await context.route("**/*", async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    const foreign = url.protocol.startsWith("http") && url.origin !== base;
    if (
      foreign ||
      (url.pathname.startsWith("/api/") && request.method() !== "GET")
    ) {
      evidence.blocked_requests.push({
        role: item.role,
        method: request.method(),
        path: url.pathname,
        reason: foreign ? "external_request" : "read_only_api_guard",
      });
      save();
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  await context.addInitScript(
    ({ id, planId, textScale }) => {
      localStorage.clear();
      localStorage.setItem("edu-tab", "classroom");
      localStorage.setItem("edu-lesson", id);
      localStorage.setItem("edu-text-scale", String(textScale));
      localStorage.setItem(
        `lecture:${planId}`,
        JSON.stringify({
          step: 0,
          progress: 1,
          audio_position: 0,
          selected_cell: null,
        }),
      );
      window.__readonlyMedia = [];
      window.__readonlyLesson = [];
      for (const kind of [
        "loadedmetadata",
        "playing",
        "pause",
        "ended",
        "error",
      ])
        document.addEventListener(
          kind,
          (event) => {
            if (!(event.target instanceof HTMLAudioElement)) return;
            const audio = event.target;
            window.__readonlyMedia.push({
              type: kind,
              at_ms: performance.now(),
              at_iso: new Date().toISOString(),
              step_id: audio.dataset.stepId,
              current_time: audio.currentTime,
              duration: audio.duration,
              playback_rate: audio.playbackRate,
              muted: audio.muted,
              volume: audio.volume,
              ready_state: audio.readyState,
              error_code: audio.error?.code || null,
            });
          },
          true,
        );
      window.addEventListener("edu:lesson", (event) =>
        window.__readonlyLesson.push(event.detail),
      );
    },
    { id: item.record.id, planId: item.record.plan.lesson_id, textScale },
  );
  const page = await context.newPage();
  page.on("pageerror", (error) =>
    evidence.page_errors.push({ role: item.role, message: error.message }),
  );
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/"))
      evidence.api_reads.push({
        via: "browser",
        method: request.method(),
        path: url.pathname,
        role: item.role,
      });
  });
  await page.goto(base);
  await page
    .getByRole("button", { name: "서버 연결 필요", exact: true })
    .click();
  await page
    .getByLabel("로컬 토큰 파일", { exact: true })
    .setInputFiles(tokenFile);
  await page
    .getByRole("button", { name: "로컬 연결됨", exact: true })
    .waitFor({ timeout: 30000 });
  await navigate(page, "강의실");
  await page
    .locator(`.classroom[data-lesson-record-id="${item.record.id}"]`)
    .waitFor({ timeout: 15000 });
  return { context, page };
}
async function checkLesson(browser, item) {
  const entry = {
    role: item.role,
    lesson_record_id: item.record.id,
    source_live_file: item.file,
    question: item.record.plan.question_text,
    title: item.record.plan.title,
    speech_allowed: item.record.speech_allowed,
    first_step_id: item.record.plan.steps[0].id,
    actual_first_speech: item.record.plan.steps[0].speech,
    existing_audio_steps: item.record.audio_steps || [],
    variants: [],
    full_playback: { status: "NOT_RUN" },
  };
  evidence.lessons.push(entry);
  save();
  const variants = [
    { width: 1440, height: 1100, scale: 1 },
    { width: 390, height: 844, scale: 1 },
    { width: 1440, height: 1100, scale: 2 },
    { width: 390, height: 844, scale: 2 },
  ];
  for (const size of variants) {
    const label = `${item.role}-${size.width}-text${size.scale * 100}`;
    console.log(
      JSON.stringify({ phase: "geometry", role: item.role, variant: label }),
    );
    const { context, page } = await openLesson(
      browser,
      item,
      { width: size.width, height: size.height },
      size.scale,
    );
    try {
      const step = item.record.plan.steps[0];
      const variant = {
        ...size,
        before_selection: await geometry(page, step, "gesture_target"),
      };
      entry.variants.push(variant);
      const screenshot = resolve(output, `${label}-target.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      variant.screenshot = screenshot;
      const highlightedId = step.board_actions.find(
        (a) => a.type === "highlight" && a.cell_ids?.length,
      )?.cell_ids?.[0];
      let cell = highlightedId
        ? page.locator(`[data-cell-id="${highlightedId}"] .board-cell-button`)
        : page
            .locator(
              `[data-board-element="${step.gesture.target_element_id}"] .board-cell-button`,
            )
            .first();
      if (!(await cell.count()))
        cell = page.locator(".chalk-board .board-cell-button").first();
      if (await cell.count()) {
        await cell.click();
        variant.after_selection = await geometry(page, step, "selected_cell");
        const selectedScreenshot = resolve(output, `${label}-selected.png`);
        await page.screenshot({ path: selectedScreenshot, fullPage: true });
        variant.selected_screenshot = selectedScreenshot;
      } else variant.selection_status = "NO_TABLE_CELL_IN_FIRST_STEP";
      if (
        size.width === 1440 &&
        size.scale === 1 &&
        ["A", "D-normal"].includes(item.role) &&
        !layoutOnly
      ) {
        const available = (item.record.audio_steps || []).find(
          (audio) => audio.step_id === step.id && audio.audio_url,
        );
        if (!available)
          entry.full_playback = { status: "NOT_RUN_NO_CACHED_FIRST_STEP" };
        else {
          console.log(
            JSON.stringify({
              phase: "cached_full_playback_start",
              role: item.role,
              step_id: step.id,
              new_speech_job: false,
            }),
          );
          const before = evidence.blocked_requests.length;
          await page
            .getByRole("button", { name: "현재 단계 음성 준비", exact: true })
            .click();
          await page
            .locator("audio")
            .waitFor({ state: "attached", timeout: 20000 });
          await page.waitForFunction(
            () => Number.isFinite(document.querySelector("audio")?.duration),
            undefined,
            { timeout: 20000 },
          );
          const metadata = await page.locator("audio").evaluate((audio) => ({
            duration: audio.duration,
            current_time: audio.currentTime,
            playback_rate: audio.playbackRate,
          }));
          if (metadata.current_time > 0.05 || metadata.playback_rate !== 1)
            throw new Error("Full playback must start at zero at normal rate");
          await page
            .getByRole("button", { name: "음성 재생", exact: true })
            .click();
          await page.waitForFunction(
            () => window.__readonlyMedia.some((e) => e.type === "playing"),
            undefined,
            { timeout: 10000 },
          );
          await page.waitForFunction(
            () =>
              window.__readonlyMedia.some(
                (e) => e.type === "ended" || e.type === "error",
              ),
            undefined,
            { timeout: Math.ceil(metadata.duration * 1000) + 20000 },
          );
          const media = await page.evaluate(() => window.__readonlyMedia);
          const playing = media.find((event) => event.type === "playing"),
            ended = media.find((event) => event.type === "ended");
          entry.full_playback = {
            status:
              ended &&
              ended.current_time >= metadata.duration - 0.05 &&
              evidence.blocked_requests.length === before
                ? "PASS_BROWSER_COMPLETION"
                : "FAIL",
            audio: available,
            metadata,
            events: media,
            playing_to_ended_ms:
              playing && ended ? ended.at_ms - playing.at_ms : null,
            source_audio_preexisting: true,
            new_speech_jobs: 0,
            human_review: "NOT_RUN",
          };
          await page.screenshot({
            path: resolve(output, `${label}-audio-ended.png`),
            fullPage: true,
          });
          console.log(
            JSON.stringify({
              phase: "cached_full_playback_complete",
              role: item.role,
              status: entry.full_playback.status,
              duration: metadata.duration,
            }),
          );
        }
      }
      variant.lesson_events = await page.evaluate(
        () => window.__readonlyLesson,
      );
      save();
    } catch (error) {
      entry.errors ??= [];
      entry.errors.push({ variant: label, message: String(error) });
      await page
        .screenshot({
          path: resolve(output, `${label}-failure.png`),
          fullPage: true,
        })
        .catch(() => {});
      save();
    } finally {
      await context.close();
    }
  }
}

let browser;
try {
  evidence.budget_before = await get("/resources/budget");
  const jobs = await get("/jobs");
  const active = jobs.filter((job) =>
    [
      "queued",
      "running",
      "loading",
      "pending",
      "cancel_requested",
      "cancelling",
      "saving",
      "checkpointing",
    ].includes(job.state || job.status),
  );
  if (active.length)
    throw new Error(
      "Active server jobs exist; run this read-only witness after all real GPU scenarios finish",
    );
  const candidates = discover(),
    chosen = [];
  for (const role of ["A", "D-normal", "C"]) {
    const options = explicit.has(role)
      ? [{ role, id: explicit.get(role), file: "explicit read-only selection" }]
      : candidates.filter((candidate) => candidate.role === role);
    const seen = new Set();
    for (const candidate of options) {
      if (seen.has(candidate.id)) continue;
      seen.add(candidate.id);
      const record = await get(`/lessons/${candidate.id}`);
      if (
        record.valid !== false &&
        record.plan?.steps?.length &&
        record.speech_allowed === true
      ) {
        chosen.push({ ...candidate, record });
        break;
      }
    }
    if (!chosen.some((item) => item.role === role))
      evidence.errors.push(
        `${role}: no valid previously played lesson found; no model request was submitted`,
      );
  }
  browser = await chromium.launch({ channel: "chrome", headless: true });
  for (const item of chosen) await checkLesson(browser, item);
  evidence.budget_after = await get("/resources/budget");
  evidence.generation_counters_unchanged = [
    "gpu_seconds_used",
    "new_audio_attempts",
    "vision_attempts",
  ].every((key) => evidence.budget_before[key] === evidence.budget_after[key]);
  const geometricFailures = evidence.lessons
    .flatMap((lesson) =>
      lesson.variants.flatMap((variant) =>
        [variant.before_selection, variant.after_selection].filter(Boolean),
      ),
    )
    .filter(
      (sample) =>
        !sample.no_document_horizontal_overflow ||
        (sample.pointer_expected && !sample.pointer_present) ||
        sample.cell_center_matches === false ||
        (sample.expected_target_kind !== "selected_cell" &&
          sample.gesture_target_contains_endpoint === false),
    );
  evidence.geometry_failures = geometricFailures;
  const audioFailures = layoutOnly
    ? []
    : evidence.lessons.filter(
        (lesson) =>
          ["A", "D-normal"].includes(lesson.role) &&
          lesson.full_playback.status !== "PASS_BROWSER_COMPLETION",
      );
  evidence.status =
    evidence.errors.length ||
    evidence.page_errors.length ||
    evidence.blocked_requests.length ||
    !evidence.generation_counters_unchanged ||
    geometricFailures.length ||
    audioFailures.length ||
    evidence.lessons.some((lesson) => lesson.errors?.length)
      ? "ISSUES_OR_INCOMPLETE"
      : layoutOnly
        ? "PASS_READONLY_LAYOUT_SCOPE"
        : "PASS_READONLY_BROWSER_SCOPE";
} catch (error) {
  evidence.errors.push(String(error));
  evidence.status = "ISSUES_OR_INCOMPLETE";
} finally {
  await browser?.close();
  evidence.completed_at = new Date().toISOString();
  save();
  console.log(
    JSON.stringify({
      status: evidence.status,
      report: resolve(output, "report.json"),
      blocked_requests: evidence.blocked_requests.length,
      human_review: "NOT_RUN",
    }),
  );
  if (!evidence.status.startsWith("PASS_READONLY_")) process.exitCode = 1;
}
