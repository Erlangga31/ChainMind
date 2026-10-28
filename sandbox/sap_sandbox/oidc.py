"""Local OIDC provider used to exercise ChainMind's role-based login flow."""

# ruff: noqa: E501
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


def _login_page(
    hidden_fields: dict[str, str],
    *,
    language: str,
    username: str = "",
    error: bool = False,
) -> str:
    is_english = language == "en"
    title = "Sign in to ChainMind" if is_english else "Masuk ke ChainMind"
    subtitle = (
        "Identity provider (sandbox) — simulates SAP BTP IAS"
        if is_english
        else "Identity provider (sandbox) — meniru SAP BTP IAS"
    )
    user_label = "User" if is_english else "Pengguna"
    password_label = "Password" if is_english else "Kata sandi"
    sign_in = "Sign in" if is_english else "Masuk"
    show_password = "Show password" if is_english else "Tampilkan kata sandi"
    hide_password = "Hide password" if is_english else "Sembunyikan kata sandi"
    choose_account = "Choose a demo account" if is_english else "Pilih akun demo"
    approver = "Approver" if is_english else "Approver"
    viewer = "Viewer" if is_english else "Viewer"
    error_title = (
        "Sign-in failed. Check your username and password and try again."
        if is_english
        else "Gagal masuk. Periksa nama pengguna dan kata sandi, lalu coba lagi."
    )
    footer = "Sandbox: not the real SAP IAS" if is_english else "Sandbox: bukan SAP IAS asli"
    inputs = "".join(
        f'<input type="hidden" name="{html.escape(name, quote=True)}" '
        f'value="{html.escape(value, quote=True)}">'
        for name, value in hidden_fields.items()
    )
    error_html = (
        f'<div class="error" role="alert" aria-live="polite"><span aria-hidden="true">!</span>'
        f"<p>{error_title}</p></div>"
        if error
        else ""
    )
    safe_username = html.escape(username, quote=True)
    safe_language = "en" if is_english else "id"
    return f"""<!doctype html>
<html lang="{safe_language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{title}</title>
  <style>
    :root {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; color: #172235; background: #edf3f7; font-synthesis: none; text-rendering: optimizeLegibility; }}
    * {{ box-sizing: border-box; }}
    body {{ min-width: 320px; min-height: 100vh; margin: 0; display: grid; place-items: center; padding: 28px 16px; background: radial-gradient(ellipse at 82% 15%, rgba(45,212,191,.20), transparent 34%), radial-gradient(ellipse at 12% 90%, rgba(56,189,248,.15), transparent 35%), #edf3f7; }}
    main {{ width: min(100%, 450px); }}
    .brand {{ display: flex; align-items: center; gap: 12px; margin: 0 0 20px 4px; color: #172235; font-size: 13px; font-weight: 850; letter-spacing: .16em; }}
    .mark {{ display: grid; width: 42px; height: 42px; place-items: center; border-radius: 13px; background: #2dd4bf; color: #10243a; font-size: 19px; box-shadow: 0 7px 22px rgba(15,118,110,.2); }}
    .card {{ border: 1px solid rgba(255,255,255,.82); border-radius: 26px; padding: clamp(24px, 6vw, 40px); background: rgba(255,255,255,.84); box-shadow: 0 24px 70px rgba(15,35,55,.14); backdrop-filter: blur(16px); }}
    .eyebrow {{ margin: 0; color: #0f766e; font-size: 11px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; }}
    h1 {{ margin: 10px 0 0; font-size: clamp(26px, 7vw, 34px); line-height: 1.15; letter-spacing: -.035em; }}
    .subtitle {{ margin: 12px 0 24px; color: #526174; font-size: 14px; line-height: 1.55; }}
    label {{ display: block; margin: 16px 0 7px; color: #28374a; font-size: 13px; font-weight: 750; }}
    input {{ width: 100%; min-height: 48px; border: 1px solid #cbd5e1; border-radius: 11px; padding: 11px 13px; background: #fff; color: #172235; font: inherit; }}
    input:focus-visible, button:focus-visible {{ outline: 3px solid #0f766e; outline-offset: 3px; }}
    .password-wrap {{ display: flex; gap: 8px; }}
    .password-wrap input {{ min-width: 0; }}
    button {{ min-height: 44px; border: 0; border-radius: 11px; padding: 10px 15px; font: inherit; font-weight: 750; cursor: pointer; }}
    .show {{ flex: 0 0 auto; border: 1px solid #cbd5e1; background: #f8fafc; color: #26364a; font-size: 12px; }}
    .primary {{ width: 100%; margin-top: 22px; background: #0f766e; color: #fff; box-shadow: 0 8px 20px rgba(15,118,110,.18); }}
    .primary:hover {{ background: #115e59; }}
    .quick {{ display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 18px; }}
    .quick span {{ width: 100%; color: #526174; font-size: 12px; }}
    .chip {{ min-height: 34px; border: 1px solid #99f6e4; border-radius: 999px; background: #f0fdfa; color: #115e59; font-size: 12px; }}
    .error {{ display: flex; gap: 10px; align-items: flex-start; margin: 18px 0; border: 1px solid #fda4af; border-radius: 12px; padding: 12px 14px; background: #fff1f2; color: #881337; font-size: 13px; line-height: 1.5; }}
    .error p {{ margin: 0; }}
    footer {{ margin-top: 18px; color: #526174; text-align: center; font-size: 12px; }}
    @media (prefers-color-scheme: dark) {{
      :root {{ color: #e2e8f0; background: #0b1220; }}
      body {{ background: radial-gradient(ellipse at 82% 15%, rgba(13,148,136,.24), transparent 34%), #0b1220; }}
      .brand, h1 {{ color: #f1f5f9; }}
      .card {{ border-color: #334155; background: rgba(17,30,48,.9); }}
      .subtitle, .quick span, footer {{ color: #cbd5e1; }}
      label {{ color: #e2e8f0; }}
      input {{ border-color: #475569; background: #0b1220; color: #e2e8f0; }}
      .show {{ border-color: #475569; background: #172235; color: #e2e8f0; }}
      .chip {{ border-color: #115e59; background: #123a3a; color: #ccfbf1; }}
      .error {{ border-color: #9f1239; background: #3b1020; color: #ffe4e6; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important; }} }}
  </style>
</head>
<body>
  <main>
    <div class="brand"><span class="mark" aria-hidden="true">C</span><span>CHAINMIND</span></div>
    <section class="card" aria-labelledby="page-title">
      <p class="eyebrow">Autonomous Disruption Resolver</p>
      <h1 id="page-title">{title}</h1>
      <p class="subtitle">{subtitle}</p>
      {error_html}
      <form method="post" action="/oidc/login">
        {inputs}
        <label for="username">{user_label}</label>
        <input id="username" name="username" value="{safe_username}" autocomplete="username" required>
        <label for="password">{password_label}</label>
        <div class="password-wrap">
          <input id="password" name="password" type="password" autocomplete="current-password" required>
          <button class="show" type="button" id="toggle-password" aria-pressed="false">{show_password}</button>
        </div>
        <div class="quick" aria-label="{choose_account}">
          <span>{choose_account}</span>
          <button class="chip" type="button" data-username="approver">{approver}</button>
          <button class="chip" type="button" data-username="viewer">{viewer}</button>
        </div>
        <button class="primary" type="submit">{sign_in}</button>
      </form>
    </section>
    <footer>{footer}</footer>
  </main>
  <script>
    const username = document.getElementById("username");
    const password = document.getElementById("password");
    document.querySelectorAll("[data-username]").forEach((button) => button.addEventListener("click", () => {{
      username.value = button.dataset.username;
      username.focus();
    }}));
    document.getElementById("toggle-password").addEventListener("click", (event) => {{
      const button = event.currentTarget;
      const reveal = password.type === "password";
      password.type = reveal ? "text" : "password";
      button.setAttribute("aria-pressed", String(reveal));
      button.textContent = reveal ? "{hide_password}" : "{show_password}";
    }});
  </script>
</body>
</html>"""


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
        ui_locales: str = "id",
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
        language = "en" if ui_locales == "en" else "id"
        hidden_fields = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "ui_locales": language,
        }
        return HTMLResponse(_login_page(hidden_fields, language=language))

    @app.post("/oidc/login")
    async def login(request: Request) -> Response:
        fields = {
            key: value[0]
            for key, value in parse_qs((await request.body()).decode("utf-8")).items()
            if value
        }
        hidden_fields = {
            key: fields.get(key, "")
            for key in ("client_id", "redirect_uri", "state", "nonce", "code_challenge")
        }
        language = "en" if fields.get("ui_locales") == "en" else "id"
        hidden_fields["ui_locales"] = language
        user = users.get(fields.get("username", ""))
        if user is None or not secrets.compare_digest(user["password"], fields.get("password", "")):
            return HTMLResponse(
                _login_page(
                    hidden_fields,
                    language=language,
                    username=fields.get("username", ""),
                    error=True,
                ),
                status_code=401,
            )
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
            "tenant_id": "demo",
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
