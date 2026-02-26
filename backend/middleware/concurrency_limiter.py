"""
并发连接限制中间件

限制最大并发连接数。
"""

import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import get_config
from backend.logging_config import get_logger


logger = get_logger("concurrency_limiter")


class ConcurrencyLimiter(BaseHTTPMiddleware):
    """并发连接限制器"""

    def __init__(self, app: FastAPI, max_connections: int):
        super().__init__(app)
        self.max_connections = max_connections
        self.current_connections = 0
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        async with self._lock:
            if self.current_connections >= self.max_connections:
                logger.warning(
                    f"并发连接数超限 - 当前: {self.current_connections}, "
                    f"最大: {self.max_connections}, IP: {request.client.host}"
                )
                raise HTTPException(
                    status_code=503,
                    detail="服务器繁忙，请稍后再试"
                )
            self.current_connections += 1

        try:
            response = await call_next(request)
            return response
        finally:
            async with self._lock:
                self.current_connections -= 1


_concurrency_limiter: Optional[ConcurrencyLimiter] = None


def setup_concurrency_limiter(app: FastAPI) -> None:
    """设置并发连接限制器"""
    global _concurrency_limiter

    config = get_config()
    max_connections = config.security.max_concurrent_connections

    app.add_middleware(ConcurrencyLimiter, max_connections=max_connections)

    logger.info(f"并发连接限制已启用: 最大 {max_connections} 连接")
