import { activeJob, api } from "./api";

/** Local browser events only: no network telemetry or retained student content. */
export function lessonEvent(
  type: string,
  detail: Record<string, unknown> = {},
) {
  window.dispatchEvent(
    new CustomEvent("edu:lesson", {
      detail: {
        type,
        at_ms: performance.now(),
        at_iso: new Date().toISOString(),
        ...detail,
      },
    }),
  );
}

export type SpeechRequest = {
  controller: AbortController;
  id?: string;
  completed?: boolean;
  creation?: Promise<any>;
  cancellation?: Promise<void>;
  serverCancellation?: Promise<void>;
};

export function cancelSpeechRequest(request?: SpeechRequest): Promise<void> {
  if (!request) return Promise.resolve();
  request.controller.abort();
  // Keep server cleanup independent from the bounded UI wait. Even after the
  // caller times out, a late POST response still supplies a job we must cancel.
  request.serverCancellation ??= (async () => {
    if (!request.id && request.creation) {
      const created = await request.creation;
      request.id = created.job_id;
    }
    if (!request.id) return;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    const signal = controller.signal;
    try {
      await api(`/jobs/${request.id}/cancel`, {
        method: "POST",
        body: "{}",
        signal,
      });
      while (activeJob(await api(`/jobs/${request.id}`, { signal }))) {
        await new Promise((resolve) => setTimeout(resolve, 200));
        signal.throwIfAborted();
      }
    } finally {
      clearTimeout(timer);
    }
  })();
  request.cancellation ??= new Promise<void>((resolve, reject) => {
    // This deadline includes waiting for creation, not just cancellation I/O.
    const timer = setTimeout(
      () =>
        reject(
          new Error(
            "기존 음성 작업의 중지 확인이 15초 안에 끝나지 않았습니다. 질문은 전송하지 않았습니다.",
          ),
        ),
      15000,
    );
    request.serverCancellation!.then(
      () => {
        clearTimeout(timer);
        resolve();
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
  return request.cancellation;
}
