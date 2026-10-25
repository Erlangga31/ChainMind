"""Validate a ChainMind configuration profile without contacting external services."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from chainmind.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
Profile = Literal["mock", "sandbox", "aws", "real"]


@dataclass(frozen=True)
class ConfigCheck:
    """One non-sensitive configuration validation result."""

    name: str
    passed: bool
    detail: str


def read_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE dotenv lines without expanding or printing values."""

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(f"Invalid .env syntax on line {line_number}.")
        key, value = stripped.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip()
        if value[:1] in {"'", '"'} and value[-1:] == value[:1]:
            value = value[1:-1]
        values[key] = value
    return values


def _settings_values(environment: dict[str, str], profile: Profile) -> dict[str, object]:
    field_names = Settings.model_fields.keys()
    values: dict[str, object] = {}
    for field_name in field_names:
        key = f"CHAINMIND_{field_name.upper()}"
        if key in environment:
            raw = environment[key]
            if raw.startswith(("[", "{")):
                try:
                    values[field_name] = json.loads(raw)
                    continue
                except json.JSONDecodeError:
                    pass
            values[field_name] = raw
    region = environment.get("AWS_REGION") or environment.get("AWS_DEFAULT_REGION")
    if region:
        values["aws_region"] = region
    values.update({"mode": "mock", "sap_backend": "mock", "llm_backend": "mock"})
    if profile == "sandbox":
        values["sap_backend"] = "sandbox"
    elif profile == "aws":
        values.update({"mode": "aws", "sap_backend": "mock", "llm_backend": "bedrock"})
    elif profile == "real":
        values.update({"mode": "aws", "sap_backend": "real", "llm_backend": "bedrock"})
    return values


def validate_profile(profile: Profile, environment: dict[str, str]) -> list[ConfigCheck]:
    """Check profile-required fields and Pydantic settings without making network calls."""

    try:
        settings = Settings.model_validate(_settings_values(environment, profile))
    except ValidationError as exc:
        return [
            ConfigCheck(
                "Pydantic settings",
                False,
                (
                    f"{len(exc.errors())} value(s) failed validation; "
                    "values are intentionally omitted."
                ),
            )
        ]
    checks = [
        ConfigCheck("Pydantic settings", True, "Field types and configured ranges are valid."),
        ConfigCheck(
            "Selected profile",
            settings.mode == ("mock" if profile in {"mock", "sandbox"} else "aws"),
            profile,
        ),
    ]

    required: list[tuple[str, bool]] = []
    if profile in {"aws", "real"}:
        required.extend(
            [
                ("AWS region", bool(settings.aws_region.strip())),
                ("Bedrock model ID", bool(settings.bedrock_model_id.strip())),
                ("EventBridge bus name", bool(settings.event_bus_name.strip())),
                ("DynamoDB event table", bool(settings.event_table_name.strip())),
                ("S3 artifact bucket", bool(settings.artifact_bucket_name.strip())),
                ("Notification link secret ID", bool(settings.notification_link_secret_id)),
            ]
        )
    if profile == "sandbox":
        required.append(
            (
                "SAP sandbox URL",
                settings.sap_backend == "sandbox"
                and settings.sap_workflow_base_url.startswith(("http://", "https://")),
            )
        )
    if profile == "real":
        required.extend(
            [
                ("SAP Integration Suite URL", bool(settings.sap_integration_suite_url)),
                ("SAP OAuth token URL", bool(settings.sap_token_url)),
                ("SAP client ID", bool(settings.sap_client_id)),
                (
                    "SAP secret source",
                    bool(settings.sap_secrets_secret_id or settings.sap_client_secret),
                ),
            ]
        )
    checks.extend(
        ConfigCheck(
            name,
            passed,
            "Configured (value hidden)" if passed else "Missing or invalid; see docs/GO_LIVE.md.",
        )
        for name, passed in required
    )
    return checks


def validate_configuration(
    profile: Profile,
    env_file: Path,
    process_environment: dict[str, str] | None = None,
) -> list[ConfigCheck]:
    """Merge dotenv values with process environment and validate a profile offline."""

    environment = read_env_file(env_file)
    environment.update(process_environment if process_environment is not None else os.environ)
    return validate_profile(profile, environment)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "sandbox", "aws", "real"), default="mock")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    arguments = parser.parse_args()
    try:
        checks = validate_configuration(arguments.mode, arguments.env_file)
    except OSError as exc:
        print(f"Unable to read the configuration file: {exc}", file=sys.stderr)
        return 2
    for check in checks:
        print(f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
    failed = sum(not check.passed for check in checks)
    passed = len(checks) - failed
    print(f"\nConfig validation ({arguments.mode}): {passed}/{len(checks)} checks passed.")
    print("No network requests or service calls were made.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
