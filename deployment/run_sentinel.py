"""Entry point for compiled SENTINEL backend.
Replaces uvicorn CLI invocation for PyInstaller builds."""
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info")
    uvicorn.run("app.main:app", host=host, port=port, log_level=log_level, reload=False)
