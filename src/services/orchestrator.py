"""Main flow orchestration (Phase 1: GREEN path)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta

from ..config import get_settings
from ..exceptions import OrchestrationError
from ..models.suite import RunContext, RunOutcome, SuiteInput, SuiteStatus
from ..utils.logger import get_logger
from .staf_client import StafClient
from .storage import InMemoryStorage


class Orchestrator:
    def __init__(self, storage: InMemoryStorage, staf: StafClient) -> None:
        self._storage = storage
        self._staf = staf
        self._settings = get_settings()
        self._logger = get_logger("triage.orchestrator")

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
        return directory

    async def poll_run(self, run_id: str) -> None:
        """Step 2: poll status until completion (GREEN/AMBER) or timeout."""
        ctx = self._storage.get_run(run_id)
        if not ctx:
            raise OrchestrationError(f"Run not found: {run_id}")
        if not ctx.directory:
            raise OrchestrationError(f"Run missing directory (activate first): {run_id}")

        start_time = datetime.now()
        deadline = start_time + timedelta(seconds=self._settings.poll_max_wait_seconds)
        not_ready_deadline = start_time + timedelta(
            seconds=self._settings.directory_not_ready_max_wait_seconds
        )

        self._logger.info(
            "Polling start directory=%s poll_interval=%ss max_wait=%ss",
            ctx.directory,
            self._settings.poll_interval_seconds,
            self._settings.poll_max_wait_seconds,
        )
        while datetime.now() < deadline:
            ctx = self._storage.get_run(run_id)
            if not ctx or not ctx.directory:
                raise OrchestrationError(f"Run context missing during polling: {run_id}")

            try:
                ctx.status_call_count += 1
                status = await self._staf.status(ctx.directory)
            except Exception as e:
                ctx.execution_status = None
                ctx.outcome = RunOutcome.MANUAL_INTERVENTION
                ctx.completed_at = datetime.now()
                ctx.log_iteration(SuiteStatus.ERROR, f"Status fetch failed: {e}")
                self._storage.update_run(run_id, ctx)
                self._logger.error("Status fetch failed directory=%s: %s", ctx.directory, e)
                return

            # Immediately after activation STAF may return null fields for a short window.
            if status.is_invalid_directory and datetime.now() < not_ready_deadline:
                ctx.execution_status = None
                ctx.log_iteration(
                    SuiteStatus.RUNNING,
                    "Status not ready yet (directory not registered). Retrying soon...",
                )
                self._storage.update_run(run_id, ctx)
                self._logger.info(
                    "Status not ready yet directory=%s (retry in %ss)",
                    ctx.directory,
                    self._settings.directory_not_ready_poll_interval_seconds,
                )
                await asyncio.sleep(self._settings.directory_not_ready_poll_interval_seconds)
                continue

            # Status-ready marker (directory registered): passed=0 skipped=0 failed=0 completed=False
            if (
                not status.is_invalid_directory
                and status.passed_tests == 0
                and status.skipped_tests == 0
                and status.failed_tests == 0
                and status.flow_completed is False
            ):
                if not ctx.status_ready_seen:
                    ctx.status_ready_seen = True
                    ctx.log_iteration(SuiteStatus.RUNNING, "Status is ready (initial counters are zero).")
                ctx.status_ready_call_count += 1

            ctx.execution_status = status
            suite_status = status.suite_status

            detail = (
                f"passed={status.passed_tests} skipped={status.skipped_tests} "
                f"failed={status.failed_tests} completed={status.flow_completed}"
            )
            ctx.log_iteration(suite_status, detail)
            self._storage.update_run(run_id, ctx)
            self._logger.info(
                "Status directory=%s %s (status_calls=%s, report_calls=%s, status_ready_calls=%s)",
                ctx.directory,
                detail,
                ctx.status_call_count,
                ctx.report_call_count,
                ctx.status_ready_call_count,
            )

            if suite_status == SuiteStatus.RUNNING:
                self._logger.info(
                    "Sleeping %ss before next poll (directory=%s)",
                    self._settings.poll_interval_seconds,
                    ctx.directory,
                )
                await asyncio.sleep(self._settings.poll_interval_seconds)
                continue

            # Completion: decide GREEN vs AMBER and next steps.
            if suite_status == SuiteStatus.GREEN:
                ctx.outcome = RunOutcome.SUCCESS
                self._logger.info("DECISION directory=%s -> GREEN", ctx.directory)
                self._logger.info("NEXT directory=%s -> Regression PASSED. Exiting.", ctx.directory)
            else:
                if suite_status == SuiteStatus.AMBER:
                    self._logger.info("DECISION directory=%s -> AMBER", ctx.directory)
                    self._logger.info(
                        "NEXT directory=%s -> AMBER analysis not implemented yet (Phase 2 pending).",
                        ctx.directory,
                    )
                    # Phase 2 not implemented yet: don't fetch/store huge HTML report by default.
                    ctx.outcome = None
                else:
                    # ERROR
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

