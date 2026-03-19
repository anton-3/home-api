import os

from fastapi import Depends, FastAPI

from .routers import garage_router, lights_router
from .utils.api_key_auth import make_api_key_dependency

app = FastAPI()

def _normalize_router_prefix(prefix: str) -> str:
    # Compare env-provided router names against FastAPI router prefixes.
    return (prefix or "").strip().lstrip("/").lower()


def _parse_auth_required(raw: str | None) -> set[str]:
    # AUTH_REQUIRED format: CSV string, e.g. "lights,garage".
    if raw is None:
        return set()
    raw = raw.strip()
    if not raw:
        return set()

    parts = [p.strip() for p in raw.split(",")]
    return {_normalize_router_prefix(p) for p in parts if p}


_auth_required = _parse_auth_required(os.getenv("AUTH_REQUIRED"))
if _auth_required:
    auth_api_key = (os.getenv("AUTH_API_KEY") or "").strip()
    if not auth_api_key:
        raise RuntimeError("AUTH_API_KEY must be set when AUTH_REQUIRED is enabled.")

    available_prefixes = {
        _normalize_router_prefix(r.prefix) for r in (lights_router, garage_router) if _normalize_router_prefix(r.prefix)
    }
    unknown = _auth_required - available_prefixes
    if unknown:
        raise RuntimeError(f"AUTH_REQUIRED contains unknown router prefixes: {sorted(unknown)}")

    api_key_dep = make_api_key_dependency(auth_api_key)
else:
    api_key_dep = None

routers_to_include = (lights_router, garage_router)
for router in routers_to_include:
    if api_key_dep is not None and _normalize_router_prefix(router.prefix) in _auth_required:
        app.include_router(router, dependencies=[Depends(api_key_dep)])
    else:
        app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

