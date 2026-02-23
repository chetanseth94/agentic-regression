"""Analysis response schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class ActualFailureDetail(BaseModel):
    """Detail for a single actual failure."""

    flow_tag: str
    rca: str
    stack_trace: Optional[str] = None
    relevant_log_lines: list[str] = Field(default_factory=list)
    fix_suggestion: Optional[str] = None


class AnalysisResponse(BaseModel):
    """Response from flow failure analysis."""

    aggregate_result: str  # ALL_INTERMITTENT, ALL_ACTUAL, BOTH
    intermittent_count: int = 0
    actual_count: int = 0
    intermittent_flow_tags: list[str] = Field(default_factory=list)
    actual_failures: list[ActualFailureDetail] = Field(default_factory=list)


class EndFlowReport(BaseModel):
    """Final presentable report at END FLOW."""

    run_id: str
    suite_tag: str
    outcome: str  # SUCCESS, ACTUAL_FAILURES, MIXED_FAILURES, MANUAL_INTERVENTION, RETRIGGER_SUCCESS
    suite_status: str  # GREEN, AMBER
    total_flows: int = 0
    passed_flows: int = 0
    failed_flows: int = 0

    # Populated based on outcome
    message: str = ""
    retry_count: int = 0
    max_retries: int = 3

    # Analysis detail (populated for AMBER paths)
    analysis: Optional[AnalysisResponse] = None

    # History of iterations
    history: list[dict] = Field(default_factory=list)
