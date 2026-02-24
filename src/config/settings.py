"""Application settings and configuration."""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Agentic Test Triage API"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # API
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    # Automation STAF API
    # Keep default sanitized; set AUTOMATION_API_BASE_URL in your local .env
    automation_api_base_url: str = "https://<your-staf-runtime-host>"
    automation_activate_path: str = "/automation/v1/activateFlowJobStaf"
    automation_status_path: str = "/automation/v1/status"
    automation_report_path: str = "/automation/v1/stafReport"
    automation_api_timeout: int = 300  # seconds
    automation_ssl_verify: bool = True
    automation_ca_bundle_path: Optional[str] = None  # path to corporate CA bundle (PEM)

    # Status Polling
    poll_interval_seconds: int = 60
    poll_max_wait_seconds: int = 1200  # 20 minutes max
    directory_not_ready_poll_interval_seconds: int = 5
    directory_not_ready_max_wait_seconds: int = 60  # allow STAF to register the directory

    # Anthropic Claude
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    anthropic_max_tokens: int = 4096

    # MCP (Model Context Protocol) - OCP Logs
    mcp_server_url: Optional[str] = None
    mcp_server_config: Optional[str] = None  # JSON string

    # Jira
    jira_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None

    # OCP (OpenShift)
    ocp_api_url: Optional[str] = None
    ocp_token: Optional[str] = None
    ocp_namespace: Optional[str] = None

    # Storage
    storage_type: str = "memory"  # memory, sqlite, postgres
    storage_path: Optional[str] = None

    # Retry Configuration
    max_retry_attempts: int = 3
    retry_delay_seconds: int = 5

    # Analysis Configuration
    log_filter_levels: list[str] = ["ERROR", "WARN", "FATAL"]
    log_max_lines: int = 1000
    enable_caching: bool = True
    cache_ttl_seconds: int = 300

    model_config = SettingsConfigDict(
        # Support a local, gitignored env file for org-specific configuration.
        env_file=(".env", "local/amdocs/.env", "local/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def activate_url(self) -> str:
        """Full URL for /automation/v1/activateFlowJobStaf."""
        return f"{self.automation_api_base_url}{self.automation_activate_path}"

    @property
    def status_url(self) -> str:
        """Full URL for /automation/v1/status."""
        return f"{self.automation_api_base_url}{self.automation_status_path}"

    @property
    def report_url(self) -> str:
        """Full URL for /automation/v1/stafReport."""
        return f"{self.automation_api_base_url}{self.automation_report_path}"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
