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
from .models.suite import RunOutcome, SuiteInput
from .services import InMemoryStorage, Orchestrator, StafClient
from .utils.logger import setup_logger
from .utils.presenter import format_end_flow_report


class TriageCliApp:
    """Single entry point to execute the main flow from JSON input."""

    def __init__(self) -> None:
        self._storage = InMemoryStorage()
        self._staf = StafClient()
        self._orchestrator = Orchestrator(storage=self._storage, staf=self._staf)

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
                next_step = "AMBER analysis not implemented yet (Phase 2 pending)."

        report_text = format_end_flow_report(ctx)

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

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        # Default: concise, formatted decision.
        directory = result.get("directory")
        decision = result.get("decision")
        next_step = result.get("nextStep")
        failed = result.get("failedTests")
        completed = result.get("flowCompleted")
        print("============================================================")
        print(f"Directory : {directory}")
        print(f"Completed : {completed}")
        print(f"Decision  : {decision}")
        if decision == "GREEN":
            print("Result    : Regression PASSED")
        elif decision == "AMBER":
            print(f"Result    : Regression FAILED (failedTests={failed})")
        else:
            print("Result    : UNKNOWN")
        print(f"Next step : {next_step}")
        print("============================================================")

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()

