from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import requests

from config import get_secret
from services.edmgr import fetch_years

PATENT_TABLE = "university_patent_stats"
TRANSFER_TABLE = "university_transfer_stats"
SYNC_TABLE = "university_disclosure_sync"

PATENT_DB_TO_API = {
    "school_name": "schlNm",
    "branch_yn": "brncYn",
    "year": "aplcnYr",
    "domestic_patent_applications": "dmstPtntApplNocs",
    "domestic_patent_registrations": "dmstPtntRegNocs",
    "overseas_patent_applications": "ovrsPtntApplNocs",
    "overseas_patent_registrations": "ovrsPtntRegNocs",
}
TRANSFER_DB_TO_API = {
    "school_name": "schlNm",
    "branch_yn": "brncYn",
    "year": "aplcnYr",
    "transfer_contracts": "ctrtNocs",
    "transfer_income": "techBfrImpfAmt",
}

API_TO_PATENT_DB = {v: k for k, v in PATENT_DB_TO_API.items()}
API_TO_TRANSFER_DB = {v: k for k, v in TRANSFER_DB_TO_API.items()}


@dataclass
class SyncReport:
    requested_years: list[int]
    patent_inserted: int = 0
    transfer_inserted: int = 0
    patent_synced_years: list[int] | None = None
    transfer_synced_years: list[int] | None = None
    skipped_patent_years: list[int] | None = None
    skipped_transfer_years: list[int] | None = None
    errors: list[str] | None = None

    def as_dict(self) -> dict:
        return {
            "requested_years": self.requested_years,
            "patent_inserted": self.patent_inserted,
            "transfer_inserted": self.transfer_inserted,
            "patent_synced_years": self.patent_synced_years or [],
            "transfer_synced_years": self.transfer_synced_years or [],
            "skipped_patent_years": self.skipped_patent_years or [],
            "skipped_transfer_years": self.skipped_transfer_years or [],
            "errors": self.errors or [],
        }


def is_configured() -> bool:
    return bool(get_secret("SUPABASE_URL") and get_secret("SUPABASE_SECRET_KEY"))


def _base_url() -> str:
    """Return only the Supabase project origin.

    Accepts either the project URL (https://<ref>.supabase.co) or a Data API URL
    accidentally copied with /rest/v1 appended. This prevents paths such as
    /rest/v1/rest/v1/<table>, which PostgREST rejects with PGRST125.
    """
    raw = (get_secret("SUPABASE_URL") or "").strip()
    if not raw:
        raise ValueError("SUPABASE_URL이 설정되지 않았습니다.")

    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw

    parts = urlsplit(raw)
    if not parts.netloc:
        raise ValueError("SUPABASE_URL 형식이 올바르지 않습니다.")

    return urlunsplit((parts.scheme or "https", parts.netloc, "", "", "")).rstrip("/")


def _key() -> str:
    key = get_secret("SUPABASE_SECRET_KEY") or ""
    if not key:
        raise ValueError("SUPABASE_SECRET_KEY가 설정되지 않았습니다.")
    return key


