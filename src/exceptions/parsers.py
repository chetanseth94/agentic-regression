"""Parser-related exceptions."""

from .base import TriageException


class ParserError(TriageException):
    """Base exception for parser errors."""

    pass


class InvalidReportError(ParserError):
    """Raised when report format is invalid."""

    def __init__(self, format_type: str, reason: str = None):
        message = f"Invalid {format_type} report format"
        if reason:
            message += f": {reason}"
        super().__init__(message, {"format": format_type, "reason": reason})


class UnsupportedFormatError(ParserError):
    """Raised when report format is not supported."""

    def __init__(self, format_type: str):
        message = f"Unsupported report format: {format_type}"
        super().__init__(message, {"format": format_type})
