"""Payments router — 2c, scaffolded only.

Per the CEO's phased approval, no real payment data is recorded yet (Legal
review pending, including whether Aura ever processes money or only logs
payments made elsewhere — see docs/phase2/DB_SCHEMA.md open assumption #3).
Every route under this router returns a 501 stub instead of touching the
database, on purpose.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/payments", tags=["payments"])

NOT_AVAILABLE = {
    "detail": "Payments module not yet available — pending Legal review (Phase 2c).",
}


@router.api_route("", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def payments_not_available(full_path: str = ""):
    return JSONResponse(status_code=501, content=NOT_AVAILABLE)
