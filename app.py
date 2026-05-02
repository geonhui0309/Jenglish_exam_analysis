"""GPT·Obsidian 등에서 작성한 마크다운 리포트 → 대시보드 시각화."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from report_parser import parse_report_markdown, ratio_column_to_float
from saved_reports import list_saved, load_report, save_report


def _strip_total_row(df: pd.DataFrame | None, first_col: str | None = None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return df
    c0 = first_col or df.columns[0]
    if c0 not in df.columns:
        return df
    return df[~df[c0].astype(str).str.strip().eq("합계")].copy()


def _safe_pie(df: pd.DataFrame | None, names_col: str, values_col: str, title: str) -> None:
    if df is None or df.empty or names_col not in df.columns or values_col not in df.columns:
        st.info("차트를 그릴 표 데이터가 없습니다.")
        return
    d = df.copy()
    if values_col == "비율":
        d["_v"] = ratio_column_to_float(d[values_col])
    else:
        d["_v"] = pd.to_numeric(d[values_col], errors="coerce").fillna(0)
    d = d[d["_v"] > 0]
    if d.empty:
        st.info("값이 비어 있습니다.")
        return
    fig = px.pie(
        d,
        names=names_col,
        values="_v",
        title=title,
        hole=0.35,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)


def _render_dashboard(md: str, source_note: str) -> None:
    rep = parse_report_markdown(md)
    for n in rep.parse_notes:
        st.warning(n)

    st.markdown(f"## {rep.title}")
    if rep.intro:
        st.markdown(rep.intro)
    st.caption(f"원본: **{source_note}**")

    mcols = st.columns(4)
    n_q = len(rep.exam_questions) if rep.exam_questions is not None else 0
    with mcols[0]:
        st.metric("분석 문항 수", str(n_q) if n_q else "—")

    hit = "—"
    if rep.final_compare is not None and "개수" in rep.final_compare.columns and "구분" in rep.final_compare.columns:
        sub = rep.final_compare[
            rep.final_compare["구분"].astype(str).str.strip().eq("적중")
        ]
        if not sub.empty:
            hit = str(sub.iloc[0]["개수"])

    with mcols[1]:
        st.metric("파이널 ‘적중’ 문항 수", hit)

    top_type = "—"
    tr = _strip_total_row(rep.type_ratio)
    if tr is not None and not tr.empty and "유형" in tr.columns and "개수" in tr.columns:
        tt = tr.copy()
        tt["_n"] = pd.to_numeric(tt["개수"], errors="coerce").fillna(0)
        if tt["_n"].max() > 0:
            top_type = str(tt.loc[tt["_n"].idxmax(), "유형"])

    with mcols[2]:
        st.metric("최다 유형", top_type)

    unk = "—"
    if (
        rep.source_ratio is not None
        and "출처" in rep.source_ratio.columns
        and "개수" in rep.source_ratio.columns
    ):
        sr = rep.source_ratio.copy()
        msk = sr["출처"].astype(str).str.contains("미확인", na=False)
        if msk.any():
            unk = str(int(sr.loc[msk, "개수"].sum()))

    with mcols[3]:
        st.metric("출처 미확인 합계(개)", unk)

    st.divider()

    t1, t2, t3, t4, t5, t6 = st.tabs(
        ["① 시험·유형", "② 출처", "③ 파이널 비교", "④ 고난도", "⑤ 어휘 난이도", "⑥ 최종 평가"]
    )

    with t1:
        c1, c2 = st.columns((1.2, 1))
        with c1:
            st.subheader("문항·유형")
            if rep.exam_questions is not None:
                st.dataframe(rep.exam_questions, use_container_width=True, hide_index=True)
            else:
                st.info("시험 분석 표를 찾지 못했습니다.")
        with c2:
            st.subheader("유형 비율")
            tru = _strip_total_row(rep.type_ratio)
            _safe_pie(tru, names_col="유형", values_col="비율", title="유형 비율")
            if tru is not None:
                st.dataframe(tru, use_container_width=True, hide_index=True)

    with t2:
        c1, c2 = st.columns((1.2, 1))
        with c1:
            st.subheader("문항별 출처")
            if rep.source_questions is not None:
                st.dataframe(rep.source_questions, use_container_width=True, hide_index=True)
            else:
                st.info("출처 표를 찾지 못했습니다.")
        with c2:
            st.subheader("출처 비율")
            sru = _strip_total_row(rep.source_ratio)
            if sru is not None and not sru.empty and "출처" in sru.columns:
                _safe_pie(sru, names_col="출처", values_col="비율", title="출처 비율")
                st.dataframe(sru, use_container_width=True, hide_index=True)
            else:
                st.info("출처 비율 표 없음.")

    with t3:
        st.subheader("파이널 비교 요약")
        if rep.final_compare is not None:
            dfc = rep.final_compare.copy()
            if "비율" in dfc.columns and "구분" in dfc.columns:
                dfc["_p"] = ratio_column_to_float(dfc["비율"])
                colors = px.colors.qualitative.Set2
                fig = go.Figure(
                    go.Bar(
                        x=dfc["구분"].astype(str),
                        y=dfc["_p"],
                        marker_color=[colors[i % len(colors)] for i in range(len(dfc))],
                    )
                )
                fig.update_layout(yaxis_title="비율 (%)", margin=dict(t=36, l=28, r=28, b=80))
                st.plotly_chart(fig, use_container_width=True)
            st.dataframe(rep.final_compare, use_container_width=True, hide_index=True)
        else:
            st.info("파이널 비교 표 없음.")
        if rep.final_criteria:
            st.markdown("**판단 기준**")
            st.markdown(rep.final_criteria)

    with t4:
        st.subheader("고난도 문항")
        if not rep.hard_blocks:
            st.info("고난도 섹션을 찾지 못했습니다.")
        for title, hdf in rep.hard_blocks:
            with st.expander(f"📌 {title}", expanded=len(rep.hard_blocks) <= 2):
                if hdf is not None:
                    st.dataframe(hdf, use_container_width=True, hide_index=True)

    with t5:
        vc1, vc2 = st.columns(2)
        with vc1:
            st.markdown("**상위 난이도 어휘**")
            if rep.vocab_high is not None:
                st.dataframe(rep.vocab_high, use_container_width=True, hide_index=True)
            else:
                st.caption("없음")
        with vc2:
            st.markdown("**중상 난이도 어휘**")
            if rep.vocab_mid is not None:
                st.dataframe(rep.vocab_mid, use_container_width=True, hide_index=True)
            else:
                st.caption("없음")

    with t6:
        st.subheader("최종 평가")
        if rep.evaluation is not None:
            for _, row in rep.evaluation.iterrows():
                k = str(row.iloc[0])
                v = str(row.iloc[1]) if len(row) > 1 else ""
                st.markdown(f"**{k}**\n\n{v}")
                st.divider()
        else:
            st.info("최종 평가 표 없음.")


def main() -> None:
    st.set_page_config(
        page_title="시험 분석 리포트 대시보드",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.sidebar.header("파일")
    uploaded = st.sidebar.file_uploader(
        "마크다운 (.md)",
        type=["md", "markdown", "txt"],
        help="김포고1 형식 리포트 파일",
        key="report_file_uploader",
    )

    # ── 업로드가 있으면 그 내용 우선 (대시보드와 동일)
    def _current_markdown_for_save() -> str:
        if uploaded is not None:
            return uploaded.getvalue().decode("utf-8", errors="replace")
        return str(st.session_state.get("report_md_paste") or "").strip()

    st.sidebar.divider()
    st.sidebar.subheader("저장")
    school_name = st.sidebar.text_input(
        "학교 이름",
        key="school_name_save",
        placeholder="예: 김포고",
        help="저장 목록 왼쪽에 표시되는 이름입니다.",
    )
    if st.sidebar.button("이 내용 저장", use_container_width=True, key="btn_save_snapshot"):
        body = _current_markdown_for_save()
        if not body.strip():
            st.sidebar.error("저장할 마크다운이 없습니다. 파일을 올리거나 붙여넣기 해 주세요.")
        elif not school_name.strip():
            st.sidebar.error("학교 이름을 입력하세요.")
        else:
            try:
                save_report(school_name, body)
                st.sidebar.success(f"저장했습니다 · {school_name.strip()}")
                if "report_file_uploader" in st.session_state:
                    try:
                        del st.session_state["report_file_uploader"]
                    except Exception:
                        st.session_state["report_file_uploader"] = None
                st.session_state["report_md_paste"] = body
                st.rerun()
            except ValueError as e:
                st.sidebar.error(str(e))

    st.sidebar.divider()
    st.sidebar.subheader("저장 기록")
    saved_rows = list_saved()
    if not saved_rows:
        st.sidebar.caption("아직 저장된 기록이 없습니다.")
    else:
        for entry in saved_rows:
            lbl = entry.get("school", "?")
            when = entry.get("saved_at", "")
            pv = entry.get("title_preview") or ""
            line2 = (pv[:42] + ("…" if len(pv) > 42 else "")) if pv.strip() else ""
            bid = entry.get("id", "")
            cap = f"📌 {lbl}\n_{when}_"
            if line2:
                cap += f"\n{line2}"
            if st.sidebar.button(cap, key=f"snap_load_{bid}", use_container_width=True):
                try:
                    text = load_report(bid)
                except Exception as ex:
                    st.sidebar.error(f"불러오기 실패: {ex}")
                else:
                    st.session_state["report_md_paste"] = text
                    if "report_file_uploader" in st.session_state:
                        try:
                            del st.session_state["report_file_uploader"]
                        except Exception:
                            st.session_state["report_file_uploader"] = None
                    st.sidebar.success(f"불러옴 · {lbl}")
                    st.rerun()

    tb_dash, tb_edit = st.tabs(["대시보드", "마크다운 붙여넣기"])
    with tb_edit:
        st.text_area(
            "# 제목 과 ## ① … 표 를 붙여 넣음",
            height=460,
            key="report_md_paste",
            placeholder="# 김포고1 영어 시험 분석 리포트\n\n---\n\n## ① 시험 분석\n| 번호 | 유형 | 근거 |",
        )

    md_content = ""
    source_note = ""
    if uploaded is not None:
        md_content = uploaded.getvalue().decode("utf-8", errors="replace")
        source_note = uploaded.name
    else:
        md_content = str(st.session_state.get("report_md_paste") or "").strip()
        source_note = "붙여넣기"

    with tb_dash:
        st.markdown("GPT에서 생성한 마크다운을 **파일 업로드** 또는 **붙여넣기 탭**에서 넣습니다.")
        if not md_content.strip():
            st.warning("내용이 비어 있습니다. 왼쪽 사이드바에서 파일을 올리거나 「마크다운 붙여넣기」로 입력해 주세요.")
        else:
            _render_dashboard(md_content, source_note)


if __name__ == "__main__":
    main()
