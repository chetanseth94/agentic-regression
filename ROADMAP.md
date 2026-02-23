## Agentic Test Execution & Triage — Implementation Roadmap

### Purpose
Build the complete “Agentic Test Execution and Triage System” described in `README.md` and `flowchart.md`: trigger regression suites via STAF, monitor execution, analyze failures via AI + logs, decide intermittent vs actual issues, optionally retrigger intermittent-only failures, and produce an END-FLOW report via API.

### Scope
- **In scope**
  - FastAPI backend implementing `/api/v1/*` endpoints.
  - STAF automation integration: activate, status polling, report fetch.
  - HTML report parsing into structured flow failures.
  - AI analysis (Anthropic) for intermittent vs actual classification and RCA/fix suggestions.
  - Optional integrations: OpenShift logs via MCP/OCP access; Jira linking/issue creation; persistence backends.
- **Out of scope (initially)**
  - Frontend/UI (unless later requested).
  - Production-grade multi-tenant authz (unless required).
  - Fully automated “self-healing” code changes (this system should suggest fixes, not apply them).

### Current baseline (repo reality)
- **Implemented**
  - App wiring: `src/main.py`
  - Settings: `src/config/settings.py`
  - Data models: `src/models/*`
  - END-FLOW formatting: `src/utils/presenter.py`
  - Exceptions + basic validators: `src/exceptions/*`, `src/utils/validators.py`
- **Not implemented / stubs**
  - API handlers: `src/api/routes/main.py` has TODOs
  - Base interfaces: `src/core/base_client.py`, `src/core/base_parser.py`, `src/core/base_storage.py` are abstract stubs
  - Services: `src/services/` has no concrete implementations
  - Tests: none (only empty package initializers)
  - `.env.example` referenced by README is missing

---

## Roadmap overview (phases)
The phases are ordered to deliver a working system early, then add triage intelligence, then harden for production.

- **Phase 0 — Contracts & inputs**
- **Phase 1 — Runnable MVP (GREEN path)**
- **Phase 2 — AMBER plumbing (report fetch + parse)**
- **Phase 3 — AI triage (classification + aggregate)**
- **Phase 4 — Retrigger loop + END-FLOW output**
- **Phase 5 — Context enrichment (OCP logs + historical failures + Jira)**
- **Phase 6 — Persistence & concurrency scaling**
- **Phase 7 — Quality gates + CI/CD + deployability**
- **Phase 8 — Production hardening**

---

## Phase 0 — Contracts & inputs (unblock everything)

### Goal
Make the upstream interfaces and formats explicit so implementation and tests are deterministic.

### Tasks
- **STAF contract confirmation**
  - Document request/response for (see `docs/contracts/staf.md`):
    - `POST /automation/v1/activateFlowJobStaf` → returns `{ "path": "<directory>" }`
    - `GET /automation/v1/status?directory=<directory>` → returns **string-typed** counters + `flowCompleted`
    - `GET /automation/v1/stafReport?directory=<directory>` → returns HTML (exists for GREEN and AMBER)
  - Confirm shared request fields are final (varying env/flow types may add fields, but these are always present):
    - `envType`, `flows[].name`, `numberOfThreads`
  - Confirm no additional headers are required beyond `Content-Type: application/json`
  - Confirm status fields are always strings and no additional fields appear:
    - `passedTests`, `skippedTests`, `failedTests`, `flowCompleted`
  - Capture invalid directory behavior:
    - all fields are returned as `null`
- **HTML report samples**
  - Collect at least 3 real report samples:
    - GREEN run (0 failures)
    - AMBER run (1–N failures)
    - Mixed failure styles (timeouts, assertion failures, infra errors)
  - Store as test fixtures under `tests/fixtures/reports/` (sanitized).
- **Runtime constraints**
  - Confirm max expected runtime and polling cadence requirements (recommended: poll every 60s; max wait 20 mins).
  - Confirm retry policy (max retries, delay) and whether retrigger is per flow tag or per suite.

