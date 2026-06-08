"""EHR API client helpers shared by bot.py and flows/nodes.py."""
import os

import httpx
from loguru import logger

try:
    from audit import record_http
except ImportError:
    def record_http(*args, **kwargs):  # noqa: E302
        pass

_EHR_BASE = os.environ.get("EHR_API_BASE_URL")
_EHR_HEADERS = {"X-API-Key": os.environ.get("EHR_API_KEY", "")}


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=_EHR_BASE, headers=_EHR_HEADERS, timeout=10.0)


def _friendly_error(resp: httpx.Response) -> dict:
    if 400 <= resp.status_code < 500:
        try:
            detail = resp.json().get("detail")
        except Exception:
            detail = None
        if isinstance(detail, str):
            return {"detail": detail}
        return {"detail": "The request was invalid. Please double-check the details and try again."}
    return {"detail": "The scheduling system is temporarily unavailable. Please try again."}


async def ehr_post(client: httpx.AsyncClient, path: str, body: dict) -> tuple[bool, dict]:
    try:
        resp = await client.post(path, json=body)
    except httpx.RequestError as e:
        logger.exception("EHR POST %s failed", path)
        record_http("POST", path, body, None, None, error=str(e))
        return False, {"detail": "Could not reach the scheduling system. Please try again."}
    payload = resp.json() if resp.content else None
    record_http("POST", path, body, resp.status_code, payload)
    if resp.is_success:
        return True, payload
    logger.warning("EHR POST %s -> %s: %s", path, resp.status_code, resp.text)
    return False, _friendly_error(resp)


async def ehr_get(client: httpx.AsyncClient, path: str, params: dict) -> tuple[bool, dict | list]:
    try:
        resp = await client.get(path, params=params)
    except httpx.RequestError as e:
        logger.exception("EHR GET %s failed", path)
        record_http("GET", path, params, None, None, error=str(e))
        return False, {"detail": "Could not reach the scheduling system. Please try again."}
    payload = resp.json() if resp.content else None
    record_http("GET", path, params, resp.status_code, payload)
    if resp.is_success:
        return True, payload
    logger.warning("EHR GET %s -> %s: %s", path, resp.status_code, resp.text)
    return False, _friendly_error(resp)
