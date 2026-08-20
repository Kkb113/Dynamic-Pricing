"""Runnable local FastAPI application for the Phase 2 pricing chat backend."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .agent import OpenAIAgentAdapter
from .config import ConfigurationError, Settings
from .contracts import dump_model, validate_model
from .exceptions import PricingAPIError
from .middleware import BodyLimitMiddleware
from .models import ErrorDetail, HealthResponse, PricingChatError, PricingChatRequest, PricingChatResponse, WarningDetail
from .orchestrator import PricingOrchestrator
from .services import ServiceContainer
from .sse import event_payload, format_sse
from .tools import GovernedToolset


def _request_id() -> str:
    return "req_" + uuid.uuid4().hex[:24]


def _error_envelope(request_id: str, code: str, message: str, *, retryable: bool = False, field: str | None = None) -> dict[str, Any]:
    allowed = {
        "INVALID_REQUEST",
        "UNSUPPORTED_INTENT",
        "MISSING_PRICING_CONTEXT",
        "POLICY_REJECTED",
        "UNKNOWN_PRICING_DECISION",
        "INVALID_CANDIDATE_PRICE",
        "MODEL_SUPPORT_LIMIT",
        "ARTIFACT_INTEGRITY_FAILURE",
        "AGENT_NOT_CONFIGURED",
        "AGENT_TIMEOUT",
        "AGENT_RATE_LIMITED",
        "AGENT_CALL_FAILED",
        "AGENT_OUTPUT_INVALID",
        "TOOL_FAILURE",
        "TOOL_VALIDATION_FAILED",
        "INTERNAL_ERROR",
    }
    if code not in allowed:
        code = "INTERNAL_ERROR"
    model = PricingChatError(request_id=request_id, error=ErrorDetail(code=code, message=message[:500], retryable=retryable, field=field))
    validate_model(model, "pricing_chat_error_v1.schema.json")
    return dump_model(model)


class _UnavailableServices:
    """Safe startup placeholder when frozen artifact setup cannot complete."""

    ready = False
    integrity = {"status": "BLOCKED", "code": "ARTIFACT_INTEGRITY_FAILURE"}

    @property
    def integrity_status(self) -> str:
        return "blocked"

    def health(self, *, agent_available: bool) -> dict[str, Any]:
        return {"status": "blocked", "runtime": "local", "contract_version": "1", "agent_available": bool(agent_available), "artifacts_integrity": "blocked"}


def create_app(
    *,
    settings: Settings | None = None,
    container: ServiceContainer | Any | None = None,
    agent_adapter: Any | None = None,
) -> FastAPI:
    """Create an injectable application; no external calls occur at import time."""

    try:
        app_settings = settings or Settings.from_env()
    except ConfigurationError:
        # Keep the module importable, but let health expose a blocked local
        # runtime rather than binding an unsafe host or leaking config values.
        app_settings = Settings()
        container = None

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        _initialize_runtime(application, container, agent_adapter)
        yield
        application.state.orchestrator = None
        application.state.services = None

    application = FastAPI(
        title="Dynamic Pricing Local API",
        version="2.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.services = container
    application.state.orchestrator = None
    application.state.agent = agent_adapter
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.react_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept"],
        expose_headers=[],
    )
    application.add_middleware(BodyLimitMiddleware, max_bytes=app_settings.body_limit_bytes)

    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=_error_envelope(_request_id(), "INVALID_REQUEST", "Request body does not match the versioned pricing chat contract."))

    @application.exception_handler(PricingAPIError)
    async def pricing_error_handler(request: Request, exc: PricingAPIError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_envelope(_request_id(), exc.code, exc.message, retryable=exc.retryable, field=exc.field))

    @application.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Deliberately do not log the exception: provider prompts/tool args
        # must not become logs or artifacts.
        return JSONResponse(status_code=500, content=_error_envelope(_request_id(), "INTERNAL_ERROR", "The local pricing service could not complete the request."))

    @application.get("/api/v1/healthz", response_model=HealthResponse)
    async def healthz(request: Request) -> HealthResponse:
        _initialize_runtime(application, container, agent_adapter)
        services = application.state.services or _UnavailableServices()
        report = services.health(agent_available=bool(getattr(application.state.agent, "available", False)))
        model = HealthResponse.model_validate(report)
        return JSONResponse(status_code=200 if model.status != "blocked" else 503, content=dump_model(model))

    @application.post("/api/v1/pricing/chat", response_model=PricingChatResponse)
    async def pricing_chat(payload: PricingChatRequest, request: Request) -> JSONResponse:
        _initialize_runtime(application, container, agent_adapter)
        orchestrator = application.state.orchestrator
        if orchestrator is None:
            raise PricingAPIError("INTERNAL_ERROR", "The local pricing service is not initialized", status_code=500)
        result = await asyncio.wait_for(orchestrator.handle(payload, _request_id()), timeout=app_settings.request_timeout_seconds)
        return JSONResponse(status_code=200, content=dump_model(result.response), headers={"Cache-Control": "no-store"})

    @application.post("/api/v1/pricing/chat/stream")
    async def pricing_chat_stream(payload: PricingChatRequest, request: Request) -> StreamingResponse:
        _initialize_runtime(application, container, agent_adapter)
        orchestrator = application.state.orchestrator
        request_id = _request_id()

        async def stream() -> AsyncIterator[str]:
            sequence = 0
            try:
                yield format_sse(event_payload("chat.started", request_id, sequence, {"status": "started"}))
                result = await asyncio.wait_for(orchestrator.handle(payload, request_id), timeout=app_settings.request_timeout_seconds) if orchestrator is not None else None
                if result is None:
                    yield format_sse(event_payload("chat.error", request_id, sequence + 1, {"error": {"code": "INTERNAL_ERROR", "message": "The local pricing service is not initialized", "retryable": False}}))
                    return
                for trace in result.traces:
                    sequence += 1
                    status = "completed" if trace.status == "called" else ("failed" if trace.status == "failed" else "started")
                    tool_payload: dict[str, Any] = {"tool_name": trace.tool_name, "status": status, "record_count": trace.record_count}
                    if trace.error_code:
                        tool_payload["error_code"] = trace.error_code
                    yield format_sse(event_payload("chat.tool", request_id, sequence, tool_payload))
                # Numeric claims are intentionally withheld from deltas; they
                # appear only in the validated completed response.
                sequence += 1
                yield format_sse(event_payload("chat.delta", request_id, sequence, {"text": "A validated pricing response is ready."}))
                sequence += 1
                if result.response.status == "failed" and result.response.errors:
                    error = dump_model(result.response.errors[0])
                    yield format_sse(event_payload("chat.error", request_id, sequence, {"error": error}))
                else:
                    yield format_sse(event_payload("chat.completed", request_id, sequence, {"response": dump_model(result.response)}))
            except asyncio.CancelledError:
                raise
            except Exception:
                sequence += 1
                yield format_sse(event_payload("chat.error", request_id, sequence, {"error": {"code": "INTERNAL_ERROR", "message": "The local pricing stream could not complete", "retryable": False}}))

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    return application


def _initialize_runtime(application: FastAPI, container: Any | None, agent_adapter: Any | None) -> None:
    if application.state.orchestrator is not None:
        return
    services = application.state.services or container
    if services is None:
        try:
            services = ServiceContainer.create(application.state.settings.root)
        except Exception:
            services = _UnavailableServices()
    application.state.services = services
    toolset = GovernedToolset(services) if getattr(services, "ready", False) else GovernedToolset.__new__(GovernedToolset)
    if not getattr(services, "ready", False):
        # Avoid constructing SDK tool wrappers around unavailable services.
        toolset = _EmptyToolset()
    agent = agent_adapter or OpenAIAgentAdapter(application.state.settings, toolset)
    application.state.agent = agent
    application.state.orchestrator = PricingOrchestrator(services, agent, toolset=toolset)


class _EmptyToolset:
    names: tuple[str, ...] = ()
    sdk_tools: tuple[Any, ...] = ()

    def drain_trace(self) -> list[Any]:
        return []

    def execute(self, name: str, **kwargs: Any) -> Any:
        return {"error_code": "ARTIFACT_INTEGRITY_FAILURE", "error": "Frozen pricing artifacts are unavailable."}


app = create_app()


__all__ = ["app", "create_app"]
