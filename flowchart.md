# Agentic Test Execution and Triage

## Main Flow

```
    ┌──────────────────────────────────────────────────────────────┐
    │  MAIN FLOW (Triggered manually via backend/UI)               │
    │  Input: suite tag, no of threads, type of env, ...           │
    └──────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  Step 1: Trigger Suite Execution                             │
    │  POST /automation/v1/activateFlowJobStaf                     │
    │  (suite tag, threads, env type)                              │
    └──────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  Step 2: Monitor Execution Status                            │
    │  GET /automation/v1/status?directory={{path}}                 │
    └──────────────────────────┬───────────────────────────────────┘
                               │
                ┌──────────────┼──────────────────┐
                │              │                  │
                ▼              ▼                  ▼
    ┌────────────────┐ ┌──────────────┐ ┌─────────────────────┐
    │ completed=true │ │completed=true│ │ completed=false      │
    │ failed=0       │ │ failed!=0    │ │                     │
    │                │ │              │ │ Wait & poll again    │
    │   🟢 GREEN     │ │  🟡 AMBER    │ │ (Go back to Step 2) │
    └───────┬────────┘ └──────┬───────┘ └──────────┬──────────┘
            │                 │                     │
            │                 │                     └──────┐
            ▼                 ▼                            │
    ┌────────────────┐ ┌──────────────────────────────┐    │
    │ Step 3: GREEN  │ │ Step 3: AMBER                │    │
    │ Mark suite as  │ │ Fetch HTML report             │    │
    │ SUCCESS        │ │ GET /automation/v1/stafReport │    │
    │                │ │     ?directory={{path}}        │    │
    └───────┬────────┘ └──────────────┬───────────────┘    │
            │                         │                     │
            │                         ▼                     │
            │          ┌──────────────────────────────┐     │
            │          │ FLOW FAILURE ANALYSIS         │     │
            │          │ (AI Agent - see sub-flow)     │     │
            │          │ Input: HTML report            │     │
            │          └──────────────┬───────────────┘     │
            │                         │                     │
            │           ┌─────────────┼─────────────┐       │
            │           │             │             │       │
            │           ▼             ▼             ▼       │
            │  ┌──────────────┐ ┌──────────┐ ┌──────────┐  │
            │  │ALL           │ │ALL       │ │ BOTH     │  │
            │  │INTERMITTENT  │ │ACTUAL    │ │ (mix)    │  │
            │  └──────┬───────┘ └────┬─────┘ └────┬─────┘  │
            │         │              │             │        │
            │         ▼              ▼             ▼        │
            │  ┌──────────────┐ ┌──────────┐ ┌───────────────────────┐
            │  │Step 4: INT   │ │Step 4:   │ │Step 4: BOTH           │
            │  │Retrigger     │ │ACTUAL    │ │                       │
            │  │failed flow   │ │Collect:  │ │Collect:               │
            │  │tags using    │ │• RCA     │ │• Intermittent flow    │
            │  │activateFlow  │ │• Stack   │ │  tags (no retrigger)  │
            │  │JobStaf API   │ │  trace   │ │• RCA for actual       │
            │  │              │ │• Relevant│ │  issues               │
            │  │              │ │  log     │ │• Stack trace          │
            │  │              │ │  lines   │ │• Relevant log lines   │
            │  │              │ │• Fix     │ │• Fix suggestion       │
            │  │              │ │  suggest │ │                       │
            │  └──────┬───────┘ └────┬─────┘ └───────────┬───────────┘
            │         │              │                    │
            │         ▼              │                    │
            │  ┌──────────────┐      │                    │
            │  │retry < max?  │      │                    │
            │  └──┬───────┬───┘      │                    │
            │     │       │          │                    │
            │    YES      NO         │                    │
            │     │       │          │                    │
            │     │       ▼          │                    │
            │     │  ┌──────────┐    │                    │
            │     │  │Mark:     │    │                    │
            │     │  │"Require  │    │                    │
            │     │  │ manual   │    │                    │
            │     │  │ interv." │    │                    │
            │     │  └────┬─────┘    │                    │
            │     │       │          │                    │
            │     │       ▼          ▼                    ▼
            │     │    ┌──────────────────────────────────────┐
            │     │    │           END FLOW                    │
            │     │    │  Print information in presentable    │
            │     │    │  manner (summary + details)          │
            │     │    └──────────────────────────────────────┘
            │     │
            ▼     └──────────────────────┐
    ┌──────────────────────────────────┐ │
    │           END FLOW               │ │
    │  Print: Suite run SUCCESS        │ │
    └──────────────────────────────────┘ │
                                         │
                    ┌────────────────────┘
                    │ (Loop back to Step 2
                    │  with retrigger path)
                    ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  Go to Step 2: Monitor retrigger execution status            │
    │  GET /automation/v1/status?directory={{path}}                 │
    └──────────────────────────────────────────────────────────────┘
```

## Flow Failure Analysis (AI Agent Sub-Flow)

```
    ┌──────────────────────────────────────────────────────────────┐
    │  FLOW FAILURE ANALYSIS                                       │
    │  Input: HTML report                                          │
    └──────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  1. Parse HTML report to identify failed flows               │
    └──────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  2. Gather Context (in parallel):                            │
    │     • MCP: Collect OCP logs for failed flows                 │
    │     • Analyze codebase for relevant code                     │
    │     • Search past similar issues/failures                    │
    └──────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  3. AI Agent classifies each failed flow:                    │
    │     • INTERMITTENT or ACTUAL ISSUE                           │
    └──────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  4. Output:                                                  │
    │     • Count: intermittent vs actual failures                 │
    │     • For intermittent: flow tags                            │
    │     • For actual: RCA, stack trace, log lines, fix suggest   │
    │     • Aggregate result: ALL_INT / ALL_ACTUAL / BOTH          │
    └──────────────────────────────────────────────────────────────┘
```

## End Flow

```
    ┌──────────────────────────────────────────────────────────────┐
    │  END FLOW: Print information in presentable manner           │
    │                                                              │
    │  Possible outputs:                                           │
    │                                                              │
    │  GREEN:                                                      │
    │    ✅ Suite run SUCCESS - all flows passed                    │
    │                                                              │
    │  ALL INTERMITTENT (after max retries):                       │
    │    ⚠️  Require manual intervention                            │
    │    • Failed flow tags that couldn't pass after X retries     │
    │                                                              │
    │  ALL ACTUAL:                                                 │
    │    ❌ Actual failures found                                   │
    │    • RCA per failed flow                                     │
    │    • Stack trace                                             │
    │    • Relevant log lines                                      │
    │    • Suggestion to fix                                       │
    │                                                              │
    │  BOTH:                                                       │
    │    ⚠️  Mixed failures                                         │
    │    • Intermittent flow tags (not retriggered)                 │
    │    • RCA + stack trace + logs + fix for actual issues         │
    └──────────────────────────────────────────────────────────────┘
```

## Key Rules

1. **BOTH path**: Intermittent flows are NOT retriggered — only reported
2. **Only ALL INTERMITTENT** triggers retrigger with retry loop
3. **Retry loop**: Retrigger → Go back to Step 2 (monitor again)
4. **Max retries**: After X retries → "Require manual intervention" → END
5. **GREEN path**: No analysis needed, immediate success
