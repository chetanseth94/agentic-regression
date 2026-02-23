"""Base exception classes."""

from typing import Optional


class TriageException(Exception):
    """Base exception for all triage-related errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(TriageException):
    """Raised when there's a configuration error."""

    pass


class ValidationError(TriageException):
    """Raised when validation fails."""

    pass


class ServiceUnavailableError(TriageException):
    """Raised when an external service is unavailable."""

    def __init__(self, service_name: str, message: str = None):
        msg = message or f"Service '{service_name}' is currently unavailable"
        super().__init__(msg, {"service": service_name})
