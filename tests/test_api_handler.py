from typing import Any

import chainmind.handlers.api as api_handler


def test_api_handler_removes_untrusted_client_role_header(monkeypatch: Any) -> None:
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

    assert result["headers"] == {}
    assert result["requestContext"]["authorizer"]["claims"]["cognito:groups"] == '["viewer"]'


def test_api_handler_preserves_gateway_authorization_context(monkeypatch: Any) -> None:
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

    assert result["headers"] == {}
    assert (
        result["requestContext"]["authorizer"]["claims"]["cognito:groups"]
        == '["viewer","approver"]'
    )
