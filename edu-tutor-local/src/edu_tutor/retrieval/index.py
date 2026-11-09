from __future__ import annotations

import hashlib
import io
import re
import threading
from pathlib import Path

from edu_tutor.storage.db import Store, new_id, utcnow

MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 2_000_000
MAX_DOCUMENTS = 100
MAX_CORPUS_TEXT = 5_000_000
SQL_WORDS = {"select", "count", "null", "where", "having", "join", "group", "primary", "foreign", "avg", "sum",
             "ddl", "dml", "dcl", "tcl", "create", "alter", "drop", "insert", "update", "delete", "truncate", "commit", "rollback"}


class DocumentIndex:
    def __init__(self, store: Store):
        self.store = store
        self.lock = threading.RLock()

    def ingest(self, filename: str, raw: bytes, title: str, rights: str, subject: str):
        suffix = Path(filename).suffix.lower()
        if suffix not in {".txt", ".md", ".pdf"}:
            raise ValueError("TXT, MD, 텍스트 PDF만 지원합니다.")
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError("파일은 1바이트 이상 10MiB 이하여야 합니다.")
        if not rights.strip():
            raise ValueError("자료 이용 권리를 입력하세요.")
        with self.lock:
            if len(self.store.list("documents")) >= MAX_DOCUMENTS:
                raise ValueError("자료는 최대 100개까지 등록할 수 있습니다.")
            pages = []
            if suffix == ".pdf":
                if not raw.startswith(b"%PDF-"):
                    raise ValueError("PDF 파일 내용이 올바르지 않습니다.")
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(raw))
                if reader.is_encrypted or len(reader.pages) > 300:
                    raise ValueError("암호화 PDF 또는 300쪽 초과 PDF는 지원하지 않습니다.")
                for number, page in enumerate(reader.pages, 1):
                    pages.append((number, page.extract_text() or ""))
                    if sum(len(text) for _, text in pages) > MAX_TEXT:
                        raise ValueError("추출 텍스트가 200만 글자 제한을 초과했습니다.")
            else:
                try:
                    pages = [(None, raw.decode("utf-8-sig"))]
                except UnicodeDecodeError as exc:
                    raise ValueError("텍스트 자료는 UTF-8로 저장해 주세요.") from exc
            full_text = "\n".join(text for _, text in pages)
            if len(full_text) > MAX_TEXT or "\x00" in full_text:
                raise ValueError("텍스트 크기 또는 내용이 허용 범위를 벗어났습니다.")
            if sum(len(c["text"]) for c in self.store.list("chunks")) + len(full_text) > MAX_CORPUS_TEXT:
                raise ValueError("전체 자료 텍스트 500만 글자 제한을 초과했습니다.")
            ident = new_id()
            version = hashlib.sha256(raw).hexdigest()
            chunks = []
            for page, text in pages:
                lines = text.splitlines()
                pending, start = [], 1
                for number, line in enumerate(lines, 1):
                    # Hard-wrap long lines, keeping source line attribution.
                    for piece in [line[i:i + 800] for i in range(0, max(1, len(line)), 800)]:
                        if pending and sum(len(x) + 1 for x in pending) + len(piece) > 1000:
                            chunks.append((page, start, "\n".join(pending)))
                            pending, start = [], number
                        if not pending:
                            start = number
                        pending.append(piece)
                if "\n".join(pending).strip():
                    chunks.append((page, start, "\n".join(pending)))
            document = {"id": ident, "title": title.strip() or Path(filename).name,
                        "filename": Path(filename.replace("\\", "/")).name, "rights": rights,
                        "subject": subject, "version": version, "review_status": "pending",
                        "preview": full_text[:16000], "preview_truncated": len(full_text) > 16000,
                        "full_preview_url": f"/api/documents/{ident}/chunks", "chunk_count": len(chunks), "created_at": utcnow(),
                        "extraction_status": "extracted" if chunks else "needs_manual_transcription",
                        "suffix": suffix}
            self.store.file("uploads", ident, suffix).write_bytes(raw)
            try:
                self.store.put("documents", document)
                for page, line, text in chunks:
                    chunk_id = new_id()
                    self.store.put("chunks", {"id": chunk_id, "chunk_id": chunk_id, "document_id": ident,
                        "source_title": document["title"], "page": page, "line": line, "text": text,
                        "rights": rights, "subject": subject, "version": version})
            except Exception:
                self.store.delete("documents", ident)
                self.store.file("uploads", ident, suffix).unlink(missing_ok=True)
                raise
            return document

    def review(self, ident, approved):
        with self.lock:
            doc = self.store.get("documents", ident)
            if not doc:
                raise KeyError(ident)
            if approved and not doc["chunk_count"]:
                raise ValueError("추출된 텍스트가 없습니다. 수동 전사가 필요합니다.")
            doc.update(review_status="approved" if approved else "rejected", reviewed_at=utcnow())
            self.store.put("documents", doc)
            self.store.record("document_review", ident, approved=approved)
            return doc

    def delete(self, ident):
        with self.lock:
            doc = self.store.get("documents", ident)
            if not doc:
                raise KeyError(ident)
            # No persistent index cache: deletion takes effect in the next search.
            self.store.file("uploads", ident, doc["suffix"]).unlink(missing_ok=True)
            self.store.delete("documents", ident)
            self.store.record("document_delete", ident)

    def search(self, query: str, limit=5):
        from sklearn.feature_extraction.text import TfidfVectorizer
        with self.lock:
            approved = {d["id"] for d in self.store.list("documents") if d["review_status"] == "approved"}
            chunks = [c for c in self.store.list("chunks") if c["document_id"] in approved]
        if not chunks or not query.strip():
            return []
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), lowercase=True)
        try:
            matrix = vectorizer.fit_transform([c["text"] for c in chunks])
            scores = (matrix @ vectorizer.transform([query]).T).toarray().ravel()
        except ValueError:
            return []
        query_words = set(re.findall(r"[a-z]+", query.lower())) & SQL_WORDS
        for i, chunk in enumerate(chunks):
            words = set(re.findall(r"[a-z]+", chunk["text"].lower()))
            scores[i] += 0.08 * len(query_words & words)
        hits = sorted(zip(chunks, scores), key=lambda item: item[1], reverse=True)
        return [{**c, "score": round(float(score), 6)} for c, score in hits[:limit] if score >= 0.03]

    def validate_sources(self, sources, retrieved):
        allowed = {(c["document_id"], c["chunk_id"]) for c in retrieved}
        return all((s.get("document_id"), s.get("chunk_id")) in allowed for s in sources)
