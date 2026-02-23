"""Data models for the application."""

from .failure import FailureDetails, APIDetails, FailureClassification
from .report import HTMLReport, FlowResult, FlowStatus
from .suite import (
    SuiteInput,
    SuiteStatus,
    ExecutionStatus,
    AggregateResult,
    AnalysisResult,
    RunOutcome,
    RunContext,
)

__all__ = [
    # Failure
    "FailureDetails",
    "APIDetails",
    "FailureClassification",
    # Report
    "HTMLReport",
    "FlowResult",
    "FlowStatus",
    # Suite
    "SuiteInput",
    "SuiteStatus",
    "ExecutionStatus",
    "AggregateResult",
    "AnalysisResult",
    "RunOutcome",
    "RunContext",
]
