"""OIDC bearer-token verification and role dependencies for protected API actions."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from urllib.error import URLError

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from chainmind.core.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    """Verified identity claims used by authorization checks."""

    subject: str
    roles: frozenset[str]


class OIDCVerifier:
    """Verify RS256 access tokens against a configured OIDC issuer and JWKS."""

    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.auth_issuer.rstrip("/")
        self._audience = settings.auth_audience
        self._key_client = jwt.PyJWKClient(settings.auth_jwks_url, cache_keys=True, timeout=5)

    def verify(self, token: str) -> AuthenticatedUser:
        """Verify signature, issuer, audience, and expiry before returning claims."""

        try:
            signing_key = self._key_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except (jwt.PyJWTError, URLError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token is invalid or expired.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        raw_roles = claims.get("roles", claims.get("cognito:groups", []))
        if not isinstance(raw_roles, list) or any(not isinstance(role, str) for role in raw_roles):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token contains invalid role claims.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthenticatedUser(subject=str(claims["sub"]), roles=frozenset(raw_roles))


def get_oidc_verifier() -> OIDCVerifier:
    """Build a verifier from the current application settings."""

    settings = get_settings()
    return cached_verifier(settings.auth_issuer, settings.auth_audience, settings.auth_jwks_url)


@lru_cache(maxsize=8)
def cached_verifier(issuer: str, audience: str, jwks_url: str) -> OIDCVerifier:
    """Reuse JWKS clients so signing keys benefit from the client's cache."""

    settings = Settings(auth_issuer=issuer, auth_audience=audience, auth_jwks_url=jwks_url)
    return OIDCVerifier(settings)


def authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    verifier: Annotated[OIDCVerifier, Depends(get_oidc_verifier)],
) -> AuthenticatedUser:
    """Authenticate the request, honoring only the explicit local development bypass."""

    if settings.auth_dev_bypass and settings.mode == "mock":
        return AuthenticatedUser(subject="local-development-bypass", roles=frozenset({"approver"}))
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verifier.verify(credentials.credentials)


def require_approver(
    user: Annotated[AuthenticatedUser, Depends(authenticated_user)],
) -> AuthenticatedUser:
    """Require the verified approver role for financial decisions."""

    if "approver" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The approver role is required for this action.",
        )
    return user
