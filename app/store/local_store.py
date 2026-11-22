"""本地内存图谱后端（``GRAPH_BACKEND=local``，默认、离线可跑、纯标准库）。

数据来源
--------
- ``data/entities.csv``：节点（列见 ``docs/api.md`` §1.1）。
- ``data/triples_shine_muscat.csv``（M1 门禁产物，20 行）＋ ``data/triples.csv``
  （全量）：两者同列，**存在即读取并按 (subject, predicate, object) 合并去重**。
- ``data/sources.csv``（可选）：用于把 ``source_ids`` 渲染成来源标题；缺失时降级为 id。

设计要点
--------
- 启动即建三张索引：``_out``（按 subject）、``_in``（按 object）、``_by_predicate``。
- ``execute(spec)`` 按 ``spec.intent`` 分派到 9 个意图的检索函数；所有意图都返回
  「边 dict」再由 :meth:`LocalStore._finish` 统一转 :class:`Evidence`、
  排序/去重/截断（规则集中在 :mod:`app.store.base`）。
- **不做 Cypher 字符串拼接**：Cypher 只用于 :meth:`query_cypher` 展示与 Neo4j 后端。
- ``params`` 约定（与 planner 对齐，未知 key 忽略）::

      variety_ids / condition_ids / indicator_ids / disease_ids: list[str]
      entity_ids: list[str]      # 全部命中实体 id；其他 *_ids 缺省时按实体 label 自动归类
      keywords: list[str]        # general 关键词兜底
      question: str              # general 关键词兜底（可选）
      hit_terms: list[str]       # 命中度用词（可选，默认从上面的 id/名称推断）
      k: int                     # 证据条数上限，默认 6

数据缺失时抛 :class:`app.store.base.DataError`，消息含「缺哪个文件 / 期望列 / 实际路径」。
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

try:  # 兼容 `python app/ui.py`（sys.path[0] 为 app/）
    from app.contracts import Evidence, QuerySpec
except ImportError:  # pragma: no cover
    from contracts import Evidence, QuerySpec  # type: ignore[no-redef]

from .base import (
    DEFAULT_K,
    DataError,
    GraphStore,
    as_list,
    build_evidence,
    normalize_term,
    rank_evidence,
    to_float,
)

__all__ = ["LocalStore", "TRIPLE_FILES"]

ENTITY_FILE = "entities.csv"
SOURCES_FILE = "sources.csv"
TRIPLE_FILES: tuple[str, ...] = ("triples_shine_muscat.csv", "triples.csv")

# Condition.category 取值（docs/spec.md §1.2）
CATEGORY_TEMPERATURE = "温度"
CATEGORY_HUMIDITY = "湿度"
CATEGORY_ATMOSPHERE = "气调"
INDICATOR_SHELF_LIFE = "shelf_life"
INDICATOR_SHELF_LIFE_NAME = "耐贮性"

# query_cypher 展示用：Cypher 模板里的 $ 参数名，以及 QuerySpec 中对应的 list 参数
_CYPHER_PARAM_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_LIST_PARAM_NAMES: tuple[str, ...] = (
    "variety_ids",
    "condition_ids",
    "indicator_ids",
    "disease_ids",
    "entity_ids",
    "keywords",
)

# 边 dict 的统一字段（CSV 缺列时补空）
EDGE_DEFAULTS: dict[str, Any] = {
    "sid": "",
    "subject_id": "",
    "subject_name": "",
    "subject_label": "",
    "predicate": "",
    "object_id": "",
    "object_name": "",
    "object_label": "",
    "value": None,
    "value_min": None,
    "value_max": None,
    "unit": "",
    "stage": "",
    "effect": "",
    "level": "",
    "severity": "",
    "efficacy": "",
    "reason": "",
    "source_ids": [],
    "locator": "",
    "quote": "",
    "status": "anchor",
    "confidence": 0.5,
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _template_param_names(template: str) -> list[str]:
    """按首次出现顺序提取 Cypher 模板里实际用到的 ``$参数`` 名。"""
    names: list[str] = []
    for match in _CYPHER_PARAM_RE.finditer(template or ""):
        name = match.group(1)
        if name not in names:
            names.append(name)
    return names


def _format_cypher_value(value: Any) -> str:
    """把参数值格式化成 Cypher 风格字面量（仅用于 ``// params:`` 展示注释）。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple, set)):
        return "[" + ", ".join(_format_cypher_value(item) for item in value) + "]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


