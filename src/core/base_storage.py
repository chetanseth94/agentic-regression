"""Base storage interface for extensibility."""

from abc import ABC, abstractmethod
from typing import Any, Optional
from ..models.failure import FailureDetails
from ..models.suite import RunContext


class BaseStorage(ABC):
    """Abstract base class for storage backends."""

    # Failure storage
    @abstractmethod
    def store_failure(self, failure: FailureDetails, directory: str) -> str:
        """Store a failure and return its ID."""
        pass

    @abstractmethod
    def get_failure(self, failure_id: str) -> Optional[FailureDetails]:
        """Retrieve a failure by ID."""
        pass

    @abstractmethod
    def get_failures_by_flow_tags(
        self, flow_tags: list[str], limit: int = 10
    ) -> list[FailureDetails]:
        """Get past failures matching flow tags."""
        pass

    # Run context storage
    @abstractmethod
    def store_run(self, run_context: RunContext) -> str:
        """Store a run context and return its ID."""
        pass

    @abstractmethod
    def get_run(self, run_id: str) -> Optional[RunContext]:
        """Retrieve a run context by ID."""
        pass

    @abstractmethod
    def update_run(self, run_id: str, run_context: RunContext) -> None:
        """Update a run context."""
        pass

    # Analysis results
    @abstractmethod
    def store_analysis_result(self, directory: str, result: dict[str, Any]) -> str:
        """Store analysis result."""
        pass

    @abstractmethod
    def get_analysis_result(self, analysis_id: str) -> Optional[dict[str, Any]]:
        """Retrieve analysis result by ID."""
        pass
