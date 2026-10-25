from base64 import urlsafe_b64encode
from hashlib import sha256
from urllib.parse import parse_qs, urlparse

import jwt
from fastapi.testclient import TestClient
from sap_sandbox.config import SandboxSettings
from sap_sandbox.main import create_app


def test_oidc_authorization_code_pkce_and_role_claims() -> None:
    issuer = "http://127.0.0.1:8100"
    redirect_uri = "http://localhost:5173/"
    client = TestClient(
        create_app(
            SandboxSettings(
                oidc_issuer=issuer,
                oidc_audience="chainmind-dashboard",
                oidc_client_id="dashboard-client",
                oidc_redirect_uri=redirect_uri,
            )
        )
    )
    verifier = "a" * 48
    challenge = urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = "test-state"
    nonce = "test-nonce"
    authorize = client.get(
        "/oidc/authorize",
        params={
            "response_type": "code",
            "client_id": "dashboard-client",
            "redirect_uri": redirect_uri,
            "scope": "openid profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert authorize.status_code == 200
    assert client.get("/.well-known/openid-configuration").json()["issuer"] == issuer
    login = client.post(
        "/oidc/login",
        data={
            "username": "approver",
            "password": "demo",
            "client_id": "dashboard-client",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
        },
        follow_redirects=False,
    )
    assert login.status_code == 303
    callback = parse_qs(urlparse(login.headers["location"]).query)
    assert callback["state"] == [state]

    tokens = client.post(
        "/oidc/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "dashboard-client",
            "redirect_uri": redirect_uri,
            "code": callback["code"][0],
            "code_verifier": verifier,
        },
    )

    assert tokens.status_code == 200
    claims = jwt.decode(
        tokens.json()["id_token"],
        jwt.PyJWK.from_dict(client.get("/.well-known/jwks.json").json()["keys"][0]).key,
        algorithms=["RS256"],
        audience="chainmind-dashboard",
        issuer=issuer,
    )
    assert claims["roles"] == ["approver"]
    assert claims["nonce"] == nonce

    second_login = client.post(
        "/oidc/login",
        data={
            "username": "viewer",
            "password": "demo",
            "client_id": "dashboard-client",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
        },
        follow_redirects=False,
    )
    second_code = parse_qs(urlparse(second_login.headers["location"]).query)["code"][0]
    wrong_pkce = client.post(
        "/oidc/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "dashboard-client",
            "redirect_uri": redirect_uri,
            "code": second_code,
            "code_verifier": "b" * 48,
        },
    )
    assert wrong_pkce.status_code == 400


def test_oidc_rejects_invalid_credentials_and_pkce_verifiers() -> None:
    client = TestClient(create_app(SandboxSettings()))
    bad_login = client.post(
        "/oidc/login",
        data={
            "username": "approver",
            "password": "wrong",
            "client_id": "chainmind-dashboard",
            "redirect_uri": "http://localhost:5173/",
            "state": "state",
            "nonce": "nonce",
            "code_challenge": "A" * 43,
        },
    )
    assert bad_login.status_code == 401

    bad_authorize = client.get(
        "/oidc/authorize",
        params={
            "response_type": "code",
            "client_id": "chainmind-dashboard",
            "redirect_uri": "http://localhost:5173/",
            "scope": "openid",
            "state": "state",
            "nonce": "nonce",
            "code_challenge": "A" * 43,
            "code_challenge_method": "S256",
        },
    )
    assert bad_authorize.status_code == 200
    bad_token = client.post(
        "/oidc/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "chainmind-dashboard",
            "redirect_uri": "http://localhost:5173/",
            "code": "unknown",
            "code_verifier": "B" * 48,
        },
    )
    assert bad_token.status_code == 400
