// User-selected PNG assets stay inside this browser's local IndexedDB.
function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("edu-tutor-local-ui", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("assets");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(new Error("로컬 아바타 저장소를 열 수 없습니다."));
  });
}
export async function readAvatar(): Promise<Blob | undefined> {
  const db = await open();
  try {
    return await new Promise((resolve, reject) => {
      const request = db
        .transaction("assets", "readonly")
        .objectStore("assets")
        .get("avatar");
      request.onsuccess = () => resolve(request.result?.blob);
      request.onerror = () =>
        reject(new Error("저장한 아바타를 읽을 수 없습니다."));
    });
  } finally {
    db.close();
  }
}
export async function saveAvatar(blob: Blob | null): Promise<void> {
  const db = await open();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("assets", "readwrite");
      if (blob)
        transaction.objectStore("assets").put(
          {
            blob,
            kind: "static_png",
            saved_at: new Date().toISOString(),
            rights_note:
              "사용자가 직접 선택한 이미지. 사용 권리는 사용자 확인 대상.",
          },
          "avatar",
        );
      else transaction.objectStore("assets").delete("avatar");
      transaction.oncomplete = () => resolve();
      transaction.onerror = () =>
        reject(
          new Error(
            "아바타를 저장하지 못했습니다. 브라우저 저장 공간을 확인하세요.",
          ),
        );
      transaction.onabort = () =>
        reject(new Error("아바타 저장이 중단되었습니다."));
    });
  } finally {
    db.close();
  }
}
