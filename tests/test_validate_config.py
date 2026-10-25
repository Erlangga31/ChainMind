"""Offline profile validation and dotenv parsing tests."""

from pathlib import Path

import pytest

from scripts.validate_config import read_env_file, validate_configuration, validate_profile


def test_mock_profile_needs_no_external_account_settings() -> None:
    checks = validate_profile("mock", {})

    assert all(check.passed for check in checks)
    assert not any("secret" in check.name.lower() for check in checks)


def test_aws_and_real_profiles_report_missing_settings_without_values() -> None:
    aws_checks = validate_profile("aws", {})
    real_checks = validate_profile("real", {})

    assert any(
        check.name == "Notification link secret ID" and not check.passed for check in aws_checks
    )
    assert any(
        check.name == "SAP Integration Suite URL" and not check.passed for check in real_checks
    )
    assert all(
        "Configured" not in check.detail or "value hidden" in check.detail for check in aws_checks
    )


def test_configuration_reads_env_and_process_environment_overrides(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CHAINMIND_NOTIFICATION_LINK_SECRET_ID=from-file\nAWS_REGION=eu-west-1\n",
        encoding="utf-8",
    )

    checks = validate_configuration(
        "aws",
        env_file,
        {
            "CHAINMIND_NOTIFICATION_LINK_SECRET_ID": "from-process",
            "CHAINMIND_BEDROCK_MODEL_ID": "example-model",
        },
    )
    by_name = {check.name: check for check in checks}

    assert by_name["Notification link secret ID"].passed
    assert by_name["Bedrock model ID"].passed
    assert all("from-process" not in check.detail for check in checks)


def test_invalid_dotenv_syntax_is_reported(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("NOT_A_KEY_VALUE_LINE\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        read_env_file(env_file)
