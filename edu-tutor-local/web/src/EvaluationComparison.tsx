import { useEffect, useState } from "react";
import { api, errorText, post } from "./api";
import { comparisonItems } from "./evaluation";
import type { EvaluationArtifact, EvaluationItem } from "./evaluation";
type Review = {
  id: string;
  run_id: string;
  item_id: string;
  scores: Record<string, number>;
  comment: string;
  reviewed_at: string;
  report_sha256?: string;
};
const rubrics = [
  {
    key: "correctness",
    label: "정확성",
    hint: "SQL 결과와 설명에 오류가 없는가",
  },
  {
    key: "clarity",
    label: "명료성",
    hint: "학습자가 이해할 수 있게 설명했는가",
  },
  { key: "grounding", label: "근거성", hint: "주어진 표와 조건에 근거했는가" },
];
function Answer({
  run,
  item,
  reviews,
  onSaved,
  authenticated,
}: {
  run: EvaluationArtifact;
  item: EvaluationItem;
  reviews: Review[];
  onSaved: (review: Review) => void;
  authenticated: boolean;
}) {
  const [scores, setScores] = useState<Record<string, string>>({}),
    [comment, setComment] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const previous = reviews.filter(
    (review) => review.run_id === run.run_id && review.item_id === item.id,
  );
  async function save() {
    setBusy(true);
    setError("");
    try {
      const saved = await post<Review>("/evaluations/reviews", {
        run_id: run.run_id,
        item_id: item.id,
        scores: Object.fromEntries(
          rubrics.map((rubric) => [rubric.key, Number(scores[rubric.key])]),
        ),
        comment,
      });
      onSaved(saved);
      setScores({});
      setComment("");
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="comparison-answer">
      <h3>{run.report.adapter ? "어댑터 평가" : "기반 모델 평가"}</h3>
      <p className="fine-print mono">{run.run_id}</p>
      <span className="badge amber">설명 정확성 · 사람 검토 별도</span>
      <pre className="evaluation-answer">{item.text}</pre>
      <p className="fine-print">
        {item.sql_result?.status === "executed"
          ? item.sql_result.match
            ? "이 문항의 SQL 실행 결과 일치"
            : "이 문항의 SQL 실행 결과 불일치"
          : "SQL 실행 검증 없음"}{" "}
        · 종료 {item.finish_reason || "미기록"}
        {item.finish_reason === "length" ? " (길이 제한 도달)" : ""}
      </p>
      <p className="fine-print">
        응답{" "}
        {typeof item.latency_seconds === "number"
          ? `${item.latency_seconds.toFixed(2)}초`
          : "미기록"}{" "}
        · 출력 {item.output_tokens ?? "미기록"}토큰 · 최대 VRAM{" "}
        {typeof item.peak_vram_bytes === "number"
          ? `${(item.peak_vram_bytes / 1024 ** 3).toFixed(2)}GiB`
          : "미기록"}
      </p>
      <details>
        <summary>직접 검토 점수 입력 · 저장 기록 {previous.length}개</summary>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <fieldset disabled={busy || !authenticated}>
            <legend>내 검토 · 1 낮음 / 5 높음</legend>
            {rubrics.map((rubric) => (
              <label key={rubric.key}>
                {rubric.label}
                <span className="fine-print">{rubric.hint}</span>
                <select
                  aria-label={`${run.run_id} ${rubric.label}`}
                  value={scores[rubric.key] || ""}
                  required
                  onChange={(event) =>
                    setScores({ ...scores, [rubric.key]: event.target.value })
                  }
                >
                  <option value="">직접 선택</option>
                  {[1, 2, 3, 4, 5].map((score) => (
                    <option key={score} value={score}>
                      {score}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <label>
              검토 메모
              <textarea
                aria-label={`${run.run_id} 검토 메모`}
                value={comment}
                maxLength={2000}
                onChange={(event) => setComment(event.target.value)}
                rows={3}
              />
            </label>
            <button
              className="button secondary"
              disabled={rubrics.some((rubric) => !scores[rubric.key])}
            >
              내 검토 저장
            </button>
          </fieldset>
        </form>
        {error && (
          <p role="alert" className="notice error">
            {error}
          </p>
        )}
        <p className="fine-print">
          입력한 점수만 별도 기록합니다. 전문가 인증이나 모델 자동 승격으로
          처리하지 않습니다. 기존 기록은 수정하지 않습니다.
        </p>
        {previous.map((review) => (
          <div className="review-record" key={review.id}>
            <strong>
              사용자 검토 기록 ·{" "}
              {new Date(review.reviewed_at).toLocaleString("ko-KR")}
            </strong>
            <p>
              {rubrics
                .map((rubric) => `${rubric.label} ${review.scores[rubric.key]}`)
                .join(" · ")}
            </p>
            <p>{review.comment || "메모 없음"}</p>
            <small className="mono">
              보고서 SHA {review.report_sha256 || "미기록"}
            </small>
          </div>
        ))}
      </details>
    </article>
  );
}
export default function EvaluationComparison({
  reports,
  authenticated,
}: {
  reports: EvaluationArtifact[];
  authenticated: boolean;
}) {
  const available = reports.filter(
    (report) =>
      report.artifact === "evaluation.json" &&
      report.report.status === "completed" &&
      report.report.items?.length,
  );
  const [leftId, setLeftId] = useState(""),
    [rightId, setRightId] = useState(""),
    [itemId, setItemId] = useState(""),
    [reviews, setReviews] = useState<Review[]>([]),
    [error, setError] = useState("");
  const left =
    available.find((report) => report.run_id === leftId) ||
    available.find((report) => !report.report.adapter) ||
    available[0];
  const right =
    available.find((report) => report.run_id === rightId) ||
    available.find(
      (report) => report.run_id !== left?.run_id && report.report.adapter,
    ) ||
    available.find((report) => report.run_id !== left?.run_id);
  const items = comparisonItems(left, right),
    selected = items.find((item) => item.id === itemId) || items[0];
  useEffect(() => {
    if (authenticated)
      api<{ reviews: Review[] }>("/evaluations/reviews")
        .then((value) => setReviews(value.reviews))
        .catch((error) => setError(errorText(error)));
  }, [authenticated]);
  return (
    <section className="card evaluation-comparison">
      <div className="card-heading">
        <h2>같은 질문 · 전후 비교</h2>
        <span className="badge muted-badge">사용자가 직접 검토</span>
      </div>
      <p className="fine-print">
        완료된 실제 평가 중 데이터 SHA와 생성 조건이 같은 문항만 나란히
        표시합니다. 점수는 미선택 상태로 시작합니다.
      </p>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {available.length < 2 ? (
        <p className="muted">비교 가능한 완료 평가가 2개 이상 필요합니다.</p>
      ) : (
        <>
          <div className="comparison-selectors">
            {[
              { label: "왼쪽 평가", value: left?.run_id, set: setLeftId },
              { label: "오른쪽 평가", value: right?.run_id, set: setRightId },
            ].map((side) => (
              <label key={side.label}>
                {side.label}
                <select
                  value={side.value || ""}
                  onChange={(event) => {
                    side.set(event.target.value);
                    setItemId("");
                  }}
                >
                  {available.map((report) => (
                    <option key={report.run_id} value={report.run_id}>
                      {report.report.adapter ? "어댑터" : "기반"} ·{" "}
                      {report.run_id}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          {!selected || !left || !right ? (
            <p className="notice">
              선택한 평가의 데이터 또는 생성 조건이 다르거나, 공통 문항이
              없습니다.
            </p>
          ) : (
            <>
              <label>
                비교 문항
                <select
                  value={selected.id}
                  onChange={(event) => setItemId(event.target.value)}
                >
                  {items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id}
                    </option>
                  ))}
                </select>
              </label>
              <div className="comparison-question">
                <strong>공통 질문</strong>
                <pre>
                  {selected.left.question ||
                    selected.right.question ||
                    "이 보고서의 질문 원문을 확인할 수 없습니다. 데이터 해시와 문항 ID만 일치합니다."}
                </pre>
              </div>
              <div className="comparison-columns">
                <Answer
                  key={`${left.run_id}:${selected.id}`}
                  run={left}
                  item={selected.left}
                  reviews={reviews}
                  authenticated={authenticated}
                  onSaved={(review) =>
                    setReviews((previous) => [review, ...previous])
                  }
                />
                <Answer
                  key={`${right.run_id}:${selected.id}`}
                  run={right}
                  item={selected.right}
                  reviews={reviews}
                  authenticated={authenticated}
                  onSaved={(review) =>
                    setReviews((previous) => [review, ...previous])
                  }
                />
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
