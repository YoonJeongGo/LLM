import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
const tokenPath = resolve(process.cwd(), "../.local/auth-token");
async function connect(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page
    .getByLabel("로컬 토큰 파일", { exact: true })
    .setInputFiles(tokenPath);
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible();
}
async function nav(page: Page, name: string) {
  await page
    .getByRole("navigation")
    .getByRole("button", { name, exact: true })
    .click();
}
test("Live API UI: auth file and current model/resources come from server", async ({
  page,
}) => {
  await connect(page);
  await nav(page, "모델 분석");
  await expect(
    page.getByRole("heading", { name: "모델 분석", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "시스템 자원 · 진단" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => JSON.stringify(localStorage).includes("Bearer")),
  ).toBe(false);
  await page.screenshot({
    path: "test-results-live/model-current.png",
    fullPage: true,
  });
});
test("Live API UI: own material upload review search and exact-target deletion", async ({
  page,
}) => {
  const filename = `ui-check-${Date.now()}.txt`;
  let documentId: string | undefined;
  try {
    await connect(page);
    await nav(page, "교육자료");
    await page
      .getByLabel("사용 권한 메모")
      .fill("직접 작성한 UI 통합 검사 자료. 테스트 후 이 자료만 삭제.");
    await page.getByLabel("주제", { exact: true }).fill("UI 검증");
    const created = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/documents") && r.request().method() === "POST",
    );
    await page.getByLabel("교육자료 업로드").setInputFiles({
      name: filename,
      mimeType: "text/plain",
      buffer: Buffer.from(
        "직접 작성한 검증자료입니다. 반딧불튜터검증은 로컬 검색 흐름을 검사하기 위한 고유 단어입니다.",
        "utf8",
      ),
    });
    const response = await created;
    expect(response.ok()).toBe(true);
    documentId = (await response.json()).id;
    await page
      .getByRole("button", { name: new RegExp(filename.replace(".", "\\.")) })
      .click();
    await expect(
      page.getByText("직접 작성한 검증자료입니다.", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "검토 승인", exact: true }).click();
    await page.getByLabel("자료 검색어").fill("반딧불튜터검증");
    await page.getByRole("button", { name: "검색", exact: true }).click();
    await expect(page.locator(".search-hit")).toContainText("반딧불튜터검증");
    await page.screenshot({
      path: "test-results-live/material-search.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: new RegExp(filename.replace(".", "\\.")) })
      .click();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "삭제", exact: true }).click();
    await expect(
      page.getByRole("button", {
        name: new RegExp(filename.replace(".", "\\.")),
      }),
    ).toHaveCount(0);
    documentId = undefined;
  } finally {
    if (documentId)
      await page.request.delete(`/api/documents/${documentId}`, {
        headers: {
          Authorization: `Bearer ${readFileSync(tokenPath, "utf8").trim()}`,
          Origin: "http://127.0.0.1:8000",
        },
      });
  }
});
test("Live API UI: manual photo revision and confirmation remain explicit", async ({
  page,
}) => {
  let photoId: string | undefined;
  try {
    await connect(page);
    await nav(page, "대화");
    await page.getByRole("button", { name: "문제 사진 첨부" }).click();
    const created = page.waitForResponse(
      (r) => r.url().endsWith("/api/photos") && r.request().method() === "POST",
    );
    await page.getByLabel("문제 사진 업로드").setInputFiles({
      name: "self-authored-pixel.png",
      mimeType: "image/png",
      buffer: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/mXcAAAAASUVORK5CYII=",
        "base64",
      ),
    });
    const response = await created;
    expect(response.ok()).toBe(true);
    photoId = (await response.json()).id;
    const solve = page.getByRole("button", { name: "확정한 문제 풀이" });
    await expect(solve).toBeDisabled();
    await page
      .getByLabel("문제 본문")
      .fill("직접 입력한 UI 검사 문제. 2 + 3 = ?");
    await page.getByRole("button", { name: "교정 저장" }).click();
    await page.getByRole("button", { name: "이 원문으로 확정" }).click();
    await expect(solve).toBeEnabled();
    await page.getByLabel("문제 본문").fill("교정된 UI 검사 문제. 2 + 4 = ?");
    await expect(solve).toBeDisabled();
    await page.screenshot({
      path: "test-results-live/photo-confirmation.png",
      fullPage: true,
    });
  } finally {
    if (photoId)
      await page.request.delete(`/api/photos/${photoId}`, {
        headers: {
          Authorization: `Bearer ${readFileSync(tokenPath, "utf8").trim()}`,
          Origin: "http://127.0.0.1:8000",
        },
      });
  }
});
test("Live API UI: server demo is clearly marked and restores step after authentication", async ({
  page,
}) => {
  await connect(page);
  await nav(page, "강의실");
  await page.getByRole("button", { name: "설명용 예시 열기" }).click();
  await expect(
    page.getByText("데모 데이터 재생", { exact: true }),
  ).toBeVisible();
  await page.locator('button[aria-label="다음 단계"]').click();
  await expect(page.locator('[data-board-element="query"]')).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page
    .getByLabel("로컬 토큰 파일", { exact: true })
    .setInputFiles(tokenPath);
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible();
  await nav(page, "강의실");
  await expect(page.locator('[data-board-element="query"]')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results-live/lecture-server-demo.png",
    fullPage: true,
  });
});
