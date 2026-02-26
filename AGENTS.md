# AGENTS.md

> 本文件面向自动化 Agent 与人工协作者，基于仓库扫描结果重写。更新时间：2026-02-27。

## 1. 目标与适用范围

- 目标：在不引入行为回归的前提下，保持改动可回滚、可验证、可审计。
- 范围：适用于本仓库所有协作行为（开发、测试、评审、维护）。

## 2. 仓库画像（可验证事实）

- 项目：`local-media-server`（见 `pyproject.toml`）。
- 技术栈：`Python + FastAPI` 后端，原生 `HTML/CSS/JavaScript` 前端静态资源。
- 依赖清单：
  - `pyproject.toml`
  - `requirements.txt`
- 启动脚本：
  - Windows: `run.bat`
  - Linux/macOS: `run.sh`
- 关键目录：
  - `backend/`：服务端代码
  - `frontend/`：静态前端
  - `config/`：配置文件
  - `tests/`：测试用例
  - `docs/`：文档
- CI/部署信号：
  - 未检测到 CI 配置（如 `.github/workflows`、GitLab CI、Azure Pipeline）。
  - 未检测到明确部署编排文件（需按实际环境补充）。

## 3. 代码边界与结构约定

- 入口：`backend/main.py`（`create_app()` + 路由注册）。
- API 路由层：`backend/routers/`。
- 业务实现层：`backend/services/`（新代码优先使用）。
- 兼容层：`backend/modules/`（历史导入兼容，不作为新增实现首选位置）。
- 配置：`config/config.yaml`。
- 前端静态资源：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`。

## 4. 安全与变更红线

- 禁止执行破坏性命令（如清库、强推受保护分支、覆盖生产配置）。
- 禁止提交或输出敏感信息（密钥、令牌、Cookie、私钥、连接串）。
- 禁止执行来源不明脚本或未审计的下载执行链路（如 `curl | bash`）。
- 涉及权限、用户数据、外网暴露面时，先给出风险点与防护措施，再实施改动。

## 5. 质量门禁与验证命令

以下命令为当前仓库可复现的基础验证：

1. 语法与编译检查  
`.\.venv\Scripts\python -m compileall backend tests`

2. 测试  
`.\.venv\Scripts\python -m pytest -q`

3. 应用可导入性（快速烟测）  
`.\.venv\Scripts\python -c "import backend.main; print('import-ok')"`

可选门禁（需要先安装 dev 依赖）：

1. 静态类型检查  
`.\.venv\Scripts\python -m mypy .`

2. 打包检查  
`.\.venv\Scripts\python -m build`

说明：当前环境实测 `mypy` 与 `build` 模块未安装，直接执行会失败。

## 6. 提交与评审规范

- Commit message 使用 Conventional Commits：
  - `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`, `build`
- 单次提交聚焦单一问题，避免功能改动与大规模重构混杂。
- 变更说明必须包含：
  - What（改了什么）
  - Why（为什么改）
  - How to verify（如何验证：命令 + 预期结果）
- 评审优先关注：行为回归、边界条件、异常处理、性能退化、兼容性。

## 7. Agent 执行清单

开始前：

- 明确需求边界、影响范围、回滚路径。
- 确认是否影响启动方式、配置项、API 或前端行为。

执行中：

- 小步改动，单点验证。
- 先复用现有模块与约定，再新增抽象。
- 遇到异常变更或不确定风险，先停并说明。

结束前：

- 运行并记录验证命令结果，不得“口头通过”。
- 总结改动文件、风险点、已知限制。
- 若改动使用方式或结构，补充 `README` 或 `docs/` 文档。

