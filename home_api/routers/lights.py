from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, conint

from home_api.utils.wiz import (
    LIGHTS_MAP,
    LightConfigError,
    LightInputError,
    LightResult,
    set_brightness,
    set_rgb,
    turn_off,
    turn_on,
)

router = APIRouter(prefix="/lights", tags=["lights"])


class BrightnessRequest(BaseModel):
    brightness: conint(ge=0, le=255)  # type: ignore[valid-type]
    light_id: Optional[str] = None


class ColorRequest(BaseModel):
    rgb: List[conint(ge=0, le=255)] = Field(..., min_length=3, max_length=3)  # type: ignore[valid-type]
    light_id: Optional[str] = None


def _raise_for_result(result: LightResult) -> None:
    """Raise an HTTP error when all targets failed, otherwise return cleanly."""
    if result["succeeded"] or not result["failed"]:
        return
    # All targets failed – treat as upstream failure.
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=result,
    )


@router.get("")
async def list_lights() -> dict:
    """List configured lights from LIGHTS_MAP."""
    items = [{"id": light_id } for light_id in LIGHTS_MAP.keys()]
    return {"items": items}


@router.post("/on")
async def lights_on(light_id: Optional[str] = Query(default=None)) -> dict:
    """Turn on a single light, or all lights when light_id is omitted."""
    try:
        result = await turn_on(light_id=light_id)
    except LightInputError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LightConfigError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    _raise_for_result(result)
    return result


@router.post("/off")
async def lights_off(light_id: Optional[str] = Query(default=None)) -> dict:
    """Turn off a single light, or all lights when light_id is omitted."""
    try:
        result = await turn_off(light_id=light_id)
    except LightInputError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LightConfigError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    _raise_for_result(result)
    return result


@router.post("/brightness")
async def set_light_brightness(payload: BrightnessRequest) -> dict:
    """Set brightness for a single light, or all lights."""
    try:
        result = await set_brightness(brightness=payload.brightness, light_id=payload.light_id)
    except LightInputError as exc:
        # Invalid light_id or brightness outside allowed range.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LightConfigError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    _raise_for_result(result)
    return result


@router.post("/color")
async def set_light_color(payload: ColorRequest) -> dict:
    """Set RGB color for a single light, or all lights."""
    rgb_tuple = (payload.rgb[0], payload.rgb[1], payload.rgb[2])
    try:
        result = await set_rgb(rgb=rgb_tuple, light_id=payload.light_id)
    except LightInputError as exc:
        # Invalid light_id or RGB components outside allowed range.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LightConfigError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    _raise_for_result(result)
    return result

