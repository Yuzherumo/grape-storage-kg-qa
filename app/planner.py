"""意图路由与查询规划（Lead 写区）。

对外契约见 docs/api.md §4：
    route(question, hits) -> (intent, confidence, candidates)
    build_query(intent, hits, k=6) -> QuerySpec
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Any

from app import planner_rules as R
from app.contracts import INTENTS, EntityHit, QuerySpec

_FULLWIDTH = {ord(c): ord(c) - 0xFEE0 for c in "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ（）【】～"}


_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(text: str) -> int | None:
    """把 0~99 的中文数字（含「十八」「二十」）转成整数，无法解析返回 None。"""
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total, cur = 0, 0
    for ch in text:
        if ch == "十":
            cur = cur or 1
            total += cur * 10
            cur = 0
        elif ch in _CN_DIGITS:
            cur = _CN_DIGITS[ch]
        else:
            return None
    return total + cur


def _negate_zero_below(s: str) -> str:
    """「零下18度」「零下十八度」「负2度」→ 「-18度」「-2度」。"""
    def _repl(m: re.Match) -> str:
        val = _cn_to_int(m.group(1))
        return f"-{val}" if val is not None else m.group(0)
    s = re.sub(r"(?:零下|负)([0-9零〇一二两三四五六七八九十]+)", _repl, s)
    s = re.sub(r"(?:零下|负)(?![0-9])", "-", s)
    return s


def normalize_question(q: str) -> str:
    """全角转半角、去空白、异体写法归一、中文数字/零下转数值、句末语气词剥离。"""
    if not q:
        return ""
    s = unicodedata.normalize("NFKC", str(q))
    s = s.translate(_FULLWIDTH)
    s = re.sub(r"\s+", "", s)
    for a, b in R.NORMALIZE_MAP.items():
        s = s.replace(a, b)
    s = _negate_zero_below(s)
    changed = True
    while changed:
        changed = False
        for p in R.TRAILING_PARTICLES:
            if s.endswith(p) and len(s) > len(p):
                s = s[: -len(p)]
                changed = True
    return s


def score_intents(question: str, hits: Sequence[EntityHit]) -> dict[str, float]:
    """L2 触发词 + 句式模式 + L3 实体先验，返回原始分（未归一）。"""
    q = normalize_question(question)
    scores: dict[str, float] = {}

    for intent, rules in R.TRIGGERS.items():
        for word, weight in rules:
            if word in q:
                scores[intent] = scores.get(intent, 0.0) + weight

    for pattern, intent, bonus in R.PATTERNS:
        if re.search(pattern, q):
            scores[intent] = scores.get(intent, 0.0) + bonus

    labels = {h.label for h in hits}
    for label, priors in R.ENTITY_PRIOR.items():
        if label in labels:
            for intent, bonus in priors:
                scores[intent] = scores.get(intent, 0.0) + bonus

    # 同一实体出现多次（两个品种）→ 对比意图额外加分
    variety_hits = [h for h in hits if h.label == "Variety"]
    if len({h.node_id for h in variety_hits}) >= 2:
        scores["variety_compare"] = scores.get("variety_compare", 0.0) + 1.2

    return scores


def route(question: str, hits: Sequence[EntityHit]) -> tuple[str, float, list[tuple[str, float]]]:
    """返回 (intent, confidence, top3候选)。

    confidence = 最高分 / 总分；低于 LOW_CONFIDENCE 时由 qa 走澄清兜底。
    无任何信号 → general, 0.0。
    """
    scores = score_intents(question, hits)
    q = normalize_question(question)
    # 「怎么做/怎么用」+ 命中条件实体 → 实体中心检索（general），避免套错处置清单
    if hits and any(k in q for k in R.HOWTO_KEYWORDS) and any(h.label == "Condition" for h in hits):
        return R.DEFAULT_INTENT, 0.5, []
    # 命中「条文型操作条件」（包装/入库量/堆码/温度波动/销售/档案…）→ 实体中心检索
    if any(h.node_id in R.OPERATION_CONDITIONS for h in hits) and "CONTRA_INDICATED_FOR" not in scores:
        return R.DEFAULT_INTENT, 0.6, []
    # 全是条件实体 + 比较/区别/影响类问句（如「冰温贮藏和冷藏比怎么样」「高浓度CO2有什么问题」）→ 实体中心检索
    if hits and all(h.label == "Condition" for h in hits) and any(
        k in q for k in ("比", "对比", "区别", "哪个好", "怎么样", "有什么不同",
                         "有什么问题", "有什么影响", "有什么作用", "影响")
    ):
        return R.DEFAULT_INTENT, 0.6, []
    # 「因果/关系」问句 + 命中病害 → 病害风险意图（回答「结露诱发灰霉」，而不是给处置清单）
    if any(h.label == "Disease" for h in hits) and any(
        k in q for k in ("有什么关系", "有啥关系", "什么关系", "为什么", "咋会", "怎么引起", "什么原因", "诱因")
    ):
        return "disease_risk", 0.6, []
    if not scores:
        return R.DEFAULT_INTENT, 0.0, []

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in ranked) or 1.0
    top_intent, top_score = ranked[0]
    confidence = top_score / total
    # 分数太低（全是很弱的触发词）→ 视为低置信，由 qa 加 warning
    return top_intent, round(confidence, 3), [(k, round(v, 2)) for k, v in ranked[:3]]


def _ids(hits: Iterable[EntityHit], label: str) -> list[str]:
    out: list[str] = []
    for h in hits:
        if h.label == label and h.node_id not in out:
            out.append(h.node_id)
    return out


def build_query(intent: str, hits: Sequence[EntityHit], k: int = 6) -> QuerySpec:
    """意图 → 参数化查询。只产参数，不拼 Cypher。"""
    hits = list(hits or [])
    variety_ids = _ids(hits, "Variety")
    condition_ids = _ids(hits, "Condition")
    indicator_ids = _ids(hits, "QualityIndicator")
    disease_ids = _ids(hits, "Disease")
    entity_ids = [h.node_id for h in hits]
    # 去重保序
    entity_ids = list(dict.fromkeys(entity_ids))
    # entity_ids 只给 general 兜底用：其余意图走 typed ids，避免「冷库→cold_0」把温度结果窄化成 1 条，
    # 也保证 LocalStore 与 Neo4j 模板过滤口径一致（双后端 parity）。
    if (intent if intent in INTENTS else R.DEFAULT_INTENT) != "general":
        entity_ids = []

    keywords = [h.surface for h in hits if h.surface][:5]

    params: dict[str, Any] = {
        "intent": intent if intent in INTENTS else R.DEFAULT_INTENT,
        "variety_ids": variety_ids,
        # 只有禁忌意图才按具体条件过滤（否则「冷库」会把温度结果收窄成 1 条）
        "condition_ids": condition_ids if intent == "contraindication" else [],
        "indicator_ids": indicator_ids,
        "disease_ids": disease_ids,
        "entity_ids": entity_ids,
        "keywords": keywords,
        "k": int(k or 6),
    }
    return QuerySpec(
        intent=params["intent"],
        params=params,
        cypher_file=f"graph/queries/{params['intent']}.cypher",
        cypher_params={
            "variety_ids": variety_ids,
            "condition_ids": params["condition_ids"],
            "indicator_ids": indicator_ids,
            "disease_ids": disease_ids,
            "entity_ids": entity_ids,
            "limit": params["k"],
        },
    )
