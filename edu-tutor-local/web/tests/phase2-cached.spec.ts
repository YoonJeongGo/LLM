import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
async function nav(page: Page, name: string) {
  const menu = page.getByRole("button", { name: "메뉴 열기" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name, exact: true })
    .click();
  if (await menu.isVisible())
    await expect
      .poll(() =>
        page
          .locator(".sidebar")
          .evaluate((element) => element.getBoundingClientRect().right),
      )
      .toBeLessThanOrEqual(0);
}
for (const question of [1, 2]) {
  test(`saved actual Q${question} lesson: highlighted NULL pointer and cached audio after final UI changes`, async ({
    page,
  }) => {
    const live = JSON.parse(
        readFileSync("test-results-phase2-live/evidence.json", "utf8"),
      ),
      repaired = JSON.parse(
        readFileSync(
          resolve("../runs/phase2/current/live/T03-short-summary.json"),
          "utf8",
        ),
      );
    expect(repaired).toHaveLength(2);
    const record = repaired.find((item: any) => item.index === question),
      lesson = { id: record.lesson_id };
    const forbidden: string[] = [],
      errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/api/**", async (route) => {
      if (route.request().method() !== "GET") {
        forbidden.push(
          route.request().method() +
            " " +
            new URL(route.request().url()).pathname,
        );
        await route.abort();
      } else await route.continue();
    });
    await page.addInitScript(
      ({ session, id }) => {
        localStorage.clear();
        localStorage.setItem("edu-session", session);
        localStorage.setItem("edu-lesson", id);
        localStorage.setItem("edu-tab", "classroom");
      },
      { session: live.checkpoint.session_id, id: lesson.id },
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");
    await page.getByRole("button", { name: "서버 연결 필요" }).click();
    await page
      .getByLabel("로컬 토큰 파일", { exact: true })
      .setInputFiles(resolve("../.local/auth-token"));
    await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible(
      {
        timeout: 60000,
      },
    );
    await nav(page, "강의실");
    const checks: any[] = [];
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await expect
        .poll(() =>
          page.locator(".chalk-stage").evaluate((stage) => {
            const cell = stage
                .querySelector("td.highlight-cell")
                ?.getBoundingClientRect(),
              root = stage.getBoundingClientRect(),
              pointer = stage.querySelector('[data-testid="avatar-pointer"]');
            return cell && pointer
              ? Math.hypot(
                  Number(pointer.getAttribute("x2")) -
                    (cell.left + cell.width / 2 - root.left),
                  Number(pointer.getAttribute("y2")) -
                    (cell.top + cell.height / 2 - root.top),
                )
              : 10000;
          }),
        )
        .toBeLessThan(1);
      const selected = await page
        .locator("td.highlight-cell")
        .allTextContents();
      expect(selected).toContain("NULL");
      checks.push({
        width,
        highlighted: selected,
        pointer_matches_highlighted_cell: true,
      });
    }
    await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
    await expect(
      page.getByRole("button", { name: "음성 재생", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "음성 재생", exact: true }).click();
    await expect
      .poll(() =>
        page
          .locator("audio")
          .evaluate((audio: HTMLAudioElement) => audio.currentTime),
      )
      .toBeGreaterThan(0.15);
    await page.getByRole("button", { name: "일시정지", exact: true }).click();
    const audio = await page
      .locator("audio")
      .evaluate((element: HTMLAudioElement) => ({
        src: new URL(element.src).pathname,
        duration: element.duration,
        current_time: element.currentTime,
        paused: element.paused,
      }));
    expect(audio.duration).toBeCloseTo(record.audio[0].duration, 1);
    await nav(page, "설정");
    await expect(page.getByText("기록 시각:", { exact: false })).toBeVisible();
    await page.getByLabel("화면 글자 크기").selectOption("2");
    await nav(page, "강의실");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    mkdirSync("test-results-phase2-cached", { recursive: true });
    await page.screenshot({
      path: `test-results-phase2-cached/q${question}-390-text200.png`,
      fullPage: true,
    });
    await nav(page, "대화");
    await page.getByText("원본 표·SQL 입력", { exact: false }).click();
    await page.getByLabel("이 질문에 원본 표·SQL을 함께 보냅니다").check();
    await page
      .getByLabel("문제의 원본 SQL")
      .fill("SELECT AVG(score) FROM exam_result;");
    await nav(page, "강의실");
    await expect(
      page.getByText(
        "원본 입력이 수정되어 이전 풀이·판서·음성이 무효화되었습니다.",
        { exact: false },
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: "이 답변으로 판서 강의 생성",
        exact: true,
      }),
    ).toBeDisabled();
    expect(await page.locator("audio").count()).toBe(0);
    expect(forbidden).toEqual([]);
    expect(errors).toEqual([]);
    writeFileSync(
      `test-results-phase2-cached/q${question}-evidence.json`,
      JSON.stringify(
        {
          scope:
            "Saved actual response with new short narration and EOS-checked Qwen-TTS replay after final UI fixes; no new model/TTS requests from this browser test",
          new_model_requests: 0,
          new_TTS_requests: 0,
          lesson_id: lesson.id,
          prior_live_lesson_id: live[`supplement_${question}`].lesson.id,
          audio,
          checks,
          typed_edit_invalidates_active_audio_board: true,
          page_errors: errors,
          forbidden_mutations: forbidden,
          human_review: "not_reviewed",
        },
        null,
        2,
      ),
    );
  });
}
