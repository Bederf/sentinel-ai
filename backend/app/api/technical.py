"""Technical chat support endpoints."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.config.demo_configs import get_demo_config_for_email, has_demo_site_access
from app.database.repositories.user_site_access_repository import UserSiteAccessRepository
from app.middleware.auth_middleware import require_auth, AuthLevel
from app.models.auth import AuthContext, SentinelRole
from app.models.audit_log import AuditResultType
from app.services.audit_logger import AuditLogger
from app.services.concept_document_search import (
    ConceptDocumentSearchUnavailable,
    get_concept_document_search_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/technical", tags=["technical"])


class ConceptSearchRequest(BaseModel):
    site_id: str = Field(..., min_length=1)
    building_id: str | None = None
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(10, ge=1, le=25)


class ConceptDocumentSearchResult(BaseModel):
    document_id: str
    concept_document_id: str
    title: str
    document_type: str | None = None
    document_date: str | None = None
    building_name: str | None = None
    equipment_category: str | None = None
    equipment_name: str | None = None
    path: str
    open_url: str
    download_url: str | None = None
    match_reasons: list[str] = []
    snippet: str | None = None


class ConceptSearchResponse(BaseModel):
    mode: Literal["concept_document_search"]
    query: str
    building_id: str
    results: list[ConceptDocumentSearchResult]
    total_matched: int = 0
    total_results: int
    weak_results: bool = False


class ConceptDocumentActionRequest(BaseModel):
    site_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    action: Literal["open", "download"]
    query: str | None = Field(default=None, max_length=500)


def _assert_site_access(auth: AuthContext, site_id: str) -> None:
    if auth.role == SentinelRole.ADMIN:
        return

    email = (auth.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User email missing for site access check")

    demo_config = get_demo_config_for_email(email)
    if demo_config:
        if not has_demo_site_access(email, site_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"You do not have access to site {site_id}"
            )
        return

    repo = UserSiteAccessRepository()
    if not repo.has_access_to_site_code(email, auth.role, site_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"You do not have access to site {site_id}")


@router.post("/concept-search", response_model=ConceptSearchResponse)
async def concept_search(
    payload: ConceptSearchRequest,
    request: Request,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> ConceptSearchResponse:
    _assert_site_access(auth, payload.site_id)

    service = get_concept_document_search_service()
    try:
        response = service.search(
            site_id=payload.site_id,
            building_id=payload.building_id,
            query=payload.query,
            top_k=payload.top_k,
        )
    except ConceptDocumentSearchUnavailable as exc:
        AuditLogger().log_system_event(
            event_type="concept_document_search_unavailable",
            user=auth.user_id,
            result=AuditResultType.FAILURE,
            error_message=str(exc),
            metadata={
                "site_id": payload.site_id,
                "building_id": payload.building_id or payload.site_id,
                "query": payload.query,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Concept document search is currently unavailable.",
        ) from exc

    AuditLogger().log_system_event(
        event_type="concept_document_search",
        user=auth.user_id,
        metadata={
            "site_id": payload.site_id,
            "building_id": payload.building_id or payload.site_id,
            "query": payload.query,
            "result_count": response["total_results"],
            "source_ip": getattr(auth, "source_ip", None),
            "user_agent": request.headers.get("user-agent"),
        },
    )

    return ConceptSearchResponse.model_validate(response)


@router.post(
    "/concept-search/click",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def log_concept_document_click(
    payload: ConceptDocumentActionRequest,
    request: Request,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> Response:
    _assert_site_access(auth, payload.site_id)

    AuditLogger().log_system_event(
        event_type="concept_document_click",
        user=auth.user_id,
        metadata={
            "site_id": payload.site_id,
            "clicked_document_id": payload.document_id,
            "action": payload.action,
            "query": payload.query,
            "source_ip": getattr(auth, "source_ip", None),
            "user_agent": request.headers.get("user-agent"),
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
