"""Extent Spark BDD HTML report parser."""

from __future__ import annotations

import re
from datetime import datetime
from itertools import islice
from typing import Optional

from bs4 import BeautifulSoup

from ..core.base_parser import BaseReportParser
from ..exceptions import InvalidReportError, ParserError
from ..models.report import FlowResult, FlowStatus, HTMLReport


_TAG_RE = re.compile(r"@[A-Za-z0-9_\-]+")
_AGENTIC_TAG_RE = re.compile(r"@agentic_analysis_[A-Za-z0-9_\-]+")
_KEY_RE = re.compile(r"\b[A-Za-z]{2,8}[- ]?\d{2,6}\b")
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", flags=re.I)
_ACTUAL_STATUS_CODE_RE = re.compile(r"Actual\s+Status\s+Code\s*:?[\s\xa0]*([1-5]\d{2})", flags=re.I)


def _limited_text(
    el,
    *,
    max_chars: int,
    max_fragments: int,
) -> str:
    """
    Safely extract text from a possibly huge DOM subtree.

    Extent reports can embed massive log blobs inside step nodes; calling `.get_text()`
    walks the entire subtree and can be extremely slow. `stripped_strings` is a generator,
    so we can stop early once we have enough signal for summarization.
    """

    if el is None:
        return ""

    out: list[str] = []
    total = 0

    try:
        it = el.stripped_strings
    except Exception:
        # Best-effort fallback; still bounded.
        try:
            txt = el.get_text(" ", strip=True)
        except Exception:
            return ""
        return txt[:max_chars]

    for s in islice(it, max_fragments):
        if not s:
            continue

        # +1 to account for joining spaces.
        next_total = total + len(s) + 1
        if next_total > max_chars:
            remaining = max_chars - total
            if remaining > 0:
                out.append(s[:remaining])
            out.append("…")
            break

        out.append(s)
        total = next_total

    return " ".join(out).strip()


def _extract_keys(flow_name: str) -> list[str]:
    """
    Extract stable identifiers like 'RBS-780', 'RBS 2807', 'MAF448' from flow names.
    Used to scope log rows to the current test-item (Extent reports can include nested logs).
    """
    keys = []
    for m in _KEY_RE.finditer(flow_name):
        raw = m.group(0).strip()
        if raw:
            keys.append(raw)
    # De-dup while preserving order
    out: list[str] = []
    seen = set()
    for k in keys:
        if k not in seen:
            out.append(k)
            seen.add(k)
    return out[:3]


def _matches_any_key(text: str, keys: list[str]) -> bool:
    if not keys:
        return True
    t = text
    t_compact = re.sub(r"[\s\-]+", "", t)
    for k in keys:
        if k in t:
            return True
        if re.sub(r"[\s\-]+", "", k) in t_compact:
            return True
    return False


def _summarize_step(div_text: str, title: str) -> str:
    """
    Create a safe, compact step summary.
    We intentionally avoid dumping request headers/payloads (may include tokens/PII).
    """
    parts: list[str] = []
    t = title.strip() if title else ""
    if t:
        parts.append(t)

    m = _URL_RE.search(div_text)
    if m:
        parts.append(f"url={m.group(0)}")

    m = _ACTUAL_STATUS_CODE_RE.search(div_text)
    if m:
        parts.append(f"Actual Status Code: {m.group(1)}")

    return " | ".join(parts).strip()


