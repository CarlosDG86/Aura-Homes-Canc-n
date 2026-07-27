"""Tenant router — 2b, scaffolded only.

Per the CEO's phased approval, tenant accounts and tenant PII are not built
yet (Legal review pending). Every route under this router returns a 501
stub instead of touching the database, on purpose — there is no data-writing
logic behind this router at all, so there is nothing to accidentally leak.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/tenant", tags=["tenant"])

NOT_AVAILABLE = {
    "detail": "Tenant portal not yet available — pending Legal review (Phase 2b).",
}


@router.api_route("", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def tenant_not_available(full_path: str = ""):
    return JSONResponse(status_code=501, content=NOT_AVAILABLE)
