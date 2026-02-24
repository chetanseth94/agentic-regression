import os

from src.config.settings import get_settings
from src.services.ai_agent import AiAgent


def test_ai_agent_heuristic_aggregate_both(monkeypatch):
    # Ensure we don't attempt real Anthropic calls in unit tests.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()

    agent = AiAgent()
    preliminary = [
        {
            "uniqueFlowTag": "@agentic_analysis_RBS_1",
            "lastAPIResponseCode": "500",
            "failureType": "Execution step failure",
            "Failure details": "Given CARE - Get Customer Header | Actual Status Code: 500",
        },
        {
            "uniqueFlowTag": "@agentic_analysis_RBS_2",
            "lastAPIResponseCode": "404",
            "failureType": "Execution step failure",
            "Failure details": "Then Something | Actual Status Code: 404",
        },
        {"reportLocation": "/tmp/report.html"},
    ]

    result = agent.analyze_preliminary_report(preliminary)
    assert result.aggregate.value == "BOTH"
    assert "@agentic_analysis_RBS_1" in result.intermittent_flow_tags
    assert any(x["flow_tag"] == "@agentic_analysis_RBS_2" for x in result.actual_failures)


def test_ai_agent_heuristic_all_intermittent(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()

    agent = AiAgent()
    preliminary = [
        {
            "uniqueFlowTag": "@agentic_analysis_RBS_1",
            "lastAPIResponseCode": "503",
            "failureType": "Execution step failure",
            "Failure details": "Service unavailable | Actual Status Code: 503",
        }
    ]

    result = agent.analyze_preliminary_report(preliminary)
    assert result.aggregate.value == "ALL_INTERMITTENT"
    assert result.intermittent_count == 1
    assert result.actual_count == 0

