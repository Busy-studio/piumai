from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import pandas as pd
import requests

from config import (
    EDMGR_AUTH_MODE,
    MAX_YEARS_PER_QUERY,
    PATENT_API_URL,
    TRANSFER_API_URL,
    get_secret,
)

PATENT_COLUMNS = {
    "exmnYr": "조사연도",
    "schlNm": "학교명",
    "brncYn": "분교여부",
    "aplcnYr": "적용연도",
    "dmstPtntApplNocs": "국내특허출원건수",
    "dmstPtntRegNocs": "국내특허등록건수",
    "ovrsPtntApplNocs": "해외특허출원건수",
    "ovrsPtntRegNocs": "해외특허등록건수",
}

TRANSFER_COLUMNS = {
    "exmnYr": "조사연도",
    "schlNm": "학교명",
    "brncYn": "분교여부",
    "aplcnYr": "적용연도",
    "ctrtNocs": "기술이전계약건수",
    "techBfrImpfAmt": "기술이전수입료금액",
}

METRIC_LABELS = {
    "dmstPtntApplNocs": "국내특허출원건수",
    "dmstPtntRegNocs": "국내특허등록건수",
    "ovrsPtntApplNocs": "해외특허출원건수",
    "ovrsPtntRegNocs": "해외특허등록건수",
    "ctrtNocs": "기술이전계약건수",
    "techBfrImpfAmt": "기술이전수입료금액",
}
ALL_METRICS = list(METRIC_LABELS)


def _safe_response_message(resp: requests.Response) -> str:
    text = (resp.text or "").strip()
    return text[:500] + ("..." if len(text) > 500 else "")


def _service_label(url: str) -> str:
    if url == PATENT_API_URL:
        return "특허출원및등록실적"
    if url == TRANSFER_API_URL:
        return "기술이전수입료및계약실적"
    return "대학정보공시"


def _portal_test_url(url: str) -> str | None:
    """Return the endpoint observed in the portal's own DevTools test request.

    This is used only as a fallback after the documented openapi.edmgr.kr
    endpoint returns the gateway-level PROVIDER 404. It may be a portal-only
    proxy requiring a logged-in session, so it is not treated as authoritative
    unless it actually succeeds from the Streamlit server.
    """
    if url == PATENT_API_URL:
        return "https://www.edmgr.kr/ot/udp/api/cm/SA00202500062"
    if url == TRANSFER_API_URL:
        return "https://www.edmgr.kr/ot/udp/api/cm/SA00202500061"
    return None


def _api_key_for_url(url: str) -> tuple[str, str, str]:
    """Both university-disclosure services use the same approved API key."""
    label = _service_label(url)
    api_key = get_secret("EDMGR_API_KEY")
    if not api_key:
        raise ValueError(
            f"{label} OpenAPI 인증키가 없습니다. "
            "Streamlit Secrets에 공통 EDMGR_API_KEY를 설정해 주세요. "
            "EDMGR_PATENT_API_KEY/EDMGR_TRANSFER_API_KEY는 더 이상 사용하지 않습니다."
        )
    return api_key, "EDMGR_API_KEY", label


def _post_once(url: str, payload: dict, content_mode: str) -> requests.Response:
    api_key, _, _ = _api_key_for_url(
        PATENT_API_URL if "SA00202500062" in url else TRANSFER_API_URL
    )
    auth_mode = str(EDMGR_AUTH_MODE or "header").lower().strip()
    if auth_mode not in {"header", "body", "both"}:
        auth_mode = "header"

    headers = {"Accept": "application/json"}
    body = dict(payload)
    if auth_mode in {"header", "both"}:
        headers["API_KEY"] = api_key
    if auth_mode in {"body", "both"}:
        body["userApiAthkCn"] = api_key

    if content_mode == "json":
        headers["Content-Type"] = "application/json"
        return requests.post(url, headers=headers, json=body, timeout=60)
    return requests.post(url, headers=headers, data=body, timeout=60)


def _find_best_record_list(obj, expected_keys):
    candidates = []
    expected = set(expected_keys)

    def walk(x, path="root"):
        if isinstance(x, list):
            rows = [r for r in x if isinstance(r, dict)]
            if rows:
                score = max(len(set(r) & expected) for r in rows)
                candidates.append((score, len(rows), path, rows))
            for i, item in enumerate(x[:20]):
                walk(item, f"{path}[{i}]")
        elif isinstance(x, dict):
            score = len(set(x) & expected)
            if score >= 2:
                candidates.append((score, 1, path, [x]))
            for key, value in x.items():
                walk(value, f"{path}.{key}")

    walk(obj)
    if not candidates:
        return [], None
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return candidates[0][3], candidates[0][2]


def _is_provider_not_found(resp: requests.Response) -> bool:
    if resp.status_code != 404:
        return False
    text = (resp.text or "").upper()
    return "PROVIDER" in text and "NOT FOUND" in text


