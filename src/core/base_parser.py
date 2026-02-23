"""Base parser interface for extensibility."""

from abc import ABC, abstractmethod
from ..models.report import HTMLReport


class BaseReportParser(ABC):
    """Abstract base class for report parsers."""

    @abstractmethod
    def parse(self, raw_html: str, directory: str) -> HTMLReport:
        """
        Parse HTML report content into structured data.

        Args:
            raw_html: Raw HTML string from stafReport API
            directory: Execution directory path

        Returns:
            HTMLReport with parsed flow results

        Raises:
            ParserError: If parsing fails
        """
        pass

    def validate(self, raw_html: str) -> bool:
        """Validate that content looks like a valid HTML report."""
        if not raw_html or len(raw_html.strip()) == 0:
            return False
        return "<" in raw_html and "</" in raw_html
