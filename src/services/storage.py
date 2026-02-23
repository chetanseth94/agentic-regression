"""In-memory storage backend (Phase 1)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional
from uuid import uuid4

from ..core.base_storage import BaseStorage
from ..exceptions import StorageError
from ..models.failure import FailureDetails
from ..models.suite import RunContext


class InMemoryStorage(BaseStorage):
    def __init__(self) -> None:
        self._runs: dict[str, RunContext] = {}
        self._failures: dict[str, FailureDetails] = {}
        self._analysis: dict[str, dict[str, Any]] = {}

    # Failure storage
    def store_failure(self, failure: FailureDetails, directory: str) -> str:
        try:
            failure_id = uuid4().hex
            self._failures[failure_id] = failure
            return failure_id
        except Exception as e:
            raise StorageError(f"Failed to store failure: {e}") from e

    def get_failure(self, failure_id: str) -> Optional[FailureDetails]:
        return self._failures.get(failure_id)

    def get_failures_by_flow_tags(self, flow_tags: list[str], limit: int = 10) -> list[FailureDetails]:
        # Phase 1: naive scan; optimized indexing can be added later.
        matches: list[FailureDetails] = []
        for f in self._failures.values():
            if f.flow_tag in flow_tags:
                matches.append(f)
            if len(matches) >= limit:
                break
        return matches

    # Run context storage
    def store_run(self, run_context: RunContext) -> str:
        try:
            run_id = uuid4().hex
            # store a copy to avoid outside mutation without update_run
            self._runs[run_id] = replace(run_context)
            return run_id
        except Exception as e:
            raise StorageError(f"Failed to store run: {e}") from e

    def get_run(self, run_id: str) -> Optional[RunContext]:
        rc = self._runs.get(run_id)
        return replace(rc) if rc else None

    def update_run(self, run_id: str, run_context: RunContext) -> None:
        if run_id not in self._runs:
            raise StorageError(f"Run not found: {run_id}")
        self._runs[run_id] = replace(run_context)

    def list_runs(self) -> list[tuple[str, RunContext]]:
        return [(run_id, replace(rc)) for run_id, rc in self._runs.items()]

    # Analysis results
    def store_analysis_result(self, directory: str, result: dict[str, Any]) -> str:
        analysis_id = uuid4().hex
        self._analysis[analysis_id] = result
        return analysis_id

    def get_analysis_result(self, analysis_id: str) -> Optional[dict[str, Any]]:
        return self._analysis.get(analysis_id)

