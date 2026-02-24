"""Client for STAF-compatible automation APIs."""

from __future__ import annotations

from typing import Any, Optional, Union

import httpx

from ..config import get_settings
from ..exceptions import ServiceUnavailableError, ValidationError
from ..models.suite import ExecutionStatus, SuiteInput


class StafClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        ssl_verify: Optional[bool] = None,
        ca_bundle_path: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.automation_api_base_url).rstrip("/")
        self._activate_path = settings.automation_activate_path
        self._status_path = settings.automation_status_path
        self._report_path = settings.automation_report_path
        self._timeout = settings.automation_api_timeout
        self._ssl_verify = settings.automation_ssl_verify if ssl_verify is None else ssl_verify
        self._ca_bundle_path = ca_bundle_path or settings.automation_ca_bundle_path

    def _verify_param(self) -> Union[bool, str]:
        # httpx accepts `verify` as bool or a path to CA bundle.
        if self._ca_bundle_path:
            return self._ca_bundle_path
        return bool(self._ssl_verify)

    @property
    def base_url(self) -> str:
        return self._base_url

    async def activate(self, suite_input: SuiteInput) -> str:
        """Trigger suite/flows execution and return the directory/path."""
        url = f"{self._base_url}{self._activate_path}"
        payload = suite_input.to_api_payload()

        async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify_param()) as client:
            try:
                resp = await client.post(url, json=payload)
            except httpx.RequestError as e:
                raise ServiceUnavailableError("staf-activate", str(e)) from e

        if resp.status_code // 100 != 2:
            raise ServiceUnavailableError(
                "staf-activate",
                f"Non-2xx from activate: {resp.status_code} {resp.text[:500]}",
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise ValidationError(f"activate returned non-JSON response: {resp.text[:500]}") from e

        directory = data.get("path")
        if not directory or not isinstance(directory, str):
            raise ValidationError(f"activate response missing 'path': {data}")

        return directory

    async def status(self, directory: str) -> ExecutionStatus:
        """Fetch execution status and normalize to ExecutionStatus."""
        if not directory or not isinstance(directory, str):
            raise ValidationError("directory is required")

        url = f"{self._base_url}{self._status_path}"
        params = {"directory": directory}

        async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify_param()) as client:
            try:
                resp = await client.get(url, params=params)
            except httpx.RequestError as e:
                raise ServiceUnavailableError("staf-status", str(e)) from e

        if resp.status_code // 100 != 2:
            raise ServiceUnavailableError(
                "staf-status",
                f"Non-2xx from status: {resp.status_code} {resp.text[:500]}",
            )

        try:
            data: dict[str, Any] = resp.json()
        except ValueError as e:
            raise ValidationError(f"status returned non-JSON response: {resp.text[:500]}") from e

        # API guarantees fields exist, but they may be null for invalid directory
        passed_raw = data.get("passedTests")
        skipped_raw = data.get("skippedTests")
        failed_raw = data.get("failedTests")
        completed_raw = data.get("flowCompleted")

        # Invalid directory: all null
        if passed_raw is None and skipped_raw is None and failed_raw is None and completed_raw is None:
            return ExecutionStatus(directory=directory)

        def parse_int(value: Any, field_name: str) -> int:
            if not isinstance(value, str):
                raise ValidationError(f"status field {field_name} expected string, got {type(value)}")
            try:
                return int(value)
            except ValueError as e:
                raise ValidationError(f"status field {field_name} not an int string: {value!r}") from e

        def parse_bool(value: Any, field_name: str) -> bool:
            if not isinstance(value, str):
                raise ValidationError(f"status field {field_name} expected string, got {type(value)}")
            if value == "true":
                return True
            if value == "false":
                return False
            raise ValidationError(f"status field {field_name} not 'true'/'false': {value!r}")

        return ExecutionStatus(
            directory=directory,
            passed_tests=parse_int(passed_raw, "passedTests"),
            skipped_tests=parse_int(skipped_raw, "skippedTests"),
            failed_tests=parse_int(failed_raw, "failedTests"),
            flow_completed=parse_bool(completed_raw, "flowCompleted"),
        )

    async def report_html(self, directory: str) -> str:
        """Fetch raw HTML report for a given directory."""
        if not directory or not isinstance(directory, str):
            raise ValidationError("directory is required")

        url = f"{self._base_url}{self._report_path}"
        params = {"directory": directory}

        async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify_param()) as client:
            try:
                resp = await client.get(url, params=params)
            except httpx.RequestError as e:
                raise ServiceUnavailableError("staf-report", str(e)) from e

        if resp.status_code // 100 != 2:
            raise ServiceUnavailableError(
                "staf-report",
                f"Non-2xx from report: {resp.status_code} {resp.text[:500]}",
            )

        return resp.text

