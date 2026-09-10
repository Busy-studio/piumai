from __future__ import annotations

from functools import lru_cache
import xml.etree.ElementTree as ET

import requests

from config import KIPRIS_BASE, get_secret

STATUS_CODES = {
    "all": "",
    "published": "A",
    "withdrawn": "C",
    "expired": "F",
    "abandoned": "G",
    "invalid": "I",
    "rejected": "J",
    "registered": "R",
}


def is_configured() -> bool:
    return bool(get_secret("KIPRIS_API_KEY"))


def _text(node, names):
    for name in names:
        found = node.find(f".//{name}")
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _parse_root(text: str) -> dict:
    root = ET.fromstring(text)
    total_text = _text(root, ["TotalSearchCount", "totalSearchCount", "totalCount"])
    try:
        total = int(total_text.replace(",", "")) if total_text else None
    except Exception:
        total = None

    items = root.findall(".//PatentUtilityInfo")
    if not items:
        items = root.findall(".//item")

    rows = []
    for item in items:
        rows.append(
            {
                "invention_title": _text(item, ["InventionName", "inventionTitle", "InventionTitle"]),
                "application_number": _text(item, ["ApplicationNumber", "applicationNumber"]),
                "application_date": _text(item, ["ApplicationDate", "applicationDate"]),
                "open_number": _text(item, ["OpenNumber", "openNumber", "PublicNumber"]),
                "register_number": _text(item, ["RegisterNumber", "registerNumber"]),
                "applicant": _text(item, ["ApplicantName", "applicantName", "Applicant"]),
                "inventor": _text(item, ["InventorName", "inventorName", "Inventor"]),
                "status": _text(item, ["RegisterStatus", "registerStatus", "FinalDisposal"]),
            }
        )
    return {"total_count": total, "items": rows}


@lru_cache(maxsize=256)
def search(
    word: str = "",
    applicant: str = "",
    application_number: str = "",
    status: str = "all",
    docs_count: int = 30,
) -> dict:
    key = get_secret("KIPRIS_API_KEY")
    if not key:
        raise ValueError("KIPRIS_API_KEY가 설정되지 않았습니다.")

    docs_count = max(1, min(int(docs_count), 100))
    common = {
        "docsStart": 1,
        "docsCount": docs_count,
        "patent": "true",
        "utility": "false",
        "lastvalue": STATUS_CODES.get(status, ""),
        "accessKey": key,
    }

    if application_number:
        endpoint = f"{KIPRIS_BASE}/applicationNumberSearchInfo"
        params = {**common, "applicationNumber": application_number}
        search_type = "application_number"
    elif applicant:
        endpoint = f"{KIPRIS_BASE}/applicantNameSearchInfo"
        params = {**common, "applicant": applicant}
        search_type = "applicant"
    else:
        endpoint = f"{KIPRIS_BASE}/freeSearchInfo"
        params = {**common, "word": word}
        search_type = "free"

    resp = requests.get(endpoint, params=params, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"KIPRIS Plus 호출 실패: HTTP {resp.status_code}")

    parsed = _parse_root(resp.text)
    parsed.update(
        {
            "search_type": search_type,
            "query": word,
            "applicant": applicant,
            "application_number": application_number,
            "status_filter": status,
            "returned_count": len(parsed["items"]),
        }
    )
    return parsed
