"""Run the FastAPI app with host/port from .env (HOST, PORT)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

_project_root = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(_project_root / ".env", override=False)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

if __name__ == "__main__":
    import uvicorn

    from .main import app

    uvicorn.run(app, host=HOST, port=PORT)
