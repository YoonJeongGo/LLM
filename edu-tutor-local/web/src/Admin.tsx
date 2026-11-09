import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  Check,
  ChevronDown,
  Database,
  FileText,
  FolderOpen,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
} from "lucide-react";
import { activeJob, api, errorText, list, post, statusLabel } from "./api";
import type { Job } from "./api";
import Metrics from "./Metrics";
export function Materials({ authenticated }: { authenticated: boolean }) {
  const [documents, setDocuments] = useState<any[]>([]),
    [results, setResults] = useState<any[]>([]),
    [q, setQ] = useState(""),
    [rights, setRights] = useState(""),
    [subject, setSubject] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [selected, setSelected] = useState<any>(),
    [fullPreview, setFullPreview] = useState<{
      id: string;
      chunks: any[];
    } | null>(null);
  const refresh = async () => {
    try {
      setDocuments(list(await api("/documents")));
    } catch (e) {
      setError(errorText(e));
    }
  };
  useEffect(() => {
    if (authenticated) void refresh();
  }, [authenticated]);
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("rights", rights);
      body.append("subject", subject);
      body.append("title", file.name);
      await api("/documents", { method: "POST", body });
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function previewAll(doc: any) {
    try {
      setFullPreview({
        id: doc.id,
        chunks: list(await api(`/documents/${doc.id}/chunks`)),
      });
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function review(doc: any, approved: boolean) {
    try {
      await post(`/documents/${doc.id}/review`, { approved });
      await refresh();
      setSelected(undefined);
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function remove(doc: any) {
    if (
      !window.confirm(
        `“${doc.title}” 자료와 검색 청크를 삭제합니다. 계속할까요?`,
      )
    )
      return;
    try {
      await api(`/documents/${doc.id}`, { method: "DELETE" });
      await refresh();
      setResults([]);
      setSelected(undefined);
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function search() {
    setBusy(true);
    setError("");
    try {
      setResults(list(await api(`/search?q=${encodeURIComponent(q)}`)));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page-content">
      <div className="section-heading">
        <div>
          <div className="eyebrow">근거를 함께 살펴보는 공부</div>
          <h1>교육자료</h1>
          <p>내 자료를 등록하고, 출처가 있는 답변에 활용하세요.</p>
        </div>
        <span className="badge muted-badge">로컬 보관</span>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      <div className="materials-grid">
        <section className="card">
          <div className="card-heading">
            <h2>자료 등록</h2>
            <Upload size={18} />
          </div>
          <label>
            사용 권한 메모{" "}
            <input
              value={rights}
              onChange={(e) => setRights(e.target.value)}
              placeholder="예: 직접 작성 / 개인 학습 이용 허용"
            />
          </label>
          <label>
            주제{" "}
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="예: SQL 기초"
            />
          </label>
          <label className="upload-zone compact">
            <FolderOpen size={28} />
            <strong>{busy ? "처리 중…" : "자료 파일 선택"}</strong>
            <span>TXT · MD · 텍스트 PDF</span>
            <input
              type="file"
              aria-label="교육자료 업로드"
              accept=".txt,.md,.pdf"
              disabled={!authenticated || busy || !rights.trim()}
              onChange={(e) => upload(e.target.files?.[0])}
            />
          </label>
          <p className="fine-print">
            등록 후 내용을 검토하고 승인하세요. 자료 등록은 모델 추가 학습과
            별개입니다.
          </p>
        </section>
        <section className="card">
          <div className="card-heading">
            <h2>
              등록한 자료 <span className="count">{documents.length}</span>
            </h2>
            <button
              className="icon-button"
              aria-label="자료 새로고침"
              onClick={refresh}
              disabled={!authenticated}
            >
              <RefreshCw size={16} />
            </button>
          </div>
          {documents.length === 0 ? (
            <div className="empty-state">
              <FileText size={30} />
              <strong>아직 등록한 자료가 없습니다</strong>
              <p>
                {authenticated
                  ? "직접 만든 노트부터 추가해 보세요."
                  : "로컬 서버에 연결하면 자료를 관리할 수 있습니다."}
              </p>
            </div>
          ) : (
            <div className="document-list">
              {documents.map((doc) => (
                <button
                  className={`document-item ${selected?.id === doc.id ? "selected" : ""}`}
                  key={doc.id}
                  onClick={() => setSelected(doc)}
                >
                  <div className="file-icon">
                    <FileText size={20} />
                  </div>
                  <div>
                    <strong>{doc.title}</strong>
                    <small>
                      {doc.chunk_count ?? 0}개 청크 ·{" "}
                      {doc.subject || "주제 미지정"}
                    </small>
                  </div>
                  <span
                    className={`badge ${doc.review_status === "approved" ? "green" : "amber"}`}
                  >
                    {statusLabel(doc.review_status)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
      {selected && (
        <section className="card preview-card">
          <div className="card-heading">
            <h2>{selected.title}</h2>
            <div className="button-row">
              <button
                className="button secondary"
                onClick={() => review(selected, true)}
              >
                <Check size={15} />
                검토 승인
              </button>
              <button
                className="button subtle danger"
                onClick={() => remove(selected)}
              >
                <Trash2 size={15} />
                삭제
              </button>
            </div>
          </div>
          <p className="fine-print">
            권한: {selected.rights || "기록 없음"} · 버전:{" "}
            {selected.version ?? 1}
          </p>
          <pre className="document-preview">
            {selected.preview || "미리보기가 없습니다."}
          </pre>
          {selected.preview_truncated && (
            <button
              className="button secondary"
              onClick={() => previewAll(selected)}
            >
              전체 추출 내용 보기
            </button>
          )}
          {fullPreview && fullPreview.id === selected.id && (
            <div>
              {fullPreview.chunks.map((chunk) => (
                <details key={chunk.id || chunk.chunk_id}>
                  <summary>
                    {chunk.page ? `${chunk.page}쪽` : `${chunk.line || 1}행`} ·{" "}
                    {chunk.chunk_id || chunk.id}
                  </summary>
                  <pre className="document-preview">{chunk.text}</pre>
                </details>
              ))}
            </div>
          )}
        </section>
      )}
      <section className="card">
        <div className="card-heading">
          <h2>검색 테스트</h2>
          <span className="fine-print">
            검색 결과의 원문과 출처를 확인합니다
          </span>
        </div>
        <form
          className="search-form"
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
        >
          <Search size={18} />
          <input
            aria-label="자료 검색어"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="어떤 개념을 찾아볼까요?"
          />
          <button
            className="button primary"
            disabled={!authenticated || busy || !q.trim()}
          >
            검색
          </button>
        </form>
        <div className="search-results">
          {results.map((hit) => (
            <article className="search-hit" key={hit.chunk_id}>
              <span className="badge muted-badge">
                {hit.source_title}
                {hit.page ? ` · ${hit.page}쪽` : ""}
                {hit.line ? ` · ${hit.line}행` : ""}
              </span>
              <p>{hit.text}</p>
              <small>청크 {hit.chunk_id} · 검토된 검색 근거</small>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
export function Models({
  authenticated,
  model,
  doctor,
  onRefresh,
}: {
  authenticated: boolean;
  model: any;
  doctor: any;
  onRefresh: () => void;
}) {
  const [modelJobs, setModelJobs] = useState<Job[]>([]);
  useEffect(() => {
    if (authenticated)
      api("/jobs")
        .then((value) => setModelJobs(list(value)))
        .catch(() => {});
  }, [authenticated, model]);
  const [tokens, setTokens] = useState<any>(),
    [text, setText] = useState("NULL은 0과 어떻게 다른가요?"),
    [error, setError] = useState("");
  async function tokenize() {
    setError("");
    try {
      setTokens(await post("/models/tokenize", { text }));
    } catch (e) {
      setError(errorText(e));
    }
  }
  const modules = Array.isArray(model?.modules) ? model.modules : [];
  const moduleGroups = new Map<string, any[]>();
  for (const module of modules) {
    const group =
      String(module.name || "").match(/^(.*?\blayers\.\d+)(?:\.|$)/)?.[1] ||
      "공통 모듈";
    moduleGroups.set(group, [...(moduleGroups.get(group) || []), module]);
  }
  return (
    <div className="page-content">
      <div className="section-heading">
        <div>
          <div className="eyebrow">측정된 정보만, 있는 그대로</div>
          <h1>모델 분석</h1>
          <p>현재 모델과 모듈 구조, 자원 사용을 확인합니다.</p>
        </div>
        <button
          className="button secondary"
          onClick={onRefresh}
          disabled={!authenticated}
        >
          <RefreshCw size={16} />
          새로고침
        </button>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      <div className="stat-grid">
        <div className="stat-card">
          <span>현재 기반 모델</span>
          <strong className="model-name">{model?.model_id || "확인 전"}</strong>
          <small>
            {model?.revision
              ? `revision ${model.revision}`
              : "manifest 기록 없음"}
          </small>
        </div>
        <div className="stat-card">
          <span>모델 상태</span>
          <strong>
            {model?.ready
              ? "준비됨"
              : model?.installed
                ? "설치됨 · 로딩 필요"
                : "미준비"}
          </strong>
          <small>{model?.reason || "서버가 보고한 상태입니다."}</small>
        </div>
        <div className="stat-card">
          <span>다음 생성에 선택된 어댑터</span>
          <strong>{model?.active_adapter || "기반 모델"}</strong>
          <small>
            서버 선택 기록입니다. 마지막 실행 모델과 다를 수 있습니다.
          </small>
        </div>
      </div>
      <section className="card">
        <div className="card-heading">
          <h2>모델 구조도</h2>
          <span className="badge muted-badge">실시간 신경 활동 아님</span>
        </div>
        <div className="key-values">
          <div>
            <span>구조를 마지막으로 읽은 시각</span>
            <b>{model?.last_loaded_at || "기록 없음"}</b>
          </div>
          <div>
            <span>구조 기록의 어댑터</span>
            <b>
              {model?.last_loaded_at
                ? model.last_loaded_adapter || "기반 모델"
                : "기록 없음"}
            </b>
          </div>
          <div>
            <span>GPU 상주 여부</span>
            <b>
              {model?.resident === true
                ? "서버가 상주 상태로 보고함"
                : model?.resident === false
                  ? "상주하지 않음 · 최근 로딩 구조"
                  : "미확인"}
            </b>
          </div>
        </div>
        <p className="fine-print">
          {model?.structure_notice ||
            "실제 실행 그래프는 미지원입니다. 모듈 구조는 최근 로딩 시 수집된 기록이며, 현재 GPU 소유 작업은 시스템 진단에서 확인하세요."}
        </p>
        <p className="fine-print">
          저장 텐서 요소 수 (양자화):{" "}
          {typeof model?.parameter_count === "number"
            ? model.parameter_count.toLocaleString()
            : "미기록"}
          .{" "}
          {model?.parameter_count_notice ||
            "4bit 저장 요소 수는 논리적 모델 파라미터 수와 다를 수 있습니다."}{" "}
          수집된 모듈 {modules.length}개
          {model?.modules_truncated ? " · 일부 구조만 수집됨" : ""}.
        </p>
        {modules.length === 0 ? (
          <div className="empty-state">
            <Database size={30} />
            <strong>로드된 모듈 정보가 없습니다</strong>
            <p>
              실제 named_modules 정보가 준비되면 계층과 파라미터를 표시합니다.
            </p>
          </div>
        ) : (
          <div className="module-tree">
            {Array.from(moduleGroups).map(([group, groupModules]) => (
              <details className="module-layer" key={group}>
                <summary>
                  <strong>{group}</strong>
                  <span>{groupModules.length}개 모듈</span>
                </summary>
                <div className="module-children">
                  {groupModules.map((module: any, i: number) => (
                    <details key={module.name ?? i}>
                      <summary>
                        <span className="mono">{module.name || "(root)"}</span>
                        <span>{module.type || module.class || "module"}</span>
                        <span className="badge muted-badge">
                          {Array.isArray(module.tensors)
                            ? module.tensors.length === 0
                              ? "직접 파라미터 없음"
                              : module.tensors.some(
                                    (tensor: any) => tensor.trainable,
                                  )
                                ? "trainable"
                                : "frozen"
                            : module.trainable === undefined
                              ? "학습 상태 미기록"
                              : module.trainable
                                ? "trainable"
                                : "frozen"}
                        </span>
                        {module.lora === true && (
                          <span className="badge amber">실제 LoRA 모듈</span>
                        )}
                      </summary>
                      <p className="fine-print">
                        직접 저장 텐서 요소 수 (양자화):{" "}
                        {typeof module.parameters === "number"
                          ? module.parameters.toLocaleString()
                          : "미기록"}{" "}
                        · LoRA 직접 모듈:{" "}
                        {module.lora === true
                          ? "예"
                          : module.lora === false
                            ? "아니요"
                            : "미기록"}
                      </p>
                      {Array.isArray(module.tensors) &&
                      module.tensors.length > 0 ? (
                        <div className="table-scroll">
                          <table className="module-tensors">
                            <caption>직접 파라미터의 실제 구조</caption>
                            <thead>
                              <tr>
                                <th>이름</th>
                                <th>shape</th>
                                <th>dtype</th>
                                <th>device</th>
                                <th>학습 여부</th>
                              </tr>
                            </thead>
                            <tbody>
                              {module.tensors.map(
                                (tensor: any, index: number) => (
                                  <tr key={tensor.name || index}>
                                    <td>{tensor.name}</td>
                                    <td>
                                      {Array.isArray(tensor.shape)
                                        ? tensor.shape.join(" × ") || "scalar"
                                        : "미기록"}
                                    </td>
                                    <td>{tensor.dtype || "미기록"}</td>
                                    <td>{tensor.device || "미기록"}</td>
                                    <td>
                                      {tensor.trainable === true
                                        ? "trainable"
                                        : tensor.trainable === false
                                          ? "frozen"
                                          : "미기록"}
                                    </td>
                                  </tr>
                                ),
                              )}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="fine-print">
                          {Array.isArray(module.tensors)
                            ? "직접 파라미터가 없는 상위 모듈입니다. 하위 모듈을 펼쳐 보세요."
                            : "이전 구조 기록에는 tensor 상세가 없습니다. 다음 실제 로딩 시 수집됩니다."}
                        </p>
                      )}
                      <pre className="json-view">
                        {JSON.stringify(module, null, 2)}
                      </pre>
                    </details>
                  ))}
                </div>
              </details>
            ))}
          </div>
        )}
        <details>
          <summary>모델 config / manifest</summary>
          <pre className="json-view">
            {JSON.stringify(model || { state: "아직 연결되지 않음" }, null, 2)}
          </pre>
        </details>
      </section>
      <section className="card">
        <div className="card-heading">
          <h2>실제 학습 지표</h2>
          <span className="badge muted-badge">가장 최근 지표가 있는 작업</span>
        </div>
        <Metrics
          records={
            [...modelJobs]
              .sort((a, b) =>
                (b.created_at || "").localeCompare(a.created_at || ""),
              )
              .find((job) => job.metrics?.length)?.metrics
          }
        />
      </section>
      <section className="card">
        <div className="card-heading">
          <h2>토큰 확인</h2>
          <span className="fine-print">실제 토크나이저 결과</span>
        </div>
        <form
          className="search-form"
          onSubmit={(e) => {
            e.preventDefault();
            void tokenize();
          }}
        >
          <input
            aria-label="토큰 분석할 문장"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button
            className="button primary"
            disabled={!authenticated || !model?.installed}
          >
            분석
          </button>
        </form>
        {tokens && (
          <pre className="json-view">{JSON.stringify(tokens, null, 2)}</pre>
        )}
      </section>
      <section className="card">
        <div className="card-heading">
          <h2>시스템 자원 · 진단</h2>
          <span className="badge muted-badge">전용 VRAM 기준</span>
        </div>
        <p className="fine-print">
          공유 GPU 메모리는 VRAM에 합산하지 않습니다. 수집되지 않은 값은
          미확인입니다.
        </p>
        {doctor?.cached && (
          <p className="notice">
            {doctor.cache_notice ||
              "저장된 환경 진단 기록입니다. 현재 GPU 여유 공간이 아닐 수 있습니다."}{" "}
            기록 시각: {doctor.recorded_at || "미기록"}
          </p>
        )}
        <pre className="json-view">
          {JSON.stringify(
            doctor || {
              status: "N/A",
              reason: "서버 연결 후 확인할 수 있습니다.",
            },
            null,
            2,
          )}
        </pre>
      </section>
    </div>
  );
}
