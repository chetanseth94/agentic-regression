"""Test report data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class FlowStatus(str, Enum):
    """Individual flow execution status."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass
class FlowResult:
    """Individual flow result from the HTML report."""

    flow_tag: str
    flow_name: str
    status: FlowStatus
    duration: Optional[float] = None  # seconds
    error_message: Optional[str] = None
    trace: Optional[str] = None
    timestamp: Optional[datetime] = None
    steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    screenshot_path: Optional[str] = None


@dataclass
class HTMLReport:
    """Parsed HTML report from /automation/v1/stafReport."""

    directory: str
    raw_html: str = ""
    total_flows: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[float] = None  # seconds
    flow_results: list[FlowResult] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def failed_flows(self) -> list[FlowResult]:
        """Get all failed flows."""
        return [
            flow
            for flow in self.flow_results
            if flow.status in [FlowStatus.FAILED, FlowStatus.ERROR]
        ]

    @property
    def passed_flows(self) -> list[FlowResult]:
        """Get all passed flows."""
        return [flow for flow in self.flow_results if flow.status == FlowStatus.PASSED]

    @property
    def failed_flow_tags(self) -> list[str]:
        """Get flow tags of all failed flows."""
        return [flow.flow_tag for flow in self.failed_flows]

    def has_failures(self) -> bool:
        """Check if report has any failures."""
        return self.failed > 0
