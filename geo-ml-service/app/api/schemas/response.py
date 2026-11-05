"""Standard response envelopes shared by the ML service API."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

PayloadT = TypeVar("PayloadT")


class APIResponse(BaseModel, Generic[PayloadT]):
    """Successful API response with an optional typed payload."""

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: PayloadT | None = None
    message: str | None = None


class ErrorDetail(BaseModel):
    """Safe structured validation detail that can be returned to API clients."""

    model_config = ConfigDict(extra="allow")

    location: list[str | int] = Field(default_factory=list)
    message: str
    error_type: str | None = None


class ErrorResponse(BaseModel):
    """Consistent safe error response that intentionally excludes stack traces."""

    model_config = ConfigDict(extra="forbid")

    success: bool = False
    message: str
    error_code: str | None = None
    details: list[ErrorDetail] | None = None


class PaginatedResponse(BaseModel, Generic[PayloadT]):
    """Generic response for bounded list endpoints."""

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: list[PayloadT]
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)


__all__ = [
    "APIResponse",
    "ErrorDetail",
    "ErrorResponse",
    "PaginatedResponse",
]

