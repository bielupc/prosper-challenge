#
# Audit logging for the voice agent's tool calls and conversation.
#
# Tool handlers are wrapped by `audited(...)`, which records the LLM arguments,
# the EHR API exchange (captured via the `_http_exchange` context var that
# `record_http` writes into), and the result handed back to the LLM. Everything
# is shipped to the EHR API over the bot's existing authenticated httpx client.
# Audit failures are swallowed — they must never break a live call.
#
import contextvars
import json
import time
from typing import Any, Awaitable, Callable, Optional

import httpx
from loguru import logger

# Holds the in-flight tool call's HTTP exchange. Set by `audited`, written by
# `record_http` (called from inside _ehr_get/_ehr_post), read back when logging.
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
    """Coerce to JSON-serializable, tolerating uuids/dates/sets in tool payloads."""
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

    async def _post(self, path: str, body: dict) -> None:
        try:
            await self._client.post(path, json=_safe(body))
        except Exception:
            logger.exception("Audit POST {} failed", path)

    async def start(self) -> None:
        await self._post("/audit/session", {"session_id": self._session_id})

    async def sync_transcript(self) -> None:
        await self._post(
            "/audit/session",
            {
                "session_id": self._session_id,
                "patient_id": self._state.get("patient_id"),
                "patient_name": self._state.get("patient_name"),
                "transcript": self._get_transcript(),
            },
        )

    async def finish(self) -> None:
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
        # Failure = an HTTP error reached us, or the request raised. Short-circuit
        # handlers that never hit the API (no status, no error) count as success.
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


def audited(
    audit: AuditLogger,
    tool_name: str,
    handler: Callable[[Any], Awaitable[None]],
) -> Callable[[Any], Awaitable[None]]:
    """Wrap a Pipecat tool handler so each invocation is persisted to the audit log."""

    async def wrapped(params: Any) -> None:
        token = _http_exchange.set({})
        start = time.monotonic()
        captured: dict = {}

        original_cb = params.result_callback

        async def capturing_cb(result, *a, **k):
            captured["result"] = result
            return await original_cb(result, *a, **k)

        params.result_callback = capturing_cb
        try:
            await handler(params)
        finally:
            params.result_callback = original_cb
            http = _http_exchange.get()
            _http_exchange.reset(token)
            duration_ms = int((time.monotonic() - start) * 1000)
            try:
                await audit.log_tool_call(
                    tool_name=tool_name,
                    arguments=getattr(params, "arguments", None),
                    http=http,
                    result=captured.get("result"),
                    duration_ms=duration_ms,
                )
                await audit.sync_transcript()
            except Exception:
                logger.exception("Audit logging for {} failed", tool_name)

    return wrapped
