"""GraphStore 工厂（``docs/api.md`` §5，store-builder 写区）。

用法::

    from app.store import get_store
    store = get_store(settings)          # settings 可为 None / dataclass / dict
    evidences = store.execute(spec)      # 已排序去重截断，eid 留空
    store.stats(), store.health()

回落策略
--------
``GRAPH_BACKEND=neo4j`` 但驱动缺失 / 服务连不上 / 认证失败 → 捕获
:class:`BackendFallback`，改用 :class:`LocalStore`，并在返回实例上置::

    store.backend_fallback = True
    store.fallback_reason  = "<失败原因>"

qa 层据此追加 ``WARN_BACKEND_FALLBACK`` 告警；UI 顶部徽标显示 ``store.name == "local"`` 即可。
本地数据文件缺失抛 :class:`DataError`（不会被静默吞掉），消息含期望路径与列。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import BackendFallback, DataError, GraphStore, StoreError
from .local_store import LocalStore

__all__ = [
    "get_store",
    "LocalStore",
    "Neo4jStore",
    "GraphStore",
    "BackendFallback",
    "DataError",
    "StoreError",
]


def _project_root() -> Path:
    # <repo>/app/store/__init__.py -> <repo>
    return Path(__file__).resolve().parents[2]


def _first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def _setting(settings: Any, *names: str, default: Any = None) -> Any:
    """从 Settings（dataclass/对象）或 dict 里按多个候选名取第一个非空值。"""
    if settings is None:
        return default
    getter = getattr(settings, "get", None)
    for name in names:
        if callable(getter):
            try:
                value = getter(name)
            except (TypeError, KeyError):
                value = None
            if value is not None and value != "":
                return value
        if hasattr(settings, name):
            value = getattr(settings, name)
            if value is not None and value != "":
                return value
    return default


def _resolve_backend(settings: Any, backend: str | None) -> str:
    value = _first(
        backend,
        _setting(settings, "graph_backend", "backend", "GRAPH_BACKEND"),
        os.getenv("GRAPH_BACKEND"),
        default="local",
    )
    return str(value).strip().lower() or "local"


def _resolve_data_dir(settings: Any, data_dir: Any) -> Path:
    value = _first(
        data_dir,
        _setting(settings, "data_dir", "data_path", "DATA_DIR"),
        os.getenv("DATA_DIR"),
    )
    if value:
        return Path(str(value)).expanduser()
    return _project_root() / "data"


def _resolve_queries_dir(settings: Any) -> Path:
    value = _first(
        _setting(settings, "queries_dir", "cypher_dir", "QUERIES_DIR"),
        os.getenv("QUERIES_DIR"),
    )
    if value:
        return Path(str(value)).expanduser()
    return _project_root() / "graph" / "queries"


def _neo4j_config(settings: Any) -> dict[str, Any]:
    return {
        "uri": str(
            _first(
                _setting(settings, "neo4j_uri", "neo4j_url", "NEO4J_URI"),
                os.getenv("NEO4J_URI"),
                default="bolt://127.0.0.1:7687",
            )
        ),
        "user": str(
            _first(
                _setting(settings, "neo4j_user", "neo4j_username", "NEO4J_USER"),
                os.getenv("NEO4J_USER"),
                default="neo4j",
            )
        ),
        "password": str(
            _first(
                _setting(settings, "neo4j_password", "NEO4J_PASSWORD"),
                os.getenv("NEO4J_PASSWORD"),
                default="",
            )
        ),
        "database": _first(
            _setting(settings, "neo4j_database", "NEO4J_DATABASE"),
            os.getenv("NEO4J_DATABASE"),
            default=None,
        ),
    }


def get_store(
    settings: Any = None,
    *,
    backend: str | None = None,
    data_dir: Any = None,
) -> GraphStore:
    """按配置创建后端；neo4j 不可用时自动回落 local 并打标记。

    - ``settings``：可为 ``None``（读环境变量）、dict 或 Lead 的 ``Settings`` dataclass；
      支持的字段名：``graph_backend`` / ``backend``、``data_dir`` / ``data_path``、
      ``neo4j_uri`` / ``neo4j_url``、``neo4j_user`` / ``neo4j_username``、``neo4j_password``、
      ``neo4j_database``、``queries_dir``。
    - ``backend`` / ``data_dir``：显式覆盖参数（测试用）。
    """
    resolved_backend = _resolve_backend(settings, backend)
    resolved_data_dir = _resolve_data_dir(settings, data_dir)
    queries_dir = _resolve_queries_dir(settings)

    if resolved_backend in {"local", "csv", "memory", "inmemory"}:
        return LocalStore(resolved_data_dir, queries_dir=queries_dir)

    if resolved_backend != "neo4j":
        raise StoreError(
            f"未知 GRAPH_BACKEND={resolved_backend!r}：只支持 'local'（默认，离线）或 'neo4j'。"
        )

    config = _neo4j_config(settings)
    try:
        from .neo4j_store import Neo4jStore  # 惰性导入：驱动缺失也能 def

        return Neo4jStore(
            str(config["uri"]),
            str(config["user"]),
            str(config["password"]),
            database=config["database"],
            queries_dir=queries_dir,
        )
    except (BackendFallback, ImportError) as exc:
        reason = str(exc)
        if isinstance(exc, ImportError):
            reason = f"neo4j 后端模块导入失败：{exc}"
        try:
            store = LocalStore(resolved_data_dir, queries_dir=queries_dir)
        except DataError as data_exc:
            raise DataError(
                f"Neo4j 不可用（{reason}），且 local 后端数据也不可用：{data_exc}"
            ) from data_exc
        store.backend_fallback = True
        store.fallback_reason = reason
        return store
