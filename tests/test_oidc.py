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
            "ui_locales": "en",
        },
    )
    assert authorize.status_code == 200
    assert '<html lang="en">' in authorize.text
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
            "ui_locales": "en",
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
    assert "Gagal masuk. Periksa nama pengguna dan kata sandi, lalu coba lagi." in bad_login.text
    assert 'name="username"' in bad_login.text

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


def test_oidc_sign_in_page_has_accessible_form_and_escaped_hidden_values() -> None:
    client = TestClient(create_app(SandboxSettings()))
    injected_state = '"><img src=x onerror=alert(1)>'
    response = client.get(
        "/oidc/authorize",
        params={
            "response_type": "code",
            "client_id": "chainmind-dashboard",
            "redirect_uri": "http://localhost:5173/",
            "scope": "openid profile",
            "state": injected_state,
            "nonce": "nonce-value",
            "code_challenge": "A" * 43,
            "code_challenge_method": "S256",
        },
    )

    assert response.status_code == 200
    assert "<title>Masuk ke ChainMind</title>" in response.text
    assert "Identity provider (sandbox) — meniru SAP BTP IAS" in response.text
    for field in ("client_id", "redirect_uri", "state", "nonce", "code_challenge", "ui_locales"):
        assert (
            f'name="{field}" type="hidden"' in response.text
            or f'type="hidden" name="{field}"' in response.text
        )
    assert '<label for="username">Pengguna</label>' in response.text
    assert '<label for="password">Kata sandi</label>' in response.text
    assert 'id="toggle-password"' in response.text
    assert 'data-username="approver"' in response.text
    assert 'data-username="viewer"' in response.text
    assert injected_state not in response.text
    assert "&quot;&gt;&lt;img src=x onerror=alert(1)&gt;" in response.text
    assert "https://" not in response.text


def test_oidc_invalid_credentials_render_the_same_generic_error_without_user_enumeration() -> None:
    client = TestClient(create_app(SandboxSettings()))
    fields = {
        "password": "wrong",
        "client_id": "chainmind-dashboard",
        "redirect_uri": "http://localhost:5173/",
        "state": "state-value",
        "nonce": "nonce-value",
        "code_challenge": "A" * 43,
        "ui_locales": "en",
    }

    known_user = client.post(
        "/oidc/login",
        data={**fields, "username": "approver"},
        follow_redirects=False,
    )
    unknown_user = client.post(
        "/oidc/login",
        data={**fields, "username": "not-a-user"},
        follow_redirects=False,
    )

    assert known_user.status_code == unknown_user.status_code == 401
    generic_error = "Sign-in failed. Check your username and password and try again."
    assert generic_error in known_user.text
    assert generic_error in unknown_user.text
    assert "user not found" not in unknown_user.text.lower()
    assert "account does not exist" not in unknown_user.text.lower()