def _headers(extra: dict | None = None) -> dict:
    key = _key()
    headers = {
        "apikey": key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    if extra:
        headers.update(extra)
    return headers


def _table_url(table: str) -> str:
    return f"{_base_url()}/rest/v1/{table}"


def _raise(resp: requests.Response, action: str) -> None:
    if resp.ok:
        return
    preview = (resp.text or "")[:500]
    raise RuntimeError(f"Supabase {action} 실패: HTTP {resp.status_code} / {preview}")


def _select_all(table: str, *, params: dict | None = None) -> list[dict]:
    rows: list[dict] = []
    page_size = 1000
    start = 0
    while True:
        headers = _headers({"Range": f"{start}-{start + page_size - 1}"})
        resp = requests.get(_table_url(table), headers=headers, params=params or {}, timeout=60)
        _raise(resp, f"{table} 조회")
        chunk = resp.json() or []
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return rows


def _bulk_insert(table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    inserted = 0
    chunk_size = 500
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        resp = requests.post(
            _table_url(table),
            headers=_headers({"Prefer": "return=minimal"}),
            json=chunk,
            timeout=90,
        )
        _raise(resp, f"{table} INSERT")
        inserted += len(chunk)
    return inserted


def _bulk_upsert(table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    written = 0
    chunk_size = 500
    params = {"on_conflict": "school_name,branch_yn,year"}
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        resp = requests.post(
            _table_url(table),
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            params=params,
            json=chunk,
            timeout=90,
        )
        _raise(resp, f"{table} UPSERT")
        written += len(chunk)
    return written


def _sync_log_upsert(source: str, year: int, row_count: int) -> None:
    row = {
        "source": source,
        "year": int(year),
        "row_count": int(row_count),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = requests.post(
        _table_url(SYNC_TABLE),
        headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        params={"on_conflict": "source,year"},
        json=[row],
        timeout=60,
    )
    _raise(resp, f"{SYNC_TABLE} 기록")


def synced_years(source: str) -> set[int]:
    if not is_configured():
        return set()
    rows = _select_all(
        SYNC_TABLE,
        params={"select": "year", "source": f"eq.{source}", "order": "year.asc"},
    )
    return {int(r["year"]) for r in rows if r.get("year") is not None}


def coverage() -> dict:
    if not is_configured():
        return {"configured": False, "patent": [], "transfer": []}
    return {
        "configured": True,
        "patent": sorted(synced_years("patent")),
        "transfer": sorted(synced_years("transfer")),
    }


def _clean_scalar(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _frame_to_db_rows(df: pd.DataFrame, mapping: dict[str, str]) -> list[dict]:
    if df.empty:
        return []
    keep = [c for c in mapping if c in df.columns]
    work = df[keep].rename(columns=mapping).copy()
    rows = []
    for record in work.to_dict(orient="records"):
        cleaned = {k: _clean_scalar(v) for k, v in record.items()}
        if cleaned.get("school_name") in (None, "") or cleaned.get("year") in (None, ""):
            continue
        cleaned["school_name"] = str(cleaned["school_name"]).strip()
        cleaned["branch_yn"] = str(cleaned.get("branch_yn") or "").strip()
        cleaned["year"] = int(float(cleaned["year"]))
        rows.append(cleaned)
    return rows


def _existing_keys(table: str, years: Iterable[int]) -> set[tuple[str, str, int]]:
    years = sorted({int(y) for y in years})
    if not years:
        return set()
    year_filter = ",".join(str(y) for y in years)
    rows = _select_all(
        table,
        params={
            "select": "school_name,branch_yn,year",
            "year": f"in.({year_filter})",
        },
    )
    return {
        (str(r.get("school_name") or "").strip(), str(r.get("branch_yn") or "").strip(), int(r["year"]))
        for r in rows
        if r.get("year") is not None
    }


def _insert_missing_rows(table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    existing = _existing_keys(table, {int(r["year"]) for r in rows})
    missing = [
        r for r in rows
        if (r["school_name"], r.get("branch_yn", ""), int(r["year"])) not in existing
    ]
    return _bulk_insert(table, missing)


def sync_years(years: Iterable[int], *, force: bool = False) -> dict:
    """Store selected EDMGR years in Supabase.

    force=False: already completed source/year snapshots are skipped and existing rows are never overwritten.
    force=True: selected years are refreshed with UPSERT. Admin use only.
    """
    if not is_configured():
        raise ValueError("Supabase 설정이 없습니다.")

    years = sorted({int(y) for y in years})
    report = SyncReport(
        requested_years=years,
        patent_synced_years=[],
        transfer_synced_years=[],
        skipped_patent_years=[],
        skipped_transfer_years=[],
        errors=[],
    )

    for source, table, mapping, inserted_attr, synced_attr, skipped_attr in (
        ("patent", PATENT_TABLE, API_TO_PATENT_DB, "patent_inserted", "patent_synced_years", "skipped_patent_years"),
        ("transfer", TRANSFER_TABLE, API_TO_TRANSFER_DB, "transfer_inserted", "transfer_synced_years", "skipped_transfer_years"),
    ):
        done = synced_years(source) if not force else set()
        targets = [y for y in years if force or y not in done]
        skipped = [y for y in years if not force and y in done]
        getattr(report, skipped_attr).extend(skipped)
        if not targets:
            continue

        try:
            data, fetch_errors = fetch_years(targets, source)
        except Exception as exc:
            report.errors.append(f"{source}: {exc}")
            continue

        for year, err in fetch_errors:
            report.errors.append(f"{source} {year}: {err}")

        for year in targets:
            year_df = data[
                pd.to_numeric(data["_requestedExmnYr"], errors="coerce") == int(year)
            ].copy()
            if year_df.empty:
                continue
            rows = _frame_to_db_rows(year_df, mapping)
            try:
                written = _bulk_upsert(table, rows) if force else _insert_missing_rows(table, rows)
                setattr(report, inserted_attr, getattr(report, inserted_attr) + written)
                _sync_log_upsert(source, year, len(rows))
                getattr(report, synced_attr).append(year)
            except Exception as exc:
                report.errors.append(f"{source} {year} 저장: {exc}")

    return report.as_dict()


def _load_table(table: str, years: Iterable[int], mapping: dict[str, str]) -> pd.DataFrame:
    years = sorted({int(y) for y in years})
    if not years:
        return pd.DataFrame(columns=list(mapping.values()))
    year_filter = ",".join(str(y) for y in years)
    rows = _select_all(
        table,
        params={
            "select": ",".join(mapping.keys()),
            "year": f"in.({year_filter})",
            "order": "year.asc,school_name.asc",
        },
    )
    if not rows:
        return pd.DataFrame(columns=list(mapping.values()))
    return pd.DataFrame(rows).rename(columns=mapping)


def load_stats(years: Iterable[int], source: str) -> tuple[pd.DataFrame, list[tuple[int, str]]]:
    """Load chatbot statistical data from Supabase with the original EDMGR field names."""
    if not is_configured():
        raise ValueError("Supabase 설정이 없습니다.")

    years = sorted({int(y) for y in years})
    errors: list[tuple[int, str]] = []

    if source == "patent":
        out = _load_table(PATENT_TABLE, years, PATENT_DB_TO_API)
    elif source == "transfer":
        out = _load_table(TRANSFER_TABLE, years, TRANSFER_DB_TO_API)
    elif source == "both":
        p = _load_table(PATENT_TABLE, years, PATENT_DB_TO_API)
        t = _load_table(TRANSFER_TABLE, years, TRANSFER_DB_TO_API)
        out = pd.merge(p, t, on=["schlNm", "brncYn", "aplcnYr"], how="outer")
    else:
        raise ValueError(f"지원하지 않는 데이터원: {source}")

    if out.empty:
        for year in years:
            errors.append((year, "Supabase에 해당 연도 데이터가 없습니다. 관리자 동기화가 필요합니다."))

    return out.drop_duplicates().reset_index(drop=True), errors
