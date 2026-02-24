"""Phase 4: retrigger confirmation for intermittent failures."""

from __future__ import annotations

from dataclasses import replace
from typing import List

from ..models.suite import AggregateResult, AnalysisResult


def confirm_intermittent_after_retrigger(
    analysis: AnalysisResult,
    retrigger_failed_unique_tags: List[str],
) -> AnalysisResult:
    """
    Confirm/refute intermittents by retrigger result.

    - If an "intermittent" flow fails again on retrigger, we treat it as ACTUAL.
    - If it passes on retrigger, we mark it confirmed intermittent.
    """
    failed_set = set(retrigger_failed_unique_tags or [])
    intermittent = list(analysis.intermittent_flow_tags or [])

    confirmed = [t for t in intermittent if t and t not in failed_set]
    refuted = [t for t in intermittent if t and t in failed_set]

    # Move refuted intermittents into actual failures.
    actual_failures = list(analysis.actual_failures or [])
    for tag in refuted:
        actual_failures.append(
            {
                "flow_tag": tag,
                "rca": "Failed again on retrigger; treat as ACTUAL failure.",
                "stack_trace": None,
                "relevant_log_lines": [],
                "fix_suggestion": "Investigate service/test/data for this flow; retrigger did not clear the failure.",
            }
        )

    # Keep only confirmed intermittents in intermittent list
    new_intermittent = confirmed

    aggregate: AggregateResult
    if new_intermittent and not actual_failures:
        aggregate = AggregateResult.ALL_INTERMITTENT
    elif actual_failures and not new_intermittent:
        aggregate = AggregateResult.ALL_ACTUAL
    else:
        aggregate = AggregateResult.BOTH

    return AnalysisResult(
        aggregate=aggregate,
        intermittent_flow_tags=new_intermittent,
        confirmed_intermittent_flow_tags=list(analysis.confirmed_intermittent_flow_tags or []) + confirmed,
        refuted_intermittent_flow_tags=list(analysis.refuted_intermittent_flow_tags or []) + refuted,
        actual_failures=actual_failures,
    )

