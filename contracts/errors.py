"""The single error envelope every service speaks (ADR-H-001).

Clients switch on `code`, never on prose. `message` is for humans and may be
reworded freely; `code` is part of the contract and may not.
"""

from __future__ import annotations

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str = ""


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def envelope(code: str, message: str = "") -> dict:
    """Build the wire form, for `HTTPException(detail=...)`."""
    return ErrorEnvelope(error=ErrorBody(code=code, message=message)).model_dump()
