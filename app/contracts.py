"""接口契约（S3 接口冻结点）：所有模块共享的数据结构均在此定义。

写区归属：Lead。其他成员只读引用，不修改本文件。
任何字段变更必须先改本文件，并同步 docs/api.md。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

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
# 第二轮可靠性加固新增（均为附加告警码，不改变既有字段/返回值契约）
WARN_SYSTEM_UNAVAILABLE = "system_unavailable"      # 核心模块未就绪：明确不可用，不返回固定答案
WARN_ANCHOR_UNVERIFIED = "anchor_unverified"        # 答案使用了待核验（anchor）证据
WARN_ANCHOR_HIGH_RISK = "anchor_high_risk"          # 仅凭 anchor 证据给出药剂/浓度/剂量/时间等高风险参数
WARN_UNSUPPORTED_FACT = "unsupported_fact"          # 事实句缺少对应证据引用（规则启发式，非语义蕴含）
WARN_CITATION_MISMATCH = "citation_mismatch"        # 引用编号有效但与句子的字面内容不相关（规则启发式）
WARN_LLM_ANSWER_REJECTED = "llm_answer_rejected"    # LLM 答案未通过校验，已回退到证据约束模板
# 第四轮交付修复新增（附加告警码，不改变既有字段/返回值契约）
WARN_ANCHOR_OVERCLAIM = "anchor_overclaim"          # anchor 证据被写成「已核验/已证实」等确定性结论
WARN_STORE_ERROR = "store_error"                    # 补充查询/后端异常，不得伪装成「图谱未收录」
WARN_OUT_OF_DOMAIN = "out_of_domain"                # 问句指向非葡萄果品（苹果/梨/桃…），离域拒答
WARN_OUT_OF_SCOPE = "out_of_scope"                  # 问句超出图谱范围（农残/安全限量等），不编造数据
# 第五轮安全加固新增（附加告警码，不改变既有字段/返回值契约）
WARN_PROMPT_INJECTION = "prompt_injection"          # 检测到绕过证据约束/系统指令的提示注入
WARN_HIGH_RISK_TOPIC = "high_risk_topic"            # 问题涉及药剂/熏蒸/剂量等高风险操作


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
    value: float | None = None
    unit: str = ""
    value_min: float | None = None
    value_max: float | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)
    source_titles: list[str] = field(default_factory=list)
    locator: str = ""
    quote: str = ""
    status: str = "anchor"         # verified | anchor
    confidence: float = 0.5
    score: float = 0.0             # 排序分

    @property
    def single_source(self) -> bool:
        return len(self.source_ids) < 2

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QuerySpec:
    """意图 → 一次结构化查询。cypher 参数化，禁止拼接。"""

    intent: str
    params: dict[str, Any] = field(default_factory=dict)
    cypher_file: str = ""
    cypher_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnswerResult:
    """问答结果（UI / CLI / 测试共用）。"""

    question: str
    entities: list[EntityHit] = field(default_factory=list)
    intent: str = "general"
    intent_confidence: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)
    answer: str = ""
    steps: list[str] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    mode: str = "template"         # llm | template；UI 层另有 unavailable | demo（不可用/演示桩）
    elapsed_ms: int = 0
    query_cypher: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    llm_meta: dict[str, Any] = field(default_factory=dict)
    context_note: str = ""  # 多轮追问承接提示（如「承接上一轮：阳光玫瑰」），单轮为空

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def to_json(self) -> str:
        """稳定的结构化输出，供 CLI/前端/日志使用。"""
        return json.dumps(self.as_dict(), ensure_ascii=False, default=str)
