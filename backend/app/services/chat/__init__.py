"""
Chat Tool Modules - Organized by Domain

The original chat_tools.py (2474 lines) has been split into domain-specific modules
for better maintainability and testability.

Tool categories:
- device: Device control, queries, status
- system: System status, diagnostics
- analysis: Equipment analysis, health, optimization
- niagara: Niagara point management and discovery
- solar: Solar PV and BESS operations
- security: Security and fire system status

Total: 22 tools across 6 domains

Each module provides typed tool handlers callable by Claude AI.
"""
