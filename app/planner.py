"""意图路由与查询规划（Lead 写区）。

对外契约见 docs/api.md §4：
    route(question, hits) -> (intent, confidence, candidates)
    build_query(intent, hits, k=6) -> QuerySpec
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, List, Sequence, Tuple

from app import planner_rules as R
from app.contracts import INTENTS, EntityHit, QuerySpec

_FULLWIDTH = {ord(c): ord(c) - 0xFEE0 for c in "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ（）【】～"}


def normalize_question(q: str) -> str:
    """全角转半角、去空白、异体写法归一、句末语气词剥离。"""
    if not q:
        return ""
    s = unicodedata.normalize("NFKC", str(q))
    s = s.translate(_FULLWIDTH)
    s = re.sub(r"\s+", "", s)
    for a, b in R.NORMALIZE_MAP.items():
        s = s.replace(a, b)
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


def route(question: str, hits: Sequence[EntityHit]) -> Tuple[str, float, List[Tuple[str, float]]]:
    """返回 (intent, confidence, top3候选)。

    confidence = 最高分 / 总分；低于 LOW_CONFIDENCE 时由 qa 走澄清兜底。
    无任何信号 → general, 0.0。
    """
    scores = score_intents(question, hits)
    if not scores:
        return R.DEFAULT_INTENT, 0.0, []

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in ranked) or 1.0
    top_intent, top_score = ranked[0]
    confidence = top_score / total
    # 分数太低（全是很弱的触发词）→ 视为低置信，由 qa 加 warning
    return top_intent, round(confidence, 3), [(k, round(v, 2)) for k, v in ranked[:3]]


def _ids(hits: Iterable[EntityHit], label: str) -> List[str]:
    out: List[str] = []
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

    keywords = [h.surface for h in hits if h.surface][:5]

    params: dict[str, Any] = {
        "intent": intent if intent in INTENTS else R.DEFAULT_INTENT,
        "variety_ids": variety_ids,
        "condition_ids": condition_ids,
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
            "condition_ids": condition_ids,
            "indicator_ids": indicator_ids,
            "disease_ids": disease_ids,
            "entity_ids": entity_ids,
            "limit": params["k"],
        },
    )
