"""Obsidian/마크다운 시험 분석 리포트 파싱 (김포고1 형식)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


def _split_header_row(line: str) -> list[str]:
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    return parts


def _is_separator_row(line: str) -> bool:
    s = line.strip().strip("|").replace(" ", "")
    if not s:
        return False
    return bool(re.match(r"^[\-:|]+$", s))


def parse_pipe_table(block: str) -> pd.DataFrame | None:
    """GFM 스타일 파이프 테이블 하나를 DataFrame으로."""
    lines: list[str] = []
    for raw in block.splitlines():
        t = raw.strip()
        if t.startswith("|") and t.endswith("|"):
            lines.append(t)
        elif lines and t == "":
            break
        elif lines and not t.startswith("|"):
            break
    if len(lines) < 2:
        return None
    if _is_separator_row(lines[1]):
        data_lines = [lines[0]] + lines[2:]
    else:
        data_lines = lines
    if len(data_lines) < 1:
        return None

    header = _split_header_row(data_lines[0])
    rows: list[list[str]] = []
    for ln in data_lines[1:]:
        if _is_separator_row(ln):
            continue
        cells = _split_header_row(ln)
        if len(cells) < len(header):
            cells.extend([""] * (len(header) - len(cells)))
        elif len(cells) > len(header):
            cells = cells[: len(header)]
        rows.append(cells)

    if not rows:
        return None
    return pd.DataFrame(rows, columns=header)


def _extract_tables_in_order(text: str) -> list[pd.DataFrame]:
    out: list[pd.DataFrame] = []
    i = 0
    lines = text.splitlines()
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            block_lines: list[str] = []
            while i < len(lines) and (
                lines[i].strip().startswith("|")
                or (lines[i].strip() == "" and block_lines and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"))
            ):
                if lines[i].strip() != "":
                    block_lines.append(lines[i])
                i += 1
            block = "\n".join(block_lines)
            df = parse_pipe_table(block)
            if df is not None and not df.empty:
                out.append(df)
            continue
        i += 1
    return out


def _slice_h2(md: str, title_re: str) -> str:
    m = re.search(title_re, md, re.MULTILINE)
    if not m:
        return ""
    start = m.end()
    rest = md[start:]
    m2 = re.search(r"\n##\s", rest)
    return rest[: m2.start()] if m2 else rest


def _after_heading(section: str, heading_sub: str) -> str:
    """`### 제목` 이후 문자열."""
    pat = rf"###\s*{re.escape(heading_sub)}\s*\n"
    m = re.search(pat, section, re.MULTILINE)
    if not m:
        return ""
    return section[m.end() :]


def _after_heading_any(section: str, *heading_subs: str) -> str:
    """`### …` 에서 후보 헤더 중 첫 매칭 이후 문자열."""
    for h in heading_subs:
        t = _after_heading(section, h)
        if t.strip():
            return t
    return ""


def _parse_hard_blocks(section_4: str) -> list[tuple[str, str, pd.DataFrame | None]]:
    """④ 구간 내 `### N번` 또는 `### 고난도 …` 블록. (제목, 본문 마크다운, 첫 표)."""
    if not section_4.strip():
        return []
    out: list[tuple[str, str, pd.DataFrame | None]] = []
    matches = list(re.finditer(r"^###\s*(.+)$", section_4, re.MULTILINE))
    if not matches:
        return []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_4)
        body = section_4[start:end]
        dfs = _extract_tables_in_order(body)
        tbl = dfs[0] if dfs else None
        out.append((title, body.strip(), tbl))
    return out


def _report_title(md: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "시험 분석 대시보드"


def _intro_lines(md: str) -> str:
    lines_out: list[str] = []
    seen_h1 = False
    for line in md.splitlines():
        if line.startswith("# "):
            seen_h1 = True
            continue
        if line.startswith("## "):
            break
        if seen_h1:
            lines_out.append(line)
    return "\n".join(lines_out).strip()


@dataclass
class ReportDashboard:
    title: str = ""
    intro: str = ""
    exam_questions: pd.DataFrame | None = None
    type_ratio: pd.DataFrame | None = None
    source_questions: pd.DataFrame | None = None
    source_ratio: pd.DataFrame | None = None
    final_compare: pd.DataFrame | None = None
    final_criteria: str = ""
    hard_blocks: list[tuple[str, str, pd.DataFrame | None]] = field(default_factory=list)
    vocab_high: pd.DataFrame | None = None
    vocab_mid: pd.DataFrame | None = None
    evaluation: pd.DataFrame | None = None
    evaluation_markdown: str = ""
    raw_markdown: str = ""
    parse_notes: list[str] = field(default_factory=list)


def parse_report_markdown(md: str) -> ReportDashboard:
    r = ReportDashboard(raw_markdown=md)
    r.title = _report_title(md)
    r.intro = _intro_lines(md)

    s1 = _slice_h2(md, r"##\s*①\s*시험\s*분석")
    s2 = _slice_h2(md, r"##\s*②\s*출처")
    s3 = _slice_h2(md, r"##\s*③\s*파이널")
    s4 = _slice_h2(md, r"##\s*④\s*고난도")
    s5 = _slice_h2(md, r"##\s*⑤\s*어휘")
    s6 = _slice_h2(md, r"##\s*⑥\s*최종")

    if not s1:
        r.parse_notes.append("섹션 ① 시험 분석을 찾지 못했습니다. `## ① 시험 분석` 형식을 확인하세요.")
    else:
        t1 = _extract_tables_in_order(s1)
        if t1:
            r.exam_questions = t1[0]
        sub_tr = _after_heading(s1, "유형 비율")
        if sub_tr:
            tt = _extract_tables_in_order(sub_tr)
            if tt:
                r.type_ratio = tt[0]

    if s2:
        t2 = _extract_tables_in_order(s2)
        if t2:
            r.source_questions = t2[0]
        sub_sr = _after_heading(s2, "출처 비율")
        if sub_sr:
            tt = _extract_tables_in_order(sub_sr)
            if tt:
                r.source_ratio = tt[0]

    if s3:
        t3 = _extract_tables_in_order(s3)
        if t3:
            r.final_compare = t3[0]
        crit = _after_heading(s3, "판단 기준")
        if crit.strip():
            r.final_criteria = crit.strip().split("---")[0].strip()

    if s4:
        r.hard_blocks = _parse_hard_blocks(s4)

    if s5:
        sub_h = _after_heading_any(s5, "상위 난이도 어휘", "상위 난이도")
        sub_m = _after_heading_any(s5, "중상 난이도 어휘", "중상 난이도")
        if sub_h:
            th = _extract_tables_in_order(sub_h)
            if th:
                r.vocab_high = th[0]
        if sub_m:
            tm = _extract_tables_in_order(sub_m)
            if tm:
                r.vocab_mid = tm[0]
        if r.vocab_high is None and r.vocab_mid is None:
            all_t = _extract_tables_in_order(s5)
            if len(all_t) >= 1:
                r.vocab_high = all_t[0]
            if len(all_t) >= 2:
                r.vocab_mid = all_t[1]

    if s6:
        t6 = _extract_tables_in_order(s6)
        if t6:
            r.evaluation = t6[0]
        if r.evaluation is None:
            r.evaluation_markdown = s6.strip()

    return r


def ratio_column_to_float(series: pd.Series) -> pd.Series:
    def one(x: Any) -> float:
        if pd.isna(x):
            return 0.0
        s = str(x).strip().replace("%", "")
        try:
            return float(s)
        except ValueError:
            return 0.0

    return series.map(one)
