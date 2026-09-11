from __future__ import annotations

import hashlib
from io import BytesIO
import json

import pandas as pd
import streamlit as st

from config import (
    AUTO_SYNC_EDMGR,
    DEFAULT_YEAR,
    SERVICE_SUBTITLE,
    SERVICE_TITLE,
    SYNC_DEFAULT_YEAR_COUNT,
    get_secret,
)
from engine import ask
from services import supabase_store
from services.openai_service import text_to_speech, transcribe_audio


st.set_page_config(
    page_title=SERVICE_TITLE,
    page_icon="🌱",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
.block-container {max-width: 920px; padding-top: 1.4rem; padding-bottom: 7rem;}
[data-testid="stChatMessage"] {border-radius: 16px; padding: 0.15rem 0.2rem;}
.pium-title {font-size: 2rem; font-weight: 800; margin-bottom: 0.1rem; letter-spacing: -0.03em;}
.pium-sub {opacity: .72; margin-bottom: 1.2rem;}
.source-chip {display:inline-block; padding:.20rem .55rem; margin-top:.4rem; border:1px solid rgba(128,128,128,.28); border-radius:999px; font-size:.78rem; opacity:.82;}
.voice-help {font-size:.82rem; opacity:.7; margin-top:-.4rem; margin-bottom:.5rem;}
@media (max-width: 640px) {
  .block-container {padding: .8rem .75rem 6.5rem .75rem;}
  .pium-title {font-size: 1.55rem;}
  .pium-sub {font-size: .92rem; margin-bottom: .8rem;}
  [data-testid="stChatMessage"] {padding-left: 0; padding-right: 0;}
  div[data-testid="stDataFrame"] {font-size: .78rem;}
}
</style>
""",
    unsafe_allow_html=True,
)


def init_state():
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("last_audio_hash", "")
    st.session_state.setdefault("kipris_calls", 0)
    st.session_state.setdefault("voice_reply", False)
    st.session_state.setdefault("last_sync_report", None)


def default_sync_years() -> list[int]:
    start = DEFAULT_YEAR - SYNC_DEFAULT_YEAR_COUNT + 1
    return list(range(start, DEFAULT_YEAR + 1))


@st.cache_resource(show_spinner=False)
def startup_sync_once():
    """On server start, fetch only source/year snapshots missing from Supabase."""
    if not AUTO_SYNC_EDMGR:
        return {"skipped": "AUTO_SYNC_EDMGR=false"}
    if not supabase_store.is_configured():
        return {"skipped": "Supabase not configured"}
    if not get_secret("EDMGR_API_KEY"):
        return {"skipped": "EDMGR_API_KEY not configured"}
    try:
        return supabase_store.sync_years(default_sync_years(), force=False)
    except Exception as exc:
        return {"errors": [f"{type(exc).__name__}: {exc}"]}


@st.cache_data(ttl=30, show_spinner=False)
def cached_coverage():
    try:
        return supabase_store.coverage()
    except Exception as exc:
        return {"configured": True, "patent": [], "transfer": [], "error": str(exc)}


def make_excel(message: dict) -> bytes | None:
    rows = message.get("data")
    if not rows:
        return None
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="근거데이터")
        plan = message.get("plan") or {}
        pd.DataFrame(
            [
                {
                    "항목": k,
                    "값": json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v,
                }
                for k, v in plan.items()
            ]
        ).to_excel(writer, index=False, sheet_name="질의계획")
        pd.DataFrame([{"AI답변": message.get("content", "")}]).to_excel(
            writer, index=False, sheet_name="AI답변"
        )
    return bio.getvalue()


def render_chart(message: dict):
    rows = message.get("raw_data")
    plan = message.get("plan") or {}
    meta = message.get("meta") or {}
    if not rows:
        return
    chart_type = plan.get("output_type", "auto")
    analysis = plan.get("analysis_type")
    if chart_type == "auto":
        chart_type = {
            "ranking": "bar",
            "trend": "line",
            "correlation": "scatter",
        }.get(analysis, "table")
    metrics = meta.get("metrics") or []
    if not metrics:
        return
    df = pd.DataFrame(rows)
    try:
        if chart_type == "bar" and {"schlNm", metrics[0]}.issubset(df.columns):
            plot = (
                df.dropna(subset=[metrics[0]])
                .sort_values(metrics[0])
                .tail(int(plan.get("top_n", 10)))
            )
            st.bar_chart(plot.set_index("schlNm")[[metrics[0]]], horizontal=True)
        elif chart_type == "line" and "aplcnYr" in df.columns:
            metric = metrics[0]
            df["aplcnYr"] = pd.to_numeric(df["aplcnYr"], errors="coerce")
            if "schlNm" in df.columns and df["schlNm"].nunique() > 1:
                pivot = df.pivot_table(
                    index="aplcnYr",
                    columns="schlNm",
                    values=metric,
                    aggfunc="sum",
                )
                st.line_chart(pivot)
            else:
                st.line_chart(df.set_index("aplcnYr")[[metric]])
        elif chart_type == "scatter" and len(metrics) >= 2:
            st.scatter_chart(df, x=metrics[0], y=metrics[1])
    except Exception:
        pass


def render_message(message: dict, index: int):
    role = message.get("role", "assistant")
    avatar = "🌱" if role == "assistant" else "👤"
    with st.chat_message(role, avatar=avatar):
        st.markdown(message.get("content", ""))
        if role == "assistant":
            mode = message.get("source_mode")
            if mode:
                st.markdown(
                    f'<span class="source-chip">{mode}</span>',
                    unsafe_allow_html=True,
                )
            rows = message.get("data")
            if rows:
                st.dataframe(
                    pd.DataFrame(rows),
                    use_container_width=True,
                    hide_index=True,
                )
                render_chart(message)
                xlsx = make_excel(message)
                if xlsx:
                    st.download_button(
                        "Excel 다운로드",
                        data=xlsx,
                        file_name="PIUM_AI_분석결과.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"xlsx_{index}",
                    )
            sources = message.get("sources") or []
            if sources:
                with st.expander("출처 보기"):
                    for src in sources[:10]:
                        title = src.get("title") or src.get("url")
                        st.markdown(f"- [{title}]({src.get('url')})")
            if message.get("audio"):
                st.audio(message["audio"], format="audio/mp3")


def process_question(question: str, from_voice: bool = False):
    if not question.strip():
        return
    user_text = question.strip()
    st.session_state.messages.append(
        {"role": "user", "content": ("🎤 " if from_voice else "") + user_text}
    )
    history_for_model = [
        {"role": m.get("role"), "content": m.get("content", "")}
        for m in st.session_state.messages[:-1]
    ]

    try:
        with st.spinner("PIUM AI가 확인하고 있습니다..."):
            result = ask(user_text, history_for_model)
    except Exception as exc:
        message = (
            "데이터 조회 중 오류가 발생했습니다. 앱은 정상적으로 계속 사용할 수 있습니다.\n\n"
            f"**진단:** `{type(exc).__name__}: {exc}`"
        )
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": message,
                "source_mode": "API/DB 오류 진단",
            }
        )
        st.rerun()
        return

    assistant = {"role": "assistant", "content": result.pop("answer"), **result}
    if assistant.get("kipris_used"):
        st.session_state.kipris_calls += 1
    if st.session_state.voice_reply:
        try:
            assistant["audio"] = text_to_speech(assistant["content"])
        except Exception as exc:
            assistant["content"] += f"\n\n_음성 생성은 실패했습니다: {exc}_"
    st.session_state.messages.append(assistant)
    st.rerun()


def render_sync_report(report: dict | None):
    if not report:
        return
    errors = report.get("errors") or []
    if errors:
        st.warning("동기화 중 일부 오류가 있었습니다.")
        with st.expander("동기화 오류"):
            for err in errors:
                st.code(err)
    elif report.get("requested_years"):
        st.success(
            f"동기화 완료 · 특허 {report.get('patent_inserted', 0)}행 / "
            f"기술이전 {report.get('transfer_inserted', 0)}행 신규 저장"
        )


init_state()
startup_report = startup_sync_once()

st.markdown(
    f'<div class="pium-title">{SERVICE_TITLE}</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="pium-sub">{SERVICE_SUBTITLE}</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("PIUM AI 설정")
    st.toggle(
        "답변 음성 재생",
        key="voice_reply",
        help="켜면 답변마다 TTS API를 호출합니다.",
    )
    if st.button("새 대화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_audio_hash = ""
        st.rerun()

    st.divider()
    st.subheader("API · DB 연결 상태")
    status_rows = [
        ("OpenAI", bool(get_secret("OPENAI_API_KEY"))),
        ("대학정보공시", bool(get_secret("EDMGR_API_KEY"))),
        ("Supabase", supabase_store.is_configured()),
        ("KIPRIS (선택)", bool(get_secret("KIPRIS_API_KEY"))),
    ]
    for label, ok in status_rows:
        st.caption(f"{'✅' if ok else '⚠️'} {label}")

    if supabase_store.is_configured():
        coverage = cached_coverage()
        patent_years = coverage.get("patent") or []
        transfer_years = coverage.get("transfer") or []
        st.caption(
            "특허 저장연도: " + (", ".join(map(str, patent_years)) if patent_years else "없음")
        )
        st.caption(
            "기술이전 저장연도: " + (", ".join(map(str, transfer_years)) if transfer_years else "없음")
        )
        if coverage.get("error"):
            st.caption(f"Supabase 상태 확인 오류: {coverage['error']}")

    if startup_report and startup_report.get("errors"):
        with st.expander("자동 동기화 상태"):
            st.caption("앱 시작 시 없는 연도만 확인하는 자동 동기화에서 오류가 있었습니다.")
            for err in startup_report["errors"]:
                st.code(err)

    st.divider()
    st.subheader("관리자 · 대학정보공시 동기화")
    admin_secret = get_secret("ADMIN_SYNC_PASSWORD")
    if not admin_secret:
        st.caption("ADMIN_SYNC_PASSWORD를 설정하면 관리자 동기화 메뉴가 활성화됩니다.")
    else:
        admin_input = st.text_input("관리자 비밀번호", type="password")
        if admin_input == admin_secret:
            default_start = DEFAULT_YEAR - SYNC_DEFAULT_YEAR_COUNT + 1
            start_year = int(
                st.number_input(
                    "시작 연도",
                    min_value=1900,
                    max_value=2100,
                    value=default_start,
                    step=1,
                )
            )
            end_year = int(
                st.number_input(
                    "종료 연도",
                    min_value=1900,
                    max_value=2100,
                    value=DEFAULT_YEAR,
                    step=1,
                )
            )
            if start_year > end_year:
                st.error("시작 연도는 종료 연도보다 클 수 없습니다.")
            else:
                years = list(range(start_year, end_year + 1))
                if st.button("신규 데이터만 동기화", use_container_width=True):
                    with st.spinner("없는 연도 데이터를 수집하고 있습니다..."):
                        report = supabase_store.sync_years(years, force=False)
                    st.session_state.last_sync_report = report
                    cached_coverage.clear()
                    startup_sync_once.clear()
                    st.rerun()

                confirm_refresh = st.checkbox(
                    "기존 데이터 덮어쓰기를 이해했습니다",
                    help="선택 연도의 기존 Supabase 값을 대학정보공시 API 값으로 갱신합니다.",
                )
                if st.button(
                    "선택 연도 전체 재동기화",
                    use_container_width=True,
                    disabled=not confirm_refresh,
                ):
                    with st.spinner("선택 연도를 전체 재동기화하고 있습니다..."):
                        report = supabase_store.sync_years(years, force=True)
                    st.session_state.last_sync_report = report
                    cached_coverage.clear()
                    startup_sync_once.clear()
                    st.rerun()
        elif admin_input:
            st.error("관리자 비밀번호가 일치하지 않습니다.")

    render_sync_report(st.session_state.last_sync_report)

    st.divider()
    st.caption(f"이번 세션 KIPRIS 호출: {st.session_state.kipris_calls}회")
    st.caption(
        "일반 통계 질문은 Supabase 저장본을 사용합니다. "
        "대학정보공시 API는 최초 적재·신규 연도 동기화·관리자 재동기화에만 사용합니다."
    )

if not st.session_state.messages:
    st.info("대학 특허, 기술이전, 연구성과, 관련 논문·기술동향을 질문해 보세요.")
    st.markdown(
        "**예시**  \n"
        "- 부산대학교 2025년 국내특허 등록건수는?  \n"
        "- 부산지역 대학 기술이전수입료 순위를 보여줘  \n"
        "- 부산대 배터리 열폭주 관련 특허와 논문을 찾아줘  \n"
        "- 부산대학교 산학협력단의 현재 등록특허를 KIPRIS 기준으로 확인해줘"
    )

for i, message in enumerate(st.session_state.messages):
    render_message(message, i)

with st.expander("🎤 음성으로 질문", expanded=False):
    st.markdown(
        '<div class="voice-help">스마트폰에서는 브라우저의 마이크 권한을 허용해 주세요.</div>',
        unsafe_allow_html=True,
    )
    audio = st.audio_input(
        "질문을 말해 주세요",
        sample_rate=16000,
        label_visibility="collapsed",
    )
    if audio is not None:
        raw = audio.getvalue()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != st.session_state.last_audio_hash:
            st.session_state.last_audio_hash = digest
            if not get_secret("OPENAI_API_KEY"):
                st.error("OPENAI_API_KEY가 필요합니다.")
            else:
                with st.spinner("음성을 텍스트로 변환하고 있습니다..."):
                    transcript = transcribe_audio(
                        raw,
                        filename=getattr(audio, "name", "voice.wav"),
                    )
                if transcript:
                    st.success(f"인식된 질문: {transcript}")
                    process_question(transcript, from_voice=True)

prompt = st.chat_input("PIUM AI에게 질문하세요")
if prompt:
    process_question(prompt)
