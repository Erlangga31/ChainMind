import json
import logging
from uuid import uuid4

from chainmind.api.main import _structured_log


def test_operational_logs_are_json_correlated_and_exclude_unapproved_fields(
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="chainmind.api")
    run_id = uuid4()

    _structured_log(
        "human_decision_recorded",
        run_id=run_id,
        mode="mock",
        decision="approve",
        token="must-not-be-logged",
    )

    record = next(record for record in caplog.records if record.name == "chainmind.api")
    payload = json.loads(record.message)
    assert payload["run_id"] == str(run_id)
    assert payload["decision"] == "approve"
    assert "token" not in payload
    assert "must-not-be-logged" not in record.message
