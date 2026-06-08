import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse

_PUBLIC_PATHS = {"/docs", "/openapi.json", "/redoc", "/health"}
_PUBLIC_PREFIXES = ("/simulate/stream/",)


async def api_key_middleware(request: Request, call_next):
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
        return await call_next(request)
    expected = os.environ.get("EHR_API_KEY")
    if not expected:
        return JSONResponse(status_code=500, content={"detail": "Server API key not configured"})
    api_key = request.headers.get("X-API-Key")
    if not api_key or not hmac.compare_digest(api_key, expected):
        return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
    return await call_next(request)
