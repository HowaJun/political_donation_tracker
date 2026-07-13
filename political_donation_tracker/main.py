"""Run the Political Donation Tracker API."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

import uvicorn
from dotenv import load_dotenv

from app.config import settings


def main() -> None:
    load_dotenv(BACKEND / ".env")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
