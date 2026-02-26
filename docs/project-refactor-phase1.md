# 工程化重构（阶段 1）：`modules -> services`

## 目标

- 将后端“核心实现层”从泛化命名 `backend.modules` 收敛到语义更明确的 `backend.services`。
- 保持运行行为不变。
- 保留旧导入兼容层，保证可回滚。

## 路径映射（`old_path -> new_path`）

- `backend/modules/archive.py -> backend/services/archive.py`
- `backend/modules/comic_reader.py -> backend/services/comic_reader.py`
- `backend/modules/filesystem.py -> backend/services/filesystem.py`
- `backend/modules/range_parser.py -> backend/services/range_parser.py`
- `backend/modules/video_stream.py -> backend/services/video_stream.py`
- `backend/modules/__init__.py -> backend/services/__init__.py`（语义上拆分为“兼容包”和“实现包”）

## 兼容策略

- `backend/modules/*.py` 现在作为兼容层，仅做转发：
  - `from backend.services.xxx import *`
- 新代码统一使用 `backend.services.*`。
- 旧代码仍可通过 `backend.modules.*` 导入，不会立即中断。

## 本阶段改动清单

- 新增目录与实现包：
  - `backend/services/`
- 更新调用方导入路径：
  - `backend/routers/files.py`
  - `backend/routers/video.py`
  - `backend/routers/comic.py`
  - `backend/routers/archive.py`
  - `tests/test_core.py`
- 保留兼容层：
  - `backend/modules/*.py`
  - `backend/modules/__init__.py`

## 验证命令

```powershell
.\.venv\Scripts\python -m py_compile backend\routers\files.py backend\routers\video.py backend\routers\comic.py tests\test_core.py
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -c "import backend.main; print('import-ok')"
```

## 验证结果

- 语法检查通过。
- 测试通过：`26 passed`。
- 应用导入通过：`import-ok`。

## 回滚方案

1. 把 `backend/routers/*` 与 `tests/test_core.py` 的 `backend.services.*` 导入改回 `backend.modules.*`。
2. 保留当前 `backend/modules` 兼容层不变即可正常运行。
3. 若需要完全撤销结构迁移，可删除 `backend/services/` 并恢复旧实现文件。

