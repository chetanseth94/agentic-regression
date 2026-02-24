from src.parsers.extent_spark_bdd_parser import ExtentSparkBddReportParser


def test_parses_failed_and_passed_items():
    html = """
    <html>
      <body class="spa bdd-report standard">
        <ul>
          <li class="test-item" status="pass">
            <div class="test-detail"><p class="name">Scenario A</p></div>
          </li>
          <li class="test-item" status="fail">
            <div class="test-detail"><p class="name">Scenario B</p></div>
            <table class="table">
              <tr><td><span class="badge log fail-bg mr-2">Fail</span></td><td>Step 1 failed</td></tr>
              <tr><td><span class="badge log pass-bg mr-2">Pass</span></td><td>Step 2 passed</td></tr>
            </table>
          </li>
          <li class="test-item">
            <div class="test-detail"><p class="name">Feature Group Node (no status)</p></div>
          </li>
        </ul>
      </body>
    </html>
    """

    parser = ExtentSparkBddReportParser()
    report = parser.parse(raw_html=html, directory="dir1")

    assert report.total_flows == 2
    assert report.passed == 1
    assert report.failed == 1
    assert report.skipped == 0

    assert report.failed_flow_tags == ["Scenario B"]

    failed = report.failed_flows[0]
    assert failed.flow_name == "Scenario B"
    assert failed.error_message is not None
    assert "Step 1 failed" in failed.error_message
    assert failed.failed_steps and any("Step 1 failed" in s for s in failed.failed_steps)

