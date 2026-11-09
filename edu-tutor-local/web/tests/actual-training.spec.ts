import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
test("T3 actual S3 smoke job early cancellation preserves actual record", async ({
  page,
}) => {
  test.skip(
    process.env.EDU_RUN_ACTUAL_S3 !== "1",
    "Explicit GPU authorization required.",
  );
  const evidence: any = {
    started_at: new Date().toISOString(),
    profile: "smoke",
    maximum_steps: 5,
    wall_seconds: 600,
    jobs: [],
    requests: [],
  };
  let latest: any;
  let trainCount = 0,
    cancelCount = 0,
    blockedChatCount = 0;
  const checkpoint = JSON.parse(
    readFileSync(
      resolve(process.cwd(), "../runs/integration-live/latest-text.json"),
      "utf8",
    ),
  );
  const tokenPath = resolve(process.cwd(), "../.local/auth-token"),
    auth = {
      Authorization: `Bearer ${readFileSync(tokenPath, "utf8").trim()}`,
    };
  await page.addInitScript(
    (session) => localStorage.setItem("edu-session", session),
    checkpoint.session_id,
  );
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    if (req.method() === "GET") {
      await route.continue();
      return;
    }
    evidence.requests.push({ method: req.method(), path });
    if (path === "/api/datasets/validate") {
      await route.continue();
      return;
    }
    if (path === "/api/train" && trainCount++ === 0) {
      await route.continue();
      return;
    }
    if (
      path === `/api/sessions/${checkpoint.session_id}/messages` &&
      blockedChatCount++ === 0
    ) {
      await route.continue();
      return;
    }
    if (/\/api\/jobs\/[^/]+\/cancel$/.test(path) && cancelCount++ === 0) {
      await route.continue();
      return;
    }
    evidence.blocked_request = path;
    await route.abort();
  });
  page.on("response", async (response) => {
    if (response.url().endsWith("/api/jobs") && response.ok())
      try {
        const jobs = await response.json();
        if (evidence.job_id) {
          const values = Array.isArray(jobs) ? jobs : jobs.jobs;
          latest = values.find((job: any) => job.id === evidence.job_id);
          if (latest)
            evidence.jobs.push({
              state: latest.state,
              progress: latest.progress,
              cancel_requested: latest.cancel_requested,
              metrics: latest.metrics,
            });
        }
      } catch {}
  });
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await page.getByRole("button", { name: "서버 연결 필요" }).click();
    await page
      .getByLabel("로컬 토큰 파일", { exact: true })
      .setInputFiles(resolve(process.cwd(), "../.local/auth-token"));
    await expect(
      page.getByRole("button", { name: "로컬 연결됨" }),
    ).toBeVisible();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "학습·평가", exact: true })
      .click();
    await page.getByLabel("데이터셋 선택").selectOption("demo");
    await page.getByLabel("실행 프로필").selectOption("smoke");
    await page
      .getByRole("button", { name: "데이터 검사 실행", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "실제 토큰 길이 검사", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "실제 토큰 길이 검사", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "예산 확인 후 학습", exact: true }),
    ).toBeEnabled({ timeout: 60000 });
    await page
      .getByRole("button", { name: "예산 확인 후 학습", exact: true })
      .click();
    const submitted = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/train") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "이 범위로 시작", exact: true })
      .click();
    const response = await submitted;
    expect(response.status()).toBe(202);
    const job = await response.json();
    evidence.job_id = job.id;
    const card = page.locator(".job-item").filter({ hasText: job.id });
    await expect(card).toBeVisible();
    await expect
      .poll(() => latest?.metrics?.length || 0, {
        timeout: 180000,
        intervals: [1000],
      })
      .toBeGreaterThan(0);
    evidence.first_metrics = latest.metrics;
    await card.scrollIntoViewIfNeeded();
    await card.screenshot({ path: "test-results-s3/actual-live-training.png" });
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "대화", exact: true })
      .click();
    const blockedQuestion = "학습 중 동시 대화 차단 검증 · 저장 금지";
    const before = await (
      await page.request.get(
        `/api/sessions/${checkpoint.session_id}/messages`,
        { headers: auth },
      )
    ).json();
    await page.getByLabel("질문 입력", { exact: true }).fill(blockedQuestion);
    const blockedResponse = page.waitForResponse(
      (response) =>
        response
          .url()
          .endsWith(`/api/sessions/${checkpoint.session_id}/messages`) &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "질문 전송", exact: true }).click();
    expect((await blockedResponse).status()).toBe(409);
    const after = await (
      await page.request.get(
        `/api/sessions/${checkpoint.session_id}/messages`,
        { headers: auth },
      )
    ).json();
    expect(after).toHaveLength(before.length);
    expect(
      after.some((message: any) => message.content === blockedQuestion),
    ).toBe(false);
    evidence.chat_conflict = {
      status: 409,
      before_count: before.length,
      after_count: after.length,
      input_persisted: false,
    };
    await page.screenshot({
      path: "test-results-s3/actual-chat-conflict.png",
      fullPage: true,
    });
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "학습·평가", exact: true })
      .click();
    await card.getByRole("button", { name: "중지 요청", exact: true }).click();
    evidence.cancel_clicked_at = new Date().toISOString();
    await expect
      .poll(() => latest?.state, { timeout: 120000, intervals: [1000] })
      .toBe("cancelled");
    evidence.final_job = latest;
    await expect
      .poll(
        async () => {
          const capabilities = await (
            await page.request.get("/api/capabilities", { headers: auth })
          ).json();
          evidence.gpu_lease = capabilities.gpu_lease;
          return capabilities.gpu_lease?.active;
        },
        { timeout: 30000 },
      )
      .toBe(false);
    await expect(card).toContainText("중지됨");
    await card.screenshot({
      path: "test-results-s3/actual-cancelled-training.png",
    });
    expect(latest.metrics?.length).toBeGreaterThan(0);
    expect(trainCount).toBe(1);
    expect(cancelCount).toBe(1);
    expect(evidence.blocked_request).toBeUndefined();
    evidence.status = "passed";
  } catch (error) {
    evidence.status = "failed";
    evidence.error = String(error);
    await page
      .screenshot({ path: "test-results-s3/s3-failure.png", fullPage: true })
      .catch(() => {});
    throw error;
  } finally {
    evidence.completed_at = new Date().toISOString();
    writeFileSync(
      "test-results-s3/s3-evidence.json",
      JSON.stringify(evidence, null, 2),
    );
  }
});
