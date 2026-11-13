from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.services import auth


@pytest.mark.asyncio
async def test_supabase_access_token_resolves_verified_user(monkeypatch):
    user_id = UUID("76b2c002-4526-45eb-95ba-d7b8637aec4a")
    verification_calls = 0
    settings = SimpleNamespace(
        supabase_url="https://project.supabase.co/",
        supabase_anon_key="public-anon-key",
    )

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"id": str(user_id)}

    class Client:
        def __init__(self, timeout):
            assert timeout == 8.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers):
            nonlocal verification_calls
            verification_calls += 1
            assert url == "https://project.supabase.co/auth/v1/user"
            assert headers == {
                "apikey": "public-anon-key",
                "Authorization": "Bearer access-token",
            }
            return Response()

    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth.httpx, "AsyncClient", Client)

    principal = await auth.get_current_principal(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token"),
        None,
    )
    cached_principal = await auth.get_current_principal(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token"),
        None,
    )

    assert principal.user_id == user_id
    assert not principal.is_guest
    assert cached_principal.user_id == user_id
    assert verification_calls == 1


@pytest.mark.asyncio
async def test_invalid_supabase_token_is_rejected(monkeypatch):
    class Response:
        status_code = 401

    class Client:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://project.supabase.co",
            supabase_anon_key="public-anon-key",
        ),
    )
    monkeypatch.setattr(auth.httpx, "AsyncClient", Client)

    with pytest.raises(HTTPException) as error:
        await auth.get_current_principal(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token"),
            None,
        )

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_guest_token_is_hashed_before_use():
    token = "a" * 64

    principal = await auth.get_current_principal(None, token)

    assert principal.user_id is None
    assert principal.guest_session_hash == auth.hash_guest_token(token)
    assert token not in principal.guest_session_hash
