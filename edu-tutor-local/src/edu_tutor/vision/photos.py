from __future__ import annotations

import io
import warnings

from PIL import Image, ImageOps

from edu_tutor.storage.db import Store, new_id, utcnow
from edu_tutor.vision.conditions import missing_condition_warnings

FIELDS = {"question", "sql", "tables", "choices", "unreadable_regions", "missing_conditions"}


class PhotoStore:
    def __init__(self, store: Store):
        self.store = store

    def upload(self, raw: bytes):
        if not raw or len(raw) > 10 * 1024 * 1024:
            raise ValueError("이미지는 10MiB 이하여야 합니다.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as original:
                    if original.format not in {"PNG", "JPEG", "WEBP"}:
                        raise ValueError("PNG, JPEG, WebP만 지원합니다.")
                    if original.width * original.height > 20_000_000:
                        raise ValueError("이미지는 20MP 이하여야 합니다.")
                    original.load()
                    image = ImageOps.exif_transpose(original).convert("RGB")
                    image.thumbnail((2400, 2400))
                    clean = Image.new("RGB", image.size)
                    clean.paste(image)
        except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("이미지를 안전하게 디코딩할 수 없습니다.") from exc
        ident = new_id()
        clean.save(self.store.file("photos", ident, ".png"), format="PNG")
        value = {"id": ident, "original_text": "", "question": "", "sql": "", "tables": [],
                 "choices": [], "unreadable_regions": [], "missing_conditions": [], "confirmed": False,
                 "confirmed_at": None, "confirmed_by": None, "revision": 1, "history": [],
                 "recognition_status": "not_run", "recognition_reason": "자동 인식 미실행: 원문을 직접 입력해 주세요.",
                 "image_url": f"/api/photos/{ident}/image", "width": clean.width, "height": clean.height,
                 "created_at": utcnow()}
        return self.store.put("photos", value)

    def edit(self, ident, fields):
        value = self.store.get("photos", ident)
        if not value:
            raise KeyError(ident)
        if set(fields) - FIELDS:
            raise ValueError("Unknown photo field")
        value["history"].append({"revision": value["revision"], "confirmed": value["confirmed"],
                                  "edited_at": utcnow(), **{key: value[key] for key in FIELDS}})
        value.update(fields)
        value.update(revision=value["revision"] + 1, confirmed=False, confirmed_at=None, confirmed_by=None)
        return self.store.put("photos", value)

    def confirm(self, ident):
        value = self.store.get("photos", ident)
        if not value:
            raise KeyError(ident)
        if not value["question"].strip():
            raise ValueError("문제 원문을 입력한 뒤 확정하세요.")
        value.update(confirmed=True, confirmed_at=utcnow(), confirmed_by="local_user")
        self.store.record("photo_confirm", ident, revision=value["revision"])
        return self.store.put("photos", value)

    def confirmed(self, ident):
        value = self.store.get("photos", ident)
        if not value:
            raise KeyError(ident)
        if not value["confirmed"]:
            raise ValueError("사진 원문을 먼저 확인하고 확정하세요.")
        missing = list(dict.fromkeys([*value.get("missing_conditions", []),
            *missing_condition_warnings(value["question"] + "\n" + value.get("sql", ""))]))
        if missing:
            raise ValueError("풀이에 필요한 조건을 입력하고 다시 확정하세요: " + "; ".join(missing))
        return value

    def delete(self, ident):
        if not self.store.get("photos", ident):
            raise KeyError(ident)
        self.store.file("photos", ident, ".png").unlink(missing_ok=True)
        self.store.delete("photos", ident)
        self.store.record("photo_delete", ident)
