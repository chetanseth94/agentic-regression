## Automation API Contract (STAF-compatible)

### Base URL
- **Runtime base**: `https://<your-staf-runtime-host>`

### Authentication / headers
- **Required**:
  - `Content-Type: application/json` (for POST)
- **Not required**:
  - No additional headers are required for functionality (e.g., `x-b3-*` tracing headers are optional).

---

## 1) Trigger regression run

### Endpoint
- **POST** `/automation/v1/activateFlowJobStaf`

### Request payload (shared fields — always present)
> Note: payload may include additional fields depending on env/flow type, but these fields are stable and must be supported.

- `envType` (string)
- `flows` (array)
  - each item: `{ "name": "<flowTag>" }`
- `numberOfThreads` (string)

### Example request
```json
{
  "envType": "<ENV_TYPE>",
  "flows": [
    { "name": "@<flowTag>" }
  ],
  "numberOfThreads": "10"
}
```

### Success response (200)
- `path` (string): directory identifier used for status/report APIs

Example:
```json
{
  "path": "59e44fffeb11478892b72e988ae98eb0"
}
```

### Error responses
- Not captured yet (no canonical 4xx/5xx response examples available). Implementation should treat non-2xx as an error and include response body (when present) in the error details.

---

## 2) Poll execution status

### Endpoint
- **GET** `/automation/v1/status?directory=<path>`

### Response fields (always present, always strings)
- `passedTests` (string number)
- `skippedTests` (string number)
- `failedTests` (string number)
- `flowCompleted` (string boolean: `"true"` / `"false"`)

### Example: running
```json
{
  "passedTests": "6",
  "skippedTests": "0",
  "failedTests": "15",
  "flowCompleted": "false"
}
```

### Example: completed
```json
{
  "passedTests": "8",
  "skippedTests": "0",
  "failedTests": "15",
  "flowCompleted": "true"
}
```

### Counter update behavior
- While `flowCompleted` is `"false"`, counters can still change as flows complete.

### Invalid directory behavior
If `directory` is invalid, fields are returned as `null`:
```json
{
  "passedTests": null,
  "skippedTests": null,
  "failedTests": null,
  "flowCompleted": null
}
```

### Client-side interpretation (recommended)
- **RUNNING**: `flowCompleted == "false"`
- **COMPLETED**: `flowCompleted == "true"`
- **GREEN**: completed + `failedTests == "0"`
- **AMBER**: completed + `failedTests != "0"`
- **ERROR**: any null fields OR non-2xx OR unexpected payload shape

---

## 3) Fetch execution report (HTML)

### Endpoint
- **GET** `/automation/v1/stafReport?directory=<path>`

### Response
- Raw **HTML page**
- Report exists and returns HTML for:
  - **GREEN** (0 failures)
  - **AMBER** (failures)

### Known HTML failure marker (for failed tests)
- Failed entries are represented with a CSS class containing:
  - `class="badge log fail-bg mr-2"`

> Parser implementation should not rely on a single marker only; treat this as a strong signal and still parse defensively.

---

## Mapping to this project’s API input model

### Key rule
- A `suite_tag` in this project represents a **collection of flow tags** (up to ~100 flows), each represented in STAF as `flows[].name`.

### Recommended internal representation
- Convert incoming `ExecutionRequest` to a list of STAF flows:
  - `suite_tag` → resolve to `flows: [{name: ...}, ...]`
  - `num_threads` → `numberOfThreads` (string)
  - `env_type` → `envType`

> If suite-to-flow expansion requires an external lookup (e.g., a suite registry), document/implement that as a separate component; otherwise accept an explicit `flows` list in the API.

---

## Runtime guidance (defaults for implementation)
- **Polling interval**: 60 seconds
- **Max expected completion time**: 20 minutes

