"""Small ASGI middleware for the local request-size boundary."""

from __future__ import annotations

import json
import uuid
from typing import Any, Awaitable, Callable


class BodyLimitMiddleware:
    def __init__(self, app: Callable[..., Awaitable[Any]], *, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    @staticmethod
    def _request_id() -> str:
        return "req_" + uuid.uuid4().hex[:24]

    async def _reject(self, send: Callable[..., Awaitable[Any]]) -> None:
        request_id = self._request_id()
        payload = {
            "schema_version": "pricing.chat.error.v1",
            "request_id": request_id,
            "status": "error",
            "error": {
                "code": "INVALID_REQUEST",
                "message": "Request body exceeds the 64 KiB local limit",
                "field": "body",
                "retryable": False,
            },
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[Any]], send: Callable[..., Awaitable[Any]]) -> None:
        if scope.get("type") != "http" or not str(scope.get("path", "")).startswith("/api/"):
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        raw_length = headers.get("content-length")
        try:
            if raw_length is not None and int(raw_length) > self.max_bytes:
                await self._reject(send)
                return
        except ValueError:
            await self._reject(send)
            return
        # Buffer at most max_bytes before FastAPI sees the request.  Raising
        # from a receive wrapper would be translated into FastAPI's generic
        # 400 parser error, so the boundary must decide 413 first and replay
        # accepted chunks to the downstream app.
        messages: list[dict[str, Any]] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    await self._reject(send)
                    return
                if not message.get("more_body", False):
                    break
            else:
                break
        index = 0

        async def replay_receive() -> dict[str, Any]:
            nonlocal index
            if index < len(messages):
                value = messages[index]
                index += 1
                return value
            # Preserve the server's real post-body receive channel.  Uvicorn
            # uses it for disconnect detection on streaming responses; a
            # synthetic disconnect here would cancel a healthy SSE stream.
            return await receive()

        await self.app(scope, replay_receive, send)


__all__ = ["BodyLimitMiddleware"]
