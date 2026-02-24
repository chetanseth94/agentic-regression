"""Build a preliminary failure report from parsed ExtentReport results.

This is a Phase 2 output format for downstream analysis (Phase 3+).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..models.report import FlowResult, FlowStatus, HTMLReport


_HTTP_CODE_RE = re.compile(r"\b([245]\d{2})\b")
_TAG_SAFE_RE = re.compile(r"[^A-Za-z0-9]+")
_AGENTIC_TAG_RE = re.compile(r"@agentic_analysis_[A-Za-z0-9_\\-]+")
_SUITE_KEY_RE = re.compile(r"\b(RBS|MAF)\s*[- ]?\s*(\d{2,6})\b", flags=re.I)
_F_RE = re.compile(r"\bF\s*[- ]?\s*(\d{1,2})\b", flags=re.I)
_SCN_RE = re.compile(r"\bSCN\s*[- ]?\s*(\d{1,2})\b", flags=re.I)


def _norm_key(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", (s or "")).lower()


def _best_agentic_tag(flow_name: str, candidates: List[str]) -> Optional[str]:
    """
    Choose the best @agentic_analysis_* tag based on suite key (RBS/MAF + number)
    and (if present) Fxx / SCNxx markers in the scenario name.
    """
    if not candidates:
        return None

    m = _SUITE_KEY_RE.search(flow_name or "")
    if not m:
        return None

    suite = m.group(1).upper()
    num = m.group(2)
    f_m = _F_RE.search(flow_name or "")
    scn_m = _SCN_RE.search(flow_name or "")
    f_raw = f_m.group(1) if f_m else None
    scn_raw = scn_m.group(1) if scn_m else None

    f_tokens = []
    if f_raw:
        f_tokens = [_norm_key(f"F{f_raw}"), _norm_key(f"F{str(int(f_raw)).zfill(2)}")]
        f_tokens = [t for t in f_tokens if t]
    scn_tokens = []
    if scn_raw:
        scn_tokens = [_norm_key(f"SCN{scn_raw}"), _norm_key(f"SCN{str(int(scn_raw)).zfill(2)}")]
        scn_tokens = [t for t in scn_tokens if t]

    best = None
    best_score = -1
    suite_token = _norm_key(f"{suite}{num}")
    for cand in candidates:
        c = _norm_key(cand)
        score = 0
        if suite_token and suite_token in c:
            score += 10
        if f_tokens and any(tok in c for tok in f_tokens):
            score += 4
        if scn_tokens and any(tok in c for tok in scn_tokens):
            score += 3
        if score > best_score:
            best_score = score
            best = cand
    return best if best_score > 0 else None


def _to_unique_flow_tag(flow_tag_or_name: str, agentic_candidates: Optional[List[str]] = None) -> str:
    # Convert a scenario name into a stable tag-like identifier.
    s = flow_tag_or_name.strip()
    m = _AGENTIC_TAG_RE.search(s)
    if m:
        return m.group(0)

    if agentic_candidates:
        picked = _best_agentic_tag(flow_name=s, candidates=agentic_candidates)
        if picked:
            return picked

    s = _TAG_SAFE_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if len(s) > 80:
        s = s[:80].rstrip("_")
    return f"@agentic_analysis_{s}"


def _infer_last_api_response_code(flow: FlowResult) -> str:
    # Best-effort: look for explicit HTTP status code in failed steps.
    haystack = " ".join([flow.error_message or ""] + (flow.failed_steps or []))
    if "5xx" in haystack.lower() or "4xx" in haystack.lower():
        return "5xx/4xx"
    # Prefer patterns like "verify 200" or "status code 500" if present.
    m = re.search(r"\b(?:verify|verified|status|code|http)\s*[:=]?\s*([245]\d{2})\b", haystack, flags=re.I)
    if m:
        return m.group(1)
    m = _HTTP_CODE_RE.search(haystack)
    if m:
        return m.group(1)
    return "UNKNOWN"


def _infer_failure_type(flow: FlowResult) -> str:
    text = " ".join([flow.flow_name, flow.error_message or ""] + (flow.failed_steps or []))
    t = text.lower()
    # Very coarse heuristics; refine when we know the exact categories desired.
    if "oh" in t and "step" in t:
        return "OH Step Failure"
    if "order hook" in t:
        return "OH Step Failure"
    if "api" in t or "http" in t or _HTTP_CODE_RE.search(t):
        return "Execution step failure"
    return "Execution step failure"


def _failure_details(flow: FlowResult) -> str:
    # Keep it short: Phase 2 is only preliminary.
    first = flow.error_message or (flow.failed_steps[0] if flow.failed_steps else "")
    first = (first or "").strip()
    code = _infer_last_api_response_code(flow)
    if code not in {"UNKNOWN", "5xx/4xx"}:
        return f"{first}\n[verify {code}]".strip()
    return first


def build_preliminary_report(
    parsed_report: Optional[HTMLReport],
    report_location: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return the preliminary report array requested by the user."""
    items: List[Dict[str, Any]] = []
    if parsed_report:
        agentic_candidates = list(parsed_report.metadata.get("agentic_analysis_tags", []) or [])
        for flow in parsed_report.failed_flows:
            items.append(
                {
                    "uniqueFlowTag": _to_unique_flow_tag(
                        flow.flow_tag or flow.flow_name,
                        agentic_candidates=agentic_candidates,
                    ),
                    "lastAPIResponseCode": _infer_last_api_response_code(flow),
                    "failureType": _infer_failure_type(flow),
                    "Failure details": _failure_details(flow),
                }
            )

    if report_location:
        items.append({"reportLocation": report_location})
    return items

