"""END FLOW: Format and present results in a readable manner."""

from ..models.suite import RunContext, RunOutcome, AggregateResult


def format_end_flow_report(run_context: RunContext) -> str:
    """
    END FLOW: Print information in presentable manner.

    Formats the final report based on the run outcome.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("  AGENTIC TEST EXECUTION AND TRIAGE - REPORT")
    lines.append("=" * 60)
    lines.append(f"  Suite Tag : {run_context.suite_input.suite_tag}")
    lines.append(f"  Env Type  : {run_context.suite_input.env_type}")
    lines.append(f"  Threads   : {run_context.suite_input.num_threads}")
    lines.append(f"  Directory : {run_context.directory}")
    lines.append(f"  Retries   : {run_context.retry_count}/{run_context.max_retries}")
    lines.append("-" * 60)

    outcome = run_context.outcome

    # ------- GREEN: Success -------
    if outcome == RunOutcome.SUCCESS:
        lines.append("")
        lines.append("  RESULT: SUCCESS")
        lines.append("  All flows passed. No failures detected.")
        lines.append("")

    # ------- RETRIGGER_SUCCESS -------
    elif outcome == RunOutcome.RETRIGGER_SUCCESS:
        lines.append("")
        lines.append("  RESULT: SUCCESS (after retrigger)")
        lines.append(f"  All flows passed after {run_context.retry_count} retrigger(s).")
        lines.append("")

    # ------- ALL ACTUAL -------
    elif outcome == RunOutcome.ACTUAL_FAILURES:
        result = run_context.analysis_result
        lines.append("")
        lines.append("  RESULT: ACTUAL FAILURES FOUND")
        lines.append(f"  Total actual failures: {result.actual_count}")
        lines.append("")
        for i, failure in enumerate(result.actual_failures, 1):
            lines.append(f"  --- Failure {i} ---")
            lines.append(f"  Flow Tag         : {failure['flow_tag']}")
            lines.append(f"  Root Cause       : {failure.get('rca', 'N/A')}")
            lines.append(f"  Stack Trace      : {failure.get('stack_trace', 'N/A')}")
            if failure.get("relevant_log_lines"):
                lines.append("  Relevant Logs    :")
                for log_line in failure["relevant_log_lines"]:
                    lines.append(f"    | {log_line}")
            lines.append(f"  Fix Suggestion   : {failure.get('fix_suggestion', 'N/A')}")
            lines.append("")

    # ------- MIXED (BOTH) -------
    elif outcome == RunOutcome.MIXED_FAILURES:
        result = run_context.analysis_result
        lines.append("")
        lines.append("  RESULT: MIXED FAILURES (Intermittent + Actual)")
        lines.append("")

        # Intermittent section
        lines.append(f"  Intermittent failures ({result.intermittent_count}):")
        lines.append(f"  (Not retriggered)")
        for tag in result.intermittent_flow_tags:
            lines.append(f"    - {tag}")
        lines.append("")

        # Actual section
        lines.append(f"  Actual failures ({result.actual_count}):")
        for i, failure in enumerate(result.actual_failures, 1):
            lines.append(f"  --- Actual Failure {i} ---")
            lines.append(f"  Flow Tag         : {failure['flow_tag']}")
            lines.append(f"  Root Cause       : {failure.get('rca', 'N/A')}")
            lines.append(f"  Stack Trace      : {failure.get('stack_trace', 'N/A')}")
            if failure.get("relevant_log_lines"):
                lines.append("  Relevant Logs    :")
                for log_line in failure["relevant_log_lines"]:
                    lines.append(f"    | {log_line}")
            lines.append(f"  Fix Suggestion   : {failure.get('fix_suggestion', 'N/A')}")
            lines.append("")

    # ------- MANUAL INTERVENTION -------
    elif outcome == RunOutcome.MANUAL_INTERVENTION:
        lines.append("")
        lines.append("  RESULT: REQUIRE MANUAL INTERVENTION")
        lines.append(f"  Retrigger limit reached ({run_context.max_retries} retries).")
        lines.append(f"  Failed flow tags that could not pass:")
        for tag in run_context.retrigger_flow_tags:
            lines.append(f"    - {tag}")
        lines.append("")

    # ------- History -------
    if run_context.history:
        lines.append("-" * 60)
        lines.append("  RUN HISTORY:")
        for entry in run_context.history:
            lines.append(
                f"    [{entry['timestamp']}] "
                f"Iter {entry['iteration']} - {entry['status']}: {entry['detail']}"
            )

    lines.append("=" * 60)

    return "\n".join(lines)
