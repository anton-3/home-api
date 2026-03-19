import hmac
import os
from typing import Awaitable, Callable

try:
    # Optional dependency safety (repo uses dotenv in other utils).
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    from fastapi import HTTPException, Request, status
except ImportError as exc:  # pragma: no cover
    raise exc


def _load_env() -> None:
    # Ensure AUTH_* env vars in `.env` are available when running locally.
    if load_dotenv is None:
        return
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)


_load_env()


def _get_expected_api_key() -> str:
    expected_key = os.getenv("AUTH_API_KEY", "")
    return expected_key.strip()


def make_api_key_dependency(expected_key: str) -> Callable[[Request], Awaitable[None]]:
    """
    Returns a FastAPI dependency that checks `X-API-Key` against `expected_key`.

    Missing/invalid API key returns 401.
    """

    expected_key = (expected_key or "").strip()

    async def _dependency(request: Request) -> None:
        provided = (request.headers.get("X-API-Key") or "").strip()
        if not provided or not hmac.compare_digest(provided, expected_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

    return _dependency


def api_key_dependency_from_env() -> Callable[[Request], Awaitable[None]]:
    """
    Convenience wrapper for building the dependency from `AUTH_API_KEY`.
    """

    expected_key = _get_expected_api_key()
    if not expected_key:
        # Intentionally no specific message to avoid leaking configuration details.
        raise RuntimeError("AUTH_API_KEY must be set when AUTH_REQUIRED is enabled.")
    return make_api_key_dependency(expected_key)

