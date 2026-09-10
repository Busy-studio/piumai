from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from openai import OpenAI

from config import OPENAI_MODEL, TRANSCRIBE_MODEL, TTS_MODEL, TTS_VOICE, get_secret
from services.edmgr import ALL_METRICS


def client() -> OpenAI:
    key = get_secret("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return OpenAI(api_key=key)


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {
            "type": "string",
            "enum": ["stats", "knowledge", "patent_web", "web", "kipris", "reject"],
        },
        "reason": {"type": "string"},
        "stats_source": {"type": "string", "enum": ["patent", "transfer", "both", "none"]},
        "years": {"type": "array", "items": {"type": "integer"}},
        "schools": {"type": "array", "items": {"type": "string"}},
        "region_scope": {"type": "string"},
        "metric": {"type": "string", "enum": ALL_METRICS + ["__all__"]},
        "metric2": {"type": "string", "enum": ALL_METRICS + ["__none__"]},
        "analysis_type": {
            "type": "string",
            "enum": ["lookup", "ranking", "trend", "compare", "correlation", "summary", "explain"],
        },
        "output_type": {"type": "string", "enum": ["auto", "text", "table", "bar", "line", "scatter"]},
        "top_n": {"type": "integer", "minimum": 1, "maximum": 100},
        "kipris_word": {"type": "string"},
        "kipris_applicant": {"type": "string"},
        "kipris_application_number": {"type": "string"},
        "kipris_status": {
            "type": "string",
            "enum": ["all", "published", "withdrawn", "expired", "abandoned", "invalid", "rejected", "registered"],
        },
    },
    "required": [
        "route", "reason", "stats_source", "years", "schools", "region_scope", "metric", "metric2",
        "analysis_type", "output_type", "top_n", "kipris_word", "kipris_applicant",
        "kipris_application_number", "kipris_status"
    ],
    "additionalProperties": False,
}

PLANNER_INSTRUCTIONS = '''
너는 PIUM AI의 비용 절약형 라우터다. 서비스 범위는 대학 특허·지식재산·연구성과·기술이전·기술료·기술사업화·산학협력·TLO·기술지주와 그 주변의 기술/기업/논문 정보다.

도구 우선순위와 route:
1) knowledge: 최신 데이터나 정확한 외부 수치가 필요 없는 개념/방법/해석. 외부 조회 금지.
2) stats: 대학정보공시의 실제 대학별 특허 출원/등록 건수, 기술이전 계약건수, 기술이전수입료, 순위/추이/비교/상관. 숫자는 반드시 API로 조회.
   - 특허 지표만 묻으면 stats_source=patent
   - 기술이전 지표만 묻으면 stats_source=transfer
   - 두 분야 관계/비교일 때만 both
3) patent_web: 관련 특허나 특허와 연계된 논문/선행기술을 탐색하는 질문. Google Patents 중심 웹검색을 사용.
4) web: 최신 기업/시장/정책/기술동향/일반 논문 등 공개 웹 정보가 필요한 질문.
5) kipris: 한국 특허의 정확한 공식 확인이 필요한 경우에만 사용. KIPRIS 호출량은 제한되어 있으므로 최후순위다.
   예: 정확한 국내 등록특허 건수, 특정 한국 특허의 현재 상태, 공식 출원/등록번호 검증, 사용자가 KIPRIS 기준을 명시.
6) reject: 서비스 범위와 관계없는 질문.

중요 구분:
- "부산대학교 2025년 국내특허 등록건수" → stats
- "부산대학교 산학협력단이 현재 보유한 등록특허 정확히 몇 건" → kipris, applicant를 가능한 정확한 명칭으로 넣고 status=registered
- "부산대 배터리 관련 특허 찾아줘" → patent_web
- "관련 논문도 찾아줘"가 앞 대화의 특허 탐색을 이어가면 patent_web
- "특허 출원과 등록 차이" → knowledge

질문에 연도가 없으면 years=[]로 둔다. 일반 stats 기본 연도는 애플리케이션이 정한다.
표/그래프 요청을 output_type에 반영한다. 순위=ranking, 연도 변화=trend, 학교간 비교=compare, 두 지표 관계=correlation.
지역/권역(부산, 부울경, 동남권 등)을 통한 대학 선별이 필요하면 region_scope에 넣는다.
'''


def _recent_history(history: list[dict], limit: int = 8) -> list[dict]:
    compact = []
    for msg in history[-limit:]:
        compact.append({
            "role": msg.get("role", "user"),
            "content": str(msg.get("content", ""))[:2500],
        })
    return compact


def plan_question(question: str, history: list[dict]) -> dict:
    payload = {"question": question, "recent_conversation": _recent_history(history)}
    resp = client().responses.create(
        model=OPENAI_MODEL,
        instructions=PLANNER_INSTRUCTIONS,
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "pium_ai_route_plan",
                "strict": True,
                "schema": PLAN_SCHEMA,
            }
        },
        store=False,
    )
    return json.loads(resp.output_text)


