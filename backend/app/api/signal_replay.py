"""
Signal Replay API — Phase 159-04
=================================
Endpoint to trigger replay of historical case data through
the signal emitter bridges and correlation engine.

POST /api/signals/replay
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/signals", tags=["signal-replay"])


class ReplayRequest(BaseModel):
    case: str = "fairlands"
    time_window: Optional[dict] = None
    verbose: bool = False


class ReplayResponse(BaseModel):
    case: str
    signals_emitted: int
    signals_deduped: int
    clusters_formed: int
    cluster_states: list[str]
    cards_generated: int
    errors: list[str]


@router.post("/replay", response_model=ReplayResponse)
async def replay_signals(req: ReplayRequest) -> ReplayResponse:
    """Replay a historical case through all signal bridges + correlation.

    Use this to validate clustering behavior against known scenarios.
    """
    from app.services.signal_replay_tool import replay_case

    try:
        result = await replay_case(
            case_name=req.case,
            time_window=req.time_window,
            verbose=req.verbose,
        )
        return ReplayResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Signal replay failed for case '%s'", req.case)
        raise HTTPException(status_code=500, detail=f"Replay failed: {exc}")
