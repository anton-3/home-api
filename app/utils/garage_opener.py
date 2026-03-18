import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx  # type: ignore[import-not-found]

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency safety
    load_dotenv = None

_project_root = Path(__file__).resolve().parents[2]
if load_dotenv is not None:
    load_dotenv(_project_root / ".env", override=False)


class GarageInputError(Exception):
    """Raised when a caller supplies an invalid/unknown door alias."""


class GarageConfigError(Exception):
    """Raised when garage integration env configuration is missing or invalid."""


class GarageUpstreamError(Exception):
    """Raised when the configured garage opener fails."""

    def __init__(self, failures: List[Dict[str, Any]]):
        self.failures = failures
        super().__init__(f"Upstream garage opener failed for {len(failures)} door(s).")


GarageDoorAliasMap = Dict[int, List[str]]

# Timeout in seconds for each opener request.
GARAGE_REQUEST_TIMEOUT = 5.0

DEFAULT_DOOR_ALIAS_MAP: GarageDoorAliasMap = {
    1: ["north", "left", "1"],
    2: ["south", "right", "2"],
}

_raw_opener_host = os.getenv("GARAGE_OPENER_HOST", "").strip()


def _normalize_alias(alias: str) -> str:
    return alias.strip().lower()


def _parse_default_door_aliases(raw: Optional[str]) -> GarageDoorAliasMap:
    if raw is None or not raw.strip():
        return dict(DEFAULT_DOOR_ALIAS_MAP)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GarageConfigError("DEFAULT_DOOR_ALIASES must be valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise GarageConfigError("DEFAULT_DOOR_ALIASES must be a JSON object mapping index -> list of aliases.")

    alias_map: GarageDoorAliasMap = {}
    for index_key, aliases_value in parsed.items():
        try:
            index = int(index_key)
        except (TypeError, ValueError) as exc:
            raise GarageConfigError("DEFAULT_DOOR_ALIASES keys must be integers (or integer strings).") from exc

        if not isinstance(aliases_value, list) or not all(isinstance(a, str) for a in aliases_value):
            raise GarageConfigError(
                "DEFAULT_DOOR_ALIASES values must be arrays of strings (aliases)."
            )

        normalized_aliases = [_normalize_alias(a) for a in aliases_value if a.strip()]
        if not normalized_aliases:
            raise GarageConfigError(f"Door index {index} has an empty alias list.")

        alias_map[index] = normalized_aliases

    if not alias_map:
        raise GarageConfigError("DEFAULT_DOOR_ALIASES must define at least one door index.")

    return alias_map


_alias_map: GarageDoorAliasMap = _parse_default_door_aliases(os.getenv("DEFAULT_DOOR_ALIASES"))
_door_indices: List[int] = sorted(_alias_map.keys())

_alias_to_index: Dict[str, int] = {}
for _index, _aliases in _alias_map.items():
    for _alias in _aliases:
        if _alias in _alias_to_index and _alias_to_index[_alias] != _index:
            raise GarageConfigError(f"Alias '{_alias}' maps to multiple door indices.")
        _alias_to_index[_alias] = _index


def _require_opener_host() -> str:
    if not _raw_opener_host:
        raise GarageConfigError("GARAGE_OPENER_HOST is missing or empty.")
    return _raw_opener_host


def _build_target_url(index: int) -> str:
    base = _require_opener_host().rstrip("/")
    return f"{base}/garage/{index}"


def resolve_door_to_index(door: str) -> int:
    normalized = _normalize_alias(door)
    try:
        return _alias_to_index[normalized]
    except KeyError as exc:
        raise GarageInputError(f"Unknown door '{door}'.") from exc


async def _post_index(*, client: httpx.AsyncClient, index: int) -> Dict[str, Any]:
    url = _build_target_url(index)
    try:
        resp = await client.post(url)
        return {"index": index, "status_code": resp.status_code}
    except Exception as exc:  # pragma: no cover - depends on network conditions
        return {
            "index": index,
            "status_code": None,
            "error": str(exc),
            "type": exc.__class__.__name__,
        }


async def trigger_one(door_alias: str) -> Dict[str, Any]:
    index = resolve_door_to_index(door_alias)

    async with httpx.AsyncClient(timeout=GARAGE_REQUEST_TIMEOUT) as client:
        result = await _post_index(client=client, index=index)

    if result.get("status_code") != 200:
        raise GarageUpstreamError([result])

    return result


async def trigger_all() -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=GARAGE_REQUEST_TIMEOUT) as client:
        # Start all requests before awaiting any of them, then wait for all results.
        coros = [_post_index(client=client, index=i) for i in _door_indices]
        results = await asyncio.gather(*coros)

    failures = [r for r in results if r.get("status_code") != 200]
    if failures:
        raise GarageUpstreamError(failures)

    return results

