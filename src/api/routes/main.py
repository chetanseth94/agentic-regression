"""Main API routes — entry points for the Main Flow."""

from fastapi import APIRouter, BackgroundTasks

from ..schemas import (
    ExecutionRequest,
    ExecutionResponse,
    StatusResponse,
    EndFlowReport,
)

router = APIRouter()


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
    # TODO: implement
    # run_id = orchestrator.start_run(request)
    # background_tasks.add_task(orchestrator.run_main_flow, run_id)
    pass


@router.get("/runs/{run_id}", response_model=EndFlowReport)
async def get_run_status(run_id: str):
    """
    Get the current status / final report of a run.
    Poll this endpoint until outcome is set.
    """
    # TODO: implement
    # return storage.get_run_report(run_id)
    pass


@router.get("/runs/{run_id}/status", response_model=StatusResponse)
async def get_execution_status(run_id: str):
    """Get current execution status (GREEN/AMBER/RUNNING)."""
    # TODO: implement
    pass


@router.get("/runs")
async def list_runs():
    """List all runs with their outcomes."""
    # TODO: implement
    pass
