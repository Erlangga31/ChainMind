"""Local OIDC provider used to exercise ChainMind's role-based login flow."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlencode

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import Response


@dataclass(frozen=True)
class AuthorizationCode:
    """One-time authorization code bound to the originating PKCE challenge."""

    subject: str
    roles: list[str]
    redirect_uri: str
    code_challenge: str
    nonce: str
    expires_at: float


def add_oidc_routes(
    app: FastAPI,
    *,
    issuer: str,
    audience: str,
    client_id: str,
    redirect_uri: str,
) -> None:
    """Register OIDC discovery, authorization-code, token, and JWKS endpoints."""

    normalized_issuer = issuer.rstrip("/")
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_id = secrets.token_urlsafe(12)
    authorization_codes: dict[str, AuthorizationCode] = {}
    users = {
        "viewer": {"password": "demo", "roles": ["viewer"]},
        "approver": {"password": "demo", "roles": ["approver"]},
    }

    @app.get("/.well-known/openid-configuration")
    def discovery() -> dict[str, Any]:
        return {
            "issuer": normalized_issuer,
            "authorization_endpoint": f"{normalized_issuer}/oidc/authorize",
            "token_endpoint": f"{normalized_issuer}/oidc/token",
            "jwks_uri": f"{normalized_issuer}/.well-known/jwks.json",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
        }

    @app.get("/.well-known/jwks.json")
    def jwks() -> dict[str, Any]:
        public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
        return {
            "keys": [
                {
                    **public_jwk,
                    "kid": key_id,
                    "use": "sig",
                    "alg": "RS256",
                }
            ]
        }

    @app.get("/oidc/authorize", response_class=HTMLResponse)
    def authorize(
        response_type: str,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        nonce: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> Response:
        if (
            response_type != "code"
            or client_id != client_id_value
            or redirect_uri != allowed_redirect_uri
            or "openid" not in scope.split()
            or code_challenge_method != "S256"
            or len(code_challenge) < 43
        ):
            return JSONResponse(status_code=400, content={"error": "invalid_authorization_request"})
        hidden_fields = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
        }
        inputs = "".join(
            f'<input type="hidden" name="{html.escape(name)}" value="{html.escape(value)}">'
            for name, value in hidden_fields.items()
        )
        return HTMLResponse(
            "<!doctype html><html><head><title>ChainMind Demo Login</title></head>"
            "<body><main><h1>ChainMind demo sign in</h1>"
            "<p>Use viewer or approver with password demo.</p>"
            '<form method="post" action="/oidc/login">'
            f"{inputs}<label>User "
            '<input name="username" autocomplete="username" required></label>'
            '<label>Password <input name="password" type="password" required></label>'
            '<button type="submit">Sign in</button></form></main></body></html>'
        )

    @app.post("/oidc/login")
    async def login(request: Request) -> Response:
        fields = {
            key: value[0]
            for key, value in parse_qs((await request.body()).decode("utf-8")).items()
            if value
        }
        user = users.get(fields.get("username", ""))
        if user is None or not secrets.compare_digest(user["password"], fields.get("password", "")):
            return JSONResponse(status_code=401, content={"error": "invalid_credentials"})
        redirect = fields.get("redirect_uri", "")
        if fields.get("client_id") != client_id_value or redirect != allowed_redirect_uri:
            return JSONResponse(status_code=400, content={"error": "invalid_authorization_request"})
        code = secrets.token_urlsafe(32)
        authorization_codes[code] = AuthorizationCode(
            subject=fields["username"],
            roles=user["roles"],
            redirect_uri=redirect,
            code_challenge=fields.get("code_challenge", ""),
            nonce=fields.get("nonce", ""),
            expires_at=time.monotonic() + 120,
        )
        callback = f"{redirect}?{urlencode({'code': code, 'state': fields.get('state', '')})}"
        return RedirectResponse(callback, status_code=303)

    @app.post("/oidc/token")
    async def token(request: Request) -> JSONResponse:
        fields = {
            key: value[0]
            for key, value in parse_qs((await request.body()).decode("utf-8")).items()
            if value
        }
        code = authorization_codes.pop(fields.get("code", ""), None)
        verifier = fields.get("code_verifier", "")
        redirect = fields.get("redirect_uri", "")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        expected_challenge = challenge.rstrip(b"=").decode("ascii")
        if (
            fields.get("grant_type") != "authorization_code"
            or fields.get("client_id") != client_id_value
            or code is None
            or code.expires_at <= time.monotonic()
            or code.redirect_uri != redirect
            or not secrets.compare_digest(code.code_challenge, expected_challenge)
            or len(verifier) < 43
        ):
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})
        now = datetime.now(UTC)
        claims = {
            "iss": normalized_issuer,
            "aud": audience,
            "sub": code.subject,
            "roles": code.roles,
            "iat": now,
            "exp": now + timedelta(minutes=15),
        }
        access_token = jwt.encode(
            claims,
            signing_key,
            algorithm="RS256",
            headers={"kid": key_id, "typ": "JWT"},
        )
        id_token = jwt.encode(
            {**claims, "nonce": code.nonce},
            signing_key,
            algorithm="RS256",
            headers={"kid": key_id, "typ": "JWT"},
        )
        return JSONResponse(
            {
                "access_token": access_token,
                "id_token": id_token,
                "token_type": "Bearer",
                "expires_in": 900,
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    allowed_redirect_uri = redirect_uri
    client_id_value = client_id
