from fastapi import APIRouter

router = APIRouter(prefix="/lights", tags=["lights"])


@router.get("")
async def list_lights() -> dict:
    return {
        "items": [
            {"id": "kitchen", "is_on": True, "brightness": 80},
            {"id": "bedroom", "is_on": False, "brightness": 0},
        ]
    }


@router.get("/{light_id}")
async def get_light(light_id: str) -> dict:
    return {"id": light_id, "is_on": False, "brightness": 0}


@router.post("/{light_id}/toggle")
async def toggle_light(light_id: str) -> dict:
    return {"id": light_id, "is_on": True, "brightness": 100, "mock": True}
