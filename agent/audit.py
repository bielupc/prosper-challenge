""" Audit logging for the voice agent's tool calls and conversation."""

import asyncio
import contextvars
import json
import time
from typing import Any, Awaitable, Callable, Optional

import httpx
from loguru import logger

_http_exchange: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "http_exchange", default=None
)


def record_http(
    method: str,
    path: str,
    request_body: Any,
    status: Optional[int],
    response_body: Any,
    error: Optional[str] = None,
) -> None:
    """Attach the EHR request/response to the current tool call, if one is active."""
    ex = _http_exchange.get()
    if ex is None:
        return
    ex.update(
        request_method=method,
        request_path=path,
        request_body=request_body,
        response_status=status,
        response_body=response_body,
        error=error,
    )


def _safe(obj: Any) -> Any:
    try:
        return json.loads(json.dumps(obj, default=str))
    except (TypeError, ValueError):
        return str(obj)


class AuditLogger:
    def __init__(
        self,
        client: httpx.AsyncClient,
        session_id: Any,
        session_state: dict,
        get_transcript: Callable[[], Any],
    ):
        self._client = client
        self._session_id = str(session_id)
        self._state = session_state
        self._get_transcript = get_transcript
        self._finished = False
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def flush_pending(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _post(self, path: str, body: dict) -> None:
        try:
            await self._client.post(path, json=_safe(body))
        except Exception:
            logger.exception("Audit POST {} failed", path)

    async def start(self) -> None:
        await self._post("/audit/session", {"session_id": self._session_id})

    async def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        await self.flush_pending()
        await self._post(
            "/audit/session",
            {
                "session_id": self._session_id,
                "patient_id": self._state.get("patient_id"),
                "patient_name": self._state.get("patient_name"),
                "transcript": self._get_transcript(),
                "ended": True,
            },
        )

    async def log_tool_call(
        self,
        tool_name: str,
        arguments: Any,
        http: Optional[dict],
        result: Any,
        duration_ms: int,
    ) -> None:
        http = http or {}
        status = http.get("response_status")
        error = http.get("error")
        success = error is None and (status is None or status < 400)
        await self._post(
            "/audit/tool_call",
            {
                "session_id": self._session_id,
                "patient_id": self._state.get("patient_id"),
                "patient_name": self._state.get("patient_name"),
                "tool_name": tool_name,
                "arguments": arguments,
                "request_method": http.get("request_method"),
                "request_path": http.get("request_path"),
                "request_body": http.get("request_body"),
                "response_status": status,
                "response_body": http.get("response_body"),
                "result": result,
                "success": success,
                "error": error,
                "duration_ms": duration_ms,
            },
        )


def flows_audited(tool_name: str, handler: Callable) -> Callable:
    """Wrap a Pipecat Flows handler (args, fm) for audit logging."""
    async def wrapped(args: Any, fm: Any):
        audit: Optional[AuditLogger] = fm.state.get("audit")
        token = _http_exchange.set({})
        start = time.monotonic()
        result = None
        try:
            result = await handler(args, fm)
            return result
        except Exception as exc:
            ex = _http_exchange.get()
            if ex is not None and "error" not in ex:
                ex["error"] = repr(exc)
            raise
        finally:
            http = _http_exchange.get()
            _http_exchange.reset(token)
            if audit:
                # Fire-and-forget: audit POSTs must NOT block the handler's return.
                duration_ms = int((time.monotonic() - start) * 1000)
                result_snapshot = result[0] if isinstance(result, tuple) else result

                async def _emit() -> None:
                    try:
                        await audit.log_tool_call(
                            tool_name=tool_name,
                            arguments=args,
                            http=http,
                            result=result_snapshot,
                            duration_ms=duration_ms,
                        )
                    except Exception:
                        logger.exception("Audit logging for {} failed", tool_name)

                audit.spawn(_emit())

    return wrapped