class ExtentSparkBddReportParser(BaseReportParser):
    """Parses Extent Spark BDD reports used by STAF stafReport API."""

    def parse(self, raw_html: str, directory: str) -> HTMLReport:
        if not self.validate(raw_html):
            raise InvalidReportError("html", "empty or non-HTML content")

        try:
            soup = BeautifulSoup(raw_html, "lxml")
        except Exception as e:
            raise ParserError(f"Failed to parse HTML: {e}") from e

        # Heuristic: Spark BDD report uses <body class="spa bdd-report ...">
        body = soup.select_one("body")
        if not body or "bdd-report" not in (body.get("class") or []):
            # still try parsing; don't hard-fail
            pass

        results: list[FlowResult] = []
        passed = failed = skipped = 0

        # Extent uses li.test-item with status=pass|fail|skip for scenarios/tests.
        test_items = soup.select("li.test-item")
        for item in test_items:
            status = (item.get("status") or "").strip().lower()
            if status not in {"pass", "fail", "skip"}:
                # Many items are feature/group nodes without a status.
                continue

            name_el = item.select_one("p.name") or item.select_one(".name")
            flow_name = name_el.get_text(strip=True) if name_el else "UNKNOWN"
            keys = _extract_keys(flow_name)

            # flow_tag: prefer explicit @tag in the name; else use the name itself.
            m = _TAG_RE.search(flow_name)
            flow_tag = m.group(0) if m else flow_name

            if status == "pass":
                flow_status = FlowStatus.PASSED
                passed += 1
            elif status == "skip":
                flow_status = FlowStatus.SKIPPED
                skipped += 1
            else:
                flow_status = FlowStatus.FAILED
                failed += 1

            # Extract failed steps / error message for failed items.
            failed_steps: list[str] = []
            steps: list[str] = []
            error_message: Optional[str] = None
            trace: Optional[str] = None

            # Preferred: parse step blocks (these contain rich details like "Actual Status Code: 200").
            step_divs = item.select("div.step")
            if step_divs:
                for div in step_divs:
                    classes = set(div.get("class") or [])
                    title_el = div.select_one("span")
                    title = title_el.get_text(" ", strip=True) if title_el else ""
                    div_text = _limited_text(div, max_chars=6000, max_fragments=1500)

                    summary = _summarize_step(div_text=div_text, title=title) or title or div_text[:300]
                    if not summary:
                        continue

                    steps.append(summary)
                    if any(c.endswith("fail-bg") or c == "fail-bg" for c in classes) or "fail-bg" in classes:
                        failed_steps.append(summary)
                        if error_message is None:
                            error_message = summary

            # Step rows are often shown in a table with badge log classes.
            # Fallback: table rows
            if not steps:
                for row in item.select("tr"):
                    row_text = _limited_text(row, max_chars=3000, max_fragments=500)
                    if not row_text:
                        continue
                    # Extent HTML sometimes nests other scenario logs; keep rows that match this scenario's keys.
                    if not _matches_any_key(row_text, keys):
                        continue

                    steps.append(row_text)
                    if row.select_one("span.badge.log.fail-bg"):
                        failed_steps.append(row_text)
                        if error_message is None:
                            error_message = row_text

            # Some reports place a trace/log blob inside <pre> or <textarea>.
            pre = item.select_one("pre") or item.select_one("textarea")
            if pre:
                t = pre.get_text("\n", strip=True)
                trace = t[:20000] if len(t) > 20000 else t

            results.append(
                FlowResult(
                    flow_tag=flow_tag,
                    flow_name=flow_name,
                    status=flow_status,
                    error_message=error_message,
                    trace=trace,
                    steps=steps[:200],  # cap to avoid massive payloads
                    failed_steps=failed_steps[:50],
                )
            )

        report = HTMLReport(
            directory=directory,
            raw_html="",  # keep empty by default to avoid huge in-memory payloads
            total_flows=passed + failed + skipped,
            passed=passed,
            failed=failed,
            skipped=skipped,
            flow_results=results,
            metadata={},
        )

        # Capture agentic tags present in the report (usually in the tag filter dropdown).
        # Note: Extent does not always populate per-scenario tag attributes.
        try:
            tags = sorted(set(_AGENTIC_TAG_RE.findall(raw_html)))
            if tags:
                report.metadata["agentic_analysis_tags"] = tags
        except Exception:
            pass

        # Try capture report timestamp (badge text usually contains datetime)
        try:
            badge = soup.select_one(".nav-right .badge.badge-primary")
            if badge:
                # e.g., "Feb 23, 2026 09:54:10 AM"
                dt = badge.get_text(strip=True)
                report.metadata["report_time"] = dt
        except Exception:
            pass

        return report

