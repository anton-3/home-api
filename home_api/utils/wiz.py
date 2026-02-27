import asyncio
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple

from pywizlight import PilotBuilder, wizlight
from pywizlight.exceptions import WizLightConnectionError, WizLightError, WizLightTimeOutError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency safety
    load_dotenv = None

# Ensure LIGHTS_MAP in project .env is available before reading os.getenv.
_project_root = Path(__file__).resolve().parents[2]
if load_dotenv is not None:
    load_dotenv(_project_root / ".env", override=False)

_raw_lights_map = os.getenv("LIGHTS_MAP", "{}")
try:
    _parsed_lights_map = json.loads(_raw_lights_map)
except json.JSONDecodeError:
    _parsed_lights_map = {}

LIGHTS_MAP: dict[str, str] = _parsed_lights_map if isinstance(_parsed_lights_map, dict) else {}

# Timeout in seconds for each light request (on/off, brightness, rgb, state).
LIGHT_REQUEST_TIMEOUT = 5.0


class LightInputError(Exception):
    """Raised when a caller supplies an invalid light identifier or value."""


class LightConfigError(Exception):
    """Raised when LIGHTS_MAP configuration is missing or unusable."""


LightResult = Dict[str, Any]


def _resolve_targets(light_id: Optional[str]) -> Mapping[str, str]:
    """Return mapping of light IDs to IPs for the requested targets."""
    if not LIGHTS_MAP:
        raise LightConfigError("LIGHTS_MAP is empty or not configured.")

    if light_id is None:
        return LIGHTS_MAP

    try:
        ip = LIGHTS_MAP[light_id]
    except KeyError as exc:
        raise LightInputError(f"Unknown light_id '{light_id}'.") from exc

    return {light_id: ip}


def _validate_brightness(brightness: int) -> int:
    if not isinstance(brightness, int):
        raise LightInputError("Brightness must be an integer between 0 and 255.")
    if not 0 <= brightness <= 255:
        raise LightInputError("Brightness must be between 0 and 255.")
    return brightness


def _validate_rgb(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if len(rgb) != 3:
        raise LightInputError("RGB must contain exactly three values.")
    r, g, b = rgb
    for value, name in ((r, "red"), (g, "green"), (b, "blue")):
        if not isinstance(value, int):
            raise LightInputError(f"RGB component '{name}' must be an integer between 0 and 255.")
        if not 0 <= value <= 255:
            raise LightInputError(f"RGB component '{name}' must be between 0 and 255.")
    return r, g, b


async def _run_for_targets(
    *,
    operation: str,
    targets: Mapping[str, str],
    op_factory: Callable[[wizlight], Awaitable[None]],
    extra: Optional[Dict[str, Any]] = None,
) -> LightResult:
    """Execute an operation for one or more targets in parallel."""

    succeeded: List[str] = []
    failed: Dict[str, Dict[str, Any]] = {}

    async def _run_single(light_id: str, ip: str) -> None:
        bulb = wizlight(ip)
        try:
            await asyncio.wait_for(op_factory(bulb), timeout=LIGHT_REQUEST_TIMEOUT)
            succeeded.append(light_id)
        except asyncio.TimeoutError:
            failed[light_id] = {
                "error": f"Request timed out after {LIGHT_REQUEST_TIMEOUT} seconds",
                "type": "TimeoutError",
            }
        except (WizLightTimeOutError, WizLightConnectionError, WizLightError, OSError) as exc:
            failed[light_id] = {"error": str(exc), "type": exc.__class__.__name__}
        except Exception as exc:  # pragma: no cover - defensive
            failed[light_id] = {"error": str(exc), "type": exc.__class__.__name__}
        finally:
            # Best-effort close of the underlying transport.
            try:
                await bulb.async_close()
            except Exception:
                pass

    await asyncio.gather(
        *(_run_single(light_id, ip) for light_id, ip in targets.items()),
        return_exceptions=False,
    )

    result: LightResult = {
        "operation": operation,
        "targets": list(targets.keys()),
        "succeeded": succeeded,
        "failed": failed,
    }
    if extra:
        result.update(extra)
    return result


async def turn_on(light_id: Optional[str] = None) -> LightResult:
    """Turn on a light by id, or all if none specified."""
    targets = _resolve_targets(light_id)

    async def _op(bulb: wizlight) -> None:
        await bulb.turn_on(PilotBuilder())

    return await _run_for_targets(operation="on", targets=targets, op_factory=_op)


async def turn_off(light_id: Optional[str] = None) -> LightResult:
    """Turn off a light by id, or all if none specified."""
    targets = _resolve_targets(light_id)

    async def _op(bulb: wizlight) -> None:
        await bulb.turn_off()

    return await _run_for_targets(operation="off", targets=targets, op_factory=_op)


async def set_brightness(brightness: int, light_id: Optional[str] = None) -> LightResult:
    """Set brightness for a specific light, or all lights."""
    brightness = _validate_brightness(brightness)
    targets = _resolve_targets(light_id)

    async def _op(bulb: wizlight) -> None:
        await bulb.turn_on(PilotBuilder(brightness=brightness))

    return await _run_for_targets(
        operation="brightness",
        targets=targets,
        op_factory=_op,
        extra={"brightness": brightness},
    )


async def set_rgb(rgb: Tuple[int, int, int], light_id: Optional[str] = None) -> LightResult:
    """Set RGB color for a specific light, or all lights."""
    rgb = _validate_rgb(rgb)
    targets = _resolve_targets(light_id)

    async def _op(bulb: wizlight) -> None:
        await bulb.turn_on(PilotBuilder(rgb=rgb))

    return await _run_for_targets(
        operation="rgb",
        targets=targets,
        op_factory=_op,
        extra={"rgb": list(rgb)},
    )


async def get_lights_state(light_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return on/off and brightness for each target light. When off, brightness is 0."""
    targets = _resolve_targets(light_id)

    async def _fetch_one(lid: str, ip: str) -> Dict[str, Any]:
        bulb = wizlight(ip)
        try:
            await asyncio.wait_for(bulb.updateState(), timeout=LIGHT_REQUEST_TIMEOUT)
            state = bulb.state
            if state is None:
                return {"id": lid, "on": False, "brightness": 0}
            on_state = state.get_state()
            try:
                raw_brightness = state.get_brightness()
                brightness = max(0, min(255, raw_brightness)) if raw_brightness is not None else 0
            except (KeyError, TypeError):
                brightness = 0
            if not on_state:
                brightness = 0
            return {"id": lid, "on": on_state, "brightness": brightness}
        except asyncio.TimeoutError:
            return {
                "id": lid,
                "on": False,
                "brightness": 0,
                "error": f"Request timed out after {LIGHT_REQUEST_TIMEOUT} seconds",
            }
        except (WizLightTimeOutError, WizLightConnectionError, WizLightError, OSError, Exception):
            return {"id": lid, "on": False, "brightness": 0}
        finally:
            try:
                await bulb.async_close()
            except Exception:
                pass

    results = await asyncio.gather(
        *(_fetch_one(lid, ip) for lid, ip in targets.items()),
        return_exceptions=False,
    )
    return list(results)

