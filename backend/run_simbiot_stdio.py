"""
Direct entry point for SIMBIOT stdio MCP server.

Avoids importing the full app.mcp module which has dependencies
that may not be available in all environments.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Import only what we need
from app.mcp.simbiot_stdio import main

if __name__ == "__main__":
    asyncio.run(main())
