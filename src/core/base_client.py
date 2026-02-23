"""Base client interface for external services."""

from abc import ABC, abstractmethod
from typing import Any


class BaseClient(ABC):
    """Abstract base class for external service clients."""

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Return the name of the service."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the service is available."""
        pass

    def health_check(self) -> dict[str, Any]:
        """Perform health check on the service."""
        return {
            "service": self.service_name,
            "available": self.is_available(),
        }
