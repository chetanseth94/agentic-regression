"""Core abstractions and base classes."""

from .base_parser import BaseReportParser
from .base_client import BaseClient
from .base_storage import BaseStorage

__all__ = ["BaseReportParser", "BaseClient", "BaseStorage"]
