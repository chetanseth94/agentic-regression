# Agentic Test Execution and Triage System

AI-powered test automation execution and triage system that triggers regression suites, monitors execution, analyzes failures, and provides intelligent classification with root cause analysis.

## How It Works

### Main Flow (triggered manually via backend/UI)

**Input**: suite tag, number of threads, environment type

1. **Trigger**: Call `/automation/v1/activateFlowJobStaf` to execute the suite
2. **Monitor**: Poll `/automation/v1/status?directory={{path}}`
   - **GREEN** (completed, 0 failures) → Mark success → END
   - **AMBER** (completed, failures exist) → Fetch HTML report → Analyze
   - **RUNNING** (not completed) → Wait and poll again
3. **Analyze** (AMBER path): Feed HTML report to AI Agent
4. **Handle Result**:
   - **ALL INTERMITTENT** → Retrigger failed flow tags (max X retries) → Back to Step 2
   - **ALL ACTUAL** → Collect RCA, stack trace, logs, fix suggestion → END
   - **BOTH** → Collect intermittent flow tags (no retrigger) + RCA for actual issues → END
5. **Retry exhausted** → Mark as "require manual intervention" → END

### Flow Failure Analysis (AI Agent Sub-Flow)

**Input**: HTML report

1. Parse report to identify failed flows
2. MCP to collect OCP logs
3. Analyze codebase
4. Search past similar issues
5. **Output**: Classification per flow (intermittent/actual), RCA, fix suggestions

### End Flow

Print information in presentable manner (summary + details per failure).

## Project Structure

```
python-project/
├── src/
│   ├── main.py                      # FastAPI app entry point
│   ├── config/
│   │   └── settings.py              # Settings (STAF URLs, Claude, MCP, retries)
│   ├── models/
│   │   ├── suite.py                 # SuiteInput, SuiteStatus, RunContext, etc.
│   │   ├── failure.py               # FailureDetails, FailureClassification
│   │   └── report.py                # HTMLReport, FlowResult, FlowStatus
│   ├── core/                        # Interfaces (extend these)
│   │   ├── base_parser.py           # BaseReportParser
│   │   ├── base_client.py           # BaseClient
│   │   └── base_storage.py          # BaseStorage
│   ├── api/
│   │   ├── routes/main.py           # API endpoints
│   │   └── schemas/                 # Request/response models
│   │       ├── execution.py         # ExecutionRequest, StatusResponse
│   │       └── analysis.py          # AnalysisResponse, EndFlowReport
│   ├── services/                    # Business logic (to implement)
│   │   ├── orchestrator.py          # Main Flow logic
│   │   ├── staf_client.py           # STAF API calls
│   │   ├── ai_agent.py              # Claude AI integration
│   │   ├── mcp_client.py            # MCP for OCP logs
│   │   ├── jira_client.py           # Jira integration
│   │   ├── report_parser.py         # HTML report parser
│   │   └── storage.py               # In-memory storage
│   ├── parsers/                     # Report parsers (extensible)
│   ├── exceptions/                  # Custom exceptions
│   └── utils/
│       ├── logger.py                # Logging
│       ├── validators.py            # Validation
│       └── presenter.py             # END FLOW report formatting
├── tests/
├── requirements.txt
├── pyproject.toml
├── flowchart.md                     # Detailed flowchart
└── .env.example                     # Environment variables
```

## Setup

```bash
python -m venv venv
venv\Scripts\activate           # Windows
pip install -r requirements.txt
cp .env.example .env            # Edit with your config
uvicorn src.main:app --reload
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/execute` | Trigger suite execution (Main Flow) |
| GET | `/api/v1/runs/{run_id}` | Get run status / final report |
| GET | `/api/v1/runs/{run_id}/status` | Get current execution status |
| GET | `/api/v1/runs` | List all runs |
| GET | `/api/v1/health` | Health check |

## Extending

- **New parser**: Inherit from `BaseReportParser`
- **New client**: Inherit from `BaseClient`
- **New storage**: Inherit from `BaseStorage`
- **Customize retries**: Change `MAX_RETRY_ATTEMPTS` in settings

## Key Design Decisions

- **BOTH path**: Intermittent flows are NOT retriggered — only reported alongside actual failures
- **Only ALL_INTERMITTENT** triggers the retrigger loop
- **Retry loop**: Goes back to Step 2 (full status monitoring) not just fire-and-forget
- **Polling**: Status monitored via loop until completion