### Deliverables
- `docs/contracts/staf.md` (authoritative contract used for implementation + tests)
- Sanitized HTML fixtures

### Acceptance criteria
- For each endpoint, the payload schema + sample response is documented and validated with at least one real sample.

### Risks / unknowns to resolve
- Report HTML structure may vary by suite/framework version.
- `suite_tag` → flow list expansion mechanism must be clarified/implemented.

---

## Phase 1 — Runnable MVP (GREEN path end-to-end)

### Goal
Deliver a working backend that can trigger a suite and monitor until completion, returning SUCCESS for GREEN runs.

### Implementation plan (modules)
- **STAF client**
  - Create `src/services/staf_client.py`
  - Functions:
    - `activate_suite(...) -> str` (returns directory/path)
    - `get_status(directory: str) -> ExecutionStatus`
    - `get_report_html(directory: str) -> str` (can be stubbed until Phase 2)
  - Use `httpx` with timeouts from settings.
- **Storage (in-memory)**
  - Create `src/services/storage.py` implementing `BaseStorage` for run contexts.
  - Minimum:
    - `store_run`, `get_run`, `update_run`, plus a simple `list_runs`.
  - Note: failure/history storage can be minimal initially.
- **Orchestrator**
  - Create `src/services/orchestrator.py`
  - Responsibilities:
    - `start_run(request: ExecutionRequest) -> str` (create RunContext, store, return run_id)
    - `run_main_flow(run_id: str) -> None` (poll status until GREEN/AMBER/timeout)
    - Update `RunContext.history` each iteration using `RunContext.log_iteration(...)`.
    - Set `RunOutcome.SUCCESS` on GREEN completion.
  - Enforce `poll_max_wait_seconds` timeout.
- **API wiring**
  - Implement in `src/api/routes/main.py`:
    - `POST /execute`: create run_id and schedule `run_main_flow` via `BackgroundTasks`.
    - `GET /runs/{run_id}/status`: return current ExecutionStatus
    - `GET /runs/{run_id}`: return `EndFlowReport` (if not complete, respond with a “RUNNING” equivalent report)
    - `GET /runs`: list runs

### Deliverables
- Working endpoints:
  - `POST /api/v1/execute`
  - `GET /api/v1/runs/{run_id}/status`
  - `GET /api/v1/runs/{run_id}`
  - `GET /api/v1/runs`
  - `GET /api/v1/health`

### Acceptance criteria
- A GREEN suite run can be triggered and monitored to completion.
- Polling respects `poll_interval_seconds` and `poll_max_wait_seconds` (recommended: 60s polling, 20 min max wait).
- `RunContext` stored and retrievable during execution.

### Tests
- Unit tests for:
  - status → `SuiteStatus` mapping (`ExecutionStatus.suite_status`)
  - orchestrator timeout handling
- Integration tests using `httpx.AsyncClient` against the FastAPI app, with STAF client mocked.

---

## Phase 2 — AMBER plumbing (report fetch + parse)

### Goal
For AMBER runs, fetch the HTML report and parse failed flows reliably.

### Implementation plan (modules)
- **Report parser**
  - Create `src/services/report_parser.py` that selects a parser implementation.
  - Create at least one concrete parser in `src/parsers/` (e.g., `staf_html_parser.py`) implementing `BaseReportParser.parse(...)`.
  - Parse into `HTMLReport` and `FlowResult` with:
    - `total_flows/passed/failed/skipped`
    - `failed_flows` list with `flow_tag`, `flow_name`, `error_message`, `trace` when available
    - `failed_steps`/`steps` if extractable
- **Orchestrator AMBER branch**
  - If status is AMBER:
    - fetch HTML via STAF client
    - parse report into `HTMLReport`
    - persist in `RunContext.html_report` (or store parsed report separately, but keep raw for audit)

### Deliverables
- AMBER run results now include:
  - failed flow tags derived from the report
  - counts: total/passed/failed

