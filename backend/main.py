"""
本地媒体服务器 - FastAPI 应用入口

基于 Python + FastAPI 的轻量级文件服务系统，
支持视频流媒体播放、漫画阅读、文件浏览和压缩包解压预览。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import get_config, load_config
from backend.logging_config import get_logger, setup_logging
from backend.routers import archive, comic, files, library, settings, video
from backend.middleware.error_handler import setup_error_handlers
from backend.middleware.concurrency_limiter import setup_concurrency_limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger = get_logger("main")
    config = get_config()

    logger.info("本地媒体服务器启动")
    logger.info(f"媒体根目录: {config.media.root_directory}")
    logger.info(f"服务器监听地址: {config.server.host}:{config.server.port}")

    yield

    logger.info("本地媒体服务器关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    load_config()
    setup_logging()

    config = get_config()

    app = FastAPI(
        title="本地媒体服务器",
        description="基于 Python + FastAPI 的轻量级文件服务系统，支持视频流媒体播放、漫画阅读、文件浏览和压缩包解压预览。",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "HEAD"],
        allow_headers=["*"],
    )

    setup_error_handlers(app)
    setup_concurrency_limiter(app)

    @app.middleware("http")
    async def frontend_cache_bypass(request, call_next):
        response = await call_next(request)
        request_path = request.url.path
        if request_path == "/" or request_path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    async def health_check():
        """健康检查端点"""
        return {
            "status": "healthy",
            "service": "local-media-server",
            "version": "1.0.0"
        }

    app.include_router(files.router)
    app.include_router(settings.router)
    app.include_router(library.router)
    app.include_router(video.router)
    app.include_router(comic.router)
    app.include_router(archive.router)

    frontend_path = Path(__file__).parent.parent / "frontend"
    if frontend_path.exists():
        @app.get("/")
        async def serve_index():
            return FileResponse(
                frontend_path / "index.html",
                headers={"Cache-Control": "no-store"}
            )

        app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run(
        "backend.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.debug,
        log_level=config.log.level.lower()
    )
