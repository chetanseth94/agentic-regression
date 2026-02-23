"""Validation utilities."""

import re
from typing import Optional

from ..exceptions import ValidationError


def validate_execution_id(execution_id: str) -> None:
    """
    Validate execution ID format.

    Args:
        execution_id: Execution ID to validate

    Raises:
        ValidationError: If execution ID is invalid
    """
    if not execution_id or not isinstance(execution_id, str):
        raise ValidationError("Execution ID is required and must be a string")

    if len(execution_id.strip()) == 0:
        raise ValidationError("Execution ID cannot be empty")

    # Basic format validation (alphanumeric, hyphens, underscores)
    if not re.match(r"^[a-zA-Z0-9_-]+$", execution_id):
        raise ValidationError(
            "Execution ID can only contain alphanumeric characters, hyphens, and underscores"
        )


def validate_report_format(content: str, format_type: str) -> None:
    """
    Validate report content format.

    Args:
        content: Report content to validate
        format_type: Expected format (html, xml, json)

    Raises:
        ValidationError: If content doesn't match expected format
    """
    if not content or len(content.strip()) == 0:
        raise ValidationError("Report content cannot be empty")

    format_type = format_type.lower()

    if format_type == "html":
        # Basic HTML validation
        if not content.strip().startswith("<") and "</" not in content:
            raise ValidationError("Content does not appear to be valid HTML")

    elif format_type == "xml":
        # Basic XML validation
        if not content.strip().startswith("<") or "<?xml" not in content[:100]:
            raise ValidationError("Content does not appear to be valid XML")

    elif format_type == "json":
        # Basic JSON validation
        content_stripped = content.strip()
        if not (
            content_stripped.startswith("{") or content_stripped.startswith("[")
        ):
            raise ValidationError("Content does not appear to be valid JSON")

    else:
        raise ValidationError(f"Unsupported format type: {format_type}")