class LocalStore(GraphStore):
    """纯标准库内存邻接表后端。线程内只读，可安全复用于多轮问答。"""

    name = "local"

    def __init__(
        self,
        data_dir: Path | str,
        *,
        queries_dir: Path | str | None = None,
        k_default: int = DEFAULT_K,
        require_triples: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.k_default = max(1, int(k_default))
        self.queries_dir = Path(queries_dir) if queries_dir else self._default_queries_dir()
        self.entities: dict[str, dict[str, Any]] = {}
        self.by_name: dict[str, str] = {}          # 规范 name -> id
        self.by_alias: dict[str, list[str]] = defaultdict(list)
        self.sources: dict[str, dict[str, str]] = {}
        self.edges: list[dict[str, Any]] = []
        self.unresolved: list[dict[str, Any]] = []
        self._lookup: dict[str, str] = {}          # 归一化 id/name/alias -> id
        self._out: dict[str, list[int]] = defaultdict(list)
        self._in: dict[str, list[int]] = defaultdict(list)
        self._by_predicate: dict[str, list[int]] = defaultdict(list)
        self._loaded_files: list[str] = []
        self._load(require_triples=require_triples)

    # ================================================================ 加载
    def _default_queries_dir(self) -> Path:
        # <repo>/app/store/local_store.py -> <repo>/graph/queries
        return Path(__file__).resolve().parents[2] / "graph" / "queries"

    def _load(self, *, require_triples: bool) -> None:
        if not self.data_dir.exists():
            raise DataError(
                f"图谱数据目录不存在：{self.data_dir}。"
                "请确认在项目根目录运行，或设置环境变量 DATA_DIR 指向 data/ 所在目录。"
            )
        self._load_entities()
        self._load_sources()
        self._load_triples(require_triples=require_triples)
        self._build_index()

    # ---------------------------------------------------------------- entities
    def _load_entities(self) -> None:
        path = self.data_dir / ENTITY_FILE
        if not path.is_file():
            raise DataError(
                f"缺少节点数据文件：{path}。"
                f"期望列：id,label,name,aliases,category,value_min,value_max,unit,stage,direction,"
                f"method,species,berry_color,seedless,maturity,region,pathogen_latin,symptom,source_ids,note"
                f"（docs/api.md §1.1）。请等待 kg-builder 产出 data/entities.csv。"
            )
        rows = self._read_csv(path, required=("id", "label", "name"))
        if not rows:
            raise DataError(f"{path} 存在但没有任何数据行（只有表头？），请先补齐节点数据。")
        for row in rows:
            entity_id = _clean(row.get("id"))
            label = _clean(row.get("label"))
            name = _clean(row.get("name"))
            if not entity_id or not label or not name:
                continue
            entity: dict[str, Any] = {
                "id": entity_id,
                "label": label,
                "name": name,
                "aliases": as_list(row.get("aliases")),
                "category": _clean(row.get("category")),
                "value": to_float(row.get("value")),
                "value_min": to_float(row.get("value_min")),
                "value_max": to_float(row.get("value_max")),
                "unit": _clean(row.get("unit")),
                "stage": _clean(row.get("stage")),
                "direction": _clean(row.get("direction")),
                "method": _clean(row.get("method")),
                "symptom": _clean(row.get("symptom")),
                "pathogen_latin": _clean(row.get("pathogen_latin")),
                "source_ids": as_list(row.get("source_ids")),
                "note": _clean(row.get("note")),
                "raw": row,
            }
            self.entities[entity_id] = entity
            if name not in self.by_name:
                self.by_name[name] = entity_id
            for alias in entity["aliases"]:
                if alias and entity_id not in self.by_alias[alias]:
                    self.by_alias[alias].append(entity_id)
            self._register_lookup(entity_id, entity_id)
            self._register_lookup(name, entity_id)
            for alias in entity["aliases"]:
                self._register_lookup(alias, entity_id)

    def _register_lookup(self, term: Any, entity_id: str) -> None:
        key = normalize_term(term)
        if key and key not in self._lookup:
            self._lookup[key] = entity_id

    # ---------------------------------------------------------------- sources
    def _load_sources(self) -> None:
        path = self.data_dir / SOURCES_FILE
        if not path.is_file():
            # 来源只影响展示（source_titles），缺失不阻塞检索
            self.sources = {}
            return
        for row in self._read_csv(path, required=("id",), strict=False):
            source_id = _clean(row.get("id"))
            if not source_id:
                continue
            self.sources[source_id] = {
                "id": source_id,
                "title": _clean(row.get("title")) or source_id,
                "authors": _clean(row.get("authors")),
                "year": _clean(row.get("year")),
                "venue": _clean(row.get("venue")),
                "type": _clean(row.get("type")),
                "doi_url": _clean(row.get("doi_url")),
            }

    # ---------------------------------------------------------------- triples
    def _load_triples(self, *, require_triples: bool) -> None:
        existing = [self.data_dir / name for name in TRIPLE_FILES if (self.data_dir / name).is_file()]
        if not existing:
            expected = "、".join(str(self.data_dir / name) for name in TRIPLE_FILES)
            raise DataError(
                f"缺少三元组数据文件：期望 {expected} 至少存在一个（docs/api.md §1.2）。"
                "请等待 kg-builder 产出 data/triples_shine_muscat.csv（M1 门禁）或 data/triples.csv。"
            )
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for path in existing:
            self._loaded_files.append(path.name)
            for raw in self._read_csv(path, required=("subject", "predicate", "object")):
                edge = self._parse_triple(raw)
                if edge is None:
                    continue
                key = (edge["subject_id"] or edge["subject_name"], edge["predicate"], edge["object_id"] or edge["object_name"])
                previous = merged.get(key)
                if previous is None or self._edge_quality(edge) > self._edge_quality(previous):
                    merged[key] = edge
        self.edges = list(merged.values())
        if not self.edges and require_triples:
            raise DataError(
                "三元组文件存在但没有任何可用数据行（subject/predicate/object 为空？）。"
                f"实际读取：{'、'.join(self._loaded_files)}。请先跑 scripts/validate_data.py 排查。"
            )
        self._by_predicate = defaultdict(list)
        for idx, edge in enumerate(self.edges):
            self._by_predicate[edge["predicate"]].append(idx)

    @staticmethod
    def _edge_quality(edge: Mapping[str, Any]) -> tuple[int, float]:
        status_rank = 1 if edge.get("status") == "verified" else 0
        return status_rank, float(edge.get("confidence") or 0.0)

    def _parse_triple(self, row: Mapping[str, Any]) -> dict[str, Any] | None:
        subject_token = _clean(row.get("subject"))
        object_token = _clean(row.get("object"))
        predicate = _clean(row.get("predicate"))
        if not subject_token or not object_token or not predicate:
            self.unresolved.append({"reason": "missing_subject_object_predicate", "row": dict(row)})
            return None
        subject_id = self._resolve_entity_id(subject_token)
        object_id = self._resolve_entity_id(object_token)
        subject = self.entities.get(subject_id or "")
        obj = self.entities.get(object_id or "")
        if subject is None or obj is None:
            self.unresolved.append(
                {"reason": "entity_not_found", "subject": subject_token, "object": object_token, "sid": _clean(row.get("sid"))}
            )
        edge = dict(EDGE_DEFAULTS)
        edge.update(
            {
                "sid": _clean(row.get("sid")),
                "subject_id": subject_id or "",
                "subject_name": (subject or {}).get("name") or subject_token,
                "subject_label": _clean(row.get("subject_type")) or (subject or {}).get("label", ""),
                "predicate": predicate,
                "object_id": object_id or "",
                "object_name": (obj or {}).get("name") or object_token,
                "object_label": _clean(row.get("object_type")) or (obj or {}).get("label", ""),
                "value": to_float(row.get("value")),
                "value_min": to_float(row.get("value_min")),
                "value_max": to_float(row.get("value_max")),
                "unit": _clean(row.get("unit")),
                "stage": _clean(row.get("stage")),
                "effect": _clean(row.get("effect")),
                "level": _clean(row.get("level")),
                "severity": _clean(row.get("severity")),
                "efficacy": _clean(row.get("efficacy")),
                "reason": _clean(row.get("reason")),
                "source_ids": as_list(row.get("source_ids")),
                "locator": _clean(row.get("locator")),
                "quote": _clean(row.get("quote")),
                "status": "verified" if _clean(row.get("status")).lower() == "verified" else "anchor",
                "confidence": to_float(row.get("confidence")) or 0.0,
            }
        )
        # 边的对象是 Condition / QualityIndicator 时，缺失的数值/单位回落到节点自身
        if obj is not None:
            if edge["value"] is None and obj.get("value") is not None:
                edge["value"] = obj.get("value")
            if edge["value_min"] is None and obj.get("value_min") is not None:
                edge["value_min"] = obj.get("value_min")
            if edge["value_max"] is None and obj.get("value_max") is not None:
                edge["value_max"] = obj.get("value_max")
            if not edge["unit"] and obj.get("unit"):
                edge["unit"] = obj.get("unit")
        return edge

    # ---------------------------------------------------------------- index
    def _build_index(self) -> None:
        self._out = defaultdict(list)
        self._in = defaultdict(list)
        for idx, edge in enumerate(self.edges):
            if edge["subject_id"]:
                self._out[edge["subject_id"]].append(idx)
            if edge["object_id"]:
                self._in[edge["object_id"]].append(idx)

    # ---------------------------------------------------------------- CSV
    @staticmethod
    def _read_csv(path: Path, *, required: Sequence[str] = (), strict: bool = True) -> list[dict[str, str]]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = [str(name or "").strip() for name in (reader.fieldnames or [])]
                if strict:
                    missing = [name for name in required if name not in fieldnames]
                    if missing:
                        raise DataError(
                            f"{path} 缺少必需列：{', '.join(missing)}；实际表头：{', '.join(fieldnames) or '(空)'}。"
                            "请对照 docs/api.md §1.2 修正。"
                        )
                rows: list[dict[str, str]] = []
                for raw in reader:
                    rows.append({str(key or "").strip(): value for key, value in raw.items() if key is not None})
                return rows
        except UnicodeDecodeError as exc:
            raise DataError(f"{path} 不是 UTF-8 编码（{exc}）。请另存为 UTF-8（无 BOM 亦可）。") from exc

    # ================================================================ 实体解析
    def _resolve_entity_id(self, token: Any) -> str:
        text = _clean(token)
        if not text:
            return ""
        if text in self.entities:
            return text
        return self._lookup.get(normalize_term(text), "")

    def _ids_for_label(
        self,
        spec: QuerySpec,
        label: str,
        keys: Sequence[str],
        *,
        also_entity_ids: bool = True,
    ) -> list[str]:
        params = getattr(spec, "params", None) or {}
        tokens: list[str] = []
        for key in keys:
            tokens.extend(as_list(params.get(key)))
        if also_entity_ids:
            tokens.extend(as_list(params.get("entity_ids")))
        ids: list[str] = []
        for token in tokens:
            entity_id = self._resolve_entity_id(token)
            if entity_id and self.entities.get(entity_id, {}).get("label") == label and entity_id not in ids:
                ids.append(entity_id)
        return ids

    def _all_ids(self, spec: QuerySpec) -> list[str]:
        params = getattr(spec, "params", None) or {}
        tokens: list[str] = []
        for key in ("entity_ids", "variety_ids", "condition_ids", "indicator_ids", "disease_ids", "hit_terms"):
            tokens.extend(as_list(params.get(key)))
        ids: list[str] = []
        for token in tokens:
            entity_id = self._resolve_entity_id(token)
            if entity_id and entity_id not in ids:
                ids.append(entity_id)
        return ids

    def _categories(self, entity_id: str) -> str:
        return _clean(self.entities.get(entity_id, {}).get("category"))

    def _condition_matches(self, entity_id: str, category: str) -> bool:
        """Condition 是否属于某 category；category 缺失时按名称做保守兜底。"""
        entity = self.entities.get(entity_id)
        if entity is None:
            return False
        cat = _clean(entity.get("category"))
        if cat:
            return cat == category
        name = _clean(entity.get("name"))
        if category == CATEGORY_TEMPERATURE:
            return ("温" in name) and ("常温" not in name) and ("高温" not in name)
        if category == CATEGORY_HUMIDITY:
            return ("湿度" in name) or ("RH" in name)
        if category == CATEGORY_ATMOSPHERE:
            return ("气调" in name) or ("O₂" in name) or ("O2" in name) or ("CO₂" in name) or ("CO2" in name)
        return False

    def _shelf_life_indicator_ids(self) -> list[str]:
        ids: list[str] = []
        for entity_id, entity in self.entities.items():
            if entity.get("label") != "QualityIndicator":
                continue
            if entity_id == INDICATOR_SHELF_LIFE_NAME or INDICATOR_SHELF_LIFE_NAME in _clean(entity.get("name")):
                ids.append(entity_id)
        return ids

    # ================================================================ 执行入口
    def execute(self, spec: QuerySpec) -> list[Evidence]:
        intent = _clean(getattr(spec, "intent", "")) or "general"
        handler = {
            "temperature": self._load_temperature,
            "humidity": self._load_humidity,
            "atmosphere": self._load_atmosphere,
            "shelf_life": self._load_shelf_life,
            "disease_control": self._load_disease_control,
            "disease_risk": self._load_disease_risk,
            "quality_indicator": self._load_quality_indicator,
            "variety_compare": self._load_variety_compare,
            "contraindication": self._load_contraindication,
            "general": self._load_general,
        }.get(intent, self._load_general)
        try:
            return handler(spec)
        except DataError:
            raise
        except Exception as exc:  # pragma: no cover - 防御性：绝不把内部异常抛成看不懂的堆栈
            raise DataError(f"local 后端执行 intent={intent} 失败：{exc}") from exc

    # ================================================================ 通用工具
    def _edge_matches(
        self,
        edge: Mapping[str, Any],
        *,
        predicates: Iterable[str] | None = None,
        subject_ids: Iterable[str] | None = None,
        object_ids: Iterable[str] | None = None,
        object_category: str | None = None,
        subject_label: str | None = None,
        object_label: str | None = None,
    ) -> bool:
        if predicates is not None and edge["predicate"] not in set(predicates):
            return False
        if subject_ids is not None and edge["subject_id"] not in set(subject_ids):
            return False
        if object_ids is not None and edge["object_id"] not in set(object_ids):
            return False
        if object_category is not None and not self._condition_matches(edge["object_id"], object_category):
            return False
        if subject_label is not None and edge["subject_label"] != subject_label:
            return False
        if object_label is not None and edge["object_label"] != object_label:
            return False
        return True

    def _collect(
        self,
        *,
        predicates: Iterable[str] | None = None,
        subject_ids: Iterable[str] | None = None,
        object_ids: Iterable[str] | None = None,
        object_category: str | None = None,
        subject_label: str | None = None,
        object_label: str | None = None,
    ) -> list[dict[str, Any]]:
        """按条件过滤边 dict（图谱很小，直接线性扫描，保证可读性）。"""
        selected: list[dict[str, Any]] = []
        for edge in self.edges:
            if self._edge_matches(
                edge,
                predicates=predicates,
                subject_ids=subject_ids,
                object_ids=object_ids,
                object_category=object_category,
                subject_label=subject_label,
                object_label=object_label,
            ):
                selected.append(edge)
        return selected

    def _edge_row(self, edge: Mapping[str, Any]) -> dict[str, Any]:
        """边 dict → :func:`build_evidence` 需要的行 dict。

        ``properties`` 里保留 qa 层依赖的元数据：subject_id / object_id / category /
        stage / effect / severity / efficacy / reason（qa 的 compose_steps 用 category/stage，
        数值校验用 value/unit/value_min/value_max，禁忌提示用 severity/efficacy/reason）。
        """
        properties: dict[str, Any] = {
            key: edge.get(key)
            for key in ("sid", "stage", "effect", "level", "severity", "efficacy", "reason")
            if edge.get(key) not in (None, "")
        }
        object_category = self._categories(edge.get("object_id", "")) or _clean(edge.get("object_label"))
        subject_category = self._categories(edge.get("subject_id", "")) or _clean(edge.get("subject_label"))
        # “category” 取条件侧的分类（温度/湿度/气调/化学/采后操作/...），供分步动作使用
        if _clean(edge.get("object_label")) == "Condition":
            category = object_category
        elif _clean(edge.get("subject_label")) == "Condition":
            category = subject_category
        else:
            category = ""
        if category:
            properties["category"] = category
        if object_category:
            properties["object_category"] = object_category
        if subject_category:
            properties["subject_category"] = subject_category
        return {
            "subject": edge.get("subject_name") or edge.get("subject_id") or "",
            "subject_id": edge.get("subject_id") or "",
            "subject_label": edge.get("subject_label") or "",
            "predicate": edge.get("predicate") or "",
            "object": edge.get("object_name") or edge.get("object_id") or "",
            "object_id": edge.get("object_id") or "",
            "object_label": edge.get("object_label") or "",
            "value": edge.get("value"),
            "unit": edge.get("unit") or "",
            "value_min": edge.get("value_min"),
            "value_max": edge.get("value_max"),
            "status": edge.get("status") or "anchor",
            "confidence": edge.get("confidence"),
            "source_ids": edge.get("source_ids") or [],
            "locator": edge.get("locator") or "",
            "quote": edge.get("quote") or "",
            "properties": properties,
        }

    def _source_titles(self) -> dict[str, str]:
        return {source_id: source.get("title", source_id) for source_id, source in self.sources.items()}

    def _finish(self, edges: Iterable[Mapping[str, Any]], spec: QuerySpec, *, k_override: int | None = None) -> list[Evidence]:
        rows = [self._edge_row(edge) for edge in edges]
        titles = self._source_titles()
        evidences = [build_evidence(row, source_titles=titles) for row in rows]
        k = k_override if k_override is not None else self._spec_k(spec)
        return self._rank(evidences, spec, k_override=k)

    def _spec_k(self, spec: QuerySpec) -> int:
        params = getattr(spec, "params", None) or {}
        value = to_float(params.get("k"))
        k = int(value) if value is not None else self.k_default
        return max(1, min(50, k))

    def _rank(
        self,
        evidences: Iterable[Evidence],
        spec: QuerySpec,
        *,
        k_override: int | None = None,
    ) -> list[Evidence]:
        """local 后端能用节点表把实体 id 展开成中文 name/别名，命中度更有意义。"""
        params = getattr(spec, "params", None) or {}
        terms: list[str] = []
        for key in ("hit_terms", "entity_names"):
            terms.extend(as_list(params.get(key)))
        tokens: list[str] = []
        for key in ("entity_ids", "variety_ids", "condition_ids", "indicator_ids", "disease_ids"):
            tokens.extend(as_list(params.get(key)))
        for token in tokens:
            entity_id = self._resolve_entity_id(token)
            if not entity_id:
                continue
            entity = self.entities.get(entity_id, {})
            terms.append(_clean(entity.get("name")))
            terms.append(entity_id)
            terms.extend(entity.get("aliases", []))
        k = k_override if k_override is not None else self._spec_k(spec)
        return rank_evidence(evidences, k=max(1, min(50, int(k))), hit_terms=terms)

    # ================================================================ 意图：温度/湿度/气调
    def _load_condition_intent(self, spec: QuerySpec, category: str) -> list[Evidence]:
        variety_ids = self._ids_for_label(spec, "Variety", ("variety_ids",))
        condition_ids = self._ids_for_label(spec, "Condition", ("condition_ids", "target_condition_ids"))
        edges: list[dict[str, Any]] = []
        if condition_ids:
            # 只保留属于本意图类别的条件；若命中的条件全不属于该类（例如 temperature 问句里
            # 附带命中了 SO₂ 熏蒸），回落到类别过滤，避免“有实体反而 0 证据”。
            matching = [cid for cid in condition_ids if self._condition_matches(cid, category)]
            if matching:
                edges.extend(
                    self._collect(
                        predicates=("REQUIRES",),
                        subject_ids=variety_ids or None,
                        object_ids=matching,
                    )
                )
            else:
                edges.extend(
                    self._collect(
                        predicates=("REQUIRES",),
                        subject_ids=variety_ids or None,
                        object_category=category,
                    )
                )
        else:
            edges.extend(
                self._collect(
                    predicates=("REQUIRES",),
                    subject_ids=variety_ids or None,
                    object_category=category,
                )
            )
            if not edges:
                # 数据未标注 category 时的最后兜底：全部 REQUIRES（与 cypher 模板的放宽条件一致）
                edges.extend(self._collect(predicates=("REQUIRES",), subject_ids=variety_ids or None))
        return self._finish(_dedupe_edges(edges), spec)

    def _load_temperature(self, spec: QuerySpec) -> list[Evidence]:
        return self._load_condition_intent(spec, CATEGORY_TEMPERATURE)

    def _load_humidity(self, spec: QuerySpec) -> list[Evidence]:
        return self._load_condition_intent(spec, CATEGORY_HUMIDITY)

    def _load_atmosphere(self, spec: QuerySpec) -> list[Evidence]:
        return self._load_condition_intent(spec, CATEGORY_ATMOSPHERE)

    # ================================================================ 意图：耐贮性
    def _load_shelf_life(self, spec: QuerySpec) -> list[Evidence]:
        variety_ids = self._ids_for_label(spec, "Variety", ("variety_ids",))
        indicator_ids = self._shelf_life_indicator_ids()
        edges: list[dict[str, Any]] = []
        if indicator_ids:
            edges.extend(
                self._collect(
                    predicates=("HAS_INDICATOR_VALUE",),
                    subject_ids=variety_ids or None,
                    object_ids=indicator_ids,
                )
            )
            if not variety_ids:
                edges.extend(self._collect(predicates=("HAS_INDICATOR_VALUE",), object_ids=indicator_ids))
            # 相关 AFFECTS：哪些条件影响耐贮性
            edges.extend(self._collect(predicates=("AFFECTS",), object_ids=indicator_ids))
        if not edges:
            edges.extend(self._collect(predicates=("HAS_INDICATOR_VALUE",), subject_ids=variety_ids or None))
        return self._finish(_dedupe_edges(edges), spec)

    # ================================================================ 意图：病害
    def _related_disease_ids(self, spec: QuerySpec, variety_ids: Sequence[str]) -> list[str]:
        disease_ids = self._ids_for_label(spec, "Disease", ("disease_ids",))
        if disease_ids:
            return disease_ids
        if variety_ids:
            related: list[str] = []
            for edge in self._collect(predicates=("SUSCEPTIBLE_TO",), subject_ids=variety_ids):
                if edge["object_id"] and edge["object_id"] not in related:
                    related.append(edge["object_id"])
            return related
        # 未命中任何实体：返回全部病害 id（保持确定性顺序）
        return [
            entity_id
            for entity_id, entity in self.entities.items()
            if entity.get("label") == "Disease"
        ]

    def _load_disease_control(self, spec: QuerySpec) -> list[Evidence]:
        variety_ids = self._ids_for_label(spec, "Variety", ("variety_ids",))
        disease_ids = self._related_disease_ids(spec, variety_ids)
        edges: list[dict[str, Any]] = []
        if disease_ids:
            edges.extend(self._collect(predicates=("PREVENTED_BY",), subject_ids=disease_ids))
            edges.extend(self._collect(predicates=("INDUCED_BY",), subject_ids=disease_ids))
        if not edges:
            edges.extend(self._collect(predicates=("PREVENTED_BY",)))
            edges.extend(self._collect(predicates=("INDUCED_BY",)))
        return self._finish(_dedupe_edges(edges), spec)

    def _load_disease_risk(self, spec: QuerySpec) -> list[Evidence]:
        variety_ids = self._ids_for_label(spec, "Variety", ("variety_ids",))
        disease_ids = self._related_disease_ids(spec, variety_ids)
        edges: list[dict[str, Any]] = []
        if disease_ids:
            edges.extend(self._collect(predicates=("INDUCED_BY",), subject_ids=disease_ids))
            edges.extend(
                self._collect(
                    predicates=("SUSCEPTIBLE_TO",),
                    subject_ids=variety_ids or None,
                    object_ids=disease_ids,
                )
            )
            if not variety_ids:  # 只问病害时，展示「哪些品种易感」
                edges.extend(self._collect(predicates=("SUSCEPTIBLE_TO",), object_ids=disease_ids))
        if not edges:
            edges.extend(self._collect(predicates=("INDUCED_BY",)))
            edges.extend(self._collect(predicates=("SUSCEPTIBLE_TO",)))
        return self._finish(_dedupe_edges(edges), spec)

    # ================================================================ 意图：品质指标
    def _load_quality_indicator(self, spec: QuerySpec) -> list[Evidence]:
        variety_ids = self._ids_for_label(spec, "Variety", ("variety_ids",))
        indicator_ids = self._ids_for_label(spec, "QualityIndicator", ("indicator_ids",))
        edges: list[dict[str, Any]] = []
        if indicator_ids:
            edges.extend(self._collect(predicates=("AFFECTS",), object_ids=indicator_ids))
            edges.extend(
                self._collect(
                    predicates=("HAS_INDICATOR_VALUE",),
                    subject_ids=variety_ids or None,
                    object_ids=indicator_ids,
                )
            )
            if not variety_ids:
                edges.extend(self._collect(predicates=("HAS_INDICATOR_VALUE",), object_ids=indicator_ids))
        else:
            edges.extend(self._collect(predicates=("AFFECTS",)))
            edges.extend(
                self._collect(
                    predicates=("HAS_INDICATOR_VALUE",),
                    subject_ids=variety_ids or None,
                )
            )
        if not edges:
            edges.extend(self._collect(predicates=("HAS_INDICATOR_VALUE",), subject_ids=variety_ids or None))
        return self._finish(_dedupe_edges(edges), spec)

    # ================================================================ 意图：品种对比
    def _load_variety_compare(self, spec: QuerySpec) -> list[Evidence]:
        variety_ids = self._ids_for_label(spec, "Variety", ("variety_ids",))
        edges: list[dict[str, Any]] = []
        for variety_id in variety_ids:
            edges.extend(self._collect(predicates=("HAS_INDICATOR_VALUE",), subject_ids=[variety_id]))
            edges.extend(
                self._collect(
                    predicates=("REQUIRES",),
                    subject_ids=[variety_id],
                    object_category=CATEGORY_TEMPERATURE,
                )
            )
            edges.extend(self._collect(predicates=("CONTRA_INDICATED_FOR",), object_ids=[variety_id]))
        if not edges:
            edges.extend(self._collect(predicates=("HAS_INDICATOR_VALUE",)))
        k = self._spec_k(spec)
        rows = [self._edge_row(edge) for edge in _dedupe_edges(edges)]
        titles = self._source_titles()
        evidences = [build_evidence(row, source_titles=titles) for row in rows]
        pool = self._rank(evidences, spec, k_override=max(k * 3, 18))
        return self._select_with_coverage(pool, variety_ids, k)

    # ================================================================ 意图：禁忌
    def _load_contraindication(self, spec: QuerySpec) -> list[Evidence]:
        variety_ids = self._ids_for_label(spec, "Variety", ("variety_ids",))
        condition_ids = self._ids_for_label(spec, "Condition", ("condition_ids",))
        edges: list[dict[str, Any]] = []
        if condition_ids:
            # 条件既可能是禁忌的“施加对象”（subject），也可能作为对照词出现（object）
            edges.extend(self._collect(predicates=("CONTRA_INDICATED_FOR",), subject_ids=condition_ids))
            edges.extend(self._collect(predicates=("CONTRA_INDICATED_FOR",), object_ids=condition_ids))
            bad_conditions = condition_ids
            for direction in ("object_ids", "subject_ids"):
                edges.extend(
                    self._collect(predicates=("ALTERNATIVE_TO",), **{direction: bad_conditions})
                )
        else:
            contra_edges = self._collect(
                predicates=("CONTRA_INDICATED_FOR",),
                object_ids=variety_ids or None,
            )
            edges.extend(contra_edges)
            bad_conditions = [
                edge["subject_id"] for edge in contra_edges if edge.get("subject_id")
            ]
            if bad_conditions:
                # 数据方向：焦亚硫酸盐缓释片 -ALTERNATIVE_TO-> SO₂ 熏蒸（替代方案 → 被替代条件）
                edges.extend(self._collect(predicates=("ALTERNATIVE_TO",), object_ids=bad_conditions))
                edges.extend(self._collect(predicates=("ALTERNATIVE_TO",), subject_ids=bad_conditions))
        if not edges:
            edges.extend(self._collect(predicates=("CONTRA_INDICATED_FOR",)))
            edges.extend(self._collect(predicates=("ALTERNATIVE_TO",)))
        return self._finish(_dedupe_edges(edges), spec)

    # ================================================================ 意图：general
    def _load_general(self, spec: QuerySpec) -> list[Evidence]:
        params = getattr(spec, "params", None) or {}
        entity_ids = self._all_ids(spec)
        edges: list[dict[str, Any]] = []
        for entity_id in entity_ids:
            edges.extend(self.edges[index] for index in self._out.get(entity_id, []))
            edges.extend(self.edges[index] for index in self._in.get(entity_id, []))
        edges = _dedupe_edges(edges)

        # 关键词兜底：实体名/别名出现在问题里 → 补其相连边；quote 命中关键词 → 补该边
        keywords = as_list(params.get("keywords"))
        question = _clean(params.get("question"))
        fallback_ids: list[str] = []
        if question:
            normalized_question = normalize_term(question)
            for entity_id, entity in self.entities.items():
                names = [entity.get("name", ""), *entity.get("aliases", [])]
                if any(normalize_term(name) and normalize_term(name) in normalized_question for name in names):
                    fallback_ids.append(entity_id)
        for entity_id in fallback_ids:
            if entity_id not in entity_ids:
                edges.extend(self.edges[index] for index in self._out.get(entity_id, []))
                edges.extend(self.edges[index] for index in self._in.get(entity_id, []))
        edges = _dedupe_edges(edges)

        k = self._spec_k(spec)
        if len(edges) < k and keywords:
            for edge in self.edges:
                haystack = normalize_term(
                    " ".join(
                        [
                            _clean(edge.get("subject_name")),
                            _clean(edge.get("object_name")),
                            _clean(edge.get("quote")),
                            _clean(edge.get("reason")),
                        ]
                    )
                )
                if any(normalize_term(keyword) and normalize_term(keyword) in haystack for keyword in keywords):
                    edges.append(edge)
            edges = _dedupe_edges(edges)

        if not edges and not entity_ids and not keywords and not question:
            # 完全无信息：给出全局最高置信边，避免空结果（qa 仍会按需加 no_evidence 以外的提示）
            edges = list(self.edges)
        return self._finish(edges, spec)

    # ================================================================ 展示/健康
    def query_cypher(self, spec: QuerySpec) -> list[str]:
        """返回 ``[header, params, template]`` 三个**非空**元素（供 UI 原样展示）。

        - 不再返回空分隔元素（UI 逐元素 ``st.code``，空串会渲染空白代码框）；
        - ``params`` 行只列模板里真实出现的 ``$`` 参数（去掉 ``intent``/``k`` 等非 Cypher 参数，
          ``k`` 映射为模板的 ``$limit``），列表用 Cypher 风格双引号；
        - 找不到模板时只返回 header（列表仍非空，qa-tester e2e 不依赖模板存在）。
        """
        intent = _clean(getattr(spec, "intent", "")) or "general"
        lines: list[str] = ["// backend=local（内存邻接表检索，下方为该意图的等价 Cypher 模板，参数见 QuerySpec）"]
        template = self._template_text(intent)
        if template:
            rendered = self._render_cypher_params(spec, template)
            if rendered:
                lines.append(
                    "// params: "
                    + ", ".join(f"{name}={_format_cypher_value(value)}" for name, value in rendered)
                )
            lines.append(template)
        return [line for line in lines if line.strip()]

    def _render_cypher_params(self, spec: QuerySpec, template: str) -> list[tuple[str, Any]]:
        """按模板参数名收集并格式化参数值（只保留模板实际用到的 ``$`` 参数）。"""
        names = _template_param_names(template)
        if not names:
            return []
        params = getattr(spec, "params", None) or {}
        cypher_params = getattr(spec, "cypher_params", None) or {}
        merged: dict[str, Any] = {}
        if isinstance(params, Mapping):
            merged.update(params)
        if isinstance(cypher_params, Mapping):
            merged.update(cypher_params)

        limit_value = merged.get("limit", merged.get("k"))
        limit_number = to_float(limit_value)
        limit = int(limit_number) if limit_number is not None else self.k_default
        values: dict[str, Any] = {name: as_list(merged.get(name)) for name in _LIST_PARAM_NAMES}
        values["limit"] = max(1, min(50, limit))

        rendered: list[tuple[str, Any]] = []
        for name in names:
            if name in values:
                rendered.append((name, values[name]))
            elif name in merged:
                rendered.append((name, merged[name]))
        return rendered

    def _template_text(self, intent: str) -> str:
        path = self.queries_dir / f"{intent}.cypher"
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def stats(self) -> dict[str, Any]:
        counts: dict[str, int] = defaultdict(int)
        for entity in self.entities.values():
            counts[entity.get("label", "")] += 1
        return {
            "backend": self.name,
            "nodes": len(self.entities),
            "rels": len(self.edges),
            "varieties": counts.get("Variety", 0),
            "conditions": counts.get("Condition", 0),
            "indicators": counts.get("QualityIndicator", 0),
            "diseases": counts.get("Disease", 0),
            "sources": len(self.sources),
            "unresolved_edges": len(self.unresolved),
            "data_files": list(self._loaded_files),
        }

    def health(self) -> tuple[bool, str]:
        if not self.entities or not self.edges:
            return False, f"local: 数据为空（nodes={len(self.entities)}, rels={len(self.edges)}，data_dir={self.data_dir}）"
        return True, (
            f"local: {len(self.entities)} 节点 / {len(self.edges)} 条边"
            f"（{'、'.join(self._loaded_files)}，data_dir={self.data_dir}）"
        )

    def close(self) -> None:  # local 无连接可释放
        return None


def _dedupe_edges(edges: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """按 (subject_id/name, predicate, object_id/name) 去重，保留首次出现（保持顺序确定）。"""
    seen: set = set()
    result: list[dict[str, Any]] = []
    for edge in edges:
        key = (
            edge.get("subject_id") or edge.get("subject_name"),
            edge.get("predicate"),
            edge.get("object_id") or edge.get("object_name"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(edge))
    return result
