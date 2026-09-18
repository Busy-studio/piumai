from __future__ import annotations

import os
from typing import Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read a secret from Streamlit secrets first, then environment variables."""
    if st is not None:
        try:
            value = st.secrets.get(name)
            if value not in (None, ""):
                return str(value)
        except Exception:
            pass
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    return default


def get_bool_secret(name: str, default: bool = False) -> bool:
    raw = get_secret(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


OPENAI_MODEL = get_secret("OPENAI_MODEL", "gpt-5.6-terra")
TRANSCRIBE_MODEL = get_secret("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
TTS_MODEL = get_secret("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = get_secret("OPENAI_TTS_VOICE", "coral")

PATENT_API_URL = get_secret(
    "EDMGR_PATENT_API_URL",
    "https://openapi.edmgr.kr/openAPI/service/SA00202500062",
)
TRANSFER_API_URL = get_secret(
    "EDMGR_TRANSFER_API_URL",
    "https://openapi.edmgr.kr/openAPI/service/SA00202500061",
)
EDMGR_AUTH_MODE = get_secret("EDMGR_AUTH_MODE", "header")

DEFAULT_YEAR = int(get_secret("DEFAULT_YEAR", "2025"))
MAX_YEARS_PER_QUERY = int(get_secret("MAX_YEARS_PER_QUERY", "20"))

# Supabase snapshot sync. The five-year window is only the initial UI/default window;
# administrators can change the start/end years before syncing.
SYNC_DEFAULT_YEAR_COUNT = max(1, int(get_secret("SYNC_DEFAULT_YEAR_COUNT", "5")))
AUTO_SYNC_EDMGR = get_bool_secret("AUTO_SYNC_EDMGR", True)

KIPRIS_BASE = get_secret(
    "KIPRIS_BASE_URL",
    "https://plus.kipris.or.kr/openapi/rest/patUtiModInfoSearchSevice",
)

SERVICE_TITLE = "PIUM AI"
SERVICE_SUBTITLE = "대학 기술사업화 통합 AI"
