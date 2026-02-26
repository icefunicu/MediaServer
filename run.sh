#!/bin/bash

echo "========================================"
echo "  本地媒体服务器启动脚本"
echo "========================================"
echo

# 检查虚拟环境
if [ ! -f ".venv/bin/python" ]; then
    echo "[错误] 虚拟环境不存在，请先运行安装脚本"
    exit 1
fi

# 检查配置文件
if [ ! -f "config/config.yaml" ]; then
    echo "[警告] 配置文件不存在，将使用默认配置"
fi

# 启动服务器
echo "[信息] 正在启动服务器..."
echo "[信息] 访问地址: http://localhost:8001"
echo "[信息] API文档: http://localhost:8001/docs"
echo "[信息] 提示: 设置 MEDIA_SERVER_RELOAD=1 可启用热重载（仅开发）"
echo

RELOAD_FLAG=""
if [ "${MEDIA_SERVER_RELOAD:-0}" = "1" ]; then
    RELOAD_FLAG="--reload"
fi

.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 $RELOAD_FLAG
