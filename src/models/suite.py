"""Suite execution data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SuiteStatus(str, Enum):
    """Suite execution status based on monitoring."""

    GREEN = "GREEN"       # completed=true, failed=0
    AMBER = "AMBER"       # completed=true, failed!=0
    RUNNING = "RUNNING"   # completed=false, still executing
    ERROR = "ERROR"       # unexpected error during execution


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

    suite_tag: str
    num_threads: int = 1
    env_type: str = "staging"
    additional_params: dict = field(default_factory=dict)

    def to_api_payload(self) -> dict:
        """Convert to payload for /automation/v1/activateFlowJobStaf."""
        payload = {
            "suiteTag": self.suite_tag,
            "threads": self.num_threads,
            "envType": self.env_type,
        }
        payload.update(self.additional_params)
        return payload


@dataclass
class ExecutionStatus:
    """Status response from /automation/v1/status."""

    directory: str
    completed: bool = False
    failed_flow_count: int = 0
    total_flow_count: int = 0
    passed_flow_count: int = 0

    @property
    def suite_status(self) -> SuiteStatus:
        """Derive GREEN / AMBER / RUNNING status."""
        if not self.completed:
            return SuiteStatus.RUNNING
        if self.failed_flow_count == 0:
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
