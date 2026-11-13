"""Authentication helpers for Supabase users and temporary guest sessions."""

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

_bearer_scheme = HTTPBearer(auto_error=False)
_USER_CACHE_TTL_SECONDS = 30
_USER_CACHE_MAX_ENTRIES = 512
_verified_user_cache: OrderedDict[str, tuple[UUID, float]] = OrderedDict()


@dataclass(frozen=True)
class Principal:
    """Verified user identity or a temporary guest session."""

    user_id: UUID | None = None
    guest_session_hash: str | None = None

    @property
    def is_guest(self) -> bool:
        return self.guest_session_hash is not None


def hash_guest_token(token: str) -> str:
    """Hash guest credentials before they are stored or compared."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    guest_session: str | None = Header(default=None, alias="X-Guest-Session"),
) -> Principal:
    """Validate a Supabase access token or accept a guest session credential."""
    if credentials is not None:
        token_hash = hash_guest_token(credentials.credentials)
        cached_user = _verified_user_cache.get(token_hash)
        if cached_user is not None:
            user_id, expires_at = cached_user
            if expires_at > time.monotonic():
                _verified_user_cache.move_to_end(token_hash)
                return Principal(user_id=user_id)
            del _verified_user_cache[token_hash]

        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_anon_key:
            raise HTTPException(
                status_code=503,
                detail="Google sign-in is not configured on the backend.",
            )
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                    headers={
                        "apikey": settings.supabase_anon_key,
                        "Authorization": f"Bearer {credentials.credentials}",
                    },
                )
        except httpx.RequestError as error:
            raise HTTPException(
                status_code=503,
                detail="Could not verify the sign-in session. Please retry.",
            ) from error

        if response.status_code in {401, 403}:
            raise HTTPException(status_code=401, detail="Sign-in session is invalid or expired.")
        if response.status_code != 200:
            raise HTTPException(status_code=503, detail="Could not verify the sign-in session.")
        try:
            user_id = UUID(response.json()["id"])
        except (KeyError, TypeError, ValueError, httpx.DecodingError) as error:
            raise HTTPException(status_code=401, detail="Sign-in session is invalid.") from error
        _verified_user_cache[token_hash] = (
            user_id,
            time.monotonic() + _USER_CACHE_TTL_SECONDS,
        )
        _verified_user_cache.move_to_end(token_hash)
        while len(_verified_user_cache) > _USER_CACHE_MAX_ENTRIES:
            _verified_user_cache.popitem(last=False)
        return Principal(user_id=user_id)

    if guest_session is not None:
        if len(guest_session) < 32 or len(guest_session) > 256:
            raise HTTPException(status_code=401, detail="Guest session is invalid.")
        return Principal(guest_session_hash=hash_guest_token(guest_session))

    raise HTTPException(
        status_code=401,
        detail="Sign in with Google or continue as a guest to use AgentForge.",
    )
