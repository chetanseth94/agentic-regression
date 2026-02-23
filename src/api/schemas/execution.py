"""Execution request/response schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class ExecutionRequest(BaseModel):
    """Request to trigger a suite execution (Main Flow input)."""

    suite_tag: str = Field(..., description="Suite tag to execute")
    num_threads: int = Field(default=1, ge=1, description="Number of parallel threads")
    env_type: str = Field(default="staging", description="Environment type")
    max_retries: int = Field(default=3, ge=0, description="Max retrigger attempts for intermittent failures")
    additional_params: dict = Field(default_factory=dict, description="Additional parameters for the suite")


class ExecutionResponse(BaseModel):
    """Response after triggering a suite execution."""

    run_id: str
    directory: str
    status: str  # RUNNING, GREEN, AMBER, ERROR
    message: str


class StatusResponse(BaseModel):
    """Execution status polling response."""

    directory: str
    completed: bool
    failed_flow_count: int
    total_flow_count: int
    passed_flow_count: int
    suite_status: str  # GREEN, AMBER, RUNNING
