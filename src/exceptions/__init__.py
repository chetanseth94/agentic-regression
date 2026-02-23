"""Custom exceptions for the application."""

from .base import (
    TriageException,
    ConfigurationError,
    ValidationError,
    ServiceUnavailableError,
)
from .parsers import ParserError, InvalidReportError, UnsupportedFormatError
from .services import (
    AnalysisError,
    AIAgentError,
    StorageError,
    OrchestrationError,
)

__all__ = [
    "TriageException",
    "ConfigurationError",
    "ValidationError",
    "ServiceUnavailableError",
    "ParserError",
    "InvalidReportError",
    "UnsupportedFormatError",
    "AnalysisError",
    "AIAgentError",
    "StorageError",
    "OrchestrationError",
]
