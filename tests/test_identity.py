from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from chainmind.api.identity import OIDCVerifier, authenticated_user
from chainmind.core.config import Settings


@pytest.fixture
def signing_material() -> tuple[Any, Any]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def make_verifier(
    signing_material: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[OIDCVerifier, Any]:
    private_key, public_key = signing_material

    class FakeJWKClient:
        def get_signing_key_from_jwt(self, _: str) -> SimpleNamespace:
            return SimpleNamespace(key=public_key)

    verifier = OIDCVerifier(
        Settings(
            auth_issuer="https://issuer.example.test",
            auth_audience="chainmind-dashboard",
            auth_jwks_url="https://issuer.example.test/jwks",
        )
    )
    monkeypatch.setattr(verifier, "_key_client", FakeJWKClient())
    return verifier, private_key


def encode_token(private_key: Any, **claim_overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": "https://issuer.example.test",
        "aud": "chainmind-dashboard",
        "sub": "approver-1",
        "tenant_id": "factory-demo",
        "roles": ["approver"],
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def test_verifies_valid_rs256_access_token(
    signing_material: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier, private_key = make_verifier(signing_material, monkeypatch)

    user = verifier.verify(encode_token(private_key))

    assert user.subject == "approver-1"
    assert user.roles == frozenset({"approver"})
    assert user.tenant_id == "factory-demo"


def test_rejects_tokens_without_tenant_claim(
    signing_material: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier, private_key = make_verifier(signing_material, monkeypatch)

    with pytest.raises(HTTPException) as error:
        verifier.verify(encode_token(private_key, tenant_id=None))

    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"aud": "another-client"},
    ],
    ids=["expired", "wrong-audience"],
)
def test_rejects_expired_and_wrong_audience_tokens(
    claims: dict[str, object],
    signing_material: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier, private_key = make_verifier(signing_material, monkeypatch)

    with pytest.raises(HTTPException):
        verifier.verify(encode_token(private_key, **claims))


def test_rejects_tampered_signature(
    signing_material: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier, private_key = make_verifier(signing_material, monkeypatch)
    token = encode_token(private_key)
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-1]}{'A' if signature[-1] != 'A' else 'B'}"

    with pytest.raises(HTTPException):
        verifier.verify(tampered)


def test_viewer_token_is_valid_but_does_not_grant_approver_role(
    signing_material: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier, private_key = make_verifier(signing_material, monkeypatch)

    user = verifier.verify(encode_token(private_key, roles=["viewer"]))

    assert "viewer" in user.roles
    assert "approver" not in user.roles


def test_development_bypass_is_explicit_and_mock_only(
    signing_material: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier, _ = make_verifier(signing_material, monkeypatch)

    with pytest.raises(HTTPException) as default_error:
        authenticated_user(None, Settings(), verifier)
    assert default_error.value.status_code == 401

    bypassed = authenticated_user(
        None,
        Settings(mode="mock", auth_dev_bypass=True),
        verifier,
    )
    assert "approver" in bypassed.roles

    with pytest.raises(HTTPException) as aws_error:
        authenticated_user(
            None,
            Settings(mode="aws", auth_dev_bypass=True),
            verifier,
        )
    assert aws_error.value.status_code == 401
