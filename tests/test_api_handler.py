from typing import Any

import chainmind.handlers.api as api_handler


def test_cognito_viewer_claim_overrides_client_supplied_approver_role(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        api_handler,
        "_mangum_handler",
        lambda event, context: event,
    )
    event = {
        "headers": {"X-ChainMind-Role": "approver"},
        "requestContext": {"authorizer": {"claims": {"cognito:groups": '["viewer"]'}}},
    }

    result = api_handler.handler(event, None)

    assert result["headers"]["X-ChainMind-Role"] == "viewer"


def test_cognito_approver_group_is_propagated_to_api_routes(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        api_handler,
        "_mangum_handler",
        lambda event, context: event,
    )
    event = {
        "headers": {},
        "requestContext": {"authorizer": {"claims": {"cognito:groups": '["viewer","approver"]'}}},
    }

    result = api_handler.handler(event, None)

    assert result["headers"]["X-ChainMind-Role"] == "approver"
