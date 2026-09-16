"""Phase 2 local FastAPI application boundary.

The package is deliberately presentation-agnostic.  It owns configuration,
read-only service access, contract validation, and the optional provider
adapter; a React client only receives the versioned envelopes exposed here.
"""

from .app import app, create_app

__all__ = ["app", "create_app"]
