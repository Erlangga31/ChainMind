from __future__ import annotations

import httpx

from scripts.verify_sap_tenant import METADATA_PATHS, READ_PATHS, verify_tenant


def test_sap_tenant_verifier_checks_token_metadata_and_each_read_service() -> None:
    requested: list[tuple[str, str]] = []
    authorization: list[str | None] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, request.url.path))
        authorization.append(request.headers.get("Authorization"))
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "test-token"})
        if request.url.path.endswith("$metadata"):
            return httpx.Response(
                200,
                content=b'<edmx:Edmx xmlns:edmx="urn:test"></edmx:Edmx>',
                headers={"content-type": "application/xml"},
            )
        return httpx.Response(200, json={"d": {"results": []}})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    results = verify_tenant(
        base_url="https://sap.example.invalid",
        token_url="https://sap.example.invalid/oauth/token",
        client_id="test-client",
        client_secret="test-secret",
        client=client,
    )

    assert len(results) == 1 + len(METADATA_PATHS) + len(READ_PATHS)
    assert all(result.status == "PASS" for result in results)
    assert len(requested) == 1 + len(METADATA_PATHS) + len(READ_PATHS)
    assert authorization[0] is None
    assert authorization[1:] == ["Bearer test-token"] * (len(METADATA_PATHS) + len(READ_PATHS))
    assert {path for _, path in requested[1:]} == set(METADATA_PATHS + READ_PATHS)
    client.close()


def test_sap_tenant_verifier_reports_oauth_failure_without_service_calls() -> None:
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(401, json={"error": "invalid_client"})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    results = verify_tenant(
        base_url="https://sap.example.invalid",
        token_url="https://sap.example.invalid/oauth/token",
        client_id="wrong-client",
        client_secret="wrong-secret",
        client=client,
    )

    assert results[0].status == "FAIL"
    assert requests == ["/oauth/token"]
    client.close()
