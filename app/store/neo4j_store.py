"""Neo4j 后端（可选，``GRAPH_BACKEND=neo4j``）。

设计
----
- **惰性导入**：模块 import 时不碰 ``neo4j`` 驱动，没装依赖也能正常 ``import app.store``；
  真正创建实例时才 ``import neo4j``，失败抛 :class:`app.store.base.BackendFallback`。
- 所有查询走 ``graph/queries/{intent}.cypher`` 模板，**参数化执行**，绝不拼接字符串。
- 查询结果列与 :func:`app.store.base.build_evidence` 对齐；连接/执行失败统一抛
  ``BackendFallback``，由 :func:`app.store.get_store` 回落 ``LocalStore`` 并打
  ``backend_fallback`` 标记（qa 据此加 ``WARN_BACKEND_FALLBACK``）。

参数（两种情况都支持）
----------------------
``QuerySpec.params`` / ``QuerySpec.cypher_params`` 里的同名 key 会合并，缺省补空：
``variety_ids / condition_ids / indicator_ids / disease_ids / entity_ids / keywords``
（list[str]，空列表表示不限）、``limit``（int，默认取 ``k`` 或 6）。
列表参数**不能传 None**（模板里用 ``size($x)``），本类统一转成 ``[]``。
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:  # 兼容 `python app/ui.py`
    from app.contracts import Evidence, QuerySpec
except ImportError:  # pragma: no cover
    from contracts import Evidence, QuerySpec  # type: ignore[no-redef]

from .base import (
    DEFAULT_K,
    BackendFallback,
    GraphStore,
    as_list,
    build_evidence,
    to_float,
)

__all__ = ["Neo4jStore"]

LIST_PARAMS: tuple[str, ...] = (
    "variety_ids",
    "condition_ids",
    "indicator_ids",
    "disease_ids",
    "entity_ids",
    "keywords",
)

SOURCE_TITLES_QUERY = (
    "MATCH (n:Source) WHERE n.id IS NOT NULL "
    "RETURN n.id AS id, coalesce(n.title, n.id) AS title"
)

STATS_QUERIES: dict[str, str] = {
    "nodes": "MATCH (n) RETURN count(n) AS c",
    "rels": "MATCH ()-[r]->() RETURN count(r) AS c",
    "varieties": "MATCH (n:Variety) RETURN count(n) AS c",
    "conditions": "MATCH (n:Condition) RETURN count(n) AS c",
    "indicators": "MATCH (n:QualityIndicator) RETURN count(n) AS c",
    "diseases": "MATCH (n:Disease) RETURN count(n) AS c",
    "sources": "MATCH (n:Source) RETURN count(n) AS c",
}


class Neo4jStore(GraphStore):
    """Neo4j 查询后端；连接失败抛 :class:`BackendFallback`（不在此处回落）。"""

    name = "neo4j"

    def __init__(
        self,
        uri: str,
        user: str = "",
        password: str = "",
        *,
        database: str | None = None,
        queries_dir: Path | str | None = None,
        connection_timeout: float = 5.0,
    ) -> None:
        try:
            import neo4j  # noqa: F401  （惰性导入：未安装时只在这里失败）
        except ImportError as exc:  # pragma: no cover - 取决于运行环境
            raise BackendFallback(
                "未安装 neo4j 驱动（可选依赖：pip install 'neo4j>=5.20'）；已回落 local 后端。"
            ) from exc

        self.uri = str(uri or "").strip()
        self.database = (str(database).strip() or None) if database else None
        self.queries_dir = (
            Path(queries_dir) if queries_dir else Path(__file__).resolve().parents[2] / "graph" / "queries"
        )
        self._neo4j = neo4j
        self._driver = None
        self._query_cache: dict[str, str] = {}
        self._source_titles_cache: dict[str, str] | None = None

        auth = (str(user or ""), str(password or ""))
        driver_kwargs: dict[str, Any] = {}
        try:
            driver_kwargs["connection_timeout"] = float(connection_timeout)
            driver = neo4j.GraphDatabase.driver(self.uri, auth=auth, **driver_kwargs)
        except TypeError:  # 旧版驱动没有 connection_timeout 参数
            driver = neo4j.GraphDatabase.driver(self.uri, auth=auth)
        except Exception as exc:
            raise BackendFallback(f"Neo4j 连接失败（{self.uri}）：{exc}；已回落 local 后端。") from exc

        try:
            driver.verify_connectivity()
        except Exception as exc:
            try:
                driver.close()
            except Exception:  # pragma: no cover - close 失败无需覆盖
                pass
            raise BackendFallback(
                f"Neo4j 连接失败（{self.uri}）：{exc}。"
                "请确认服务已启动、账号密码正确；已回落 local 后端。"
            ) from exc
        self._driver = driver

    # ---------------------------------------------------------------- 执行
    def execute(self, spec: QuerySpec) -> list[Evidence]:
        intent = str(getattr(spec, "intent", "") or "general").strip() or "general"
        query = self._query_text(intent, spec)
        params = self._prepare_params(spec)
        limit = int(params.get("limit") or DEFAULT_K)
        try:
            with self._session() as session:
                rows = [self._record_to_row(record) for record in session.run(query, params)]
        except BackendFallback:
            raise
        except Exception as exc:
            raise BackendFallback(f"Neo4j 查询失败（intent={intent}）：{exc}") from exc

        titles = self._source_titles()
        evidences = [build_evidence(row, source_titles=titles) for row in rows]
        if intent == "variety_compare":
            pool = self._rank(evidences, spec, k_override=max(limit * 3, 18))
            return self._select_with_coverage(pool, self._variety_ids(spec), limit)
        return self._rank(evidences, spec, k_override=limit)

    def _session(self):
        if self._driver is None:
            raise BackendFallback("Neo4j 连接已关闭，请重新创建 store。")
        if self.database:
            return self._driver.session(database=self.database)
        return self._driver.session()

    def _query_text(self, intent: str, spec: QuerySpec) -> str:
        name = str(getattr(spec, "cypher_file", "") or "").strip() or f"{intent}.cypher"
        name = Path(name).name  # 只允许模板名，禁止路径穿越
        path = self.queries_dir / name
        if not path.is_file():
            raise BackendFallback(
                f"缺少 Cypher 模板：{path}（intent={intent}）。graph/queries/ 下应有 9+ 个意图模板。"
            )
        if name not in self._query_cache:
            self._query_cache[name] = path.read_text(encoding="utf-8")
        return self._query_cache[name]

    def _prepare_params(self, spec: QuerySpec) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for source in (getattr(spec, "params", None) or {}, getattr(spec, "cypher_params", None) or {}):
            if isinstance(source, Mapping):
                merged.update(source)
        params: dict[str, Any] = {key: as_list(merged.get(key)) for key in LIST_PARAMS}
        limit_value = merged.get("limit", merged.get("k", DEFAULT_K))
        limit_number = to_float(limit_value)
        limit = int(limit_number) if limit_number is not None else DEFAULT_K
        params["limit"] = max(1, min(50, limit))
        return params

    @staticmethod
    def _variety_ids(spec: QuerySpec) -> list[str]:
        params = getattr(spec, "params", None) or {}
        cypher_params = getattr(spec, "cypher_params", None) or {}
        ids = as_list(params.get("variety_ids")) or (
            as_list(cypher_params.get("variety_ids")) if isinstance(cypher_params, Mapping) else []
        )
        return ids

    @staticmethod
    def _record_to_row(record: Any) -> dict[str, Any]:
        """neo4j Record → 行 dict；缺失字段回落到关系 ``properties``。"""
        try:
            row: dict[str, Any] = dict(record)
        except (TypeError, ValueError):  # pragma: no cover - 驱动版本差异
            keys = list(record.keys())
            row = {key: record[key] for key in keys}
        properties = row.get("properties")
        if not isinstance(properties, Mapping):
            properties = {}
        row["properties"] = dict(properties)
        for key in ("value", "unit", "value_min", "value_max", "status", "confidence", "source_ids", "locator", "quote"):
            current = row.get(key)
            if current in (None, "", []) and key in properties:
                row[key] = properties[key]
        if row.get("object_category") in (None, ""):
            row["object_category"] = properties.get("object_category")
        return row

    # ---------------------------------------------------------------- 连接/统计
    def _source_titles(self) -> dict[str, str]:
        if self._source_titles_cache is not None:
            return self._source_titles_cache
        titles: dict[str, str] = {}
        try:
            with self._session() as session:
                for record in session.run(SOURCE_TITLES_QUERY):
                    titles[str(record["id"])] = str(record["title"])
        except Exception:  # 来源节点缺失/查询失败不影响证据返回
            titles = {}
        self._source_titles_cache = titles
        return titles

    def stats(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "backend": self.name,
            "nodes": 0,
            "rels": 0,
            "varieties": 0,
            "conditions": 0,
            "indicators": 0,
            "diseases": 0,
            "sources": 0,
        }
        if self._driver is None:
            result["error"] = "连接已关闭"
            return result
        try:
            with self._session() as session:
                for key, query in STATS_QUERIES.items():
                    record = session.run(query).single()
                    result[key] = int(record["c"]) if record else 0
        except Exception as exc:
            result["error"] = f"stats 查询失败：{exc}"
        return result

    def health(self) -> tuple[bool, str]:
        if self._driver is None:
            return False, "neo4j: 连接已关闭"
        try:
            self._driver.verify_connectivity()
        except Exception as exc:
            return False, f"neo4j 连接失败（{self.uri}）：{exc}"
        return True, f"neo4j: 已连接 {self.uri}（database={self.database or 'default'}）"

    def query_cypher(self, spec: QuerySpec) -> list[str]:
        intent = str(getattr(spec, "intent", "") or "general").strip() or "general"
        try:
            query = self._query_text(intent, spec)
        except BackendFallback as exc:
            return [f"// {exc}"]
        params = self._prepare_params(spec)
        rendered = ", ".join(f"{key}={params[key]!r}" for key in sorted(params))
        return [query, f"// params: {rendered}"]

    def close(self) -> None:
        driver, self._driver = self._driver, None
        if driver is not None:
            try:
                driver.close()
            except Exception:  # pragma: no cover
                pass
