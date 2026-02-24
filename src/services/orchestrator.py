"""Main flow orchestration (Phase 1: GREEN path)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Optional

from ..config import get_settings
from ..exceptions import OrchestrationError
from ..models.suite import AggregateResult, ExecutionStatus, RunContext, RunOutcome, SuiteInput, SuiteStatus
from ..utils.logger import get_logger
from ..utils.preliminary_report import build_preliminary_report
from ..utils.retrigger_confirmation import confirm_intermittent_after_retrigger
from .ai_agent import AiAgent
from .staf_client import StafClient
from .report_parser import ReportParser
from .storage import InMemoryStorage


class Orchestrator:
    def __init__(self, storage: InMemoryStorage, staf: StafClient) -> None:
        self._storage = storage
        self._staf = staf
        self._settings = get_settings()
        self._logger = get_logger("triage.orchestrator")
        self._report_parser = ReportParser()
        self._ai_agent = AiAgent()

    def _phase(self, ctx: RunContext, phase: str, event: str, directory: Optional[str] = None) -> None:
        d = directory or ctx.directory or ""
        msg = f"PHASE_{event.upper()} {phase} directory={d}".strip()
        self._logger.info(msg)
        # also push to history for CLI/API consumers
        ctx.log_iteration(SuiteStatus.RUNNING, msg)

    def start_run(self, suite_input: SuiteInput, max_retries: int) -> str:
        ctx = RunContext(
            suite_input=suite_input,
            retry_count=0,
            max_retries=max_retries,
            started_at=datetime.now(),
        )
        return self._storage.store_run(ctx)

    async def activate_run(self, run_id: str) -> str:
        """Step 1: activate and persist directory."""
        ctx = self._storage.get_run(run_id)
        if not ctx:
            raise OrchestrationError(f"Run not found: {run_id}")

        self._phase(ctx, "PHASE_1_ACTIVATE", "start")
        self._logger.info(
            "Activating suite=%s envType=%s flows=%s threads=%s base_url=%s",
            ctx.suite_input.suite_tag,
            ctx.suite_input.env_type,
            len(ctx.suite_input.flows),
            ctx.suite_input.number_of_threads,
            self._staf.base_url,
        )
        try:
            directory = await self._staf.activate(ctx.suite_input)
        except Exception as e:
            ctx.outcome = RunOutcome.MANUAL_INTERVENTION
            ctx.completed_at = datetime.now()
            ctx.log_iteration(SuiteStatus.ERROR, f"Activate failed: {e}")
            self._storage.update_run(run_id, ctx)
            self._logger.error("Activate failed: %s", e)
            raise OrchestrationError(f"Activate failed: {e}") from e

        ctx.directory = directory
        ctx.log_iteration(SuiteStatus.RUNNING, f"Activated. directory={directory}")
        self._storage.update_run(run_id, ctx)
        self._logger.info("Activated directory=%s", directory)
        self._phase(ctx, "PHASE_1_ACTIVATE", "complete")
        return directory

    async def _poll_directory_until_complete(self, ctx: RunContext, directory: str) -> ExecutionStatus:
        """Poll status for a specific directory until GREEN/AMBER/ERROR."""
        start_time = datetime.now()
        deadline = start_time + timedelta(seconds=self._settings.poll_max_wait_seconds)
        not_ready_deadline = start_time + timedelta(
            seconds=self._settings.directory_not_ready_max_wait_seconds
        )

        self._logger.info(
            "Polling start directory=%s poll_interval=%ss max_wait=%ss",
            directory,
            self._settings.poll_interval_seconds,
            self._settings.poll_max_wait_seconds,
        )
        while datetime.now() < deadline:
            try:
                ctx.status_call_count += 1
                status = await self._staf.status(directory)
            except Exception as e:
                ctx.log_iteration(SuiteStatus.ERROR, f"Status fetch failed (directory={directory}): {e}")
                raise OrchestrationError(f"Status fetch failed (directory={directory}): {e}") from e

            if status.is_invalid_directory and datetime.now() < not_ready_deadline:
                ctx.log_iteration(
                    SuiteStatus.RUNNING,
                    f"Status not ready yet (directory={directory}). Retrying soon...",
                )
                await asyncio.sleep(self._settings.directory_not_ready_poll_interval_seconds)
                continue

            detail = (
                f"passed={status.passed_tests} skipped={status.skipped_tests} "
                f"failed={status.failed_tests} completed={status.flow_completed}"
            )
            ctx.log_iteration(status.suite_status, f"{detail} (directory={directory})")

            if status.suite_status == SuiteStatus.RUNNING:
                await asyncio.sleep(self._settings.poll_interval_seconds)
                continue

            return status

        raise OrchestrationError(f"Polling timed out (directory={directory})")

    async def poll_run(self, run_id: str) -> None:
        """Step 2: poll status until completion (GREEN/AMBER) or timeout."""
        ctx = self._storage.get_run(run_id)
        if not ctx:
            raise OrchestrationError(f"Run not found: {run_id}")
        if not ctx.directory:
            raise OrchestrationError(f"Run missing directory (activate first): {run_id}")

        self._phase(ctx, "PHASE_1_POLL", "start")
        try:
            status = await self._poll_directory_until_complete(ctx, ctx.directory)
        except Exception as e:
            ctx.execution_status = None
            ctx.outcome = RunOutcome.MANUAL_INTERVENTION
            ctx.completed_at = datetime.now()
            ctx.log_iteration(SuiteStatus.ERROR, str(e))
            self._storage.update_run(run_id, ctx)
            self._logger.error("Polling failed directory=%s: %s", ctx.directory, e)
            return

        ctx.execution_status = status
        suite_status = status.suite_status
        self._storage.update_run(run_id, ctx)
        self._phase(ctx, "PHASE_1_POLL", "complete")

        # Completion: decide GREEN vs AMBER and next steps.
        if suite_status == SuiteStatus.GREEN:
            ctx.outcome = RunOutcome.SUCCESS
            self._logger.info("DECISION directory=%s -> GREEN", ctx.directory)
            self._logger.info("NEXT directory=%s -> Regression PASSED. Exiting.", ctx.directory)
        elif suite_status == SuiteStatus.AMBER:
            self._logger.info("DECISION directory=%s -> AMBER", ctx.directory)
            self._logger.info("NEXT directory=%s -> Fetch & parse report (Phase 2).", ctx.directory)

            # Phase 2: fetch and parse the HTML report into structured failures.
            self._phase(ctx, "PHASE_2_REPORT_PARSE", "start")
            try:
                ctx.report_call_count += 1
                raw_html = await self._staf.report_html(ctx.directory)
                ctx.parsed_report = self._report_parser.parse_html(raw_html=raw_html, directory=ctx.directory)
                ctx.report_location = (
                    f"{self._staf.base_url}/automation/v1/stafReport?directory={ctx.directory}"
                )
                ctx.log_iteration(
                    SuiteStatus.AMBER,
                    f"Parsed report: failed={ctx.parsed_report.failed} total={ctx.parsed_report.total_flows}",
                )
                self._logger.info(
                    "Report parsed directory=%s failed=%s total=%s report_calls=%s",
                    ctx.directory,
                    ctx.parsed_report.failed,
                    ctx.parsed_report.total_flows,
                    ctx.report_call_count,
                )
            except Exception as e:
                ctx.parsed_report = None
                ctx.log_iteration(SuiteStatus.ERROR, f"Report fetch/parse failed: {e}")
                self._logger.error("Report fetch/parse failed directory=%s: %s", ctx.directory, e)
            self._phase(ctx, "PHASE_2_REPORT_PARSE", "complete")

            if not ctx.parsed_report:
                ctx.outcome = RunOutcome.MANUAL_INTERVENTION
            else:
                # Phase 3: AI triage (classification + aggregate)
                self._phase(ctx, "PHASE_3_AI_TRIAGE", "start")
                preliminary = build_preliminary_report(
                    parsed_report=ctx.parsed_report, report_location=ctx.report_location
                )
                ctx.analysis_result = self._ai_agent.analyze_preliminary_report(preliminary)
                self._logger.info(
                    "AI analysis complete directory=%s aggregate=%s intermittent=%s actual=%s",
                    ctx.directory,
                    ctx.analysis_result.aggregate.value,
                    ctx.analysis_result.intermittent_count,
                    ctx.analysis_result.actual_count,
                )
                self._phase(ctx, "PHASE_3_AI_TRIAGE", "complete")

                # Phase 4: retrigger intermittents even when BOTH (confirmation)
                if ctx.analysis_result and ctx.analysis_result.intermittent_flow_tags:
                    ctx.retrigger_flow_tags = list(ctx.analysis_result.intermittent_flow_tags)
                    if ctx.can_retry():
                        ctx.increment_retry()
                        self._phase(ctx, "PHASE_4_RETRIGGER", "start")
                        try:
                            retrigger_input = replace(ctx.suite_input, flows=ctx.retrigger_flow_tags)
                            retrigger_dir = await self._staf.activate(retrigger_input)
                            ctx.retrigger_attempts.append(
                                {
                                    "attempt": ctx.retry_count,
                                    "directory": retrigger_dir,
                                    "flow_tags": list(ctx.retrigger_flow_tags),
                                }
                            )
                            retrigger_status = await self._poll_directory_until_complete(ctx, retrigger_dir)
                            retrigger_suite_status = retrigger_status.suite_status

                            retrigger_failed_unique: list[str] = []
                            if retrigger_suite_status == SuiteStatus.AMBER:
                                ctx.report_call_count += 1
                                raw_html2 = await self._staf.report_html(retrigger_dir)
                                parsed2 = self._report_parser.parse_html(
                                    raw_html=raw_html2, directory=retrigger_dir
                                )
                                prelim2 = build_preliminary_report(
                                    parsed_report=parsed2,
                                    report_location=f"{self._staf.base_url}/automation/v1/stafReport?directory={retrigger_dir}",
                                )
                                retrigger_failed_unique = [
                                    x.get("uniqueFlowTag")
                                    for x in prelim2
                                    if isinstance(x, dict) and x.get("uniqueFlowTag")
                                ]

                            ctx.analysis_result = confirm_intermittent_after_retrigger(
                                ctx.analysis_result, retrigger_failed_unique_tags=retrigger_failed_unique
                            )
                            ctx.retrigger_attempts[-1].update(
                                {
                                    "suite_status": retrigger_suite_status.value,
                                    "passedTests": retrigger_status.passed_tests,
                                    "failedTests": retrigger_status.failed_tests,
                                    "confirmed": list(ctx.analysis_result.confirmed_intermittent_flow_tags),
                                    "refuted": list(ctx.analysis_result.refuted_intermittent_flow_tags),
                                }
                            )
                            self._phase(ctx, "PHASE_4_RETRIGGER", "complete", directory=retrigger_dir)
                        except Exception as e:
                            ctx.log_iteration(SuiteStatus.ERROR, f"Retrigger failed: {e}")
                            self._logger.error("Retrigger failed directory=%s: %s", ctx.directory, e)
                            self._phase(ctx, "PHASE_4_RETRIGGER", "complete")
                    else:
                        ctx.log_iteration(
                            SuiteStatus.AMBER,
                            "Retrigger skipped: max retries exhausted.",
                        )

                # Decide final outcome based on (possibly updated) aggregate.
                if not ctx.analysis_result:
                    ctx.outcome = RunOutcome.MANUAL_INTERVENTION
                elif ctx.analysis_result.aggregate == AggregateResult.ALL_ACTUAL:
                    ctx.outcome = RunOutcome.ACTUAL_FAILURES
                elif ctx.analysis_result.aggregate == AggregateResult.BOTH:
                    ctx.outcome = RunOutcome.MIXED_FAILURES
                else:
                    # ALL_INTERMITTENT
                    ctx.outcome = (
                        RunOutcome.RETRIGGER_SUCCESS
                        if ctx.analysis_result.confirmed_intermittent_flow_tags
                        else RunOutcome.MANUAL_INTERVENTION
                    )
        else:
            ctx.outcome = RunOutcome.MANUAL_INTERVENTION

            ctx.completed_at = datetime.now()
            self._storage.update_run(run_id, ctx)
            self._logger.info(
                "Polling complete directory=%s suite_status=%s outcome=%s",
                ctx.directory,
                suite_status.value,
                ctx.outcome,
            )
            return

        # Timeout
        ctx = self._storage.get_run(run_id) or ctx
        ctx.outcome = RunOutcome.MANUAL_INTERVENTION
        ctx.completed_at = datetime.now()
        ctx.log_iteration(SuiteStatus.ERROR, "Polling timed out")
        self._storage.update_run(run_id, ctx)
        self._logger.error("Polling timed out directory=%s", getattr(ctx, "directory", None))

    async def run_main_flow(self, run_id: str) -> None:
        """Convenience wrapper: activate → poll."""
        await self.activate_run(run_id)
        await self.poll_run(run_id)

