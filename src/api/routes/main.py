"""Main API routes — entry points for the Main Flow."""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..schemas import (
    ExecutionRequest,
    ExecutionResponse,
    StatusResponse,
    EndFlowReport,
)

from ...exceptions import OrchestrationError, ServiceUnavailableError, ValidationError
from ...models.suite import RunOutcome, SuiteInput
from ...services import InMemoryStorage, Orchestrator, StafClient

router = APIRouter()

_storage = InMemoryStorage()
_staf = StafClient()
_orchestrator = Orchestrator(storage=_storage, staf=_staf)


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@router.post("/execute", response_model=ExecutionResponse)
async def execute_suite(request: ExecutionRequest, background_tasks: BackgroundTasks):
    """
    Main Flow entry point.

    Triggers suite execution and starts the full triage flow:
    1. Call activateFlowJobStaf
    2. Poll status (GREEN/AMBER/RUNNING)
    3. GREEN → success, AMBER → analysis → handle result
    4. Handle INTERMITTENT / ACTUAL / BOTH

    Returns immediately with run_id; poll /runs/{run_id} for results.
    """
    flows = [f.name for f in request.flows] if request.flows else []
    if not flows:
        # Backward compatibility: allow suite_tag to be used as a single flow tag.
        fallback = request.suite_name or request.suite_tag
        if not fallback:
            raise HTTPException(status_code=422, detail="Either 'flows' or 'suite_tag' must be provided")
        flows = [fallback]

    # Forward all extra fields (extra="allow") + additional_params into the STAF activate payload.
    extra_payload = dict(getattr(request, "model_extra", {}) or {})
    additional_params = dict(request.additional_params or {})
    additional_params.update(extra_payload)

    suite_tag = request.suite_tag or request.suite_name or (
        flows[0] if len(flows) == 1 else f"{len(flows)}_flows"
    )

    # Normalize numberOfThreads to int for internal bookkeeping (sent as string to STAF).
    try:
        num_threads_int = int(request.num_threads)
    except Exception:
        num_threads_int = 1

    suite_input = SuiteInput(
        suite_tag=suite_tag,
        env_type=request.env_type,
        flows=flows,
        number_of_threads=num_threads_int,
        automation_base_url=request.env_details,
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        additional_params=additional_params,
    )

    # Use a per-request STAF client if envDetails is supplied.
    staf = StafClient(
        base_url=suite_input.automation_base_url,
        ssl_verify=suite_input.ssl_verify,
        ca_bundle_path=suite_input.ca_bundle_path,
    )
    orchestrator = Orchestrator(storage=_storage, staf=staf)

    run_id = orchestrator.start_run(suite_input=suite_input, max_retries=request.max_retries)

    # Activate synchronously so we can return directory immediately.
    try:
        directory = await orchestrator.activate_run(run_id)
    except (ServiceUnavailableError, ValidationError, OrchestrationError) as e:
        # Provide actionable error rather than generic 500.
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error during activate: {e}") from e

    # Poll in background.
    background_tasks.add_task(orchestrator.poll_run, run_id)

    return ExecutionResponse(
        run_id=run_id,
        directory=directory,
        status="RUNNING",
        message="Execution started; polling in background",
    )


@router.get("/runs/{run_id}", response_model=EndFlowReport)
async def get_run_status(run_id: str):
    """
    Get the current status / final report of a run.
    Poll this endpoint until outcome is set.
    """
    ctx = _storage.get_run(run_id)
    if not ctx:
        return EndFlowReport(
            run_id=run_id,
            suite_tag="",
            outcome="NOT_FOUND",
            suite_status="ERROR",
            message="run_id not found",
        )

    status = ctx.execution_status
    suite_status = status.suite_status.value if status else "RUNNING"

    outcome = ctx.outcome.value if ctx.outcome else "RUNNING"
    if ctx.outcome is None and suite_status in ("AMBER", "ERROR"):
        # Phase 1: AMBER analysis is not implemented yet.
        outcome = "PENDING_ANALYSIS"

    message = "Run is still executing"
    if ctx.outcome == RunOutcome.SUCCESS:
        message = "Suite run SUCCESS - all flows passed"
    elif suite_status == "AMBER":
        message = "Suite completed with failures (analysis not implemented in Phase 1)"
    elif suite_status == "ERROR":
        message = "Error while executing/monitoring suite"

    total = status.total_tests if status else 0
    passed = status.passed_tests if status and status.passed_tests is not None else 0
    failed = status.failed_tests if status and status.failed_tests is not None else 0

    return EndFlowReport(
        run_id=run_id,
        suite_tag=ctx.suite_input.suite_tag,
        outcome=outcome,
        suite_status=suite_status,
        total_flows=total,
        passed_flows=passed,
        failed_flows=failed,
        message=message,
        retry_count=ctx.retry_count,
        max_retries=ctx.max_retries,
        history=ctx.history,
    )


@router.get("/runs/{run_id}/status", response_model=StatusResponse)
async def get_execution_status(run_id: str):
    """Get current execution status (GREEN/AMBER/RUNNING)."""
    ctx = _storage.get_run(run_id)
    if not ctx:
        return StatusResponse(directory="", suite_status="ERROR")

    # If we have directory but no cached status yet, fetch one on-demand.
    if ctx.directory and ctx.execution_status is None:
        staf = StafClient(
            base_url=ctx.suite_input.automation_base_url,
            ssl_verify=ctx.suite_input.ssl_verify,
            ca_bundle_path=ctx.suite_input.ca_bundle_path,
        )
        status = await staf.status(ctx.directory)
        ctx.execution_status = status
        _storage.update_run(run_id, ctx)

    status = ctx.execution_status
    if not status:
        return StatusResponse(directory=ctx.directory or "", suite_status="RUNNING")

    return StatusResponse(
        directory=status.directory,
        passed_tests=status.passed_tests,
        skipped_tests=status.skipped_tests,
        failed_tests=status.failed_tests,
        flow_completed=status.flow_completed,
        total_tests=status.total_tests,
        suite_status=status.suite_status.value,
    )


@router.get("/runs")
async def list_runs():
    """List all runs with their outcomes."""
    runs = []
    for run_id, ctx in _storage.list_runs():
        status = ctx.execution_status
        runs.append(
            {
                "run_id": run_id,
                "suite_tag": ctx.suite_input.suite_tag,
                "directory": ctx.directory,
                "suite_status": status.suite_status.value if status else "RUNNING",
                "outcome": ctx.outcome.value if ctx.outcome else None,
                "started_at": ctx.started_at.isoformat() if ctx.started_at else None,
                "completed_at": ctx.completed_at.isoformat() if ctx.completed_at else None,
            }
        )
    return {"runs": runs}
