"""
错误处理中间件

提供全局异常处理器和自定义异常类。
"""

from typing import Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.logging_config import get_logger


logger = get_logger("error_handler")


class ErrorResponse(BaseModel):
    """错误响应模型"""
    detail: str
    error_type: str
    status_code: int


class SecurityError(Exception):
    """安全错误异常"""
    def __init__(self, message: str = "安全错误"):
        self.message = message
        super().__init__(self.message)


class ExtractionError(Exception):
    """解压错误异常"""
    def __init__(self, message: str = "解压失败"):
        self.message = message
        super().__init__(self.message)


class RateLimitError(Exception):
    """速率限制异常"""
    def __init__(self, message: str = "请求过于频繁", retry_after: int = 60):
        self.message = message
        self.retry_after = retry_after
        super().__init__(self.message)


async def security_error_handler(request: Request, exc: SecurityError) -> JSONResponse:
    """处理安全错误"""
    logger.warning(
        f"安全错误 - 路径: {request.url.path}, IP: {request.client.host}, 错误: {exc.message}"
    )
    return JSONResponse(
        status_code=403,
        content={
            "detail": exc.message,
            "error_type": "SecurityError",
            "status_code": 403
        }
    )


async def file_not_found_error_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
    """处理文件不存在错误"""
    logger.info(f"文件不存在 - 路径: {request.url.path}, IP: {request.client.host}")
    return JSONResponse(
        status_code=404,
        content={
            "detail": str(exc),
            "error_type": "FileNotFoundError",
            "status_code": 404
        }
    )


async def range_parse_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理 Range 解析错误"""
    logger.warning(f"Range 解析错误 - 路径: {request.url.path}, IP: {request.client.host}")
    return JSONResponse(
        status_code=416,
        content={
            "detail": str(exc),
            "error_type": "RangeParseError",
            "status_code": 416
        }
    )


async def unsupported_format_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """处理不支持的格式错误"""
    logger.info(f"不支持的格式 - 路径: {request.url.path}, IP: {request.client.host}")
    return JSONResponse(
        status_code=415,
        content={
            "detail": str(exc),
            "error_type": "UnsupportedFormatError",
            "status_code": 415
        }
    )


async def extraction_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理解压错误"""
    logger.error(f"解压错误 - 路径: {request.url.path}, IP: {request.client.host}, 错误: {exc}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": str(exc),
            "error_type": "ExtractionError",
            "status_code": 422
        }
    )


async def rate_limit_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理速率限制错误"""
    logger.warning(f"速率限制 - 路径: {request.url.path}, IP: {request.client.host}")
    return JSONResponse(
        status_code=429,
        content={
            "detail": exc.message,
            "error_type": "RateLimitError",
            "status_code": 429
        },
        headers={"Retry-After": str(exc.retry_after)}
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理通用错误"""
    logger.error(f"服务器内部错误 - 路径: {request.url.path}, IP: {request.client.host}, 错误: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误",
            "error_type": "InternalServerError",
            "status_code": 500
        }
    )


def setup_error_handlers(app: FastAPI) -> None:
    """设置全局异常处理器"""
    app.add_exception_handler(SecurityError, security_error_handler)
    app.add_exception_handler(FileNotFoundError, file_not_found_error_handler)
    app.add_exception_handler(ValueError, unsupported_format_error_handler)
    app.add_exception_handler(ExtractionError, extraction_error_handler)
    app.add_exception_handler(RateLimitError, rate_limit_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)
