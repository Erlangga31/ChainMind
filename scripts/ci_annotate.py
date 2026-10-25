"""Emit concise pytest failures as GitHub annotations and job summary entries."""

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_failures(report: Path) -> list[tuple[str, str, str]]:
    """Return (test path, test name, concise message) tuples from JUnit XML."""

    root = ET.parse(report).getroot()
    failures = []
    for testcase in root.iter("testcase"):
        result = testcase.find("failure")
        if result is None:
            result = testcase.find("error")
        if result is None:
            continue
        classname = testcase.get("classname", "")
        test_file = f"{classname.replace('.', '/')}.py" if classname else ""
        message = result.get("message")
        if not message:
            traceback = (result.text or "").strip().splitlines()
            message = traceback[-1] if traceback else "Test failed without an error message."
        failures.append((test_file, testcase.get("name", "unknown test"), str(message)))
    return failures


def escape_command_data(value: str) -> str:
    """Escape values embedded in a GitHub workflow command."""

    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> int:
    """Report failures from the pytest JUnit file supplied on the command line."""

    if len(sys.argv) != 2:
        print("Usage: python scripts/ci_annotate.py <junit-report.xml>", file=sys.stderr)
        return 2

    report = Path(sys.argv[1])
    failures = parse_failures(report)
    if not failures:
        print(f"No pytest failures found in {report}.")
        return 0

    summary = ["## Backend pytest failures", ""]
    for test_file, test_name, message in failures:
        short_message = message[:300]
        annotation = escape_command_data(f"{test_name}: {short_message}")
        file_property = f"file={escape_command_data(test_file)}," if test_file else ""
        print(f"::error {file_property}title=Backend pytest failure::{annotation}")
        summary.append(f"- `{test_name}` — {short_message}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as output:
            output.write("\n".join(summary) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
