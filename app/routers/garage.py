from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.utils.garage_opener import (
    GarageConfigError,
    GarageInputError,
    GarageUpstreamError,
    trigger_all,
    trigger_one,
)

router = APIRouter(prefix="/garage", tags=["garage"])


class GarageRequest(BaseModel):
    # When this field is omitted (or when the request body is omitted entirely),
    # we trigger all configured doors.
    door: Optional[str] = None


@router.post("")
async def garage(payload: Optional[GarageRequest] = None) -> Dict[str, Any]:
    try:
        if payload is None or payload.door is None:
            results = await trigger_all()
            return {
                "ok": True,
                "targets": [f"/garage/{r['index']}" for r in results],
            }

        result = await trigger_one(payload.door)
        return {
            "ok": True,
            "target": f"/garage/{result['index']}",
        }
    except GarageInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except GarageConfigError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except GarageUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"failures": exc.failures},
        ) from exc

