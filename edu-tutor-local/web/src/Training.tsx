import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  Check,
  Database,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { activeJob, api, errorText, list, post, statusLabel } from "./api";
import type { Job } from "./api";
import Metrics from "./Metrics";
import EvaluationComparison from "./EvaluationComparison";
export default function Training({
  authenticated,
  capabilities,
}: {
  authenticated: boolean;
  capabilities: any;
}) {
  const [jobs, setJobs] = useState<Job[]>([]),
    [error, setError] = useState(""),
    [datasets, setDatasets] = useState<any[]>([]),
    [validation, setValidation] = useState<any>(),
    [tokenAudit, setTokenAudit] = useState<any>(),
    [trainingConfig, setTrainingConfig] = useState<any>(),
    [configError, setConfigError] = useState(""),
    [busy, setBusy] = useState(false),
    [profile, setProfile] = useState("smoke"),
    [evaluationRun, setEvaluationRun] = useState("base"),
    [adapters, setAdapters] = useState<any>({ adapters: [] }),
    [evaluations, setEvaluations] = useState<any>({ reports: [] }),
    [showConfirm, setShowConfirm] = useState(false),
    [datasetId, setDatasetId] = useState("demo");
  const refresh = async () => {
    try {
      const result = await Promise.all([
        api("/jobs"),
        api("/datasets"),
        api("/adapters"),
        api("/evaluations"),
      ]);
      setJobs(list(result[0]));
      setDatasets(result[1].datasets || []);
      setAdapters(result[2]);
      setEvaluations(result[3]);
    } catch (e) {
      setError(errorText(e));
    }
  };
  useEffect(() => {
    if (!authenticated) return;
    void refresh();
    api("/training/config")
      .then((value) => {
        setTrainingConfig(value);
        setConfigError("");
      })
      .catch((error) => setConfigError(errorText(error)));
    const timer = setInterval(
      () =>
        api("/jobs")
          .then((v) => setJobs(list(v)))
          .catch((e) => setError(errorText(e))),
      4000,
    );
    return () => clearInterval(timer);
  }, [authenticated]);
  async function validate() {
    setBusy(true);
    setError("");
    try {
      setValidation(
        await post(
          datasetId === "demo"
            ? "/datasets/validate"
            : `/datasets/${datasetId}/validate`,
        ),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function auditTokens() {
    setBusy(true);
    setError("");
    try {
      setTokenAudit(await api(`/datasets/${datasetId}/token-audit`));
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  async function upload(file?: File) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError("학습 데이터는 5MiB 이하의 JSONL 파일을 사용하세요.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("title", file.name);
      const result = await api("/datasets", { method: "POST", body });
      await refresh();
      setDatasetId(result.id);
      setValidation(undefined);
      setTokenAudit(undefined);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function train() {
    setBusy(true);
    setError("");
    setShowConfirm(false);
    try {
      await post("/train", {
        profile,
        dataset_id: datasetId,
        request_id: crypto.randomUUID(),
      });
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function cancel(id: string) {
    try {
      await post(`/jobs/${id}/cancel`);
      await refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function select(id: string | null) {
    if (
      !window.confirm(
        `${id || "기반 모델"}을 다음 생성부터 적용합니다. 현재 어댑터: ${adapters.active_adapter || "미적용"}. 계속할까요?`,
      )
    )
      return;
    setError("");
    try {
      await post("/adapters/select", { adapter_id: id });
      await refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function rollback() {
    setError("");
    try {
      await post("/adapters/rollback");
      await refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function startEvaluation() {
    setBusy(true);
    setError("");
    try {
      await post("/evaluations", {
        run_id: evaluationRun,
        request_id: crypto.randomUUID(),
      });
      await refresh();
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  const dataset = datasets.find((item) => item.id === datasetId) || datasets[0],
    running = jobs.some(activeJob);
  return (
    <div className="page-content">
      <div className="section-heading">
        <div>
          <div className="eyebrow">검사하고, 비교하고, 선택하세요</div>
          <h1>학습·평가</h1>
          <p>추가 학습은 검토한 데이터와 제한된 실행 예산으로 진행합니다.</p>
        </div>
        <span
          className={`badge ${capabilities?.training?.available ? "green" : "amber"}`}
        >
          {capabilities?.training?.available ? "학습 준비됨" : "학습 준비 필요"}
        </span>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      <div className="workflow-strip">
        <span>
          <b>1</b>데이터 검사
        </span>
        <ArrowRight size={15} />
        <span>
          <b>2</b>학습 예산 확인
        </span>
        <ArrowRight size={15} />
        <span>
          <b>3</b>결과 비교·검토
        </span>
      </div>
      <div className="materials-grid">
        <section className="card">
          <div className="card-heading">
            <h2>구성된 학습 데이터</h2>
            <Database size={18} />
          </div>
          <label>
            데이터셋 선택
            <select
              value={datasetId}
              onChange={(e) => {
                setDatasetId(e.target.value);
                setValidation(undefined);
                setTokenAudit(undefined);
              }}
            >
              {datasets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title || item.id}
                </option>
              ))}
            </select>
          </label>
          <label
            className="button secondary token-file"
            style={{ marginTop: 14 }}
          >
            JSONL 데이터 등록
            <input
              aria-label="학습 데이터 업로드"
              type="file"
              accept=".jsonl"
              disabled={!authenticated || busy}
              onChange={(e) => upload(e.target.files?.[0])}
            />
          </label>
          {dataset ? (
            <>
              <div className="key-values">
                <div>
                  <span>데이터셋</span>
                  <b>
                    {dataset.id} · {dataset.record_count ?? "—"}개 레코드
                  </b>
                </div>
                <div>
                  <span>학습 / 검증 / 평가</span>
                  <b>
                    {dataset.counts
                      ? Object.entries(dataset.counts)
                          .map(([key, value]) => `${key} ${value}`)
                          .join(" / ")
                      : "검사 필요"}
                  </b>
                </div>
                <div>
                  <span>사람의 내용 검토</span>
                  <b>
                    {dataset.human_review === "not_reviewed"
                      ? "미실행"
                      : dataset.human_review}
                  </b>
                </div>
              </div>
              <button
                className="button secondary"
                onClick={validate}
                disabled={busy || !authenticated}
              >
                <Check size={15} />
                데이터 검사 실행
              </button>
              <button
                className="button secondary"
                style={{ marginLeft: 8 }}
                onClick={auditTokens}
                disabled={busy || !authenticated || !validation?.valid}
              >
                실제 토큰 길이 검사
              </button>
            </>
          ) : (
            <div className="empty-state">
              <Database size={27} />
              <strong>연결 후 구성된 데이터를 표시합니다</strong>
            </div>
          )}
          {validation && (
            <details open>
              <summary>
                실제 검사 결과 ·{" "}
                {validation.valid ? "구조 검사 통과" : "검사 실패"}
              </summary>
              <pre className="json-view">
                {JSON.stringify(validation, null, 2)}
              </pre>
            </details>
          )}
          {tokenAudit && (
            <details open>
              <summary>
                실제 토크나이저 검사 · {tokenAudit.valid} / {tokenAudit.total}개
                통과
              </summary>
              <p className="fine-print">
                최대 {tokenAudit.max_sequence_length}토큰 · assistant 응답만
                학습 대상으로 표시 · 데이터 SHA {tokenAudit.dataset_sha256}
              </p>
              <div className="table-scroll">
                <table className="module-tensors">
                  <thead>
                    <tr>
                      <th>문항 / split</th>
                      <th>전체 길이</th>
                      <th>학습 대상 토큰</th>
                      <th>검사</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tokenAudit.items?.map((item: any) => (
                      <tr key={item.id}>
                        <td>
                          {item.id}
                          <br />
                          {item.split}
                        </td>
                        <td>{item.valid_length ?? "—"}</td>
                        <td>{item.target_tokens ?? "—"}</td>
                        <td>{item.valid ? "통과" : item.error || "실패"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <details>
                <summary>마스킹·학습 대상 decode 상세</summary>
                <pre className="json-view">
                  {JSON.stringify(tokenAudit, null, 2)}
                </pre>
              </details>
            </details>
          )}
          <p className="fine-print">
            JSONL은 5MiB 이하이며 family·split·권한 필드를 검사합니다. 교육자료
            등록은 추가 학습과 별개입니다. 구조 검사 통과가 교육 정확성을
            보장하지 않습니다.
          </p>
        </section>
        <section className="card">
          <div className="card-heading">
            <h2>제한된 학습 실행</h2>
            <ShieldCheck size={18} />
          </div>
          {trainingConfig ? (
            <>
              <p className="fine-print">
                데모·smoke 범위입니다. 운영 학습은 지원하지 않습니다.
              </p>
              <div className="key-values">
                <div>
                  <span>양자화 / LoRA</span>
                  <b>
                    {trainingConfig.training.bnb_4bit_quant_type} · r{" "}
                    {trainingConfig.training.lora_r} / α{" "}
                    {trainingConfig.training.lora_alpha}
                  </b>
                </div>
                <div>
                  <span>batch × 누적</span>
                  <b>
                    {trainingConfig.training.batch_size} ×{" "}
                    {trainingConfig.training.gradient_accumulation_steps}
                  </b>
                </div>
                <div>
                  <span>학습률 / 최대 길이</span>
                  <b>
                    {trainingConfig.training.learning_rate} /{" "}
                    {trainingConfig.training.max_sequence_length}토큰
                  </b>
                </div>
                <div>
                  <span>학습 대상 모듈</span>
                  <b>{trainingConfig.training.target_modules?.join(", ")}</b>
                </div>
              </div>
              <details>
                <summary>서버 고정 설정·자원 예산 전체</summary>
                <pre className="json-view">
                  {JSON.stringify(trainingConfig, null, 2)}
                </pre>
              </details>
            </>
          ) : (
            <p className="fine-print">
              서버 설정 미확인{configError ? ` · ${configError}` : ""}
            </p>
          )}
          <label>
            실행 프로필
            <select
              value={profile}
              onChange={(e) => {
                setProfile(e.target.value);
                setShowConfirm(false);
              }}
            >
              <option value="smoke">GPU QLoRA smoke</option>
              <option value="demo">데모 학습</option>
            </select>
          </label>
          <div className="key-values">
            <div>
              <span>최대 optimizer step</span>
              <b>{profile === "smoke" ? 5 : 50} step</b>
            </div>
            <div>
              <span>시간 제한</span>
              <b>{profile === "smoke" ? 600 : 900}초</b>
            </div>
            <div>
              <span>완료 후 모델 적용</span>
              <b>관리자가 선택</b>
            </div>
          </div>
          <p className="fine-print">
            {running
              ? "다른 작업이 실행 중입니다. 완료 또는 실제 중지 후 시작하세요."
              : "GPU 작업이 없는 상태에서 시작합니다. 데이터와 기반 모델은 덮어쓰지 않습니다."}
          </p>
          <button
            className="button primary"
            disabled={
              !authenticated ||
              busy ||
              !validation?.valid ||
              !tokenAudit?.total ||
              tokenAudit.valid !== tokenAudit.total ||
              !trainingConfig ||
              !capabilities?.training?.available ||
              running
            }
            onClick={() => setShowConfirm(true)}
          >
            예산 확인 후 학습
          </button>
          {showConfirm && (
            <div className="notice" style={{ marginTop: 12, flexWrap: "wrap" }}>
              <span>
                {dataset?.id} 데이터 · {profile === "smoke" ? 5 : 50} step ·
                최대 {profile === "smoke" ? 600 : 900}초. 이 범위로 실제 GPU
                학습을 시작합니다.
              </span>
              <button className="button primary" onClick={train}>
                이 범위로 시작
              </button>
              <button
                className="text-button"
                onClick={() => setShowConfirm(false)}
              >
                취소
              </button>
            </div>
          )}
          {!capabilities?.training?.available && (
            <p className="fine-print">
              {capabilities?.training?.reason ||
                "서버 연결 후 사용 가능 여부를 확인합니다."}
            </p>
          )}
        </section>
      </div>
      <section className="card">
        <div className="card-heading">
          <h2>실제 작업 기록</h2>
          <button
            className="icon-button"
            aria-label="작업 새로고침"
            onClick={refresh}
            disabled={!authenticated}
          >
            <RefreshCw size={16} />
          </button>
        </div>
        {jobs.length === 0 ? (
          <div className="empty-state">
            <Activity size={30} />
            <strong>아직 실행 기록이 없습니다</strong>
            <p>실제로 실행한 학습·평가·생성 작업이 이곳에 표시됩니다.</p>
          </div>
        ) : (
          <div className="job-list">
            {jobs.map((job) => (
              <div className="job-item" key={job.id}>
                <div>
                  <strong>{job.kind || job.type || "작업"}</strong>
                  <small>{job.id}</small>
                </div>
                <span
                  className={`badge ${activeJob(job) ? "amber" : "muted-badge"}`}
                >
                  {job.cancel_requested && activeJob(job)
                    ? "취소 요청됨 · 안전 경계 대기"
                    : statusLabel(job.state ?? job.status)}
                </span>
                {(job.worker_phase || job.worker_reason) && (
                  <p className="fine-print job-phase">
                    작업 단계: {job.worker_phase || "미기록"}
                    {job.worker_reason ? ` · ${job.worker_reason}` : ""}
                  </p>
                )}
                {activeJob(job) && (
                  <button
                    className="button secondary"
                    onClick={() => cancel(job.id)}
                    disabled={job.cancel_requested}
                  >
                    중지 요청
                  </button>
                )}
                <div className="job-metrics">
                  {job.metrics?.length ? (
                    <Metrics records={job.metrics} />
                  ) : null}
                </div>
                <details>
                  <summary>작업·검증 상세</summary>
                  <pre className="json-view">
                    {JSON.stringify(
                      {
                        progress: job.progress,
                        result: job.result,
                        error: job.error,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </div>
            ))}
          </div>
        )}
      </section>
      <section className="card">
        <div className="card-heading">
          <h2>어댑터 적용 · 복귀</h2>
          <span className="badge muted-badge">
            현재 {adapters.active_adapter || "기반 모델"}
          </span>
        </div>
        {adapters.adapters?.length ? (
          adapters.adapters.map((adapter: any) => (
            <div className="job-item" key={adapter.id}>
              <div>
                <strong>{adapter.id}</strong>
                <small>
                  base revision {adapter.base_revision} ·{" "}
                  {adapter.human_review || "사람 검토 미확인"}
                </small>
              </div>
              <button
                className="button secondary"
                disabled={running || adapter.id === adapters.active_adapter}
                onClick={() => select(adapter.id)}
              >
                이 어댑터 적용
              </button>
              <details>
                <summary>실제 저장·평가 정보</summary>
                <pre className="json-view">
                  {JSON.stringify(adapter, null, 2)}
                </pre>
              </details>
            </div>
          ))
        ) : (
          <p className="muted">저장된 어댑터가 없습니다.</p>
        )}
        <div className="button-row">
          <button
            className="button secondary"
            disabled={!authenticated || running || !adapters.active_adapter}
            onClick={() => select(null)}
          >
            기반 모델 적용
          </button>
          <button
            className="button secondary"
            disabled={!authenticated || running || !adapters.history?.length}
            onClick={rollback}
          >
            <RotateCcw size={15} />
            이전 선택으로 복귀
          </button>
        </div>
      </section>
      <EvaluationComparison
        reports={evaluations.reports || []}
        authenticated={authenticated}
      />
      <section className="card">
        <div className="card-heading">
          <h2>학습·평가 결과</h2>
          <span className="badge muted-badge">실제 실행 기록</span>
        </div>
        <div className="evaluation-start">
          <label>
            평가할 모델
            <select
              value={evaluationRun}
              onChange={(event) => setEvaluationRun(event.target.value)}
            >
              <option value="base">기반 모델</option>
              {adapters.adapters?.map((adapter: any) => (
                <option key={adapter.id} value={adapter.id}>
                  {adapter.id}
                </option>
              ))}
            </select>
          </label>
          <button
            className="button secondary"
            disabled={
              !authenticated ||
              busy ||
              running ||
              !capabilities?.text?.available
            }
            onClick={startEvaluation}
          >
            평가 시작
          </button>
        </div>
        <p className="fine-print">
          고정된 소규모 평가 세트 · RAG 사용 안 함. 실제 GPU 작업을 시작하며,
          평가 후 자동 승격하지 않습니다.
        </p>
        <p className="muted">
          {evaluations.notice ||
            "같은 질문과 조건으로 실행한 결과만 비교합니다. 교육 정확성은 별도로 검토해야 합니다."}
        </p>
        {evaluations.reports?.length ? (
          evaluations.reports.map((report: any, i: number) => (
            <details key={`${report.run_id}:${report.artifact}:${i}`}>
              <summary>
                {report.run_id} · {report.artifact}
              </summary>
              <Metrics records={report.report?.log_history} />
              <pre className="json-view">
                {JSON.stringify(report.report, null, 2)}
              </pre>
            </details>
          ))
        ) : (
          <div className="empty-state">
            <Activity size={27} />
            <strong>아직 평가 기록이 없습니다</strong>
            <p>측정한 값 없이 임의 그래프를 표시하지 않습니다.</p>
          </div>
        )}
      </section>
    </div>
  );
}
