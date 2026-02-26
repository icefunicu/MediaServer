# 本地媒体服务器

基于 Python + FastAPI 的轻量级文件服务系统，运行在本地电脑上，允许同一局域网内的设备（手机、iPad、电脑）通过浏览器访问和播放媒体文件。

## 功能特性

- 📁 **文件浏览** - 浏览本地文件系统，支持目录导航和文件搜索
- 🎬 **视频流媒体** - 支持 1080p/4K 视频播放，使用 HTTP Range Requests 实现分片传输
- 📚 **漫画阅读** - 支持 .cbz/.cbr/.zip 格式漫画，下拉式阅读体验
- 📦 **压缩包管理** - 查看压缩包内容，支持解压和下载
- 📱 **响应式设计** - 支持桌面端和移动端，触摸操作优化
- 🔒 **安全防护** - 路径遍历防护、速率限制、并发控制
- ⚡ **性能优化** - 多层缓存、异步 I/O、页面预加载

## 技术栈

- **后端**: Python 3.10+, FastAPI, uvicorn
- **视频处理**: FFmpeg
- **前端**: HTML5, CSS3, JavaScript (原生，无框架)
- **缓存**: cachetools (内存缓存), diskcache (磁盘缓存)

## 环境要求

- Python 3.10 或更高版本
- FFmpeg (用于视频转码)
- Windows / Linux / macOS

## 安装步骤

### 1. 克隆或下载项目

```bash
git clone <repository-url>
cd MediaServer
```

### 2. 创建虚拟环境

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 安装 FFmpeg (可选)

**Windows:**
1. 下载 FFmpeg: https://ffmpeg.org/download.html
2. 将 FFmpeg 添加到系统 PATH

**Linux (Ubuntu):**
```bash
sudo apt update
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### 5. 配置

编辑 `config/config.yaml` 文件：

```yaml
server:
  host: "0.0.0.0"  # 监听地址
  port: 8000        # 监听端口

media:
  root_directory: "./media"  # 媒体文件根目录
```

### 6. 创建媒体目录

将您的视频、漫画等文件放入 `media` 目录。

## 运行

### Windows

```bash
run.bat
```

或手动运行：

```bash
.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Linux/macOS

```bash
chmod +x run.sh
./run.sh
```

或手动运行：

```bash
.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## 访问

- **主界面**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

局域网访问（替换 `192.168.x.x` 为您的局域网 IP）：

```
http://192.168.x.x:8000
```

## 使用说明

### 文件浏览

1. 打开浏览器访问服务器地址
2. 点击文件夹进入子目录
3. 使用搜索框搜索文件

### 视频播放

1. 点击视频文件
2. 视频将使用 HTML5 Player 播放
3. 支持播放、暂停、进度拖动、音量控制

### 漫画阅读

1. 点击漫画文件（.cbz/.cbr/.zip）
2. 使用上下滑动或按钮翻页
3. 系统会自动预加载后续页面

### 压缩包

1. 点击压缩包文件
2. 查看压缩包内容列表
3. 点击文件可下载解压

## API 接口

### 文件管理

```
GET /api/files?path=/          # 列出目录
GET /api/files/search?query=xxx # 搜索文件
GET /api/files/info?path=xxx   # 获取文件信息
```

### 视频

```
GET /api/video/metadata?path=xxx # 获取视频元数据
GET /api/video/stream?path=xxx  # 流式传输视频
GET /api/video/stream?path=xxx&ios_compat=1 # 强制输出 iOS 兼容 MP4 转码流（H264/AAC）
```

### 漫画

```
GET /api/comic/metadata?path=xxx # 获取漫画元数据
GET /api/comic/page?path=xxx&page=1 # 获取漫画页面
```

### 压缩包

```
GET /api/archive/contents?path=xxx   # 获取压缩包内容
GET /api/archive/extract?path=xxx&entry=xxx # 解压文件
```

## 配置说明

详细配置请参考 `config/config.yaml`：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| server.host | 监听地址 | 0.0.0.0 |
| server.port | 监听端口 | 8000 |
| media.root_directory | 媒体文件根目录 | ./media |
| cache.memory_cache_size | 内存缓存大小 | 100MB |
| cache.metadata_ttl | 元数据缓存 TTL | 1小时 |
| security.max_concurrent_connections | 最大并发连接数 | 100 |
| security.rate_limit_per_minute | 每分钟请求限制 | 60 |

## 故障排除

### 视频无法播放

1. 确认 FFmpeg 已正确安装
2. 检查视频格式是否支持（.mp4, .mkv, .ts, .avi, .mov）
3. 尝试使用现代浏览器（Chrome, Firefox, Edge）

### 漫画加载失败

1. 确认压缩包格式正确（.cbz, .cbr, .zip）
2. 确保压缩包内包含图片文件
3. 检查压缩包是否损坏

### 无法访问

1. 检查防火墙设置
2. 确认服务器 IP 地址正确
3. 检查端口是否被占用

### 性能问题

1. 调整缓存配置
2. 增加内存缓存大小
3. 使用 SSD 存储媒体文件

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码格式化

```bash
black backend/
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
