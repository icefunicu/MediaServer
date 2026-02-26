"""
速率限制中间件

使用 slowapi 实现请求速率限制。
"""

import time
from collections import defaultdict
from typing import Dict

from fastapi import FastAPI, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceededError

from backend.config import get_config
from backend.logging_config import get_logger


logger = get_logger("rate_limiter")


limiter = Limiter(key_func=get_remote_address)

rate_limit_storage: Dict[str, list] = defaultdict(list)


def cleanup_old_requests(ip: str, current_time: float, window: int) -> None:
    """清理过期的请求记录"""
    rate_limit_storage[ip] = [
        t for t in rate_limit_storage[ip]
        if current_time - t < window
    ]


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceededError) -> HTTPException:
    """处理速率限制超出错误"""
    logger.warning(
        f"速率限制触发 - IP: {request.client.host}, 路径: {request.url.path}"
    )
    return HTTPException(
        status_code=429,
        detail="请求过于频繁，请稍后再试"
    )


def setup_rate_limiter(app: FastAPI) -> None:
    """设置速率限制器"""
    config = get_config()
    rate_limit = config.security.rate_limit_per_minute

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceededError, rate_limit_exceeded_handler)

    logger.info(f"速率限制已启用: {rate_limit} 请求/分钟")
