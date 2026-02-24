"""Phase 3: AI triage (classification + aggregate)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from anthropic import Anthropic

from ..config import get_settings
from ..exceptions import OrchestrationError
from ..models.suite import AggregateResult, AnalysisResult


class AiAgent:
    """
    Classify failed flows into INTERMITTENT vs ACTUAL and produce RCA suggestions.

    - Uses Anthropic when configured (anthropic_api_key).
    - Falls back to deterministic heuristics when AI is not available.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def analyze_preliminary_report(self, preliminary_report: List[Dict[str, Any]]) -> AnalysisResult:
        failures = [x for x in preliminary_report if x.get("uniqueFlowTag")]
        if not failures:
            return AnalysisResult(aggregate=AggregateResult.ALL_INTERMITTENT)

        if self._settings.anthropic_api_key:
            try:
                return self._analyze_with_anthropic(failures)
            except Exception:
                # Fail-safe: fall back to heuristics.
                return self._analyze_with_heuristics(failures)

        return self._analyze_with_heuristics(failures)

    def _analyze_with_anthropic(self, failures: List[Dict[str, Any]]) -> AnalysisResult:
        client = Anthropic(api_key=self._settings.anthropic_api_key)

        prompt = {
            "task": "Classify each failed flow as INTERMITTENT or ACTUAL. Provide RCA and fix suggestion for ACTUAL.",
            "rules": [
                "Use only the provided evidence fields; do not invent log lines.",
                "If status code is 5xx/429/408 or looks like network/transient, prefer INTERMITTENT unless evidence suggests otherwise.",
                "If status code is 4xx (except 408/429), prefer ACTUAL unless evidence suggests otherwise.",
                "Return STRICT JSON only. No markdown.",
            ],
            "failures": failures,
            "output_schema": {
                "flow_results": [
                    {
                        "flow_tag": "@agentic_analysis_...",
                        "classification": "INTERMITTENT|ACTUAL",
                        "reasoning": "string",
                        "confidence": 0.0,
                        "rca": "string (only for ACTUAL)",
                        "fix_suggestion": "string (only for ACTUAL)",
                    }
                ]
            },
        }

        message = client.messages.create(
            model=self._settings.anthropic_model,
            max_tokens=self._settings.anthropic_max_tokens,
            temperature=0,
            system="You are a senior SRE and test automation triage assistant.",
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(prompt),
                }
            ],
        )

        text = ""
        # anthropic>=0.18 returns message.content list of blocks with .text
        for block in getattr(message, "content", []) or []:
            t = getattr(block, "text", None)
            if t:
                text += t

        # Extract JSON even if the model adds incidental text.
        data = _extract_first_json_object(text)
        if not isinstance(data, dict) or "flow_results" not in data:
            raise OrchestrationError("AI response missing required 'flow_results' JSON")

        return self._aggregate_from_ai(data["flow_results"])

    def _aggregate_from_ai(self, flow_results: Any) -> AnalysisResult:
        if not isinstance(flow_results, list):
            raise OrchestrationError("AI response 'flow_results' must be a list")

        intermittent: List[str] = []
        actual_failures: List[dict] = []

        for item in flow_results:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("flow_tag") or "").strip()
            classification = str(item.get("classification") or "").strip().upper()
            if not tag:
                continue
            if classification == "INTERMITTENT":
                intermittent.append(tag)
            else:
                # Default to ACTUAL
                actual_failures.append(
                    {
                        "flow_tag": tag,
                        "rca": str(item.get("rca") or item.get("reasoning") or "N/A"),
                        "stack_trace": None,
                        "relevant_log_lines": [],
                        "fix_suggestion": str(item.get("fix_suggestion") or "N/A"),
                    }
                )

        aggregate = _aggregate(intermittent, actual_failures)
        return AnalysisResult(aggregate=aggregate, intermittent_flow_tags=intermittent, actual_failures=actual_failures)

    def _analyze_with_heuristics(self, failures: List[Dict[str, Any]]) -> AnalysisResult:
        intermittent: List[str] = []
        actual_failures: List[dict] = []

        for f in failures:
            tag = str(f.get("uniqueFlowTag") or "").strip()
            code = str(f.get("lastAPIResponseCode") or "").strip().upper()
            details = str(f.get("Failure details") or "")
            failure_type = str(f.get("failureType") or "")

            if not tag:
                continue

            classification = _classify_heuristic(code=code, details=details)
            if classification == "INTERMITTENT":
                intermittent.append(tag)
            else:
                actual_failures.append(
                    {
                        "flow_tag": tag,
                        "rca": _rca_heuristic(code=code, details=details, failure_type=failure_type),
                        "stack_trace": None,
                        "relevant_log_lines": [],
                        "fix_suggestion": _fix_suggestion_heuristic(code=code, details=details),
                    }
                )

        aggregate = _aggregate(intermittent, actual_failures)
        return AnalysisResult(aggregate=aggregate, intermittent_flow_tags=intermittent, actual_failures=actual_failures)


def _aggregate(intermittent: List[str], actual_failures: List[dict]) -> AggregateResult:
    if intermittent and not actual_failures:
        return AggregateResult.ALL_INTERMITTENT
    if actual_failures and not intermittent:
        return AggregateResult.ALL_ACTUAL
    return AggregateResult.BOTH


def _classify_heuristic(code: str, details: str) -> str:
    d = (details or "").lower()

    # Explicit buckets
    if code in {"5XX/4XX", "UNKNOWN"}:
        # fall through to keyword heuristics
        pass

    # Numeric code?
    m = re.search(r"\b([1-5]\d{2})\b", code)
    num = int(m.group(1)) if m else None

    if num is not None:
        if num >= 500:
            return "INTERMITTENT"
        if num in {408, 429}:
            return "INTERMITTENT"
        if 400 <= num < 500:
            return "ACTUAL"
        # 2xx still can fail due to validation/assertion; treat as ACTUAL unless clear transient.

    # Keyword-based
    transient_words = [
        "timeout",
        "timed out",
        "connection reset",
        "connection refused",
        "socket",
        "temporary",
        "unavailable",
        "gateway",
        "dns",
        "ssl",
        "handshake",
        "service unavailable",
        "bad gateway",
    ]
    if any(w in d for w in transient_words):
        return "INTERMITTENT"

    return "ACTUAL"


def _rca_heuristic(code: str, details: str, failure_type: str) -> str:
    m = re.search(r"Actual Status Code:\s*([1-5]\d{2})", details, flags=re.I)
    status = m.group(1) if m else code
    if status and str(status).startswith("5"):
        return f"Backend/service error returned {status} during '{failure_type or 'execution'}'."
    if status and str(status).startswith("4"):
        return f"Client/request issue returned {status} (invalid input/contract/auth) during '{failure_type or 'execution'}'."
    return "Failure occurred during execution; insufficient evidence for precise RCA (Phase 5 logs pending)."


def _fix_suggestion_heuristic(code: str, details: str) -> str:
    m = re.search(r"url=([^\s|]+)", details)
    url = m.group(1) if m else ""
    if code.startswith("5") or " 5" in code:
        return f"Check downstream service health for {url} and retry if transient; inspect server logs for 5xx root cause."
    if code.startswith("4") or " 4" in code:
        return f"Validate request payload/headers and contract for {url}; fix test data or API contract mismatch."
    return "Collect runtime logs (Phase 5) and correlate with this step to determine if intermittent or actual."


def _extract_first_json_object(text: str) -> Any:
    if not text:
        return None
    # Very small, robust extractor: find first {...} block and json.loads it.
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                snippet = text[start : i + 1]
                return json.loads(snippet)
    return None

