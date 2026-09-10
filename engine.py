from __future__ import annotations

from analysis.stats import compute_result, format_display_df
from config import DEFAULT_YEAR
from services import kipris
from services.edmgr import fetch_years
from services.openai_service import (
    kipris_answer,
    knowledge_answer,
    plan_question,
    resolve_region,
    stats_answer,
    web_answer,
)


def ask(question: str, history: list[dict]) -> dict:
    plan = plan_question(question, history)
    route = plan["route"]

    if route == "reject":
        return {
            "answer": "PIUM AI는 대학 특허·연구성과·기술이전·기술사업화 분야 전용입니다. 관련 질문을 입력해 주세요.",
            "source_mode": "scope",
            "plan": plan,
        }

    if route == "knowledge":
        return {
            "answer": knowledge_answer(question, history),
            "source_mode": "Luna",
            "plan": plan,
        }

    if route == "patent_web":
        answer, sources = web_answer(question, history, patents_only=True)
        return {
            "answer": answer,
            "source_mode": "Google Patents · Web Search",
            "sources": sources,
            "plan": plan,
        }

    if route == "web":
        answer, sources = web_answer(question, history, patents_only=False)
        return {
            "answer": answer,
            "source_mode": "Web Search",
            "sources": sources,
            "plan": plan,
        }

    if route == "kipris":
        if not kipris.is_configured():
            answer, sources = web_answer(question, history, patents_only=True)
            note = (
                "\n\n> KIPRIS API 키가 아직 설정되지 않아 이번 답변은 Google Patents 웹검색으로 대체했습니다. "
                "공식 국내 특허 확인에는 KIPRIS 키가 필요합니다."
            )
            return {
                "answer": answer + note,
                "source_mode": "Google Patents · KIPRIS fallback",
                "sources": sources,
                "plan": plan,
                "kipris_used": False,
            }

        result = kipris.search(
            word=plan.get("kipris_word", ""),
            applicant=plan.get("kipris_applicant", ""),
            application_number=plan.get("kipris_application_number", ""),
            status=plan.get("kipris_status", "all"),
            docs_count=max(10, min(plan.get("top_n", 10), 50)),
        )
        return {
            "answer": kipris_answer(question, result, history),
            "source_mode": "KIPRIS Plus",
            "kipris_result": result,
            "kipris_used": True,
            "plan": plan,
        }

    years = plan.get("years") or [DEFAULT_YEAR]
    source = plan.get("stats_source", "none")
    if source == "none":
        source = "both" if plan.get("metric") == "__all__" else (
            "transfer" if plan.get("metric") in {"ctrtNocs", "techBfrImpfAmt"} else "patent"
        )

    data, fetch_errors = fetch_years(years, source)
    region_reason = ""
    if plan.get("region_scope"):
        schools, region_reason = resolve_region(
            plan["region_scope"],
            data["schlNm"].dropna().astype(str).tolist(),
        )
        plan = dict(plan)
        plan["schools"] = schools

    result, meta = compute_result(data, plan)
    meta["region_resolution_reason"] = region_reason
    meta["fetch_errors"] = fetch_errors
    display_df = format_display_df(result)

    if result.empty:
        answer = "현재 대학정보공시 API에서 질문 조건에 맞는 데이터를 확인하지 못했습니다."
    else:
        answer = stats_answer(
            question,
            plan,
            result.where(result.notna(), None).to_dict(orient="records"),
            meta,
            history,
        )

    return {
        "answer": answer,
        "source_mode": "대학정보공시 OpenAPI",
        "plan": plan,
        "data": display_df.to_dict(orient="records"),
        "raw_data": result.where(result.notna(), None).to_dict(orient="records"),
        "meta": meta,
    }
