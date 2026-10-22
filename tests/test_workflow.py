"""Workflow decision-state protections."""

from importlib.resources import files

import pytest

from chainmind.core.config import Settings
from chainmind.core.errors import ChainMindError
from chainmind.core.events import EventStore
from chainmind.core.models import DecisionRequest, DecisionType, DisruptionEvent
from chainmind.factory import create_pipeline


def test_decision_cannot_be_replayed_after_rejection() -> None:
    pipeline = create_pipeline(Settings(mode="mock"), EventStore())
    event_json = (
        files("chainmind.data").joinpath("sample_disruption.json").read_text(encoding="utf-8")
    )
    run = pipeline.run(DisruptionEvent.model_validate_json(event_json))

    pipeline.decide(
        run.run_id,
        DecisionRequest(decision=DecisionType.REJECT, note="Rejected for review."),
    )
    with pytest.raises(ChainMindError) as error:
        pipeline.decide(
            run.run_id,
            DecisionRequest(decision=DecisionType.APPROVE),
        )

    assert error.value.code == "decision_not_allowed"
    assert error.value.status_code == 409
