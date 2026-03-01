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

---

## 2026-03 Dashboard & 分类接口更新

本次更新将首页改为 Figma 设计风格的媒体库仪表盘，并新增了面向前端分类展示的接口。

### 新增分类能力

- 新增文件类型识别：`music`、`photo`
- 视频进一步按命名规则自动拆分为：`movies`、`tv`
- 汇总分类：`movies`、`tv`、`music`、`photos`、`comics`、`archives`、`others`

### 新增 API

- `GET /api/library/categories`：返回可用分类
- `GET /api/library/overview`：返回总数、分类计数、存储占用、最近添加、精选项
- `GET /api/library/category/{category}`：按分类查询媒体，支持参数：
  - `query`：搜索关键词
  - `sort`：`recent` / `name` / `size`
  - `limit` / `offset`：分页
  - `refresh`：是否强制刷新扫描缓存
- `GET /api/files/raw?path=...`：输出原始媒体文件流（图片/音乐等预览）

### 前端变化

- 布局改为：左侧导航 + 顶栏搜索/视图切换 + 内容区 + 详情弹窗
- 首页新增：精选横幅、分类统计、最近添加、分区内容
- 分类页支持：网格/列表切换、搜索、收藏（本地浏览器存储）
- 详情弹窗支持：
  - 视频：直接播放
  - 音乐：音频试听
  - 照片：大图预览
  - 漫画：封面与页数信息
  - 压缩包：内容列表与在线提取下载

## 2026-03-01 迭代更新（媒体库可用性）

### 新增与修复

- 后端媒体库新增 SQLite 快照落库（`cache/library_snapshot.db`），用于保存扫描结果并在重启后快速恢复。
- `/api/library/overview` 与 `/api/library/category/{category}` 新增参数：`group_tv`（默认 `true`），用于按“剧 -> 分集”聚合展示。
- TV 聚合返回项新增字段（按需出现）：`is_group`、`episode_count`、`season_count`、`episodes`、`episode_no`、`season_no`、`episode_label`。
- 前端详情页新增剧集分集播放（按季分组），并支持直接逐集打开播放流。
- 漫画详情升级为可翻页阅读器（上一页/下一页/跳页/键盘左右键），不再仅显示封面。
- 漫画接口增强：支持 `.rar` 作为漫画包候选；当压缩包没有图片页时返回明确错误。
- 修复主界面滚动问题：桌面端内容区支持纵向滚动，移动端保持可滑动。

### 验证方式

- 编译检查：`\.venv\Scripts\python -m compileall backend tests`
- 测试：`\.venv\Scripts\python -m pytest -q`
- 前端语法检查：`node --check frontend/app.js`

## 2026-03-01 Settings Center

- New API:
  - `GET /api/settings`: read current app settings.
  - `PATCH /api/settings`: update media root and UI settings.
- UI settings persistence file: `config/app_settings.json`.
- `PATCH /api/settings` supports:
  - `media_root_directory`: set media root directory (optional).
  - `create_media_root_if_missing`: auto create root directory when missing.
  - `ui.home_hidden_roots` / `ui.home_hidden_categories`: hide items on homepage.
  - `ui.recent_hidden_roots` / `ui.recent_hidden_categories`: hide items in recent view.
  - `ui.home_featured_enabled`: enable or disable homepage featured banner.
  - `ui.default_layout`: `grid` or `list`.
  - `ui.player_autoplay_default`: default autoplay behavior for series playback.
  - `ui.group_tv_by_default`: default TV grouping behavior.
  - `ui.home_recent_limit`: homepage recent item limit (`1-60`).
  - `ui.category_page_limit`: category page fetch size (`60-500`).

## 2026-03-01 Media Category & Playback Update

- Added new library categories:
  - `anime`
  - `jdrama`
- Comic items now return first-page cover thumbnails in library APIs.
- Added `.vob` to supported video formats and mime mapping.
- Video stream endpoint now auto-switches to compatibility MP4 cache when container is not natively playable by browser.

## 2026-03-01 Comic Reader Upgrade

### What changed

- Added dedicated comic cover endpoint with cache:
  - `GET /api/comic/cover?path=...&max_width=420&quality=72&format=webp`
- Comic cards now use `/api/comic/cover` instead of rendering page 1 on every list request.
- Comic reader UI is now a separate full-screen reader with vertical scroll reading.
- Reader supports lazy loading images, scroll-position page tracking, and page jump.

### Format support

- Comic archives:
  - `.cbz`, `.zip`
  - `.cbr`, `.rar`
  - `.cb7`, `.7z`
  - `.cbt`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz`, `.txz`
- Image entries:
  - `.jpg`, `.jpeg`, `.jpe`, `.jfif`, `.jfi`, `.jif`
  - `.png`, `.gif`, `.webp`, `.bmp`, `.dib`
  - `.tif`, `.tiff`, `.avif`, `.heic`, `.pbm`, `.pgm`, `.ppm`

### Cache behavior

- Memory cache:
  - metadata cache
  - page bytes cache
  - optimized image cache
  - cover bytes cache
- Disk cache:
  - cover image cache path: `cache/comic_covers/`
- Cache keys include file mtime, so file replacement automatically invalidates old cache.

### Video quick-start stream

- `GET /api/video/stream` supports optional `start` (seconds) when `ios_compat=1`.
- Example: `GET /api/video/stream?path=/demo.mkv&ios_compat=1&start=42.5`
- This mode returns live fragmented MP4 from the requested progress point for faster open/seek.