### Acceptance criteria
- Parsing works on all stored fixtures and at least one live report.
- Parser failure modes are explicit (`InvalidReportError`, `ParserError`) and surfaced in run outcome as `SuiteStatus.ERROR` with details.

### Tests
- Fixture-driven parser tests (fast and deterministic).
- Orchestrator AMBER path tests with mocked STAF HTML response.

---

## Phase 3 — AI triage (classification + aggregate)

### Goal
Classify each failed flow as intermittent vs actual, produce RCA and fix suggestions for actual failures, and compute aggregate result (ALL_INTERMITTENT / ALL_ACTUAL / BOTH).

### Implementation plan (modules)
- **AI agent**
  - Create `src/services/ai_agent.py`
  - Inputs:
    - Failed flow details (from HTML parsing)
    - Optional: selected log snippets (Phase 5)
    - Optional: “past similar failures” (Phase 5)
  - Output (structured):
    - Per flow: classification, reasoning, confidence, RCA, fix suggestion
    - Aggregate: ALL_INTERMITTENT / ALL_ACTUAL / BOTH
  - Use Anthropic SDK with `anthropic_api_key`, `anthropic_model`, `anthropic_max_tokens`.
- **Aggregation logic**
  - Deterministic computation:
    - all intermittent → ALL_INTERMITTENT
    - all actual → ALL_ACTUAL
    - mix → BOTH
  - Store as `AnalysisResult` in `RunContext.analysis_result`.

### Deliverables
- `AnalysisResponse` populated in `EndFlowReport` for AMBER outcomes.

### Acceptance criteria
- For a known fixture set, the AI response is parsable and maps cleanly into `AnalysisResponse`.
- Fail-safe behavior exists when AI is unavailable:
  - Outcome becomes `MANUAL_INTERVENTION` or `ACTUAL_FAILURES` with “unknown” classification (choose policy and document it).

### Tests
- Contract tests for AI output parsing (use canned AI responses).
- Ensure PII/secrets are not included in prompts (scrub logs/tokens).

---

## Phase 4 — Retrigger loop + END-FLOW output

### Goal
Implement the retry loop exactly as described:
- **Only** ALL_INTERMITTENT triggers retrigger
- Retrigger goes back through full status monitoring
- Retries exhausted → manual intervention

### Implementation plan (modules)
- **Retrigger**
  - Implement in orchestrator:
    - If aggregate == ALL_INTERMITTENT and `run_context.can_retry()`:
      - increment retry
      - retrigger failed flow tags (capture how STAF expects these tags)
      - monitor again (same Phase 1 polling loop)
    - If subsequent run becomes GREEN → `RunOutcome.RETRIGGER_SUCCESS`
    - If retries exhausted → `RunOutcome.MANUAL_INTERVENTION`
- **BOTH path rule**
  - If aggregate == BOTH:
    - Do **not** retrigger intermittent flows
    - Return mixed report immediately (`RunOutcome.MIXED_FAILURES`)
- **END-FLOW**
  - Ensure `EndFlowReport` matches:
    - SUCCESS
    - RETRIGGER_SUCCESS
    - ACTUAL_FAILURES
    - MIXED_FAILURES
    - MANUAL_INTERVENTION
  - Optionally expose formatted text from `format_end_flow_report(...)` for humans.

### Acceptance criteria
- Behavior matches `flowchart.md` key rules.
- Run history reflects each iteration with timestamps and status.

### Tests
- State-machine tests for:
  - ALL_INTERMITTENT with success on retry 1
  - ALL_INTERMITTENT exhausting retries
  - BOTH path does not retrigger

---

## Phase 5 — Context enrichment (OCP logs + historical failures + Jira)

### Goal
Improve accuracy and usefulness of RCA by adding relevant runtime and history context.

### Implementation plan (modules)
- **OCP logs**
  - Create `src/services/mcp_client.py` (or direct OpenShift client) to fetch logs for failed flows.
  - Apply filters from settings:
    - `log_filter_levels`
    - `log_max_lines`
