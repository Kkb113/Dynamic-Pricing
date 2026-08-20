"""Typed, public-safe exceptions used by the FastAPI boundary."""

from __future__ import annotations


class PricingAPIError(Exception):
    """A controlled error with a Phase 1 error code."""

    def __init__(self, code: str, message: str, *, retryable: bool = False, field: str | None = None, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.field = field
        self.status_code = status_code


class BodyTooLargeError(PricingAPIError):
    def __init__(self):
        super().__init__("INVALID_REQUEST", "Request body exceeds the 64 KiB local limit", field="body", status_code=413)


__all__ = ["BodyTooLargeError", "PricingAPIError"]
