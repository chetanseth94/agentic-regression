"""CLI entrypoint: run the main flow from a JSON file.

Usage:
  python -m src.cli --input run.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .api.schemas.execution import ExecutionRequest
from .exceptions import OrchestrationError, ServiceUnavailableError, ValidationError
from .models.suite import ExecutionStatus, RunOutcome, SuiteInput
from .services import AiAgent, InMemoryStorage, Orchestrator, StafClient
from .services.report_parser import ReportParser
from .utils.logger import setup_logger
from .utils.preliminary_report import build_preliminary_report
from .utils.presenter import format_end_flow_report


class TriageCliApp:
    """Single entry point to execute the main flow from JSON input."""

    def __init__(self) -> None:
        self._storage = InMemoryStorage()
        self._staf = StafClient()
        self._orchestrator = Orchestrator(storage=self._storage, staf=self._staf)
        self._report_parser = ReportParser()
        self._ai_agent = AiAgent()

    @staticmethod
    def _build_suite_input(req: ExecutionRequest) -> SuiteInput:
        flows = [f.name for f in req.flows] if req.flows else []
        if not flows:
            fallback = req.suite_name or req.suite_tag
            if not fallback:
                raise ValidationError("Either 'flows' or 'suite_name' (or suite_tag) must be provided")
            flows = [fallback]

        extra_payload: Dict[str, Any] = dict(getattr(req, "model_extra", {}) or {})
        additional_params: Dict[str, Any] = dict(req.additional_params or {})
        additional_params.update(extra_payload)

        suite_tag = req.suite_tag or req.suite_name or (
            flows[0] if len(flows) == 1 else f"{len(flows)}_flows"
        )

        try:
            num_threads_int = int(req.num_threads)
        except Exception:
            num_threads_int = 1

        return SuiteInput(
            suite_tag=suite_tag,
            env_type=req.env_type,
            flows=flows,
            number_of_threads=num_threads_int,
            automation_base_url=req.env_details,
            ssl_verify=req.ssl_verify,
            ca_bundle_path=req.ca_bundle_path,
            additional_params=additional_params,
        )

    async def run_from_request(self, req: ExecutionRequest) -> dict:
        # Phase 2 only mode: parse an existing ExtentReport file locally.
        if req.skip_phase1_execution:
            if not req.extent_report_path:
                raise ValidationError("extentReportPath is required when skipPhase1Execution=true")

            report_file = Path(req.extent_report_path)
            if not report_file.exists():
                raise ValidationError(f"extentReportPath does not exist: {report_file}")

            suite_input = self._build_suite_input(req)
            directory = report_file.stem

            raw_html = report_file.read_text(encoding="utf-8", errors="ignore")
            parsed = self._report_parser.parse_html(raw_html=raw_html, directory=directory)

            # Build a minimal run context for formatted output.
            run_id = self._orchestrator.start_run(suite_input=suite_input, max_retries=req.max_retries)
            ctx = self._storage.get_run(run_id)
            if not ctx:
                raise OrchestrationError("Run context missing after creation")

            ctx.directory = directory
            ctx.report_call_count = 1
            ctx.parsed_report = parsed
            ctx.report_location = str(report_file)
            ctx.execution_status = ExecutionStatus(
                directory=directory,
                passed_tests=parsed.passed,
                skipped_tests=parsed.skipped,
                failed_tests=parsed.failed,
                flow_completed=True,
            )
            if parsed.failed == 0:
                ctx.outcome = RunOutcome.SUCCESS
            self._storage.update_run(run_id, ctx)

            status = ctx.execution_status
            suite_status = status.suite_status.value if status else "ERROR"

            decision = "GREEN" if parsed.failed == 0 else "AMBER"
            next_step = "Regression PASSED. Exit."

            report_text = format_end_flow_report(ctx)
            preliminary = build_preliminary_report(parsed_report=parsed, report_location=str(report_file))
            ctx.analysis_result = self._ai_agent.analyze_preliminary_report(preliminary)

            # Set a concrete outcome for Phase 3 (Phase 4 retrigger not implemented here).
            if parsed.failed == 0:
                ctx.outcome = RunOutcome.SUCCESS
                next_step = "Regression PASSED. Exit."
            elif ctx.analysis_result.aggregate.value == "ALL_ACTUAL":
                ctx.outcome = RunOutcome.ACTUAL_FAILURES
                next_step = "ACTUAL failures detected. Review RCA/fix suggestions."
            elif ctx.analysis_result.aggregate.value == "BOTH":
                ctx.outcome = RunOutcome.MIXED_FAILURES
                next_step = "Mixed failures (INTERMITTENT + ACTUAL). Review RCA; do not retrigger intermittent yet."
            else:
                ctx.outcome = RunOutcome.MANUAL_INTERVENTION
                next_step = "ALL_INTERMITTENT detected. Retrigger loop is Phase 4 (not implemented yet)."
            self._storage.update_run(run_id, ctx)

            return {
                "run_id": run_id,
                "directory": directory,
                "suite_tag": ctx.suite_input.suite_tag,
                "suite_status": suite_status,
                "outcome": ctx.outcome.value if ctx.outcome else "PENDING_ANALYSIS",
                "decision": decision,
                "nextStep": next_step,
                "passedTests": parsed.passed,
                "skippedTests": parsed.skipped,
                "failedTests": parsed.failed,
                "flowCompleted": True,
                "statusCallCount": ctx.status_call_count,
                "reportCallCount": ctx.report_call_count,
                "statusReadySeen": ctx.status_ready_seen,
                "statusReadyCallCount": ctx.status_ready_call_count,
                "failedFlowTags": parsed.failed_flow_tags,
                "preliminaryReport": preliminary,
                "analysis": (
                    None
                    if not ctx.analysis_result
                    else {
                        "aggregate_result": ctx.analysis_result.aggregate.value,
                        "intermittent_count": ctx.analysis_result.intermittent_count,
                        "actual_count": ctx.analysis_result.actual_count,
                        "intermittent_flow_tags": ctx.analysis_result.intermittent_flow_tags,
                        "confirmed_intermittent_flow_tags": ctx.analysis_result.confirmed_intermittent_flow_tags,
                        "refuted_intermittent_flow_tags": ctx.analysis_result.refuted_intermittent_flow_tags,
                        "actual_failures": ctx.analysis_result.actual_failures,
                    }
                ),
                "report_text": report_text,
            }

        suite_input = self._build_suite_input(req)
        staf = StafClient(
            base_url=suite_input.automation_base_url,
            ssl_verify=suite_input.ssl_verify,
            ca_bundle_path=suite_input.ca_bundle_path,
        )
        orchestrator = Orchestrator(storage=self._storage, staf=staf)

        run_id = orchestrator.start_run(suite_input=suite_input, max_retries=req.max_retries)

        try:
            directory = await orchestrator.activate_run(run_id)
            await orchestrator.poll_run(run_id)
        except (ServiceUnavailableError, ValidationError, OrchestrationError) as e:
            ctx = self._storage.get_run(run_id)
            return {
                "run_id": run_id,
                "directory": getattr(ctx, "directory", None) if ctx else None,
                "error": str(e),
                "history": ctx.history if ctx else [],
            }

        ctx = self._storage.get_run(run_id)
        if not ctx:
            raise OrchestrationError("Run context missing after execution")

        status = ctx.execution_status
        suite_status = status.suite_status.value if status else "ERROR"

        outcome = ctx.outcome.value if ctx.outcome else "RUNNING"
        if ctx.outcome is None and suite_status in ("AMBER", "ERROR"):
            outcome = "PENDING_ANALYSIS"

        decision = None
        next_step = None
        if status and status.flow_completed:
            if status.failed_tests == 0:
                decision = "GREEN"
                next_step = "Regression PASSED. Exit."
            else:
                decision = "AMBER"
                if ctx.analysis_result:
                    agg = ctx.analysis_result.aggregate.value
                    if agg == "ALL_ACTUAL":
                        next_step = "ACTUAL failures detected. Review RCA/fix suggestions."
                    elif agg == "BOTH":
                        next_step = "Mixed failures (INTERMITTENT + ACTUAL). Review RCA; do not retrigger intermittent yet."
                    else:
                        next_step = "ALL_INTERMITTENT detected. Retrigger loop is Phase 4 (not implemented yet)."
                else:
                    next_step = "Report parsed; analysis unavailable."

        report_text = format_end_flow_report(ctx)
        preliminary = build_preliminary_report(
            parsed_report=ctx.parsed_report,
            report_location=ctx.report_location,
        )

        return {
            "run_id": run_id,
            "directory": directory,
            "suite_tag": ctx.suite_input.suite_tag,
            "suite_status": suite_status,
            "outcome": outcome,
            "decision": decision,
            "nextStep": next_step,
            "passedTests": status.passed_tests if status else None,
            "skippedTests": status.skipped_tests if status else None,
            "failedTests": status.failed_tests if status else None,
            "flowCompleted": status.flow_completed if status else None,
            "statusCallCount": ctx.status_call_count,
            "reportCallCount": ctx.report_call_count,
            "statusReadySeen": ctx.status_ready_seen,
            "statusReadyCallCount": ctx.status_ready_call_count,
            "failedFlowTags": (ctx.parsed_report.failed_flow_tags if ctx.parsed_report else []),
            "preliminaryReport": preliminary,
            "analysis": (
                None
                if not ctx.analysis_result
                else {
                    "aggregate_result": ctx.analysis_result.aggregate.value,
                    "intermittent_count": ctx.analysis_result.intermittent_count,
                    "actual_count": ctx.analysis_result.actual_count,
                    "intermittent_flow_tags": ctx.analysis_result.intermittent_flow_tags,
                    "confirmed_intermittent_flow_tags": ctx.analysis_result.confirmed_intermittent_flow_tags,
                    "refuted_intermittent_flow_tags": ctx.analysis_result.refuted_intermittent_flow_tags,
                    "actual_failures": ctx.analysis_result.actual_failures,
                }
            ),
            "history": ctx.history,
            "report_text": report_text,
        }

    def run_from_file(self, input_path: str) -> dict:
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(str(path))

        data = json.loads(path.read_text(encoding="utf-8"))
        req = ExecutionRequest.model_validate(data)
        return asyncio.run(self.run_from_request(req))


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Run the triage main flow from a JSON file.")
    parser.add_argument("--input", required=True, help="Path to JSON file containing STAF payload.")
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write JSON result (also prints to stdout).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON output to stdout (default prints a concise summary).",
    )
    parser.add_argument(
        "--preliminary-report-only",
        action="store_true",
        help="Print only the preliminary report array (Phase 2 output format).",
    )
    parser.add_argument("--include-history", action="store_true", help="Include history in JSON output.")
    parser.add_argument(
        "--include-report-text",
        action="store_true",
        help="Include report_text in JSON output.",
    )
    args = parser.parse_args(argv)

    setup_logger()
    app = TriageCliApp()
    result = app.run_from_file(args.input)

    if not args.include_history:
        result.pop("history", None)
    if not args.include_report_text:
        result.pop("report_text", None)

    if args.preliminary_report_only:
        print(json.dumps(result.get("preliminaryReport", []), indent=2, default=str))
    elif args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        # Default: concise, formatted decision.
        directory = result.get("directory")
        decision = result.get("decision")
        next_step = result.get("nextStep")
        failed = result.get("failedTests")
        completed = result.get("flowCompleted")
        failed_tags = result.get("failedFlowTags") or []
        print("============================================================")
        print(f"Directory : {directory}")
        print(f"Completed : {completed}")
        print(f"Decision  : {decision}")
        if decision == "GREEN":
            print("Result    : Regression PASSED")
        elif decision == "AMBER":
            print(f"Result    : Regression FAILED (failedTests={failed})")
            if failed_tags:
                preview = ", ".join(failed_tags[:5])
                more = "" if len(failed_tags) <= 5 else f" (+{len(failed_tags)-5} more)"
                print(f"Failed flows: {preview}{more}")
            else:
                print("Failed flows: (not extracted)")
        else:
            print("Result    : UNKNOWN")
        print(f"Next step : {next_step}")
        print("============================================================")

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()

