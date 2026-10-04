"""Body and tenant request limits before ingestion or database work."""

import time

from redis import Redis
from redis.exceptions import RedisError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from rag_lab.core.errors import AppError


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = 20000000 if scope["path"] == "/api/v1/documents" else 4000000
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = limit + 1
        if length > limit:
            return await JSONResponse(
                {"code": "too_large", "message": "Body exceeds limit", "request_id": ""},
                status_code=413,
            )(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise HTTPException(status_code=413, detail="Body exceeds limit")
            return message

        await self.app(scope, limited_receive, send)


def throttle(identity, redis_url):
    key = f"rag:rate:{identity.tenant_id}:{int(time.time() // 60)}"
    try:
        with Redis.from_url(redis_url, socket_timeout=3, socket_connect_timeout=3) as redis:
            count = redis.eval(
                "local n=redis.call('INCR',KEYS[1]); "
                "if n==1 then redis.call('EXPIRE',KEYS[1],120) end; return n",
                1,
                key,
            )
    except RedisError as exc:
        raise AppError("rate_limiter_unavailable", "Request limiter is unavailable", 503) from exc
    if count > 120:
        raise AppError("rate_limited", "Tenant request limit reached; retry next minute", 429)
