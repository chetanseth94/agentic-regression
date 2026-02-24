from src.models.suite import AggregateResult, AnalysisResult
from src.utils.retrigger_confirmation import confirm_intermittent_after_retrigger


def test_confirm_intermittent_moves_refuted_to_actual():
    analysis = AnalysisResult(
        aggregate=AggregateResult.BOTH,
        intermittent_flow_tags=["@a", "@b"],
        actual_failures=[{"flow_tag": "@x", "rca": "x", "stack_trace": None, "relevant_log_lines": [], "fix_suggestion": "x"}],
    )

    updated = confirm_intermittent_after_retrigger(analysis, retrigger_failed_unique_tags=["@b"])

    assert updated.confirmed_intermittent_flow_tags == ["@a"]
    assert updated.refuted_intermittent_flow_tags == ["@b"]
    assert updated.intermittent_flow_tags == ["@a"]
    assert any(x["flow_tag"] == "@b" for x in updated.actual_failures)
    assert updated.aggregate == AggregateResult.BOTH

