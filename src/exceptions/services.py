"""Service-related exceptions."""

from .base import TriageException


class AnalysisError(TriageException):
    """Raised when analysis fails."""

    pass


class AIAgentError(TriageException):
    """Raised when AI agent operation fails."""

    pass


class StorageError(TriageException):
    """Raised when storage operation fails."""

    pass


class OrchestrationError(TriageException):
    """Raised when test orchestration fails."""

    pass
