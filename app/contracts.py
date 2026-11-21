"""接口契约（S3 接口冻结点）：所有模块共享的数据结构均在此定义。

写区归属：Lead。其他成员只读引用，不修改本文件。
任何字段变更必须先改本文件，并同步 docs/api.md。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------- 意图枚举
INTENTS = (
    "temperature",
    "humidity",
    "atmosphere",
    "shelf_life",
    "disease_control",
    "disease_risk",
    "quality_indicator",
    "variety_compare",
    "contraindication",
    "general",
)

# ---------------------------------------------------------------- 告警码
WARN_NO_EVIDENCE = "no_evidence"
WARN_NO_CITATION = "no_citation"
WARN_LLM_TIMEOUT = "llm_timeout"
WARN_LLM_UNAVAILABLE = "llm_unavailable"
WARN_BACKEND_FALLBACK = "backend_fallback"
WARN_OUT_OF_RANGE = "out_of_range"
WARN_LOW_CONFIDENCE_INTENT = "low_confidence_intent"
WARN_SINGLE_SOURCE = "single_source"


@dataclass
class EntityHit:
    """实体链接结果。"""

    node_id: str
    label: str          # Variety | Condition | QualityIndicator | Disease
    surface: str        # 命中的原文片段
    alias_hit: str      # 命中的词表条目（规范名或别名）
    score: float = 1.0
    start: int = -1
    end: int = -1


@dataclass
class Evidence:
    """一条可溯源证据（对应图谱中的一条边/一条三元组）。"""

    eid: str                       # [E1] 的编号字符串，如 "E1"
    subject: str
    predicate: str
    object: str
    value: Optional[float] = None
    unit: str = ""
    value_min: Optional[float] = None
    value_max: Optional[float] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    source_ids: List[str] = field(default_factory=list)
    source_titles: List[str] = field(default_factory=list)
    locator: str = ""
    quote: str = ""
    status: str = "anchor"         # verified | anchor
    confidence: float = 0.5
    score: float = 0.0             # 排序分

    @property
    def single_source(self) -> bool:
        return len(self.source_ids) < 2

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuerySpec:
    """意图 → 一次结构化查询。cypher 参数化，禁止拼接。"""

    intent: str
    params: Dict[str, Any] = field(default_factory=dict)
    cypher_file: str = ""
    cypher_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnswerResult:
    """问答结果（UI / CLI / 测试共用）。"""

    question: str
    entities: List[EntityHit] = field(default_factory=list)
    intent: str = "general"
    intent_confidence: float = 0.0
    evidence: List[Evidence] = field(default_factory=list)
    answer: str = ""
    steps: List[str] = field(default_factory=list)
    cited_ids: List[str] = field(default_factory=list)
    mode: str = "template"         # llm | template
    elapsed_ms: int = 0
    query_cypher: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    llm_meta: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d