@lru_cache(maxsize=128)
def _call_edmgr_cached(url: str, year: int, expected_keys: tuple[str, ...]):
    # exmnYr is the only data request parameter exposed by the portal test UI.
    payload = {"exmnYr": str(year)}
    _, secret_name, label = _api_key_for_url(url)

    resp = _post_once(url, payload, "json")
    attempts = [f"external {str(EDMGR_AUTH_MODE or 'header').lower()}/json:{resp.status_code}"]
    effective_url = url

    if resp.status_code in {400, 405, 415, 422}:
        form_resp = _post_once(url, payload, "form")
        attempts.append(f"external {str(EDMGR_AUTH_MODE or 'header').lower()}/form:{form_resp.status_code}")
        if form_resp.ok:
            resp = form_resp

    # The portal's own test button was observed to POST to
    # https://www.edmgr.kr/ot/udp/api/cm/<service-code> and return HTTP 200.
    # Try that exact route only when the documented external endpoint fails at
    # the provider-routing layer. This tells us whether the portal route is
    # callable server-to-server or only with a logged-in browser session.
    if _is_provider_not_found(resp):
        portal_url = _portal_test_url(url)
        if portal_url:
            portal_resp = _post_once(portal_url, payload, "json")
            attempts.append(
                f"portal-test {str(EDMGR_AUTH_MODE or 'header').lower()}/json:{portal_resp.status_code}"
            )
            if portal_resp.status_code in {400, 405, 415, 422}:
                portal_form = _post_once(portal_url, payload, "form")
                attempts.append(
                    f"portal-test {str(EDMGR_AUTH_MODE or 'header').lower()}/form:{portal_form.status_code}"
                )
                if portal_form.ok:
                    portal_resp = portal_form
            resp = portal_resp
            effective_url = portal_url

    if not resp.ok:
        raise RuntimeError(
            f"{label} API 호출 실패 (HTTP {resp.status_code}). "
            f"사용 키: {secret_name}. 요청 시도: {', '.join(attempts)}. "
            f"최종 End Point: {effective_url}. 응답 미리보기: {_safe_response_message(resp)}"
        )

    try:
        parsed = resp.json()
    except Exception as exc:
        raise RuntimeError(
            f"{label} API 응답을 JSON으로 해석하지 못했습니다. "
            f"최종 End Point: {effective_url}. 응답 미리보기: {_safe_response_message(resp)}"
        ) from exc

    rows, _ = _find_best_record_list(parsed, expected_keys)
    if not rows:
        raise RuntimeError(
            f"{label} API가 HTTP 200을 반환했지만 예상 데이터 행이 없습니다. "
            f"최종 End Point: {effective_url}. 응답 미리보기: {str(parsed)[:500]}"
        )
    return parsed


def _numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("원", "", regex=False)
        .str.strip()
        .replace({"": None, "None": None, "nan": None}),
        errors="coerce",
    )


def _normalize(raw, expected_columns, source_name: str) -> pd.DataFrame:
    rows, path = _find_best_record_list(raw, expected_columns.keys())
    if not rows:
        raise RuntimeError(
            f"{source_name} 응답에서 예상 데이터 행을 찾지 못했습니다. "
            f"응답 미리보기: {str(raw)[:350]}"
        )

    df = pd.DataFrame(rows)
    for col in expected_columns:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[list(expected_columns)].copy()

    text_cols = {"exmnYr", "schlNm", "brncYn", "aplcnYr"}
    for col in text_cols:
        df[col] = df[col].astype("string").str.strip()
    for col in [c for c in df.columns if c not in text_cols]:
        df[col] = _numeric_series(df[col])

    df["_source"] = source_name
    df["_detected_path"] = path
    return df


def fetch_patent(year: int) -> pd.DataFrame:
    raw = _call_edmgr_cached(PATENT_API_URL, int(year), tuple(PATENT_COLUMNS.keys()))
    return _normalize(raw, PATENT_COLUMNS, "특허출원및등록실적[대학정보공시]")


def fetch_transfer(year: int) -> pd.DataFrame:
    raw = _call_edmgr_cached(TRANSFER_API_URL, int(year), tuple(TRANSFER_COLUMNS.keys()))
    return _normalize(raw, TRANSFER_COLUMNS, "기술이전수입료및계약실적[대학정보공시]")


def fetch_years(years: Iterable[int], source: str) -> tuple[pd.DataFrame, list[tuple[int, str]]]:
    years = sorted({int(y) for y in years})
    if len(years) > MAX_YEARS_PER_QUERY:
        raise ValueError(f"한 번에 조회 가능한 연도는 최대 {MAX_YEARS_PER_QUERY}개입니다.")

    frames = []
    errors: list[tuple[int, str]] = []
    for year in years:
        try:
            if source == "patent":
                frame = fetch_patent(year)
            elif source == "transfer":
                frame = fetch_transfer(year)
            elif source == "both":
                p = fetch_patent(year).drop(columns=["_source", "_detected_path"], errors="ignore")
                t = fetch_transfer(year).drop(columns=["_source", "_detected_path"], errors="ignore")
                frame = pd.merge(
                    p,
                    t,
                    on=["exmnYr", "schlNm", "brncYn", "aplcnYr"],
                    how="outer",
                )
            else:
                raise ValueError(f"지원하지 않는 데이터원: {source}")

            frame["_requestedExmnYr"] = str(year)
            frames.append(frame)
        except Exception as exc:
            errors.append((year, str(exc)))
            # Provider/session/auth failures are independent of year. Stop
            # immediately instead of repeating the same failed request.
            text = str(exc).upper()
            if any(token in text for token in ("PROVIDER", "HTTP 401", "HTTP 403", "공통 EDMGR_API_KEY")):
                break

    if not frames:
        detail = " | ".join(f"{y}: {e}" for y, e in errors)
        raise RuntimeError(f"대학정보공시 데이터를 가져오지 못했습니다. {detail}")

    out = pd.concat(frames, ignore_index=True).drop_duplicates()
    return out, errors
