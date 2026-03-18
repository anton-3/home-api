from fastapi import FastAPI

from .routers import garage_router, lights_router

app = FastAPI()

app.include_router(lights_router)
app.include_router(garage_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

