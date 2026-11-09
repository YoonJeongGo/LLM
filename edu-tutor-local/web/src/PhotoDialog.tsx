import { useEffect, useRef, useState } from "react";
import { Check, FileImage, Save, Upload, X } from "lucide-react";
import { api, errorText, post, waitForJob, protectedBlob, list } from "./api";
import { lessonEvent } from "./student";
export default function PhotoDialog({
  onClose,
  onSolved,
  sessionId,
  visionAvailable,
  photoId,
  onRevisionChange,
  textGenerationAllowed = false,
  visionGenerationAllowed = false,
}: {
  onClose: () => void;
  onSolved: (result: any) => void;
  sessionId?: string;
  visionAvailable: boolean;
  textGenerationAllowed?: boolean;
  visionGenerationAllowed?: boolean;
  photoId?: string;
  onRevisionChange?: (photo: any) => void;
}) {
  const [photo, setPhoto] = useState<any>();
  const [savedPhotos, setSavedPhotos] = useState<any[]>([]);
  const [selectedPhotoId, setSelectedPhotoId] = useState(photoId || "");
  const [preview, setPreview] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [question, setQuestion] = useState("");
  const [sql, setSql] = useState("");
  const [tables, setTables] = useState("[]");
  const [choices, setChoices] = useState("");
  const [missing, setMissing] = useState("");
  const [unreadable, setUnreadable] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const recognition = useRef<
    { controller: AbortController; id?: string } | undefined
  >(undefined);
  const [recognizing, setRecognizing] = useState(false);
  function fillPhoto(result: any) {
    setPhoto(result);
    setQuestion(result.question || "");
    setSql(result.sql || "");
    setTables(JSON.stringify(result.tables || [], null, 2));
    setChoices((result.choices || []).join("\n"));
    setMissing((result.missing_conditions || []).join("\n"));
    setUnreadable((result.unreadable_regions || []).join("\n"));
    setDirty(false);
  }
  useEffect(() => {
    setSelectedPhotoId(photoId || "");
  }, [photoId]);
  useEffect(() => {
    if (photoId) return;
    const controller = new AbortController();
    api("/photos", { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) setSavedPhotos(list(result));
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(errorText(error));
      });
    return () => controller.abort();
  }, [photoId]);
  useEffect(() => {
    if (!selectedPhotoId) return;
    const controller = new AbortController();
    setBusy(true);
    setError("");
    Promise.all([
      api(`/photos/${selectedPhotoId}`, { signal: controller.signal }),
      protectedBlob(`/photos/${selectedPhotoId}/image`, controller.signal),
    ])
      .then(([value, blob]) => {
        if (controller.signal.aborted) return;
        fillPhoto(value);
        setPreview(URL.createObjectURL(blob));
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(errorText(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [selectedPhotoId]);
  useEffect(() => {
    dialog.current?.showModal();
    return () => {
      const request = recognition.current;
      request?.controller.abort();
      if (request?.id) void post(`/jobs/${request.id}/cancel`).catch(() => {});
    };
  }, []);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  const lines = (value: string) =>
    value
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
  async function upload(file?: File) {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setError("사진은 10MiB 이하로 올려 주세요.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = new FormData();
      data.append("file", file);
      if (sessionId) data.append("session_id", sessionId);
      const result = await api("/photos", { method: "POST", body: data });
      setPhoto(result);
      setPreview(URL.createObjectURL(file));
      setQuestion(result.question || "");
      setSql(result.sql || "");
      setTables(JSON.stringify(result.tables || [], null, 2));
      setChoices((result.choices || []).join("\n"));
      setMissing((result.missing_conditions || []).join("\n"));
      setUnreadable((result.unreadable_regions || []).join("\n"));
      setDirty(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!photo) return;
    setBusy(true);
    setError("");
    try {
      const parsed = JSON.parse(tables);
      if (!Array.isArray(parsed))
        throw new Error("표는 JSON 배열로 입력해 주세요.");
      const result = await api(`/photos/${photo.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          question,
          sql,
          tables: parsed,
          choices: lines(choices),
          unreadable_regions: lines(unreadable),
          missing_conditions: lines(missing),
        }),
      });
      setPhoto(result);
      setDirty(false);
      onRevisionChange?.(result);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    setBusy(true);
    setError("");
    try {
      setPhoto(await post(`/photos/${photo.id}/confirm`));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function restructure() {
    if (!photo?.original_text || busy || dirty) return;
    setBusy(true);
    setError("");
    try {
      const result = await post(`/photos/${photo.id}/restructure`);
      fillPhoto(result);
      onRevisionChange?.(result);
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  async function solve() {
    if (!textGenerationAllowed) { setError("활성 수업 한도와 남은 질문 횟수를 먼저 확인해 주세요."); return; }
    lessonEvent("question_submitted", {
      input_kind: "photo",
      photo_id: photo.id,
    });
    setBusy(true);
    setError("");
    try {
      const id =
        sessionId ||
        (
          await post("/sessions", {
            title: question.slice(0, 38) || "사진 문제",
          })
        ).id;
      const result = await post(`/photos/${photo.id}/solve`, {
        session_id: id,
        request_id: crypto.randomUUID(),
      });
      onSolved({ ...result, session_id: id });
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function recognize() {
    if (!visionGenerationAllowed) { setError("활성 수업 한도와 남은 사진 인식 횟수를 먼저 확인해 주세요."); return; }
    setBusy(true);
    setRecognizing(true);
    setError("");
    const request = {
      controller: new AbortController(),
      id: undefined as string | undefined,
    };
    recognition.current = request;
    try {
      const result = await post(`/photos/${photo.id}/transcribe`);
      request.id = result.job_id;
      if (
        request.controller.signal.aborted ||
        recognition.current !== request
      ) {
        await post(`/jobs/${result.job_id}/cancel`).catch(() => {});
        return;
      }
      await waitForJob(result.job_id, request.controller.signal);
      const updated = await api(`/photos/${photo.id}`, {
        signal: request.controller.signal,
      });
      if (request.controller.signal.aborted || recognition.current !== request)
        return;
      setPhoto(updated);
      setQuestion(updated.question || "");
      setSql(updated.sql || "");
      setTables(JSON.stringify(updated.tables || [], null, 2));
      setChoices((updated.choices || []).join("\n"));
      setMissing((updated.missing_conditions || []).join("\n"));
      setUnreadable((updated.unreadable_regions || []).join("\n"));
      setDirty(false);
      request.id = undefined;
    } catch (e) {
      if (!request.controller.signal.aborted) setError(errorText(e));
    } finally {
      if (recognition.current === request) {
        setBusy(false);
        setRecognizing(false);
        recognition.current = undefined;
      }
    }
  }
  async function cancelRecognition() {
    const request = recognition.current;
    request?.controller.abort();
    recognition.current = undefined;
    if (request?.id)
      await post(`/jobs/${request.id}/cancel`).catch((e) =>
        setError(errorText(e)),
      );
    setRecognizing(false);
    setBusy(false);
  }
  async function deletePhoto() {
    if (
      !window.confirm("이 문제 사진과 인식·교정 원문을 삭제합니다. 계속할까요?")
    )
      return;
    try {
      await api(`/photos/${photo.id}`, { method: "DELETE" });
      onClose();
    } catch (e) {
      setError(errorText(e));
    }
  }
  return (
    <dialog className="photo-dialog" ref={dialog} onCancel={onClose}>
      <div className="dialog-heading">
        <div>
          <span className="eyebrow">사진으로 질문하기</span>
          <h2>문제를 풀기 전에, 원문 확인</h2>
        </div>
        <button
          className="icon-button"
          aria-label="사진 창 닫기"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      <div className="notice">
        인식한 숫자와 조건을 먼저 확인해 주세요. 사진은 학습 자료에 자동
        등록되지 않습니다.
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {!photo ? (
        <>
          {savedPhotos.length > 0 && (
            <label>
              저장한 사진
              <select
                aria-label="저장한 사진"
                style={{ width: "100%", maxWidth: "100%" }}
                value={selectedPhotoId}
                disabled={busy}
                onChange={(event) => setSelectedPhotoId(event.target.value)}
              >
                <option value="">이전에 저장한 사진 선택</option>
                {savedPhotos.map((saved, index) => (
                  <option key={saved.id} value={saved.id}>
                    {saved.created_at
                      ? `${String(saved.created_at).slice(0, 19).replace("T", " ")} · `
                      : ""}
                    {String(saved.question || `저장한 사진 ${index + 1}`).slice(
                      0,
                      30,
                    )}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="upload-zone">
            <FileImage size={36} />
            <strong>문제 사진 선택</strong>
            <span>PNG · JPEG · WebP / 최대 10MiB · 20MP</span>
            <input
              aria-label="문제 사진 업로드"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={busy}
              onChange={(e) => upload(e.target.files?.[0])}
            />
          </label>
        </>
      ) : (
        <div className="photo-grid">
          <div>
            <img
              className="photo-preview"
              src={preview}
              alt="업로드한 문제 원본"
            />
            <span className="badge amber">
              {photo.recognition_status === "not_run"
                ? "자동 인식 미실행 · 직접 입력"
                : "인식 후보 · 원문과 대조 필요"}
            </span>
            <p className="fine-print">
              원문 수정은 새 revision으로 저장됩니다. 미확정 문제로 풀이를
              시작할 수 없습니다.
            </p>
            {!!photo.structure_extraction?.type_inferences?.length && (
              <p className="inline-status" role="note">
                표의 자료형은 보이는 값으로 추정한 후보입니다. 원문에서 자료형을
                읽은 결과가 아니므로, 아래 표 편집에서 열·값·자료형을 확인해 주세요.
              </p>
            )}
            <div className="button-row" style={{ marginTop: 14 }}>
              <button
                className="button secondary"
                disabled={busy || dirty || !visionAvailable || !visionGenerationAllowed}
                onClick={recognize}
              >
                로컬 모델로 원문 인식
              </button>
              {recognizing && (
                <button
                  className="button secondary"
                  onClick={cancelRecognition}
                >
                  인식 중지
                </button>
              )}
              {photo.original_text && (
                <button
                  className="button secondary"
                  disabled={busy || dirty}
                  onClick={restructure}
                >
                  인식문에서 표 다시 정리
                </button>
              )}
              <button
                className="text-button danger"
                disabled={busy}
                onClick={deletePhoto}
              >
                사진 삭제
              </button>
            </div>
            {!visionAvailable && (
              <p className="fine-print">
                로컬 비전 모델이 준비되지 않았습니다. 원문을 직접 입력할 수
                있습니다.
              </p>
            )}
            <details>
              <summary>최초 인식 원문</summary>
              <pre>{photo.original_text || "자동 인식 결과가 없습니다."}</pre>
            </details>
          </div>
          <fieldset
            disabled={busy}
            className="photo-fields"
            onChange={() => setDirty(true)}
          >
            <label>
              문제 본문{" "}
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={4}
              />
            </label>
            <label>
              SQL / 코드{" "}
              <textarea
                className="mono"
                value={sql}
                onChange={(e) => setSql(e.target.value)}
                rows={3}
              />
            </label>
            <label>
              보기{" "}
              <textarea
                value={choices}
                onChange={(e) => setChoices(e.target.value)}
                placeholder="보기마다 한 줄"
                rows={2}
              />
            </label>
            <details>
              <summary>표 · 읽지 못한 부분 · 누락 조건 편집</summary>
              <label>
                표 (JSON 배열)
                <textarea
                  className="mono"
                  aria-label="사진 표 JSON"
                  value={tables}
                  onChange={(e) => setTables(e.target.value)}
                  rows={4}
                />
              </label>
              <label>
                읽지 못한 부분
                <textarea
                  value={unreadable}
                  onChange={(e) => setUnreadable(e.target.value)}
                  rows={2}
                />
              </label>
              <label>
                누락 조건
                <textarea
                  value={missing}
                  onChange={(e) => setMissing(e.target.value)}
                  rows={2}
                />
              </label>
            </details>
            <div className="photo-status">
              <span
                className={`badge ${photo.confirmed && !dirty ? "green" : "amber"}`}
              >
                {photo.confirmed && !dirty ? "원문 확정" : "미확정"}
              </span>
              <span>
                revision {photo.revision ?? 1}
                {dirty ? " · 저장하지 않은 수정" : ""}
              </span>
            </div>
            <div className="button-row">
              <button
                className="button secondary"
                onClick={save}
                disabled={busy || !dirty}
              >
                <Save size={15} />
                교정 저장
              </button>
              <button
                className="button secondary"
                onClick={confirm}
                disabled={busy || dirty || !question.trim() || photo.confirmed}
              >
                <Check size={15} />이 원문으로 확정
              </button>
              <button
                className="button primary"
                onClick={solve}
                disabled={busy || dirty || !photo.confirmed || !textGenerationAllowed}
              >
                확정한 문제 풀이
              </button>
            </div>
          </fieldset>
        </div>
      )}
      {busy && <p role="status">로컬 서버에서 처리 중입니다…</p>}
      <div className="dialog-footer">
        <span>외부 업로드 없이 이 PC에서 처리합니다.</span>
        <button className="text-button" onClick={onClose}>
          닫기
        </button>
      </div>
    </dialog>
  );
}
