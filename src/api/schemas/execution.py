"""Execution request/response schemas."""

from typing import Any, Optional

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class FlowRef(BaseModel):
    """Single flow reference for STAF activate API."""

    name: str = Field(..., description="Flow tag/name (e.g., @Lean_Buy_solution2)")


class ExecutionRequest(BaseModel):
    """Request to trigger a suite execution (Main Flow input)."""

    # Allow passing through additional STAF fields without schema changes.
    # Any unknown fields will be forwarded to STAF activate payload.
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    # Human-friendly label for this run. If `flows` is omitted, `suite_tag` is treated as a single flow tag.
    suite_tag: Optional[str] = Field(
        default=None,
        description="Optional suite label (used for reporting). If omitted, derived from flows.",
    )

    # Preferred key for CLI/file-driven runs: a single suite/flow tag.
    suite_name: Optional[str] = Field(
        default=None,
        alias="suite_name",
        description="Suite/flow tag to execute (e.g., @BVT_Buy_sol2). Used when flows[] is omitted.",
    )

    # Optional per-run STAF base URL override (useful when running across environments).
    env_details: Optional[str] = Field(
        default=None,
        alias="envDetails",
        description="STAF runtime base URL override for this run.",
    )

    ssl_verify: Optional[bool] = Field(
        default=None,
        alias="sslVerify",
        description="TLS verify override for this run (true/false). Prefer providing a CA bundle instead.",
    )
    ca_bundle_path: Optional[str] = Field(
        default=None,
        alias="caBundlePath",
        description="Path to a CA bundle PEM file to trust for this run.",
    )

    # STAF activate payload-compatible fields (aliases allow STAF-style naming)
    env_type: str = Field(default="OCP-SM", alias="envType", description="Environment type")
    flows: list[FlowRef] = Field(
        default_factory=list,
        description="Flows to execute (up to ~100). If empty, will use suite_name (or suite_tag) as a single flow.",
    )
    num_threads: Any = Field(
        default="1",
        alias="numberOfThreads",
        description='Number of parallel threads. STAF expects a string (e.g., "10").',
    )

    max_retries: int = Field(default=3, ge=0, description="Max retrigger attempts for intermittent failures")
    additional_params: dict = Field(
        default_factory=dict,
        description="Additional parameters for the suite (merged into STAF activate payload).",
    )


class ExecutionResponse(BaseModel):
    """Response after triggering a suite execution."""

    run_id: str
    directory: str
    status: str  # RUNNING, GREEN, AMBER, ERROR
    message: str


class StatusResponse(BaseModel):
    """Execution status polling response."""

    directory: str
    passed_tests: Optional[int] = None
    skipped_tests: Optional[int] = None
    failed_tests: Optional[int] = None
    flow_completed: Optional[bool] = None
    total_tests: Optional[int] = None
    suite_status: str  # GREEN, AMBER, RUNNING