- **Historical similarity search**
  - Extend storage:
    - `store_failure(FailureDetails, directory)`
    - `get_failures_by_flow_tags(flow_tags, limit)`
  - Use history in AI prompt as “past similar issues”.
- **Jira integration (optional)**
  - Create `src/services/jira_client.py`
  - Create/update issue for `ACTUAL_ISSUE` failures with:
    - flow tag, suite tag, RCA, stack trace excerpt, logs excerpt, fix suggestion

### Acceptance criteria
- For at least one real failure, the report contains a “relevant logs” section and a “past similar issues” section.
- No secrets are stored or emitted in logs/tickets.

---

## Phase 6 — Persistence & concurrency scaling

### Goal
Make runs durable and safe under concurrent usage.

### Implementation plan
- Add storage backend options aligned to `Settings.storage_type`:
  - `memory` (already)
  - `sqlite` (recommended next)
  - `postgres` (later)
- Add a background job runner if needed:
  - If long-lived runs exceed the safety of in-process background tasks, adopt a worker model (Celery/RQ/Arq).
- Concurrency controls:
  - Run-level locks to prevent duplicate processing
  - Idempotency for `/execute` if needed

### Acceptance criteria
- Runs survive app restart (sqlite/postgres).
- Multiple runs can execute without overwriting each other.

---

## Phase 7 — Quality gates + CI/CD + deployability

### Goal
Make the project easy to validate and deploy repeatably.

### Implementation plan
- Add missing developer ergonomics:
  - `.env.example` aligned to `Settings`
  - “one command” local run + test commands documented
- Add CI workflow (GitHub Actions) running:
  - `ruff`
  - `black --check`
  - `mypy`
  - `pytest`
- Add containerization:
  - `Dockerfile`
  - optionally `docker-compose.yml` for local dependencies (db)
- Add deployment manifests if targeting OpenShift/K8s:
  - Deployment, Service, Route/Ingress, ConfigMap/Secret references

### Acceptance criteria
- CI passes on default branch for main workflows.
- Container builds and can start serving `/api/v1/health`.

---

## Phase 8 — Production hardening

### Goal
Operational excellence: secure, observable, resilient.

### Work items
- **Security**
  - Secret management (no `.env` committed)
  - Optional authN/authZ for endpoints
  - Rate limiting & request size limits
  - CORS restrictions (avoid `["*"]` if deployed)
- **Observability**
  - Structured logs with run_id correlation
  - Metrics (latency, run durations, pass/fail rate, retry rate, AI error rate)
  - Tracing if required
- **Reliability**
  - Backoff/circuit breaker for STAF and AI calls
  - Partial failure handling (AI down, MCP down)
  - Cancellation support for runs
- **Performance**
  - Caching (honor `enable_caching` + TTL)
  - Parser performance on large reports

### Acceptance criteria
- SLOs defined (e.g., status endpoint p95 latency, max run memory footprint).
- Failure modes are graceful and actionable.

---

## Cross-cutting “Definition of Done” (per phase)
- **Functionality**: meets phase acceptance criteria.
- **Tests**: unit + integration tests covering the main path for that phase.
- **Documentation**: updated README/contract docs for any new config or behavior.
- **Quality**: ruff/black/mypy pass for touched modules.
- **Security**: no secrets in repo; prompts/logs scrub tokens.

---

## Suggested delivery plan (example timeline)
This is a sizing template; adjust based on team size and STAF availability.
- **Week 1**: Phase 0 + Phase 1 (GREEN MVP)
- **Week 2**: Phase 2 (parser + AMBER plumbing)
- **Week 3**: Phase 3 (AI triage)
- **Week 4**: Phase 4 (retrigger loop + END-FLOW)
- **Week 5**: Phase 5 (logs/history/Jira)
- **Week 6**: Phase 6 + Phase 7 (persistence + CI + container)
- **Week 7+**: Phase 8 hardening (as needed for production)

