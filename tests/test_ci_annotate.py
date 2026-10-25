"""Tests for readable GitHub Actions annotations from pytest JUnit output."""

from pathlib import Path

from scripts.ci_annotate import parse_failures


def test_parse_failures_extracts_test_path_name_and_message(tmp_path: Path) -> None:
    report = tmp_path / "pytest-report.xml"
    report.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="1">
    <testcase classname="tests.test_api" name="test_kpis">
      <failure message="assert False is True">traceback content</failure>
    </testcase>
    <testcase classname="tests.test_api" name="test_ok" />
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    assert parse_failures(report) == [("tests/test_api.py", "test_kpis", "assert False is True")]
