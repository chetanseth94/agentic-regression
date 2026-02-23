"""Failure data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class FailureClassification(str, Enum):
    """Failure classification types."""

    INTERMITTENT = "INTERMITTENT"
    ACTUAL_ISSUE = "ACTUAL_ISSUE"
    UNKNOWN = "UNKNOWN"


@dataclass
class APIDetails:
    """Structure for API failure details."""

    endpoint: str
    method: str  # GET, POST, PUT, DELETE, etc.
    status_code: Optional[int] = None
    request_body: Optional[dict] = None
    response: Optional[str] = None
    headers: Optional[dict[str, str]] = None


@dataclass
class FailureDetails:
    """Structure for individual flow failure information."""

    flow_tag: str
    failed_steps: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    trace: Optional[str] = None
    api_details: Optional[APIDetails] = None
    timestamp: Optional[datetime] = None
    screenshot_path: Optional[str] = None
    log_file_path: Optional[str] = None
    execution_id: Optional[str] = None

    # Analysis results (populated by AI Agent)
    classification: Optional[FailureClassification] = None
    classification_reasoning: Optional[str] = None
    confidence: Optional[float] = None  # 0.0 to 1.0
    rca: Optional[str] = None  # Root cause analysis
    relevant_log_lines: list[str] = field(default_factory=list)
    fix_suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert failure details to dictionary format."""
        result = {
            "flow_tag": self.flow_tag,
            "failed_steps": self.failed_steps,
            "error_message": self.error_message,
            "trace": self.trace,
            "screenshot_path": self.screenshot_path,
            "log_file_path": self.log_file_path,
            "execution_id": self.execution_id,
            "classification": self.classification.value if self.classification else None,
            "classification_reasoning": self.classification_reasoning,
            "confidence": self.confidence,
            "rca": self.rca,
            "relevant_log_lines": self.relevant_log_lines,
            "fix_suggestion": self.fix_suggestion,
        }

        if self.timestamp:
            result["timestamp"] = self.timestamp.isoformat()

        if self.api_details:
            result["api_details"] = {
                "endpoint": self.api_details.endpoint,
                "method": self.api_details.method,
                "status_code": self.api_details.status_code,
                "request_body": self.api_details.request_body,
                "response": self.api_details.response,
                "headers": self.api_details.headers,
            }

        return result

    def to_rca_summary(self) -> dict:
        """Get RCA summary for actual issues."""
        return {
            "flow_tag": self.flow_tag,
            "rca": self.rca,
            "stack_trace": self.trace,
            "relevant_log_lines": self.relevant_log_lines,
            "fix_suggestion": self.fix_suggestion,
        }
