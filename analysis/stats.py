from __future__ import annotations

import re
import pandas as pd

from services.edmgr import ALL_METRICS, METRIC_LABELS

COUNT_LABELS = {
    "국내특허출원건수",
    "국내특허등록건수",
    "해외특허출원건수",
    "해외특허등록건수",
    "기술이전계약건수",
}


def _normalize_school(name: str) -> str:
    return re.sub(r"\s+", "", str(name)).strip()


def resolve_school_names(requested, available):
    if not requested:
        return []
    available = [str(x) for x in pd.Series(available).dropna().unique()]
    normalized = {_normalize_school(x): x for x in available}
    resolved = []
    for req in requested:
        n = _normalize_school(req)
        if n in normalized:
            resolved.append(normalized[n])
            continue
        n2 = n[:-1] + "대학교" if n.endswith("대") and not n.endswith("대학교") else n
        candidates = []
        for av in available:
            nav = _normalize_school(av)
            if nav == n2 or n in nav or nav in n:
                candidates.append(av)
        if len(candidates) == 1:
            resolved.append(candidates[0])
    return list(dict.fromkeys(resolved))


def _metric_list(plan):
    if plan["metric"] == "__all__":
        return list(ALL_METRICS)
    metrics = [plan["metric"]]
    metric2 = plan.get("metric2", "__none__")
    if metric2 != "__none__" and metric2 not in metrics:
        metrics.append(metric2)
    return metrics


def compute_result(df: pd.DataFrame, plan: dict) -> tuple[pd.DataFrame, dict]:
    work = df.copy()
    resolved = resolve_school_names(plan.get("schools", []), work["schlNm"])
    if plan.get("schools"):
        if not resolved:
            return work.iloc[0:0].copy(), {"resolved_schools": [], "metrics": []}
        work = work[work["schlNm"].isin(resolved)].copy()

    metrics = [m for m in _metric_list(plan) if m in work.columns and work[m].notna().any()]
    if work.empty or not metrics:
        return work.iloc[0:0].copy(), {"resolved_schools": resolved, "metrics": metrics}

    analysis = plan.get("analysis_type", "lookup")
    top_n = int(plan.get("top_n", 10))
    keys = ["aplcnYr", "schlNm", "brncYn"]

    if analysis == "ranking":
        if work["aplcnYr"].nunique(dropna=True) > 1:
            result = (
                work[keys + metrics]
                .sort_values(["aplcnYr", metrics[0]], ascending=[True, False])
                .groupby("aplcnYr", dropna=False, group_keys=False)
                .head(top_n)
            )
        else:
            result = work[keys + metrics].sort_values(metrics[0], ascending=False).head(top_n)
    elif analysis == "trend":
        group_keys = ["aplcnYr"]
        if resolved or work["schlNm"].nunique() <= 10:
            group_keys.append("schlNm")
        result = (
            work[group_keys + metrics]
            .groupby(group_keys, dropna=False, as_index=False)
            .sum(numeric_only=True, min_count=1)
        )
        result["_year"] = pd.to_numeric(result["aplcnYr"], errors="coerce")
        result = result.sort_values(["_year"] + (["schlNm"] if "schlNm" in result else [])).drop(columns="_year")
    elif analysis == "correlation":
        if len(metrics) < 2:
            raise ValueError("상관 분석에는 두 개 지표가 필요합니다.")
        result = work[keys + metrics[:2]].dropna(subset=metrics[:2]).copy()
    else:
        result = work[keys + metrics].copy()
        result["_year"] = pd.to_numeric(result["aplcnYr"], errors="coerce")
        result = result.sort_values(["_year", "schlNm"]).drop(columns="_year")

    return result.reset_index(drop=True), {
        "resolved_schools": resolved,
        "metrics": metrics,
        "analysis_type": analysis,
        "rows": len(result),
    }


def format_display_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().rename(
        columns={"aplcnYr": "연도", "schlNm": "학교명", "brncYn": "분교여부", **METRIC_LABELS}
    )
    for col in COUNT_LABELS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round().astype("Int64")
    return out
