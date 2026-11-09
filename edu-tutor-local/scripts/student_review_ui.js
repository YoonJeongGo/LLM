/* Offline, explicit local self-records only. No API, fetch, synthesis or H promotion. */
(() => {
  "use strict";
  const KEY = "edu-tutor.local-evidence-review.v1";
  const MAX_FILE_BYTES = 2 * 1024 * 1024, MAX_RECORDS = 500;
  const statuses = ["미검토", "통과", "수정 필요", "판단 어려움"];
  const issues = ["미지정", "사실 오류", "조건 누락", "불필요한 설명", "한국어 발음", "SQL/수식 읽기", "판서 불일치", "가리키는 행 오류", "대화 맥락 상실"];
  const forms = [...document.querySelectorAll("form.review-form")];
  const targets = new Map(forms.map(form => {
    const context = JSON.parse(form.dataset.reviewTarget);
    return [context.target_id, context];
  }));
  const list = document.getElementById("review-records");
  const notice = document.getElementById("review-notice");
  const count = document.getElementById("review-count");
  let records = [];
  let storageAvailable = true;
  let protectUnreadableStorage = false;
  const tell = text => { notice.textContent = text; };
  const shortString = (value, max, allowEmpty = false) => typeof value === "string" && value.length <= max && (allowEmpty || value.trim().length > 0);
  const dateString = value => shortString(value, 40) && /^\d{4}-\d{2}-\d{2}T/.test(value) && Number.isFinite(Date.parse(value));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const fields = ["review_id", "record_version", "reviewer", "reviewed_at", "saved_at", "target_id", "run_id", "case_id", "case_started_at", "lesson_id", "step_id", "audio_id", "audio_sha256", "audio_offset_seconds", "heard_utterance", "issue_kind", "comment", "review_status", "scope"];

  function validate(record) {
    if (!record || typeof record !== "object" || Array.isArray(record) || Object.keys(record).some(k => !fields.includes(k)) || fields.some(k => !(k in record))) throw new Error("검토 기록 필드가 올바르지 않습니다.");
    if (!shortString(record.review_id, 100) || !/^[a-zA-Z0-9_-]+$/.test(record.review_id) || record.record_version !== 1 || record.scope !== "local_self_record_not_global_approval") throw new Error("지원하지 않는 검토 기록 형식입니다.");
    const target = targets.get(record.target_id);
    if (!target) throw new Error("이 증거 페이지에 없는 사례/음성 기록입니다.");
    for (const k of ["run_id", "case_id", "case_started_at", "lesson_id", "step_id", "audio_id", "audio_sha256"]) {
      if (!same(record[k], target[k])) throw new Error("사례·단계·음성 ID 또는 SHA가 원본과 다릅니다.");
    }
    if (!shortString(record.reviewer, 120) || !dateString(record.reviewed_at) || !dateString(record.saved_at)) throw new Error("검토자 또는 시각을 확인하세요.");
    if (!shortString(record.heard_utterance, 2000, true) || !shortString(record.comment, 4000, true) || !statuses.includes(record.review_status) || !issues.includes(record.issue_kind)) throw new Error("검토 내용 또는 상태가 올바르지 않습니다.");
    if (record.audio_offset_seconds !== null && (typeof record.audio_offset_seconds !== "number" || !Number.isFinite(record.audio_offset_seconds) || record.audio_offset_seconds < 0 || !target.audio_id || record.audio_offset_seconds > target.duration_seconds + 0.05)) throw new Error("음성 위치가 원본 WAV 범위를 벗어났습니다.");
    if (target.audio_id && record.review_status !== "미검토" && record.audio_offset_seconds === null) throw new Error("현재 음성 위치 읽기를 눌러 검토 위치를 기록하세요.");
    return record;
  }

  function parseEnvelope(text) {
    if (new TextEncoder().encode(text).length > MAX_FILE_BYTES) throw new Error("JSON은 2MB 이하여야 합니다.");
    const data = JSON.parse(text);
    if (!data || data.schema_version !== 1 || data.scope !== "local_self_records_not_global_approval" || !dateString(data.exported_at) || !Array.isArray(data.records) || data.records.length > MAX_RECORDS || Object.keys(data).some(k => !["schema_version", "scope", "exported_at", "records"].includes(k))) throw new Error("지원하지 않는 검토 JSON입니다.");
    return data.records.map(validate);
  }

  function envelope(items = records) {
    return { schema_version: 1, scope: "local_self_records_not_global_approval", exported_at: new Date().toISOString(), records: items };
  }

  function append(items) {
    const candidate = [...records, ...items];
    if (candidate.length > MAX_RECORDS || new TextEncoder().encode(JSON.stringify(envelope(candidate), null, 2)).length > MAX_FILE_BYTES) throw new Error("기존 기록과 합친 결과가 500개 또는 2MB를 초과합니다. 기존 기록을 유지하고 추가를 중단했습니다.");
    records = candidate;
  }

  function render() {
    count.textContent = String(records.length);
    list.replaceChildren();
    const duplicates = new Map();
    for (const record of records) duplicates.set(record.review_id, (duplicates.get(record.review_id) || 0) + 1);
    for (const record of records) {
      const item = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `${record.case_id} · ${record.step_id || "조건 차단"} · ${record.review_status} · ${record.reviewer}`;
      const body = document.createElement("pre");
      body.textContent = JSON.stringify(record, null, 2);
      item.append(summary, body);
      if (duplicates.get(record.review_id) > 1) {
        const warning = document.createElement("p");
        warning.textContent = "같은 review_id의 기록도 덮어쓰지 않고 각각 보존했습니다.";
        item.append(warning);
      }
      list.append(item);
    }
  }

  function persist() {
    if (protectUnreadableStorage) { render(); return false; }
    try { localStorage.setItem(KEY, JSON.stringify(envelope())); storageAvailable = true; }
    catch { storageAvailable = false; }
    render();
    return storageAvailable;
  }

  try {
    const saved = localStorage.getItem(KEY);
    if (saved) records = parseEnvelope(saved);
    tell("검토를 직접 저장한 경우에만 기록합니다. 개별 기록은 전체 교육 승인이 아닙니다.");
  } catch (error) {
    storageAvailable = false;
    protectUnreadableStorage = true;
    tell("브라우저 저장소를 읽지 못했습니다. 원래 저장값은 지우지 않습니다. 이 페이지의 기록은 JSON 내보내기로 보존하세요. " + error.message);
  }
  render();

  for (const form of forms) {
    const context = JSON.parse(form.dataset.reviewTarget);
    const localNow = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    form.elements.namedItem("review_date").value = localNow.slice(0, 10);
    form.elements.namedItem("review_time").value = localNow.slice(11, 16);
    const feedback = form.querySelector(".review-feedback");
    form.querySelector("[data-read-offset]")?.addEventListener("click", () => {
      const audio = document.getElementById(form.dataset.audioElement);
      if (!audio || !Number.isFinite(audio.duration) || audio.readyState < 1) {
        feedback.textContent = "원본 음성을 재생하거나 메타데이터를 불러온 뒤 위치를 기록하세요.";
        return;
      }
      form.elements.namedItem("audio_offset_seconds").value = audio.currentTime.toFixed(3);
      feedback.textContent = `원본 음성의 현재 위치 ${audio.currentTime.toFixed(3)}초를 읽었습니다. 들은 발화는 직접 입력하세요.`;
    });
    form.addEventListener("submit", event => {
      event.preventDefault();
      try {
        if (!form.reportValidity()) return;
        if (records.length >= MAX_RECORDS) throw new Error("현재 페이지는 500개 기록까지만 보관합니다. 먼저 JSON으로 내보내세요.");
        const get = name => form.elements.namedItem(name).value;
        const offset = get("audio_offset_seconds");
        const record = {
          review_id: crypto.randomUUID(), record_version: 1,
          reviewer: get("reviewer").trim(), reviewed_at: new Date(get("review_date") + "T" + get("review_time")).toISOString(), saved_at: new Date().toISOString(),
          ...Object.fromEntries(["target_id", "run_id", "case_id", "case_started_at", "lesson_id", "step_id", "audio_id", "audio_sha256"].map(k => [k, context[k]])),
          audio_offset_seconds: offset === "" ? null : Number(offset), heard_utterance: get("heard_utterance"),
          issue_kind: get("issue_kind"), comment: get("comment"), review_status: get("review_status"), scope: "local_self_record_not_global_approval"
        };
        validate(record);
        append([record]);
        const stored = persist();
        feedback.textContent = stored ? "개별 자기 기록을 브라우저에 저장했습니다. JSON도 내보내 보존하세요. H_PENDING은 유지됩니다." : "현재 페이지 메모리에 기록했습니다. 브라우저 저장은 불가하므로 반드시 JSON을 내보내세요. H_PENDING은 유지됩니다.";
        tell(feedback.textContent);
      } catch (error) { feedback.textContent = error.message; }
    });
  }

  document.getElementById("review-export").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(envelope(), null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "edu-tutor-local-reviews.json"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    tell("검토 JSON 다운로드를 요청했습니다. 파일 저장 완료는 브라우저 다운로드에서 확인하세요. 서버에는 전송하지 않습니다.");
  });
  document.getElementById("review-import").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > MAX_FILE_BYTES) throw new Error("JSON은 2MB 이하여야 합니다.");
      const incoming = parseEnvelope(await file.text());
      if (records.length + incoming.length > MAX_RECORDS) throw new Error("기존 기록과 합해 500개를 초과합니다. 가져오기를 중단했습니다.");
      append(incoming); // Append even repeated review IDs; never overwrite a prior record.
      const stored = persist();
      tell(`${incoming.length}개 기록을 추가했습니다. 중복 ID도 각각 보존하며 H_PENDING은 유지됩니다.` + (stored ? "" : " 브라우저 저장 불가: 반드시 JSON으로 내보내세요."));
    } catch (error) { tell("가져오기 중단: " + error.message + " 기존 기록은 유지합니다."); }
    event.target.value = "";
  });
})();