REGION_SCHEMA = {
    "type": "object",
    "properties": {
        "schools": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["schools", "reason"],
    "additionalProperties": False,
}


def resolve_region(region_scope: str, available_schools: list[str]) -> tuple[list[str], str]:
    payload = {"region_scope": region_scope, "available_schools": sorted(set(available_schools))}
    resp = client().responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "한국 대학 소재 지역을 판별한다. 반드시 available_schools에 있는 학교명만 반환하고, "
            "모르면 포함하지 않는다. 부산·울산·경남·부울경·동남권 같은 권역도 처리한다."
        ),
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "region_resolution",
                "strict": True,
                "schema": REGION_SCHEMA,
            }
        },
        store=False,
    )
    parsed = json.loads(resp.output_text)
    allowed = set(available_schools)
    return [s for s in parsed["schools"] if s in allowed], parsed["reason"]


def knowledge_answer(question: str, history: list[dict]) -> str:
    payload = {"question": question, "recent_conversation": _recent_history(history)}
    resp = client().responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "너는 PIUM AI다. 대학 특허·기술이전·연구성과·기술사업화 분야 질문에 한국어로 직접 답한다. "
            "특정 대학/연도의 실제 통계 수치를 조회하지 않은 상태에서 숫자를 추정하지 않는다. "
            "대화 맥락을 이어서 답한다."
        ),
        input=json.dumps(payload, ensure_ascii=False),
        store=False,
    )
    return resp.output_text.strip()


def stats_answer(question: str, plan: dict, records: list[dict], metadata: dict, history: list[dict]) -> str:
    payload = {
        "question": question,
        "plan": plan,
        "metadata": metadata,
        "data_json": records,
        "recent_conversation": _recent_history(history),
    }
    resp = client().responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "너는 PIUM AI다. 현재는 대학정보공시 통계 답변이다. 수치·순위·증감·비교는 오직 data_json 값만 사용한다. "
            "없는 숫자를 만들거나 모델 기억으로 보완하지 않는다. 짧고 명확하게 답하고 기준 연도와 지표를 밝혀라."
        ),
        input=json.dumps(payload, ensure_ascii=False, default=str),
        store=False,
    )
    return resp.output_text.strip()


def kipris_answer(question: str, result: dict, history: list[dict]) -> str:
    payload = {"question": question, "kipris_result": result, "recent_conversation": _recent_history(history)}
    resp = client().responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "너는 PIUM AI다. 현재 답변의 한국 특허 사실과 숫자는 제공된 KIPRIS Plus 결과만 근거로 사용한다. "
            "total_count가 있으면 검색 조건에 따른 총 검색건수라고 명확히 표현하고, 현재 권리보유와 과거 출원 이력의 차이를 과장하지 않는다."
        ),
        input=json.dumps(payload, ensure_ascii=False, default=str),
        store=False,
    )
    return resp.output_text.strip()


def _collect_urls(obj: Any, out: dict[str, str]):
    if isinstance(obj, dict):
        url = obj.get("url")
        if isinstance(url, str) and url.startswith("http"):
            title = obj.get("title") or obj.get("text") or url
            out[url] = str(title)
        for value in obj.values():
            _collect_urls(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _collect_urls(value, out)


def web_answer(question: str, history: list[dict], patents_only: bool) -> tuple[str, list[dict]]:
    tool: dict[str, Any] = {"type": "web_search", "search_context_size": "medium"}
    if patents_only:
        tool["filters"] = {"allowed_domains": ["patents.google.com"]}
        instruction = (
            "Google Patents를 중심으로 특허 및 해당 서비스에서 노출되는 non-patent literature/선행기술을 조사한다. "
            "출원번호·공개번호·등록번호·권리자 등은 찾은 페이지에서 확인된 것만 적고 추정하지 않는다."
        )
    else:
        instruction = "최신 공개 웹 정보를 조사하되 1차 출처와 공신력 있는 출처를 우선한다."

    payload = {"question": question, "recent_conversation": _recent_history(history)}
    resp = client().responses.create(
        model=OPENAI_MODEL,
        instructions=f"너는 PIUM AI다. {instruction} 한국어로 답하고 핵심 근거를 구분한다.",
        input=json.dumps(payload, ensure_ascii=False),
        tools=[tool],
        tool_choice="auto",
        max_tool_calls=3,
        store=False,
    )
    dumped = resp.model_dump() if hasattr(resp, "model_dump") else {}
    urls: dict[str, str] = {}
    _collect_urls(dumped, urls)
    sources = [{"title": title, "url": url} for url, title in list(urls.items())[:12]]
    return resp.output_text.strip(), sources


def transcribe_audio(audio_bytes: bytes, filename: str = "voice.wav") -> str:
    bio = BytesIO(audio_bytes)
    bio.name = filename
    result = client().audio.transcriptions.create(
        model=TRANSCRIBE_MODEL,
        file=bio,
        language="ko",
    )
    text = getattr(result, "text", None)
    return (text or str(result)).strip()


def text_to_speech(text: str) -> bytes:
    spoken = text[:3800]
    response = client().audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=spoken,
        instructions="한국어로 자연스럽고 또렷한 업무 도우미 톤으로 읽어주세요.",
        response_format="mp3",
    )
    return response.read()
