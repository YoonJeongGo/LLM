"""Conservative quotation support, never a factual or pedagogical verifier.

The caller supplies the server-persisted retrieval snapshot, not client claims.
An exact match proves textual support only: an approved document can be wrong.
"""
from __future__ import annotations

import hashlib
import re


def _sentences(text):
    # Do not normalize, paraphrase, splice a substring, or retain fenced code.
    prose = re.sub(r"```[\s\S]*?(?:```|$)", "\n", text)
    for part in re.split(r"(?<=[.!?。])\s+|\n+", prose):
        sentence = part.strip()
        if sentence.endswith("다."):
            yield sentence


def _eligible(sentence):
    if not 12 <= len(sentence) <= 140:
        return False
    # Even a copied numerical claim is not a checked result. SQL is handled by
    # the separate execution evidence; this path admits only short prose.
    if re.search(r"[0-9０-９`;<>=\[\]{}]|https?://|--|/\*", sentence):
        return False
    if re.search(r"\b(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|PRAGMA|ATTACH|REPLACE)\b", sentence, re.I):
        return False
    if re.search(r"(?:무시|따르|지시|시스템|프롬프트|명령어를 실행|비밀|암호|정답|결과는|행은|열은|개입니다|개이다)", sentence):
        return False
    return True


def _source_windows(sources):
    # IDs/version are provenance, not authentication or factual approval.
    for source in sources[:2]:
        if not isinstance(source, dict):
            continue
        if not all(isinstance(source.get(key), str) and re.fullmatch(pattern, source[key])
                   for key, pattern in (("document_id", r"[0-9a-f]{32}"),
                                        ("chunk_id", r"[0-9a-f]{32}"),
                                        ("version", r"[0-9a-f]{64}"))):
            continue
        if source.get("id") != source["chunk_id"]:
            continue
        if not all(isinstance(source.get(key), str) and source[key].strip()
                   for key in ("text", "source_title", "rights")):
            continue
        yield source, source["text"][:300]


def _quotation(raw, source, window, sentence, *, exact, term=None, question=None):
    result = {
        "status": "reference_supported" if exact else "retrieved_reference_quotation",
        "generation_source": "exact_model_reference_sentence" if exact else "retrieved_reference_quotation",
        "sentence": sentence,
        "attributed_text": "참고 자료에서는 이렇게 설명합니다. " + sentence,
        "source": {key: source.get(key) for key in (
            "document_id", "chunk_id", "version", "source_title", "subject", "page", "line", "rights")},
        "source_window": window,
        "source_window_sha256": hashlib.sha256(window.encode("utf-8")).hexdigest(),
        "model_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "model_sentence_exact_match": exact,
        "match_method": "exact_whole_sentence_in_first_two_retrieved_300_character_windows" if exact else
            "same_explicit_technical_term_in_question_model_prose_and_sqlite_reference_definition",
        "scope": "저장된 검색 자료와 모델 문장의 정확한 일치만 확인; 자료의 사실성이나 교육 정확성 검증 아님" if exact else
            "실제 검색 자료의 문장을 별도로 인용; 모델 문장과의 의미 일치 또는 사실성 검증 아님",
        "raw_model_prose_validation": "not_established",
        "source_accuracy": "not_established",
        "human_review": "not_reviewed",
        "semantic_error_note": "글자 불일치는 모델의 의미 오류를 뜻하지 않으며, 원래 모델 답변의 평가를 변경하지 않습니다.",
    }
    if term:
        result["explicit_technical_term"] = term
        result["question_sha256"] = hashlib.sha256(question.encode("utf-8")).hexdigest()
        result["dialect_scope"] = "sqlite"
    return result


def _mentions(text, term):
    return bool(re.search(r"(?<![A-Za-z0-9_])"+re.escape(term)+r"(?![A-Za-z0-9_])", text, re.I))


def reference_supported_sentence(raw_model_response, sources, *, question=None, dialect=None):
    """Prefer an exact match, otherwise quote a narrowly related source sentence.

    The fallback is a separate RAG quotation, never validation/replacement of
    model prose. Its generic technical-term test does not hardcode a definition.
    Only the two 300-character windows actually supplied to the model are used.
    """
    if not isinstance(raw_model_response, str) or not isinstance(sources, list):
        return None
    windows = list(_source_windows(sources))
    candidates = [s for s in _sentences(raw_model_response) if _eligible(s)]
    for sentence in candidates:
        for source, window in windows:
            if sentence in set(_sentences(window)):
                return _quotation(raw_model_response, source, window, sentence, exact=True)

    # The surrounding example executor supports SQLite. Do not transfer a
    # reference's DBMS behavior to another or mixed-dialect question.
    if dialect != "sqlite" or not isinstance(question, str) or not question.strip():
        return None
    prose = re.sub(r"\x60{3}[\s\S]*?(?:\x60{3}|$)", "\n", raw_model_response)
    question_prose = re.sub(r"\x60{3}[\s\S]*?(?:\x60{3}|$)", "\n", question)
    foreign = r"(?<![A-Za-z0-9_])(?:Oracle|MySQL|PostgreSQL|Postgres|MariaDB|MSSQL|DB2|SQL\s+Server)(?![A-Za-z0-9_])|오라클|마이\s*에스큐엘"
    if re.search(foreign, question_prose+" "+prose, re.I):
        return None
    for source, window in windows:
        source_context = str(source.get("subject", ""))+" "+source["source_title"]+" "+window
        if not _mentions(source_context, "SQLite") or re.search(foreign, source_context, re.I):
            continue
        for sentence in _sentences(window):
            if not _eligible(sentence):
                continue
            # A warning labelling this quotation as a false/hypothetical claim
            # matters. A later caution about another example must not relabel
            # an earlier definition.
            prefix = window[:window.find(sentence)]
            if re.search(r"잘못된|틀린|오답|반례|가정", prefix):
                continue
            # Function arguments are deliberately excluded: COUNT(*) and
            # COUNT(column) do not agree merely because COUNT matches.
            head = re.match(r"^([A-Z][A-Z_]{1,31})(?:은|는|이란|란)\s+", sentence)
            if not head:
                continue
            term = head.group(1)
            if _mentions(question_prose, term) and _mentions(prose, term):
                return _quotation(raw_model_response, source, window, sentence,
                                  exact=False, term=term, question=question)
    return None
