"""Report parsing service."""

from __future__ import annotations

from ..core.base_parser import BaseReportParser
from ..models.report import HTMLReport
from ..parsers.extent_spark_bdd_parser import ExtentSparkBddReportParser


class ReportParser:
    """Selects and runs the appropriate report parser."""

    def __init__(self, parser: BaseReportParser | None = None) -> None:
        self._parser = parser or ExtentSparkBddReportParser()

    def parse_html(self, raw_html: str, directory: str) -> HTMLReport:
        return self._parser.parse(raw_html=raw_html, directory=directory)

