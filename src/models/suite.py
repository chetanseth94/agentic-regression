"""Suite execution data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SuiteStatus(str, Enum):
    """Suite execution status based on monitoring."""

    GREEN = "GREEN"  # flowCompleted=true, failedTests=0
    AMBER = "AMBER"  # flowCompleted=true, failedTests!=0
    RUNNING = "RUNNING"  # flowCompleted=false
    ERROR = "ERROR"  # unexpected error during execution / invalid directory


class AggregateResult(str, Enum):
    """Aggregate classification after flow failure analysis."""

    ALL_INTERMITTENT = "ALL_INTERMITTENT"
    ALL_ACTUAL = "ALL_ACTUAL"
    BOTH = "BOTH"


class RunOutcome(str, Enum):
    """Final outcome of the entire run."""

    SUCCESS = "SUCCESS"                           # GREEN path
    ACTUAL_FAILURES = "ACTUAL_FAILURES"           # ALL_ACTUAL path
    MIXED_FAILURES = "MIXED_FAILURES"             # BOTH path
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"   # Retries exhausted
    RETRIGGER_SUCCESS = "RETRIGGER_SUCCESS"        # Retrigger passed on retry


@dataclass
class SuiteInput:
    """Input parameters for triggering a suite execution."""

    # Human-friendly label (can represent a suite grouping of many flows)
    suite_tag: str

    # STAF activate payload fields
    env_type: str = "OCP-SM"
    flows: list[str] = field(default_factory=list)  # up to ~100 flow tags (e.g., "@Lean_Buy_solution2")
    number_of_threads: int = 1
    automation_base_url: Optional[str] = None  # per-run override for STAF runtime base URL
    ssl_verify: Optional[bool] = None
    ca_bundle_path: Optional[str] = None

    additional_params: dict = field(default_factory=dict)

    def to_api_payload(self) -> dict:
        """Convert to payload for /automation/v1/activateFlowJobStaf."""
        payload = {
            "envType": self.env_type,
            "flows": [{"name": name} for name in self.flows],
            "numberOfThreads": str(self.number_of_threads),
        }
        payload.update(self.additional_params)
        return payload


@dataclass
class ExecutionStatus:
    """Status response from /automation/v1/status."""

    directory: str
    passed_tests: Optional[int] = None
    skipped_tests: Optional[int] = None
    failed_tests: Optional[int] = None
    flow_completed: Optional[bool] = None

    @property
    def is_invalid_directory(self) -> bool:
        """True when API returns null fields for an unknown directory."""
        return (
            self.passed_tests is None
            and self.skipped_tests is None
            and self.failed_tests is None
            and self.flow_completed is None
        )

    @property
    def total_tests(self) -> Optional[int]:
        if self.passed_tests is None or self.skipped_tests is None or self.failed_tests is None:
            return None
        return self.passed_tests + self.skipped_tests + self.failed_tests

    @property
    def suite_status(self) -> SuiteStatus:
        """Derive GREEN / AMBER / RUNNING status."""
        if (
            self.passed_tests is None
            or self.skipped_tests is None
            or self.failed_tests is None
            or self.flow_completed is None
        ):
            return SuiteStatus.ERROR

        if not self.flow_completed:
            return SuiteStatus.RUNNING

        if self.failed_tests == 0:
            return SuiteStatus.GREEN

        return SuiteStatus.AMBER


@dataclass
class AnalysisResult:
    """Output from Flow Failure Analysis (AI Agent)."""

    aggregate: AggregateResult
    intermittent_flow_tags: list[str] = field(default_factory=list)
    actual_failures: list[dict] = field(default_factory=list)
    # Each actual_failure dict contains:
    #   flow_tag, rca, stack_trace, relevant_log_lines, fix_suggestion

    @property
    def intermittent_count(self) -> int:
        return len(self.intermittent_flow_tags)

    @property
    def actual_count(self) -> int:
        return len(self.actual_failures)


@dataclass
class RunContext:
    """Tracks the full state of a run through the main flow."""

    suite_input: SuiteInput
    directory: Optional[str] = None
    execution_status: Optional[ExecutionStatus] = None
    html_report: Optional[str] = None
    analysis_result: Optional[AnalysisResult] = None
    outcome: Optional[RunOutcome] = None
    retry_count: int = 0
    max_retries: int = 3
    retrigger_flow_tags: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)  # Log of each iteration
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Observability counters (Phase 1+)
    status_call_count: int = 0
    report_call_count: int = 0
    status_ready_seen: bool = False
    status_ready_call_count: int = 0

    def can_retry(self) -> bool:
        """Check if retrigger is allowed."""
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry count."""
        self.retry_count += 1

    def log_iteration(self, status: SuiteStatus, detail: str) -> None:
        """Log an iteration in the run history."""
        self.history.append({
            "iteration": self.retry_count,
            "status": status.value,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        })
