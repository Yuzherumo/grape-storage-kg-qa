"""GraphStore 抽象、后端异常与证据排序规则（契约见 ``docs/api.md`` §5）。

写区归属：store-builder（其余成员只读引用）。

本模块**只依赖标准库**；neo4j 驱动仅在 :mod:`app.store.neo4j_store` 内惰性导入，
因此 ``import app.store.base`` 在没装 neo4j 的离线环境也永远安全。

证据排序规则（api.md §5，冻结）
--------------------------------
``score = 0.5 * confidence + 0.3 * status_weight + 0.2 * entity_hit_ratio``

- ``status_weight``：``verified=1.0``、``anchor=0.6``（未知状态按 anchor 处理）。
- ``entity_hit_ratio``：本次查询命中的实体在证据两端的覆盖度，
  ``命中实体词数 / min(命中实体总数, 2)``，上限 1.0；无实体命中时取 1.0
  （不做惩罚，退化为置信度排序）。
- 排序：``score`` 降序，同分按 ``(subject, predicate, object)`` 字典序稳定兜底。
- 去重：按 ``(subject, predicate, object)`` 保留分数最高的一条。
- 截断：取前 ``k`` 条（``k`` 来自 ``QuerySpec.params["k"]``，默认 6，夹在 1~50）。
- ``eid`` 统一留空字符串，由 qa 层分配 ``E1..En``。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any

try:  # 兼容 `python app/ui.py`（此时 sys.path[0] 是 app/，没有顶层 app 包）
    from app.contracts import EntityHit, Evidence, QuerySpec
except ImportError:  # pragma: no cover - 只是 import 路径兜底
    from contracts import EntityHit, Evidence, QuerySpec  # type: ignore[no-redef]

__all__ = [
    "DEFAULT_K",
    "W_CONFIDENCE",
    "W_STATUS",
    "W_ENTITY_HIT",
    "STATUS_WEIGHTS",
    "StoreError",
    "BackendFallback",
    "DataError",
    "GraphStore",
    "clamp01",
    "status_weight",
    "to_float",
    "as_list",
    "normalize_term",
    "hit_terms_from_hits",
    "entity_hit_ratio",
    "score_evidence",
    "rank_evidence",
    "build_evidence",
]

# ---------------------------------------------------------------- 排序权重
DEFAULT_K = 6
W_CONFIDENCE = 0.5
W_STATUS = 0.3
W_ENTITY_HIT = 0.2
STATUS_WEIGHTS: dict[str, float] = {"verified": 1.0, "anchor": 0.6}
STATUS_WEIGHT_DEFAULT = 0.6
MAX_K = 50

# 下标/上标数字 → ASCII 数字：命中度比对时 "O₂"/"CO₂" 与 "O2"/"CO2" 视为同词
_SUBSCRIPT_SUPERSCRIPT = {
    0x2080: "0", 0x2081: "1", 0x2082: "2", 0x2083: "3", 0x2084: "4",
    0x2085: "5", 0x2086: "6", 0x2087: "7", 0x2088: "8", 0x2089: "9",
    0x208A: "+", 0x208B: "-",
    0x2070: "0", 0x00B9: "1", 0x00B2: "2", 0x00B3: "3", 0x2074: "4",
    0x2075: "5", 0x2076: "6", 0x2077: "7", 0x2078: "8", 0x2079: "9",
    0x207A: "+", 0x207B: "-",
}


# ---------------------------------------------------------------- 异常
class StoreError(RuntimeError):
    """GraphStore 相关错误的基类。"""


class BackendFallback(StoreError):
    """可选后端（neo4j）不可用，调用方应回落到 :class:`app.store.local_store.LocalStore`。

    典型原因：未安装 ``neo4j`` 驱动、连接被拒、认证失败、执行超时。
    由 :func:`app.store.get_store` 捕获并回落，同时把 ``store.backend_fallback`` 置 True。
    """


class DataError(StoreError):
    """本地图谱数据缺失或无法解析（``data/entities.csv`` 等）。

    消息里务必写清「缺哪个文件 / 期望列 / 实际路径」，方便演示现场排查。
    """


# ---------------------------------------------------------------- 小工具
def clamp01(value: Any, default: float = 0.0) -> float:
    """把任意值夹到 ``[0, 1]``；无法解析时返回 ``default``。"""
    number = to_float(value)
    if number is None:
        return default
    return min(1.0, max(0.0, number))


def status_weight(status: Any) -> float:
    """``verified -> 1.0``、``anchor -> 0.6``、未知 -> 0.6。"""
    key = str(status or "").strip().lower()
    return STATUS_WEIGHTS.get(key, STATUS_WEIGHT_DEFAULT)


def to_float(value: Any) -> float | None:
    """宽松转 float：空串/None/'-'/无法解析 → None；不吞掉 ``0``。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    text = str(value).strip()
    if not text or text in {"-", "--", "—", "N/A", "n/a", "null", "None", "待核验"}:
        return None
    # 去掉常见单位/符号后尝试；失败就原样再试一次（兼容 '0.5' 之外的 '−0.5'）
    cleaned = (
        text.replace("℃", "")
        .replace("°C", "")
        .replace("%", "")
        .replace("％", "")
        .replace("μL/L", "")
        .replace("μL/L", "")
        .replace("月", "")
        .replace("天", "")
        .replace("h", "")
        .replace("±", "")
        .replace(" ", "")
        .replace("−", "-")
        .replace("，", ",")
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def as_list(value: Any) -> list[str]:
    """把 ``"a;b"`` / ``["a","b"]`` / ``None`` 统一成去空白的字符串列表。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(as_list(item))
        return out
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        for sep in ("；", ";", "，", ",", "|"):
            text = text.replace(sep, ";")
        return [part.strip() for part in text.split(";") if part.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _normalize_term(text: Any) -> str:
    """命中度比对用的归一化：小写、去空白、全角常见符号转半角。"""
    raw = str(text or "")
    if not raw:
        return ""
    out = []
    for ch in raw:
        code = ord(ch)
        if code == 0x3000:  # 全角空格
            continue
        if 0xFF01 <= code <= 0xFF5E:  # 全角 ASCII
            ch = chr(code - 0xFEE0)
        elif code in _SUBSCRIPT_SUPERSCRIPT:  # 下标/上标数字（O₂ / CO₂ / SO₂）
            ch = _SUBSCRIPT_SUPERSCRIPT[code]
        out.append(ch)
    return "".join(out).lower().replace(" ", "").replace("\t", "").replace("\n", "")


def normalize_term(text: Any) -> str:
    """归一化词表/文本：全角 ASCII 转半角、小写、去空白（linking 与命中度共用）。"""
    return _normalize_term(text)


def hit_terms_from_hits(hits: Iterable[EntityHit]) -> set:
    """从 :class:`EntityHit` 列表收集用于命中度比对的词（node_id/surface/alias）。"""
    terms: set = set()
    for hit in hits or []:
        for value in (getattr(hit, "node_id", ""), getattr(hit, "surface", ""), getattr(hit, "alias_hit", "")):
            norm = _normalize_term(value)
            if norm:
                terms.add(norm)
    return terms


def _hit_terms_from_params(spec: QuerySpec) -> set:
    """QuerySpec 没有 hits 字段时，用 params 里的 id/名称做命中度词表。"""
    terms: set = set()
    params = getattr(spec, "params", None) or {}
    for key in (
        "variety_ids",
        "condition_ids",
        "indicator_ids",
        "disease_ids",
        "entity_ids",
        "hit_terms",
        "entity_names",
    ):
        for token in as_list(params.get(key)):
            norm = _normalize_term(token)
            if norm:
                terms.add(norm)
    return terms


def entity_hit_ratio(evidence: Evidence, hit_terms: Iterable[str] | None) -> float:
    """实体命中度：查询实体出现在证据 subject/object 里的覆盖比例。

    无命中实体 → 1.0（不惩罚，退化为置信度+状态排序）。
    命中 2 个及以上实体即满分（``denominator = min(len(terms), 2)``）。
    """
    terms = {_normalize_term(t) for t in (hit_terms or [])}
    terms.discard("")
    if not terms:
        return 1.0
    haystack = _normalize_term(
        " ".join(
            [
                str(getattr(evidence, "subject", "") or ""),
                str(getattr(evidence, "object", "") or ""),
                str((getattr(evidence, "properties", None) or {}).get("object_name", "") or ""),
            ]
        )
    )
    matched = sum(1 for term in terms if term and term in haystack)
    denominator = max(1, min(len(terms), 2))
    return min(1.0, matched / denominator)


def score_evidence(evidence: Evidence, hit_terms: Iterable[str] | None = None) -> float:
    """按冻结规则计算并写回 ``evidence.score``，返回分数。"""
    score = (
        W_CONFIDENCE * clamp01(getattr(evidence, "confidence", 0.5), default=0.5)
        + W_STATUS * status_weight(getattr(evidence, "status", "anchor"))
        + W_ENTITY_HIT * entity_hit_ratio(evidence, hit_terms)
    )
    evidence.score = round(min(1.0, max(0.0, score)), 6)
    return evidence.score


def rank_evidence(
    evidences: Iterable[Evidence],
    *,
    k: int = DEFAULT_K,
    hit_terms: Iterable[str] | None = None,
) -> list[Evidence]:
    """打分 → score 降序 → 按 (subject,predicate,object) 去重 → 截断 k。"""
    items = [ev for ev in (evidences or []) if ev is not None]
    if not items:
        return []
    terms = list(hit_terms or [])
    for ev in items:
        score_evidence(ev, terms)
    items.sort(
        key=lambda ev: (
            -ev.score,
            str(getattr(ev, "subject", "") or ""),
            str(getattr(ev, "predicate", "") or ""),
            str(getattr(ev, "object", "") or ""),
        )
    )
    seen = set()
    deduped: list[Evidence] = []
    for ev in items:
        key = (
            str(getattr(ev, "subject", "") or ""),
            str(getattr(ev, "predicate", "") or ""),
            str(getattr(ev, "object", "") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    try:
        limit = int(k)
    except (TypeError, ValueError):
        limit = DEFAULT_K
    limit = max(1, min(MAX_K, limit))
    return deduped[:limit]


def build_evidence(
    row: Mapping[str, Any],
    *,
    source_titles: Mapping[str, str] | None = None,
) -> Evidence:
    """把「一行图查询结果」翻译成 :class:`Evidence`（local / neo4j 共用，保证两后端同构）。

    行内约定列（缺列用空值兜底）：``subject_id, subject, subject_label, predicate,
    object_id, object, object_label, value, unit, value_min, value_max, status,
    confidence, source_ids, source_titles, locator, quote, properties``。
    """
    props: dict[str, Any] = dict(row.get("properties") or {})
    for key in ("subject_id", "subject_label", "object_id", "object_label"):
        value = row.get(key)
        if value not in (None, ""):
            props.setdefault(key, value)
    if row.get("object_category") not in (None, ""):
        props.setdefault("object_category", row.get("object_category"))

    source_ids = as_list(row.get("source_ids"))
    titles: list[str] = as_list(row.get("source_titles"))
    if not titles and source_titles:
        titles = [str(source_titles.get(sid, sid)) for sid in source_ids]

    status_raw = str(row.get("status") or "").strip().lower()
    status = status_raw if status_raw in STATUS_WEIGHTS else "anchor"

    return Evidence(
        eid="",  # qa 层统一分配 E1..En
        subject=str(row.get("subject") or row.get("subject_id") or "").strip(),
        predicate=str(row.get("predicate") or "").strip(),
        object=str(row.get("object") or row.get("object_id") or "").strip(),
        value=to_float(row.get("value")),
        unit=str(row.get("unit") or "").strip(),
        value_min=to_float(row.get("value_min")),
        value_max=to_float(row.get("value_max")),
        properties=props,
        source_ids=source_ids,
        source_titles=titles,
        locator=str(row.get("locator") or "").strip(),
        quote=str(row.get("quote") or "").strip(),
        status=status,
        confidence=clamp01(row.get("confidence"), default=0.5),
        score=0.0,
    )


class GraphStore(ABC):
    """图谱查询后端抽象（api.md §5）。

    - ``name``：``"local"`` / ``"neo4j"``。
    - ``execute(spec)``：一跳或两跳的局部子图检索，返回已排序/去重/截断的证据。
    - ``stats()``：节点/边/品种等计数（UI 侧栏展示）。
    - ``health()``：``(ok, message)``，UI/自检可用。
    - ``query_cypher(spec)``：可选便利方法，返回给 UI 折叠区展示的查询文本。
    - ``backend_fallback`` / ``fallback_reason``：由工厂在回落时写入（qa 用来加 warning）。
    """

    name: str = "base"
    backend_fallback: bool = False
    fallback_reason: str = ""

    @abstractmethod
    def execute(self, spec: QuerySpec) -> list[Evidence]:
        """执行一次结构化查询，返回证据（``eid`` 留空）。"""

    def stats(self) -> dict[str, Any]:
        """返回 ``{"nodes": int, "rels": int, "varieties": int, ...}``。"""
        raise NotImplementedError(f"{self.name}: stats() 未实现")

    def health(self) -> tuple[bool, str]:
        """返回 ``(ok, message)``；默认视为不可用。"""
        return False, f"{self.name}: health() 未实现"

    def query_cypher(self, spec: QuerySpec) -> list[str]:
        """返回该次查询对应的 Cypher 文本（供 ``AnswerResult.query_cypher`` 展示）。"""
        return []

    def close(self) -> None:  # noqa: B027
        """释放连接（local 无需操作）。"""

    # -- 内部工具 ---------------------------------------------------------
    def _rank(
        self,
        evidences: Iterable[Evidence],
        spec: QuerySpec,
        *,
        k_override: int | None = None,
    ) -> list[Evidence]:
        """按契约统一收尾：排序/去重/截断。

        命中度词表 = params 中的实体 id/名称；:class:`EntityHit` 的 surface/alias
        由 planner 直接写进 params（如 ``hit_terms``）时同样生效。
        """
        params = getattr(spec, "params", None) or {}
        if k_override is not None:
            k = k_override
        else:
            k_value = params.get("k", DEFAULT_K)
            try:
                k = int(to_float(k_value) if to_float(k_value) is not None else DEFAULT_K)
            except (TypeError, ValueError):
                k = DEFAULT_K
        k = max(1, min(MAX_K, k))
        return rank_evidence(evidences, k=k, hit_terms=_hit_terms_from_params(spec))

    # -- 品种对比覆盖（local / neo4j 共用） --------------------------------
    @staticmethod
    def _evidence_covers(evidence: Evidence, entity_id: str) -> bool:
        properties = getattr(evidence, "properties", None) or {}
        return properties.get("subject_id") == entity_id or properties.get("object_id") == entity_id

    def _select_with_coverage(
        self,
        pool: list[Evidence],
        entity_ids: Iterable[str],
        k: int,
    ) -> list[Evidence]:
        """品种对比：先保证每个品种至少一条证据，再用分数补满 k（再按分数排序）。"""
        required = [entity_id for entity_id in (entity_ids or []) if entity_id]
        selected: list[Evidence] = []
        for entity_id in required:
            for evidence in pool:
                if evidence not in selected and self._evidence_covers(evidence, entity_id):
                    selected.append(evidence)
                    break
        for evidence in pool:
            if len(selected) >= k:
                break
            if evidence not in selected:
                selected.append(evidence)
        selected.sort(
            key=lambda item: (
                -item.score,
                str(getattr(item, "subject", "") or ""),
                str(getattr(item, "predicate", "") or ""),
                str(getattr(item, "object", "") or ""),
            )
        )
        return selected[: max(1, int(k))]
