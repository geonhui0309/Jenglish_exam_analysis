"""로컬에 마크다운 리포트 저장·목록·불러오기 (학교명 + 기록)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

STORAGE_DIR = Path(__file__).resolve().parent / ".saved_reports"
MANIFEST = STORAGE_DIR / "manifest.json"
MAX_ENTRIES = 80


def _ensure_dir() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _read_manifest() -> list[dict]:
    if not MANIFEST.is_file():
        return []
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _write_manifest(rows: list[dict]) -> None:
    _ensure_dir()
    MANIFEST.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def list_saved() -> list[dict]:
    """최신순. 각 항목: id, school, saved_at, title_preview(optional)."""
    rows = _read_manifest()
    pruned: list[dict] = []
    for r in rows:
        rid = r.get("id")
        if not rid:
            continue
        p = STORAGE_DIR / f"{rid}.md"
        if p.is_file():
            pruned.append(r)
    if len(pruned) != len(rows):
        _write_manifest(pruned)
    return pruned


def save_report(school: str, markdown: str, title_preview: str = "") -> str:
    """저장 후 id 반환."""
    body = (markdown or "").strip()
    if not body:
        raise ValueError("저장할 내용이 비어 있습니다.")
    name = (school or "").strip()
    if not name:
        raise ValueError("학교 이름을 입력하세요.")

    _ensure_dir()
    rid = uuid.uuid4().hex[:16]
    (STORAGE_DIR / f"{rid}.md").write_text(body, encoding="utf-8")

    rows = list_saved()
    preview = (title_preview or "").strip()[:80]
    if not preview:
        for line in body.splitlines():
            if line.startswith("# "):
                preview = line[2:].strip()[:80]
                break

    entry = {
        "id": rid,
        "school": name,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "title_preview": preview,
    }
    rows.insert(0, entry)
    removed: list[dict] = []
    if len(rows) > MAX_ENTRIES:
        removed = rows[MAX_ENTRIES:]
        rows = rows[:MAX_ENTRIES]
    for old in removed:
        oid = old.get("id")
        if not oid:
            continue
        stale = STORAGE_DIR / f"{oid}.md"
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            pass
    _write_manifest(rows)
    return rid


def load_report(report_id: str) -> str:
    p = STORAGE_DIR / f"{report_id.strip()}.md"
    if not p.is_file():
        raise FileNotFoundError(report_id)
    return p.read_text(encoding="utf-8")


def delete_report(report_id: str) -> bool:
    """manifest에서 제거하고 .md 파일을 삭제. 성공하면 True."""
    rid = (report_id or "").strip()
    if not rid:
        return False
    rows_before = _read_manifest()
    new_rows = [r for r in rows_before if str(r.get("id", "")) != rid]
    _write_manifest(new_rows)
    p = STORAGE_DIR / f"{rid}.md"
    file_existed = p.is_file()
    if file_existed:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            return False
    return file_existed or len(new_rows) < len(rows_before)
