"""问答核心（Lead 写区）：实体链接 → 意图 → 查图谱 → 证据 → 生成 → 校验。

对外契约见 docs/api.md §6。核心保证：
- `allow_llm=False` 或 LLM 不可用时走**确定性模板**，仍返回带 [E#] 的答案与分步动作；
- 答案中的数字必须能在证据里找到来源，否则打 `unsourced_number` 告警；
- 证据为空时明确说「未检索到」，绝不编造。

CLI：
    python -m app.qa "阳光玫瑰放冷库该调到多少度？"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Sequence
from typing import Any

from app.contracts import (
    WARN_ANCHOR_HIGH_RISK,
    WARN_ANCHOR_UNVERIFIED,
    WARN_BACKEND_FALLBACK,
    WARN_CITATION_MISMATCH,
    WARN_LLM_ANSWER_REJECTED,
    WARN_LLM_TIMEOUT,
    WARN_LLM_UNAVAILABLE,
    WARN_LOW_CONFIDENCE_INTENT,
    WARN_NO_CITATION,
    WARN_NO_EVIDENCE,
    WARN_OUT_OF_RANGE,
    WARN_SINGLE_SOURCE,
    WARN_UNSUPPORTED_FACT,
    AnswerResult,
    EntityHit,
    Evidence,
    QuerySpec,
)
from app.llm import LLMClient, LLMUnavailable
from app.planner import build_query, contains_term, detect_topics, normalize_question, route

PRED_LABEL = {
    "REQUIRES": "需要条件",
    "CONTRA_INDICATED_FOR": "禁忌",
    "AFFECTS": "影响",
    "SUSCEPTIBLE_TO": "易感",
    "PREVENTED_BY": "可预防/处置",
    "INDUCED_BY": "诱发因素",
    "ALTERNATIVE_TO": "替代方案",
    "INDICATES": "预警信号",
    "HAS_INDICATOR_VALUE": "指标基线",
}

WARN_ANCHOR_OVERCLAIM = "anchor_overclaim"

SINGLE_SOURCE_PREDS = {"CONTRA_INDICATED_FOR", "ALTERNATIVE_TO", "INDICATES"}

# ------------------------------------------------------------------ 证据分级（verified / anchor）
# 高风险操作：药剂、浓度、剂量、处理时间等。仅凭「待核验」（anchor）证据不得生成具体执行参数。
HIGH_RISK_TERMS = (
    "SO₂", "SO2", "二氧化硫", "1-MCP", "1-mcp", "焦亚硫酸", "臭氧", "保鲜剂",
    "熏蒸", "熏蒸时间", "浓度", "剂量", "用量", "处理时间", "喷施", "浸泡",
)
_HIGH_RISK_UNIT_RE = re.compile(
    r"-?\d+(?:\.\d+)?\s*(?:%|℃|°C|h|小时|分钟|min|μL/L|uL/L|ppm|mg/L|g/L|mL/L|倍)"
)
_FREEZE_TERMS = ("冷冻", "冻起来", "冻住", "冻结", "冰点以下")


def _is_high_risk(e: Evidence) -> bool:
    """该证据是否涉及高风险操作参数（只看主体/客体/类别，调用方自行区分 verified/anchor）。"""
    blob = " ".join([e.subject, e.object, str(e.properties.get("category") or "")])
    if not any(term in blob for term in HIGH_RISK_TERMS):
        return False
    return bool(_HIGH_RISK_UNIT_RE.search(blob) or e.value is not None or e.value_min is not None)


def _has_high_risk_param(text: str) -> bool:
    """文本里是否出现「药剂 + 数值 + 剂量/时间/浓度单位」这类可执行参数。"""
    if not _HIGH_RISK_UNIT_RE.search(text or ""):
        return False
    return any(term in text for term in HIGH_RISK_TERMS)



# ------------------------------------------------------------------ 工具
def _get_store(store: Any = None, settings: Any = None):
    if store is not None:
        return store
    from app.config import load_settings

    settings = settings or load_settings()
    from app.store import get_store  # 延迟导入，允许 store 未就绪时仍可 import 本模块

    return get_store(settings)


def _fmt_value(e: Evidence) -> str:
    if e.value is not None:
        try:
            return f"{e.value:g}{e.unit}"
        except TypeError:
            return f"{e.value}{e.unit}"
    if e.value_min is not None or e.value_max is not None:
        lo = "" if e.value_min is None else f"{e.value_min:g}"
        hi = "" if e.value_max is None else f"{e.value_max:g}"
        if lo and hi:
            return f"{lo}~{hi}{e.unit}"
        if lo:  # 只有下限（如 SSC≥16%）→ 不能输出悬空的「16~%」
            return f"≥{lo}{e.unit}"
        return f"≤{hi}{e.unit}"
    return ""


def _status_cn(e: Evidence) -> str:
    return "已核验" if e.status == "verified" else "待核验"


def _sources_cn(e: Evidence) -> str:
    if e.source_titles:
        return "；".join(e.source_titles[:2])
    if e.source_ids:
        return "；".join(e.source_ids[:2])
    return "来源未标注"


def _evidence_line(e: Evidence) -> str:
    val = _fmt_value(e)
    tail = f"（{val}）" if val and val not in e.object else ""
    loc = f"；条款：{e.locator[:42]}" if (e.locator or "").strip() else ""
    return (
        f"[{e.eid}] {e.subject} —{PRED_LABEL.get(e.predicate, e.predicate)}→ {e.object}{tail}；"
        f"来源：{_sources_cn(e)}；{_status_cn(e)}；置信 {e.confidence:.2f}{loc}"
    )


def _assign_eids(evidence: list[Evidence]) -> list[Evidence]:
    for i, e in enumerate(evidence, start=1):
        e.eid = f"E{i}"
    return evidence


def _dedupe(evidence: Sequence[Evidence]) -> list[Evidence]:
    seen = set()
    out: list[Evidence] = []
    for e in evidence:
        key = (e.subject, e.predicate, e.object)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


# ------------------------------------------------------------------ 事实句
def _fact(e: Evidence, question_varieties: Sequence[str] = ()) -> str:
    p, eff = e.predicate, (e.properties.get("effect") or "")
    if p == "REQUIRES":
        return f"{e.subject}的适宜条件包含{e.object}"
    if p == "HAS_INDICATOR_VALUE":
        val = _fmt_value(e)
        if val:
            return f"{e.subject}的{e.object}基线为{val}"
        return f"图谱未收录{e.subject}的{e.object}具体数值"
    if p == "CONTRA_INDICATED_FOR":
        sev = e.properties.get("severity") or "需注意"
        # 数据方向：条件 -CONTRA_INDICATED_FOR-> 品种（subject=被禁条件，object=品种）
        return f"{e.subject}对{e.object}属{sev}风险，不宜使用"
    if p == "AFFECTS":
        direction = "下降" if eff == "decrease" else ("上升" if eff == "increase" else "变化")
        return f"{e.subject}会使{e.object}{direction}"
    if p == "SUSCEPTIBLE_TO":
        level = e.properties.get("level") or e.properties.get("severity") or ""
        return f"{e.subject}易感{e.object}（{level}）" if level else f"{e.subject}易感{e.object}"
    if p == "PREVENTED_BY":
        return f"防{e.subject}可用{e.object}"
    if p == "INDUCED_BY":
        return f"{e.object}会诱发{e.subject}"
    if p == "ALTERNATIVE_TO":
        return f"可用{e.subject}替代{e.object}"
    if p == "INDICATES":
        return f"{e.subject}可作为{e.object}的预警信号"
    return f"{e.subject}-{e.predicate}->{e.object}"


# ------------------------------------------------------------------ 分步动作
_STEP_RULES = (
    ("预冷", "采后尽快预冷：{obj}"),
    ("低温冷藏", "把冷库温度设到 {obj}，每天记录两次库温并留台账"),
    ("冰温", "冰温库按 {obj} 设定，注意控温精度"),
    ("相对湿度", "湿度控制在 {obj}，避免结露"),
    ("低湿", "避免湿度过低，目标 {obj}"),
    ("气调", "气调参数按 {obj} 设定并每天监测"),
    ("1-MCP", "如需 1-MCP 处理，按 {obj} 执行，先小批量试"),
    ("SO2", "如需硫处理，按 {obj} 执行，先小批量试；阳光玫瑰不建议"),
    ("焦亚硫酸盐", "缓释片按 {obj} 使用，避免直接接触果面"),
    ("臭氧", "按 {obj} 处理，注意通风"),
    ("微孔", "包装使用 {obj}，避免密封结露"),
    ("冷链", "全程冷链：{obj}"),
    ("无伤采收", "采收与搬运做到无伤：{obj}"),
    # 品质指标类（Q3「掉粒发软」与品质题需要）
    ("落粒", "轻拿轻放、减少倒筐震动；按 {obj} 监测落粒变化"),
    ("掉粒", "轻拿轻放、减少倒筐震动；按 {obj} 监测落粒变化"),
    ("褐变", "出库前逐箱检查 {obj}，褐变明显的先销"),
    ("失重", "按 {obj} 记录失水，包装/湿度异常时先排查"),
    ("腐烂", "按 {obj} 分拣病果，避免整箱传染"),
    ("硬度", "按 {obj} 分级，软果优先出库"),
    ("呼吸强度", "按 {obj} 判断是否已进入呼吸高峰，及时出库"),
    ("乙烯", "避免与高乙烯果品混放；按 {obj} 监测"),
    ("糖度", "出库前抽测 {obj}，不达标的不入高端渠道"),
    ("异味", "开箱闻味检查 {obj}，有异味整箱隔离"),
)


def compose_steps(evidence: Sequence[Evidence], intent: str, limit: int = 3) -> list[str]:
    """由证据派生「现在该做什么」，≤3 步；无证据返回 []。"""
    if intent == "general":  # 实体中心检索不硬编动作，避免「按腐烂率分拣」这类错位建议
        return []
    steps: list[str] = []
    for e in evidence:
        cat = e.properties.get("category") or ""
        if e.predicate == "CONTRA_INDICATED_FOR":
            # 数据方向：条件 -CONTRA_INDICATED_FOR-> 品种（subject=被禁条件，object=品种）；
            # 替代方向：替代条件 -ALTERNATIVE_TO-> 被替代条件（subject=可用的替代）。
            # 步骤必须指向被禁条件，绝不能生成「不要用 <品种>，改用 <被禁条件>」的反向建议。
            alt = next(
                (x.subject for x in evidence if x.predicate == "ALTERNATIVE_TO" and x.object == e.subject),
                "",
            )
            txt = f"不要用 {e.subject}"
            if alt:
                txt += f"，改用 {alt}"
            steps.append(f"{txt}（[{e.eid}]）")
            continue
        if e.predicate == "INDUCED_BY":
            steps.append(f"避免 {e.object}（[{e.eid}]）")
            continue
        if e.predicate in ("PREVENTED_BY", "REQUIRES", "HAS_INDICATOR_VALUE", "AFFECTS"):
            for keyword, tpl in _STEP_RULES:
                if keyword in e.object or keyword in cat:
                    if e.status != "verified" and _is_high_risk(e):
                        # anchor + 高风险：不得把待核验证据里的药剂/浓度/剂量/时间当执行参数
                        steps.append(
                            f"{keyword}处理的具体浓度/剂量/处理时间请按产品标签与当地技术员确认"
                            f"（[{e.eid}]）"
                        )
                    else:
                        steps.append(tpl.format(obj=e.object) + f"（[{e.eid}]）")
                    break
    # 去重保序
    out: list[str] = []
    seen: set[str] = set()
    for s in steps:
        key = re.sub(r"（\[E\d+\]）$", "", s)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


_FOCUS_TERMS: dict[str, tuple[str, ...]] = {
    "humidity": ("湿度", "相对湿度", "rh"),
    "atmosphere": ("气调", "氧气", "二氧化碳", "o2", "co2"),
    "packaging": ("包装", "保鲜袋", "保鲜膜", "纸箱", "装箱", "袋", "膜"),
    "precool": ("预冷", "打冷", "快速降温"),
    "transport": ("运输", "冷链", "物流", "发货"),
    "shelf": ("耐贮性", "货架期"),
    "room_temp": ("常温", "室温"),
}

_TOPIC_CN = {
    "humidity": "湿度",
    "atmosphere": "气调",
    "packaging": "包装",
    "precool": "预冷",
    "transport": "运输/冷链",
    "shelf": "货架期/耐贮性",
    "room_temp": "常温",
}


def _evidence_blob(e: Evidence) -> str:
    """主题匹配只看主体/客体；quote 里的偶然词（如档案记录提到运输）不能把边带进来。"""
    return normalize_question(" ".join([str(e.subject or ""), str(e.object or "")]))


def _focus_evidence_for_question(
    question: str, evidence: Sequence[Evidence], intent: str = ""
) -> tuple[list[Evidence], str | None]:
    """按问句主题过滤证据；返回 (聚焦后证据, 缺失主题)。

    只保留与问句主题（预冷/运输/包装/湿度/气调/货架）直接相关的边。
    若聚焦后为空，说明图谱写的是其他类别的知识，不能拿来回答。
    """
    topics = detect_topics(question)
    order = [t for t in ("humidity", "atmosphere", "packaging", "precool", "transport", "shelf", "room_temp") if t in topics]
    if intent == "variety_compare":
        order = [t for t in order if t != "shelf"]
    if not order:
        return list(evidence), None
    picked: list[Evidence] = []
    for item in evidence:
        blob = _evidence_blob(item)
        if any(contains_term(blob, term) for topic in order for term in _FOCUS_TERMS[topic]):
            picked.append(item)
    if picked:
        return picked, None
    return [], order[0]


def _asks_temperature(question: str) -> bool:
    q = normalize_question(question)
    return bool(re.search(r"温度|几度|多少度|℃|°C|-?\d+\s*度", q))


def _transport_temperature_supported(question: str, evidence: Sequence[Evidence]) -> bool:
    """运输温度问题必须有「运输/冷链」主体或客体 + 温度值，不能用一般冷藏温度冒充。"""
    if not _asks_temperature(question):
        return True
    for item in evidence:
        subject = normalize_question(str(item.subject or ""))
        obj = normalize_question(str(item.object or ""))
        if not any(term in subject + obj for term in ("运输", "冷链", "物流", "发货")):
            continue
        if item.unit == "℃":
            return True
        if re.search(r"-?\d+(?:\.\d+)?\s*(?:℃|°C|度)", subject + " " + obj):
            return True
    return False


def _restrict_to_hit_varieties(evidence: Sequence[Evidence], hits: Sequence[EntityHit]) -> list[Evidence]:
    """问题点名品种时，去掉其他品种的证据；通用/病害/条件边保留。"""
    hit_ids = {h.node_id for h in hits if h.label == "Variety"}
    if not hit_ids:
        return list(evidence)
    kept: list[Evidence] = []
    for item in evidence:
        subject_id = str(item.properties.get("subject_id") or "")
        object_id = str(item.properties.get("object_id") or "")
        subject_label = str(item.properties.get("subject_label") or item.properties.get("subject_category") or "")
        object_label = str(item.properties.get("object_label") or item.properties.get("object_category") or "")
        variety_ids = set()
        if subject_label == "Variety" and subject_id:
            variety_ids.add(subject_id)
        if object_label == "Variety" and object_id:
            variety_ids.add(object_id)
        if variety_ids and not (variety_ids & hit_ids):
            continue
        kept.append(item)
    return kept


def _missing_evidence_answer(question: str, hits: Sequence[EntityHit], topics: set[str]) -> str:
    names = "、".join(dict.fromkeys(h.surface or h.node_id for h in hits)) if hits else ""
    topic_cn = "、".join(_TOPIC_CN[t] for t in sorted(topics) if t in _TOPIC_CN)
    if "transport" in topics and _asks_temperature(question):
        return (
            "结论：图谱暂未收录「运输温度」的可引用证据，不能拿普通冷藏温度代替。\n\n"
            "依据：现有运输相关数据只有冷链运输/防腐条件，没有运输温度数值。\n\n"
            "可以改问：「冷库温度多少？」「运输时要注意什么？」"
        )
    if names and topic_cn:
        return (
            f"结论：图谱暂未收录「{names}」的{topic_cn}相关证据，不拿其他品种或条件凑答案。\n\n"
            "依据：该问题命中了实体，但对应类别的知识库证据为空。\n\n"
            "可以改问已收录的品种或条件，例如「阳光玫瑰湿度多少？」"
        )
    if topic_cn:
        return (
            f"结论：图谱暂未收录与「{topic_cn}」相关的可引用证据。\n\n"
            "依据：当前没有对应主题的三元组，不能拿其他类别知识代替。\n\n"
            "可以换一种问法，或改问已收录的主题。"
        )
    return (
        "结论：图谱里没有检索到与该问题直接相关的证据，不编造数据。\n\n"
        "依据：当前证据为空。\n\n"
        "可以换成已收录的品种/条疾病/指标再问。"
    )


def _anchor_note(evidence: Sequence[Evidence]) -> str:
    """anchor（待核验）证据的显式说明：不得被描述成已证实事实；高风险参数需人工确认。"""
    anchors = [e for e in evidence if e.status != "verified"]
    if not anchors:
        return ""
    note = (
        "\n\n说明：以上依据含标为「待核验」（anchor）的条目，"
        "未逐字核对来源原文；关键操作前请以来源原文或当地技术员确认为准。"
    )
    if any(_is_high_risk(e) for e in anchors):
        note += "涉及药剂、浓度、剂量或处理时间的参数不得直接照搬，需按产品标签与技术人员意见执行。"
    return note


# ------------------------------------------------------------------ 模板答案
def template_answer(
    intent: str,
    question: str,
    evidence: Sequence[Evidence],
    entities: Sequence[EntityHit],
    out_of_range: bool,
    missing_shelf_ids: set | None = None,
) -> str:
    """模板答案：结论 + 依据。每句带 [E#]。"""
    if not evidence:
        return (
            "结论：图谱里没有检索到与这个问题直接相关的证据，我不编造数据。\n\n"
            "依据：当前证据为空。\n\n"
            "可以换个问法，例如「阳光玫瑰放冷库该调到多少度？」「冷库里葡萄长白毛了怎么办？」"
        )

    facts = [_fact(e) for e in evidence[:3]]
    if out_of_range:
        temp_ev = next((e for e in evidence if e.unit == "℃"), evidence[0])
        head = (
            f"结论：不可行。图谱证据只覆盖 {temp_ev.object} 这一档（[{temp_ev.eid}]），"
            "你问的温度已超出该区间：低于冰点会冻伤果肉、解冻后很快腐烂。"
        )
        facts = [f"可用的温度区间是 {temp_ev.object}（[{temp_ev.eid}]）"]
    elif intent == "disease_control":
        prev = [e for e in evidence if e.predicate == "PREVENTED_BY"]
        risk = [e for e in evidence if e.predicate == "INDUCED_BY"]
        name = next((e.subject for e in evidence if e.predicate in ("PREVENTED_BY", "INDUCED_BY", "SUSCEPTIBLE_TO")), "")
        if prev:
            acts = "、".join(f"{e.object}（[{e.eid}]）" for e in prev[:3])
            head = f"结论：{name or '这个症状'}优先按处置条件处理，可用 {acts}。"
            if risk:
                head += f"同时要避免{'、'.join(e.object for e in risk[:2])}。"
            head += "已发病的果穗先挑出隔离，工具消毒后再处理健康果。"
        else:
            head = "结论：" + "；".join(f"{f}（[{e.eid}]）" for f, e in zip(facts, evidence[:3], strict=False)) + "。"

    elif intent == "variety_compare":
        # 先算「哪些命中品种在图里没有耐贮性基线」（以 missing_shelf_ids / 有效证据为准）
        have_ids = {
            e.properties.get("subject_id") for e in evidence
            if e.predicate == "HAS_INDICATOR_VALUE" and e.object == "耐贮性"
            and (e.value is not None or e.value_min is not None or e.value_max is not None)
        }
        missing: list[str] = []
        seen_ids: set[str] = set()
        for h in [x for x in entities if x.label == "Variety"]:
            if h.node_id in seen_ids:
                continue
            seen_ids.add(h.node_id)
            if (missing_shelf_ids is not None and h.node_id in missing_shelf_ids) or (
                missing_shelf_ids is None and h.node_id not in have_ids
            ):
                missing.append(h.surface)

        # 「哪个更能放」类对比以耐贮性为主线，糖酸作为补充
        vs = sorted(
            [e for e in evidence if e.predicate == "HAS_INDICATOR_VALUE"],
            key=lambda e: 0 if e.object == "耐贮性" else 1,
        )
        if len({e.subject for e in vs}) >= 2:
            parts = []
            for e in vs[:3]:
                val = _fmt_value(e)
                if val:
                    parts.append(f"{e.subject} {e.object} {val}（[{e.eid}]）")
                elif e.object != "耐贮性":
                    # 耐贮性缺失由下面统一说明，避免同一句重复
                    parts.append(f"图谱未收录{e.subject}的{e.object}数值（[{e.eid}]）")
            head = "结论：" + "；".join(parts)
        else:
            head = "结论：" + "；".join(f"{f}（[{e.eid}]）" for f, e in zip(facts, evidence[:3], strict=False))
        # 去重：同一品种同一句不重复出现
        if not missing and missing_shelf_ids is None:
            # 回退（无 entities 的合成场景）：直接从证据里找「有耐贮性边但没数值」的品种
            missing = [e.subject for e in vs if e.object == "耐贮性" and not _fmt_value(e)]
        missing = [m for m in missing if f"图谱未收录{m}的" not in head]
        if missing:
            head += "；图谱未收录" + "、".join(missing) + "的耐贮性数值"
        head += "。"
    elif intent == "contraindication":
        c = next((e for e in evidence if e.predicate == "CONTRA_INDICATED_FOR"), None)
        contra_name = getattr(c, "subject", "") or ""
        alt = next(
            (e for e in evidence if e.predicate == "ALTERNATIVE_TO" and e.object == contra_name),
            None,
        ) or next((e for e in evidence if e.predicate == "ALTERNATIVE_TO"), None)
        if c:
            sev = c.properties.get("severity") or "需注意"
            # 数据方向：条件 -CONTRA_INDICATED_FOR-> 品种，主语应是被禁条件
            head = f"结论：{c.subject} 对 {c.object} 属于{sev}风险，不建议直接用（[{c.eid}]）。"
            if alt:
                head += f"可考虑用 {alt.subject} 替代 {alt.object}（[{alt.eid}]）。"
            elif c.properties.get("reason"):
                head += f"原因：{c.properties.get('reason')}。"
        else:
            head = "结论：" + "；".join(f"{f}（[{e.eid}]）" for f, e in zip(facts, evidence[:3], strict=False)) + "。"
    else:
        head = "结论：" + "；".join(f"{f}（[{e.eid}]）" for f, e in zip(facts, evidence[:3], strict=False)) + "。"

    basis = "依据：\n" + "\n".join(f"- {_evidence_line(e)}" for e in evidence[:5])
    # 温度口径冲突时显式解释（国标通用区间 vs 文献工程口径）
    if intent == "temperature":
        objs = {e.object for e in evidence}
        if "低温冷藏 0±0.5℃" in objs and "低温冷藏 -1~0℃" in objs:
            head += (
                "\n\n口径说明：GB/T 16862-2026 §7.3 的通用冷藏区间是 -1℃~0℃（verified）；"
                "0±0.5℃ 是文献/工程口径（anchor）。实际设定建议按国标 -1~0℃ 控温，"
                "并保证温度波动不超过 ±0.5℃，两者并不冲突。"
            )
    return head + "\n\n" + basis + _anchor_note(evidence)


# ------------------------------------------------------------------ 数值校验
# 单位族：答案里的数字带单位时，与证据同单位的区间比对；不带单位时与证据文本数字比对。
_UNIT_FAMILIES = (
    (re.compile(r"℃|°C"), "temperature"),
    (re.compile(r"%"), "percent"),
    (re.compile(r"个月|月"), "month"),
    (re.compile(r"h|小时"), "hour"),
)
_UNIT_SUFFIX = r"(℃|°C|%|个月|月|h|小时|μL/L|uL/L|N)"
_NUM_BODY = r"-?\d+(?:\.\d+)?"
_PM_RE = re.compile(r"(" + _NUM_BODY + r")\s*±\s*(" + _NUM_BODY + r")\s*" + _UNIT_SUFFIX + "?")
_SPAN_RE = re.compile(r"(" + _NUM_BODY + r")\s*(?:~|～|—|–|-)\s*(" + _NUM_BODY + r")\s*" + _UNIT_SUFFIX + "?")
_NUM_RE = re.compile(_NUM_BODY)
_TOKEN_RE = re.compile(r"(" + _NUM_BODY + r")\s*" + _UNIT_SUFFIX + "?")


def _family_of(unit: str) -> str:
    for pat, fam in _UNIT_FAMILIES:
        if pat.search(unit or ""):
            return fam
    return ""


def _ranges_from_text(text: str):
    """从「0±0.5℃」「-1~0℃」「90~95%」「2~4月」这类证据文本里抽区间。"""
    out = []
    for m in _PM_RE.finditer(text or ""):
        center, delta = float(m.group(1)), float(m.group(2))
        fam = _family_of(m.group(3) or "")
        out.append((fam, center - abs(delta), center + abs(delta)))
    for m in _SPAN_RE.finditer(text or ""):
        a, b = float(m.group(1)), float(m.group(2))
        fam = _family_of(m.group(3) or "")
        out.append((fam, min(a, b), max(a, b)))
    return out


def check_numbers(answer: str, evidence: Sequence[Evidence], question: str = "") -> list[str]:
    """单位感知 + 区间感知的数值一致性校验。

    - 带单位的数字：与证据同单位区间比对，落在区间外 → ``out_of_range:<num><unit>``；
    - 不带单位/证据无同单位区间的数字：与证据文本中的数字比对，否则 ``unsourced_number:<num>``；
    - 先剥 ``[E#]`` 与行首步骤序号，避免把引用编号、列表序号当数字。
    """
    fam_ranges: dict[str, list[tuple[float, float]]] = {}
    bare_allowed: set[float] = set()

    def _add_bare(text: Any) -> None:
        for m in _NUM_RE.findall(str(text)):
            try:
                bare_allowed.add(round(float(m), 2))
            except ValueError:
                pass

    for e in evidence:
        fam = _family_of(e.unit)
        if fam:
            if e.value is not None:
                fam_ranges.setdefault(fam, []).append((float(e.value), float(e.value)))
            elif e.value_min is not None or e.value_max is not None:
                lo = float(e.value_min) if e.value_min is not None else float("-inf")
                hi = float(e.value_max) if e.value_max is not None else float("inf")
                fam_ranges.setdefault(fam, []).append((lo, hi))
        text = " ".join([e.subject, e.object, e.locator, str(e.properties)])
        for f2, lo, hi in _ranges_from_text(text):
            if f2:
                fam_ranges.setdefault(f2, []).append((lo, hi))
        _add_bare(text)
        # 来源标题/来源 id 里的编号（如「NY/T 1199-2006」「gbt16862_2026」）属证据元数据，
        # 会原样出现在「依据」行中，不应判为编造数字。
        _add_bare(" ".join(e.source_titles))
        _add_bare(" ".join(e.source_ids))
        _add_bare(str(e.confidence))  # 依据行里的「置信 0.78」属证据元数据，不算编造
        _add_bare(f"{e.value} {e.value_min} {e.value_max}")  # 结构化数值（如 -0.5~0.5）也是证据数字
    # 注意：问题里的数字**不加入白名单**。否则 LLM 只要复述用户问句里的 -18℃/45%
    # 就能绕过数值校验（历史审计发现）。问题中的越界值由 detect_out_of_range 单独判。

    clean = re.sub(r"\[E\d+\]", "", answer or "")          # [E5] 不是数字 5
    clean = re.sub(r"(?m)^\s*\d+[.、)）]\s*", "", clean)     # 行首步骤序号
    clean = clean.replace("1-MCP", "MCP")                   # 避免把 1-MCP 的 1 当数值

    warnings: list[str] = []

    def _warn(code: str) -> None:
        if code not in warnings:
            warnings.append(code)

    for m in _TOKEN_RE.finditer(clean):
        try:
            v = round(float(m.group(1)), 2)
        except ValueError:
            continue
        unit = (m.group(2) or "").strip()
        fam = _family_of(unit)
        if fam:
            ranges = fam_ranges.get(fam) or []
            if any(lo - 1e-6 <= v <= hi + 1e-6 for lo, hi in ranges):
                continue
            if v in bare_allowed:  # 证据文本里原样出现过（如「>5%」、「0.5℃」）
                continue
            _warn(f"out_of_range:{m.group(1)}{unit}" if ranges else f"unsourced_number:{m.group(1)}{unit}")
        else:
            if v in bare_allowed or any(abs(v - a) <= 1e-6 for a in bare_allowed):
                continue
            _warn(f"unsourced_number:{m.group(1)}")
    return warnings



_CITE_SCAN_RE = re.compile(r"[\[【]\s*([Ee])\s*(\d+)\s*[\]】]")


def _canonicalize_citations(text: str) -> str:
    """把全角【E1】、小写 [e1] 统一为半角 [E1]（编号体系不变，仅规范化）。"""
    return _CITE_SCAN_RE.sub(lambda m: f"[{m.group(1).upper()}{m.group(2)}]", str(text or ""))


def verify_citations(answer: str, evidence: Sequence[Evidence]) -> tuple[list[str], list[str]]:
    valid_ids = {e.eid for e in evidence}
    cited = re.findall(r"\[(E\d+)\]", _canonicalize_citations(answer))
    uniq = [c for c in dict.fromkeys(cited) if c in valid_ids]
    invalid = [c for c in dict.fromkeys(cited) if c not in valid_ids]
    warnings: list[str] = [] if uniq else [WARN_NO_CITATION]
    for cid in invalid:
        code = f"invalid_citation:{cid}"
        if code not in warnings:
            warnings.append(code)
    return uniq, warnings


# ------------------------------------------------------------------ 证据相关性 / 事实句校验
# 说明：这里是**规则启发式**（字面词/数值重叠 + 引用触达），不是自然语言事实蕴含（NLI）判断。
# 它只能拦「明显无引用」「引用与句子字面完全不相关」的情况，不能证明结论在语义上被证据蕴含。
_SENTENCE_SPLIT_RE = re.compile(r"(?:[。！？!?；;]+\s*|\n+)")
_HEADING_WORDS = (
    "结论", "依据", "现在该做什么", "现在要做什么", "该做什么", "操作建议",
    "下一步建议", "口径说明", "说明",
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(str(text or "")) if s.strip()]


def _is_heading(sentence: str) -> bool:
    text = sentence.strip()
    for word in _HEADING_WORDS:
        if text.startswith(word):
            rest = text[len(word):].lstrip("：:，,。 ")
            return len(rest) <= 3
    return False


def _evidence_terms(e: Evidence) -> set[str]:
    terms: set[str] = set()
    for raw in (e.subject, e.object, e.quote, _fmt_value(e), str(e.properties.get("effect") or "")):
        for token in re.split(r"[\s，。；、,;:：/（）()~—–-]+", str(raw or "")):
            token = token.strip()
            if len(token) >= 2:
                terms.add(token)
    return terms


def _sentence_relevant(sentence: str, e: Evidence) -> bool:
    """句子是否与这条证据「字面相关」：出现证据主题/客体词或同值数字。"""
    text = re.sub(r"\[E\d+\]", "", _canonicalize_citations(sentence))
    for term in _evidence_terms(e):
        if term in text:
            return True
    numbers = {round(float(x), 6) for x in re.findall(_NUM_BODY, text)}
    for value in (e.value, e.value_min, e.value_max):
        if value is not None and round(float(value), 6) in numbers:
            return True
    return False


def _uncited_fact_warnings(answer: str, evidence: Sequence[Evidence]) -> list[str]:
    """事实句（含证据词/数值）没有 [E#] 引用 → unsupported_fact（启发式）。"""
    terms: set[str] = set()
    for e in evidence:
        terms |= _evidence_terms(e)
    found = False
    for sentence in _sentences(answer):
        if _is_heading(sentence) or len(sentence) < 8:
            continue
        if _CITE_SCAN_RE.search(sentence):
            continue
        if _HIGH_RISK_UNIT_RE.search(sentence) or re.search(r"\d", sentence):
            found = True
            break
        if any(term in sentence for term in terms):
            found = True
            break
    return [WARN_UNSUPPORTED_FACT] if found else []


def _citation_mismatch_warnings(answer: str, evidence: Sequence[Evidence]) -> list[str]:
    """某句的引用编号有效、但与该句字面内容完全无关 → citation_mismatch:E#（启发式）。"""
    by_id = {e.eid: e for e in evidence}
    subject_names = {e.subject for e in evidence if e.subject}
    warnings: list[str] = []
    for sentence in _sentences(answer):
        cited = [c for c in re.findall(r"\[(E\d+)\]", _canonicalize_citations(sentence)) if c in by_id]
        if not cited:
            continue
        mentioned = {name for name in subject_names if name and name in sentence}
        relevant = False
        for cid in cited:
            item = by_id[cid]
            # 句子明确提到某个主体（如「阳光玫瑰」）时，引用证据的主体必须就是它；
            # 否则跨品种/跨病害引用仅靠数值重叠也会被误判为相关。
            if mentioned:
                if item.subject in mentioned and _sentence_relevant(sentence, item):
                    relevant = True
                    break
            elif _sentence_relevant(sentence, item):
                relevant = True
                break
        if relevant:
            continue
        for cid in cited:
            code = f"{WARN_CITATION_MISMATCH}:{cid}"
            if code not in warnings:
                warnings.append(code)
    return warnings


def _numbers_in(text: str) -> set[float]:
    # 「1-MCP」里的 1 不是参数数值，先剔除，避免把药剂名当剂量
    cleaned = re.sub(r"1-MCP", "MCP", str(text or ""), flags=re.IGNORECASE)
    numbers: set[float] = set()
    for match in re.finditer(_NUM_BODY, cleaned):
        try:
            numbers.add(round(float(match.group(0)), 6))
        except ValueError:
            continue
    return numbers


def _verified_backs_param(sentence: str, e: Evidence) -> bool:
    """同句**被引用**的 verified 证据是否直接支撑该句参数。

    必须同时满足：该证据被本句引用（调用方已筛）、status=verified、属高风险参数证据、
    与句子字面相关，且句子里的参数数字确实出现在该证据（object/quote/value）中。
    只出现在 evidence 列表里但未被本句引用的 verified 证据不能放行（历史 bug）。
    """
    if e.status != "verified" or not _is_high_risk(e) or not _sentence_relevant(sentence, e):
        return False
    sentence_numbers = _numbers_in(re.sub(r"\[E\d+\]", "", _canonicalize_citations(sentence)))
    evidence_numbers = _numbers_in(
        " ".join(
            [
                e.object,
                e.quote,
                str(e.value or ""),
                str(e.value_min or ""),
                str(e.value_max or ""),
            ]
        )
    )
    return bool(sentence_numbers & evidence_numbers)


def _anchor_high_risk_warnings(answer: str, evidence: Sequence[Evidence]) -> list[str]:
    """仅凭 anchor 证据给出药剂/浓度/剂量/时间参数 → anchor_high_risk。"""
    by_id = {e.eid: e for e in evidence}
    for sentence in _sentences(answer):
        cited = [by_id[c] for c in re.findall(r"\[(E\d+)\]", _canonicalize_citations(sentence)) if c in by_id]
        if not cited or not _has_high_risk_param(sentence):
            continue
        if not any(e.status != "verified" and _is_high_risk(e) for e in cited):
            continue
        # 只有「本句实际引用 + 已核验 + 高风险 + 数字与参数一致」的证据才能放行
        if any(_verified_backs_param(sentence, e) for e in cited):
            continue
        return [WARN_ANCHOR_HIGH_RISK]
    return []


_ANCHOR_CERTAINTY_TERMS = (
    "已核验", "已验证", "已证实", "已证明", "已经证明", "研究已经证明",
    "已充分验证", "充分验证", "充分证明", "确凿", "确认无误", "已确认",
    "确定结论", "可以确定", "证实了", "证明了",
)
_ANCHOR_HEDGE_TERMS = (
    "待核验", "待验证", "尚需验证", "尚需核实", "需人工确认", "需进一步核验",
    "初步线索", "初步结论", "未逐字核对", "不确定", "不能确定", "无法确认",
    "仅供参考", "可能", "推测", "研究提示", "提示", "待补",
)
_NEGATION_PREFIXES = ("不", "未", "非", "没有", "尚未")


def _contains_unnegated(text: str, terms: Sequence[str]) -> bool:
    for term in terms:
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            prefix = text[max(0, index - 2):index]
            if not any(neg in prefix for neg in _NEGATION_PREFIXES):
                return True
            start = index + len(term)
    return False


def _answer_cites_anchor(answer: str, evidence: Sequence[Evidence]) -> bool:
    by_id = {e.eid: e for e in evidence}
    for cid in re.findall(r"\[(E\d+)\]", _canonicalize_citations(answer or "")):
        item = by_id.get(cid)
        if item is not None and item.status != "verified":
            return True
    return False


def _anchor_overclaim_warnings(answer: str, evidence: Sequence[Evidence]) -> list[str]:
    """anchor 证据被写成“已核验/已证实”等确定性结论 → anchor_overclaim。

    这是**逐句**启发式：只判断同一句内被引用的 anchor 与该句的确定性/限定措辞，
    无法可靠判断复句中的分句级证据归属，也不能证明语句语义蕴含。
    """
    by_id = {e.eid: e for e in evidence}
    for sentence in _sentences(answer):
        cited = [
            by_id[c]
            for c in re.findall(r"\[(E\d+)\]", _canonicalize_citations(sentence))
            if c in by_id
        ]
        anchors = [e for e in cited if e.status != "verified"]
        if not anchors:
            continue
        text = re.sub(r"\[E\d+\]", "", _canonicalize_citations(sentence))
        if _contains_unnegated(text, _ANCHOR_HEDGE_TERMS):
            continue
        if _contains_unnegated(text, _ANCHOR_CERTAINTY_TERMS):
            return [WARN_ANCHOR_OVERCLAIM]
    return []


def _sanitize_invalid_citations(
    answer: str, evidence: Sequence[Evidence]
) -> tuple[str, list[str], list[str]]:
    """删除含无效引用编号的句子；返回 (清理后答案, 无效编号, 剩余有效引用)。

    - 句内同时有有效+无效引用时，整句删除（保守，避免留下无依据陈述）；
    - 只删除含无效编号的句子，其他句子的有效内容保留；
    - 不把无效编号简单去掉后继续保留无依据陈述。
    """
    valid_ids = {e.eid for e in evidence}
    invalid_ids: list[str] = []
    pattern = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?|\n")
    out: list[str] = []
    for match in pattern.finditer(answer or ""):
        chunk = match.group(0)
        if not chunk.strip() or chunk.strip() == "\n":
            out.append(chunk)
            continue
        cited = re.findall(r"\[(E\d+)\]", _canonicalize_citations(chunk))
        bad = [cid for cid in dict.fromkeys(cited) if cid not in valid_ids]
        if bad:
            for cid in bad:
                if cid not in invalid_ids:
                    invalid_ids.append(cid)
            continue  # 删除整句/整行
        out.append(chunk)
    cleaned = "".join(out).strip()
    remaining = verify_citations(cleaned, evidence)[0]
    return cleaned, invalid_ids, remaining


def validate_llm_answer(
    answer: str, evidence: Sequence[Evidence], question: str = ""
) -> tuple[list[str], bool]:
    """LLM 答案的规则校验（非语义蕴含）。

    返回 ``(warnings, critical)``；``critical=True`` 表示必须回退到证据约束的模板答案
    （关键数值越界/无来源，或仅凭 anchor 证据给出高风险执行参数）。
    """
    issues: list[str] = []
    issues.extend(check_numbers(answer, evidence, question))
    issues.extend(_uncited_fact_warnings(answer, evidence))
    issues.extend(_citation_mismatch_warnings(answer, evidence))
    issues.extend(_anchor_high_risk_warnings(answer, evidence))
    issues.extend(_anchor_overclaim_warnings(answer, evidence))
    critical_prefixes = ("out_of_range", "unsourced_number", WARN_ANCHOR_HIGH_RISK, WARN_ANCHOR_OVERCLAIM)
    critical = any(w.startswith(prefix) for w in issues for prefix in critical_prefixes)
    # anchor 答案里若出现无引用事实句（unsupported_fact），不能把 anchor 当成其他陈述的依据；
    # 保守回退模板。此规则仍是启发式，不能完整识别同一复句内的分句级归属。
    if WARN_UNSUPPORTED_FACT in issues and _answer_cites_anchor(answer, evidence):
        critical = True
    return list(dict.fromkeys(issues)), critical



# ------------------------------------------------------------------ 越界检测
def _question_requests_temperature(question: str) -> bool:
    """问句是否显式在问温度/冷冻（用于避免「零下18度能放吗」被路由到 shelf_life 漏掉越界）。"""
    q = normalize_question(question)
    if re.search(r"-?\d+(?:\.\d+)?\s*(?:℃|°C|度)", q):
        return True
    return any(term in q for term in _FREEZE_TERMS)


def detect_out_of_range(question: str, evidence: Sequence[Evidence]) -> bool:
    """问题请求的温度超出证据覆盖区间，或明确提出「冷冻」类不可行条件。"""
    q = normalize_question(question)
    temps = [e for e in evidence if e.unit == "℃"]
    if not temps:
        return False
    lo = min((e.value_min if e.value_min is not None else e.value or 0.0) for e in temps)
    hi = max((e.value_max if e.value_max is not None else e.value or 0.0) for e in temps)
    # 归一化后「零下18度」→「-18度」，只认带 度/℃ 的数字
    for m in re.findall(r"(-?\d+(?:\.\d+)?)\s*(?:℃|°C|度)", q):
        try:
            v = float(m)
        except ValueError:
            continue
        if v < lo - 1e-6 or v > hi + 1e-6:
            return True
    # 没有数字但明确要求冷冻（葡萄贮藏是 0℃ 附近的冷藏，不是冷冻）
    if any(term in q for term in _FREEZE_TERMS):
        return True
    return False



# ------------------------------------------------------------------ Prompt
def build_prompt(question: str, evidence: Sequence[Evidence]) -> list[dict[str, str]]:
    def _line(e: Evidence) -> str:
        flag = ""
        if e.status != "verified" and _is_high_risk(e):
            flag = "（高风险待核验：不得给出具体浓度/剂量/时间参数）"
        elif e.status != "verified":
            flag = "（待核验）"
        return (
            f"[{e.eid}] {e.subject} | {PRED_LABEL.get(e.predicate, e.predicate)} | {e.object}"
            + (f" | 值={_fmt_value(e)}" if _fmt_value(e) else "")
            + f" | 来源={_sources_cn(e)} | {_status_cn(e)}{flag}"
        )

    ev_lines = "\n".join(_line(e) for e in evidence)
    system = (
        "你是鲜食葡萄采后贮藏技术助手，服务对象是种植户和冷库管理员。\n"
        "硬性规则：\n"
        "1) 只能依据下面给出的证据回答，不得引入证据之外的事实。\n"
        "2) 每个结论后面必须标注证据编号，格式 [E1][E2]；每个事实句都要有对应引用。\n"
        "3) 温度、湿度、浓度、时间、剂量等数字必须原样来自证据，禁止补充或换算成证据里没有的数。\n"
        "4) 证据标注「已核验」才可作为确定结论；标注「待核验」的只能作为参考，"
        "必须写「待核验/需人工确认」，不得描述成已证实的事实。\n"
        "5) 涉及药剂、浓度、剂量、处理时间等高风险操作时，若依据只有「待核验」证据，"
        "不得给出具体执行参数（数字），只能给方向并提示按产品标签、来源原文或当地技术人员确认。\n"
        "6) 证据没覆盖的内容，明确写「图谱未收录」，不要猜。\n"
        "7) 面向种植户和冷库管理员：建议必须当天能执行、用动词开头；非高风险参数可按已核验证据给数字。\n"
        "输出结构（三段，不要额外客套）：\n"
        "结论：（1-2 句）\n"
        "依据：（逐条列证据编号与要点）\n"
        "现在该做什么：（1-3 步，动词开头，今天就能执行）\n"
        "全程口语短句，不超过 250 字。\n\n"
        f"【证据】\n{ev_lines if ev_lines else '（无证据）'}"
    )
    user = f"问题：{question}\n请按上述结构回答。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _citation_fix_messages(
    messages: list[dict[str, str]], answer: str, detail: str
) -> list[dict[str, str]]:
    """构造「只纠正引用编号」的一次纠正消息（规则校验发现 citation_mismatch 时使用）。"""
    return messages + [
        {"role": "assistant", "content": answer},
        {
            "role": "user",
            "content": (
                f"你的引用编号与对应事实句不匹配（涉及 {detail or '相关证据'}）。"
                "请只修改引用编号：每个事实句必须引用真正支撑它的证据 [E#]，"
                "不要改变事实、不要新增证据；如果证据里找不到能支撑该事实的条目，"
                "就明确写「图谱未收录」。"
            ),
        },
    ]


def _split_llm_text(text: str) -> tuple[str, list[str]]:
    """把「结论/依据/现在该做什么」拆成 answer 与 steps。"""
    raw = (text or "").strip()
    if not raw:
        return "", []
    m = re.search(r"(现在该做什么|现在要做什么|该做什么|操作建议|下一步建议)", raw)
    head, tail = (raw, "") if not m else (raw[: m.start()], raw[m.start():])
    tail = re.sub(r"^.*?(现在该做什么|现在要做什么|该做什么|操作建议|下一步建议)[:：]?", "", tail)
    steps: list[str] = []
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-•·*]?\s*(\d+[.、)）]|（\d+）|\(\d+\))?\s*", "", line)
        if line:
            steps.append(line)
        if len(steps) >= 3:
            break
    return head.strip().rstrip("：:"), steps


# ------------------------------------------------------------------ 词表缓存
_CATALOG_CACHE: dict[str, Any] = {}
_LLM_CACHE: dict[str, str] = {}
_LLM_CACHE_MAX = 64


def _llm_cache_key(question: str, evidence: Sequence[Evidence]) -> str:
    """相同问题 + 相同证据 → 复用上次生成文本（彩排/评委重复提问秒回）。"""
    import hashlib

    payload = question + "|" + "|".join(
        f"{e.eid}:{e.subject}:{e.predicate}:{e.object}:{e.value}:{e.value_min}:{e.value_max}"
        for e in evidence
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _load_catalog_cached(path: str):
    """按 (路径, mtime) 缓存实体词表，避免每问重建（entities.csv 改动后自动失效）。"""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    key = f"{path}|{mtime}"
    cached = _CATALOG_CACHE.get(key)
    if cached is None:
        from app.linking import load_catalog

        cached = load_catalog(path)
        _CATALOG_CACHE.clear()
        _CATALOG_CACHE[key] = cached
    return cached


# ------------------------------------------------------------------ 多轮追问
# 只允许「明确的指代式追问」继承上一轮实体（那/这/它/还有/再…）。
# 出现无法识别的新名词（如「苹果呢」）时不得强行套用旧实体。
_FOLLOWUP_CUES = ("那", "那么", "这", "这个", "那个", "它", "它们", "还有", "再", "换成", "继续")
_FOLLOWUP_PRONOUNS = ("它", "它们", "这个", "那个", "上述", "前面")
_FOLLOWUP_ATTR_WORDS = (
    "温度", "湿度", "气调", "贮藏", "储存", "冷藏", "预冷", "耐贮", "货架", "糖度",
    "酸度", "指标", "病害", "虫害", "腐烂", "霉", "保鲜", "参数", "要求", "标准",
    "多少", "几度", "多久", "怎么", "办", "处理", "防治", "预防", "注意", "影响",
)
# 追问里可安全忽略的虚词/问句填充词（用于判断 remainder 是不是新名词）
_QUESTION_FILLERS = (
    "怎么样", "怎么", "如何", "多少", "几度", "多久", "什么", "为什么", "能不能",
    "可以吗", "行不行", "呢", "吗", "啊", "吧", "的", "了", "请问", "问一下",
    "一下", "还有", "那么", "那", "这个", "那个", "它", "它们", "再", "换成",
    "继续", "么", "呗", "吗", "呀", "嘛",
)


def _is_referential_followup(question: str) -> bool:
    """问句是否是可继承上一轮实体的指代式追问（规则启发式，非语义理解）。

    「那湿度呢」→ True；「那巨峰呢」虽也以「那」开头，但 remainder 是新实体，
    应交给实体链接（命中则用新实体），不会走到继承；「苹果呢」→ False（新名词，不继承）。
    """
    q = normalize_question(question).strip(" ？?。.!！,，")
    if not q:
        return False
    has_cue = any(q.startswith(cue) for cue in _FOLLOWUP_CUES) or any(
        pronoun in q for pronoun in _FOLLOWUP_PRONOUNS
    )
    if not has_cue:
        return False
    rest = q
    for word in sorted(set(_QUESTION_FILLERS), key=len, reverse=True):
        rest = rest.replace(word, "")
    rest = re.sub(r"[\s，。？！?、,.：:；;]", "", rest)
    if not rest:
        return True
    return any(word in rest for word in _FOLLOWUP_ATTR_WORDS)


# ------------------------------------------------------------------ 主流程
def answer_question(
    question: str,
    *,
    store: Any = None,
    llm: Any = None,
    k: int = 6,
    allow_llm: bool = True,
    steps: bool = True,
    settings: Any = None,
    context: dict[str, Any] | None = None,
) -> AnswerResult:
    t0 = time.perf_counter()
    q = (question or "").strip()
    result = AnswerResult(question=q)
    warnings: list[str] = []
    result.warnings = warnings

    def _refuse(message: str) -> AnswerResult:
        if WARN_NO_EVIDENCE not in warnings:
            warnings.append(WARN_NO_EVIDENCE)
        result.answer = message
        result.evidence = []
        result.cited_ids = []
        result.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return result
    if not q:
        result.answer = "请输入一个问题，例如「阳光玫瑰放冷库该调到多少度？」"
        result.warnings.append(WARN_NO_EVIDENCE)
        result.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return result

    # 1) 实体链接（词表按 mtime 缓存，避免每问重建）
    try:
        from app.config import load_settings as _ls

        st = settings or _ls()
        from app.linking import link_entities

        hits = link_entities(q, _load_catalog_cached(str(st.data_path / "entities.csv")))
    except Exception:
        hits = []
    # 1.5) 多轮追问：仅「指代式追问」且本轮未命中任何实体时，才承接上一轮实体
    #      （如「那湿度呢？」→ 承接阳光玫瑰；「苹果呢」→ 不继承，避免张冠李戴）
    prev_ctx = context or {}
    if not hits and _is_referential_followup(q):
        for item in (prev_ctx.get("entities") or [])[:4]:
            if isinstance(item, EntityHit):
                hits.append(item)
            elif isinstance(item, dict) and item.get("node_id"):
                hits.append(EntityHit(
                    node_id=str(item["node_id"]),
                    label=str(item.get("label") or "Variety"),
                    surface=str(item.get("surface") or item.get("node_id")),
                    alias_hit=str(item.get("surface") or ""),
                ))
        if hits:
            result.context_note = "承接上一轮：" + "、".join(
                dict.fromkeys(h.surface or h.node_id for h in hits)
            )
    result.entities = hits
    topics = detect_topics(q)
    # 「那湿度呢」这类指代追问若上一轮也没有实体：先澄清，不能拿通用湿度/其他品种凑答案。
    followup_without_context = _is_referential_followup(q) and not hits and not prev_ctx.get("entities")

    # 2) 意图路由
    intent, confidence, candidates = route(q, hits)
    if result.context_note and intent == "general" and prev_ctx.get("intent"):
        intent, confidence = str(prev_ctx["intent"]), max(confidence, 0.4)
    # 显式问温度/冷冻（「零下18度能放吗」「冻起来能存一年吗」）优先按 temperature 处理，
    # 否则会被 shelf_life 等触发词抢占，导致越界数值漏检（历史审计 S2）。
    if intent in ("shelf_life", "quality_indicator") and _question_requests_temperature(q):
        intent, confidence = "temperature", max(confidence, 0.4)
    result.intent, result.intent_confidence = intent, confidence
    if confidence < 0.35 and intent != "general":
        warnings.append(WARN_LOW_CONFIDENCE_INTENT)

    # 2.5) general 且无实体：不查图谱（否则会返回任意证据，等于瞎答）
    if intent == "general" and not hits:
        # 主题型问题（包装/运输/货架期/湿度等）允许走 general 关键词检索；
        # 完全无主题、无实体时才走原有拒绝路径。
        if not topics:
            return _refuse(
                "结论：没识别出具体的品种、病害或指标，我不凭空回答。\n\n"
                "依据：无可用证据。\n\n"
                "可以这样说：「阳光玫瑰放冷库该调到多少度？」「冷库里葡萄长白毛了怎么办？」"
                "「阳光玫瑰和巨峰哪个更能放？」"
            )
    # 2.6) 非 temperature 的 typed 意图且无任何实体：不查全库凑答案（如「那湿度呢」但上一轮已无实体）
    #      temperature 例外：越界探测（-18℃/冷冻）需要全库温度证据来判区间。
    if intent != "general" and intent != "temperature" and not hits:
        # 湿度/气调/货架期允许“无实体”的通用主题查询（只查对应类别，不跨类别凑答案）；
        # 其他 typed 意图仍要求实体，避免查全库。
        if followup_without_context or not (topics & {"humidity", "atmosphere", "shelf"}):
            return _refuse(
                "结论：没识别出具体的品种、病害或指标，我不凭空回答。\n\n"
                "依据：无可用证据（当前问题没有可关联的实体）。\n\n"
                "请带上品种或病害再问一次，例如「阳光玫瑰的湿度要调到多少？」"
            )

    # 3) 查询图谱
    evidence: list[Evidence] = []
    store_obj = None
    try:
        store_obj = _get_store(store, settings)
        # 品种对比/实体中心检索要多取一些边，否则「第二个命中实体」的边会被 k 截掉
        eff_k = max(int(k or 6), 12) if intent in ("variety_compare", "general") else int(k or 6)
        spec: QuerySpec = build_query(intent, hits, k=eff_k, question=q)
        evidence = list(store_obj.execute(spec) or [])
        if getattr(store_obj, "backend_fallback", False):
            warnings.append(WARN_BACKEND_FALLBACK)
        if hasattr(store_obj, "query_cypher"):
            try:
                result.query_cypher = list(store_obj.query_cypher(spec) or [])
            except Exception:
                result.query_cypher = [spec.cypher_file] if spec.cypher_file else []
        else:
            result.query_cypher = [spec.cypher_file] if spec.cypher_file else []
    except Exception as exc:  # 数据未就绪 / 后端异常 → 友好降级
        warnings.append(WARN_NO_EVIDENCE)
        result.answer = (
            f"结论：图谱当前不可用（{type(exc).__name__}: {exc}），我不编造答案。\n\n"
            "依据：无可用证据。"
        )
        result.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return result

    # 4) 证据整理：优先「与命中实体相连」的证据，再按 store 分数降序
    #    （否则「灰霉病和结露」会被通用处置边挤到前面，答非所问）
    hit_ids_all = {h.node_id for h in hits}

    def _touch_rank(ev: Evidence) -> float:
        """与命中实体相连的个数：同时触达多个命中实体（如「灰霉病↔结露」）排在最前。"""
        ids = {ev.properties.get("subject_id"), ev.properties.get("object_id")}
        overlap = len(ids & hit_ids_all)
        if not overlap and (ev.subject in hit_ids_all or ev.object in hit_ids_all):
            overlap = 1
        return float(overlap)

    evidence = sorted(evidence, key=lambda ev: (_touch_rank(ev), ev.score), reverse=True)
    cap = max(int(k or 6), 12) if intent in ("variety_compare", "general") else max(1, int(k or 6))
    evidence = _dedupe(evidence)[:cap]
    focused, missing_topic = _focus_evidence_for_question(q, evidence, intent)
    if missing_topic:
        return _refuse(_missing_evidence_answer(q, hits, {missing_topic}))
    evidence = _restrict_to_hit_varieties(focused, hits)
    if not evidence:
        if hits or topics:
            return _refuse(_missing_evidence_answer(q, hits, topics))
    if "transport" in topics and not _transport_temperature_supported(q, evidence):
        return _refuse(_missing_evidence_answer(q, hits, {"transport"}))
    _assign_eids(evidence)
    result.evidence = evidence
    for e in evidence:
        if e.predicate in SINGLE_SOURCE_PREDS and len(e.source_ids) < 2:
            warnings.append(WARN_SINGLE_SOURCE)
            break

    if not evidence:
        warnings.append(WARN_NO_EVIDENCE)

    # 4.5) 覆盖校验：typed 意图下证据必须触达命中实体，否则就是「张冠李戴」
    #      （例：问「维多利亚怎么存」却拿到阳光玫瑰/红地球的耐贮性；问「1-MCP 怎么用」却答 SO₂ 禁忌）
    if hits and evidence:
        hit_ids = {h.node_id for h in hits}
        # 主实体（品种/病害）必须被证据触达。仅命中指标词（如「耐贮性」）时，
        # 图里通用的 AFFECTS 边会让「任一命中实体」判定通过，从而把别品种/通用机理
        # 当成该品种结论（历史审计 S1）。因此优先要求证据触达命中的品种/病害。
        primary_ids = {h.node_id for h in hits if h.label in ("Variety", "Disease")}
        required_ids = primary_ids or hit_ids
        covered = False
        for e in evidence:
            ids = {e.properties.get("subject_id"), e.properties.get("object_id")}
            if ids & required_ids or e.subject in required_ids or e.object in required_ids:
                covered = True
                break
        if not covered:
            names = "、".join(dict.fromkeys(h.surface for h in hits))
            warnings.append(WARN_NO_EVIDENCE)
            result.evidence = []
            result.answer = (
                f"结论：图谱里没有检索到「{names}」与该问题对应的证据，我不拿别的品种或条件来凑答案。\n\n"
                "依据：图谱未收录该问题对应的三元组（查询命中实体与证据无关联）。\n\n"
                "可以换一种问法，或改问已收录较多的品种（阳光玫瑰、巨峰、红地球、夏黑）。"
            )
            result.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return result

    # 4.6) 品种对比：逐品种核对「耐贮性」基线是否真的在图中（避免把「没取到」误报成「未收录」）
    missing_shelf_ids: set = set()
    if intent == "variety_compare" and store_obj is not None:
        variety_hits = [h for h in hits if h.label == "Variety"]

        def _has_value(evs) -> set:
            return {
                e2.properties.get("subject_id")
                for e2 in evs
                if e2.predicate == "HAS_INDICATOR_VALUE" and e2.object == "耐贮性"
                and (e2.value is not None or e2.value_min is not None or e2.value_max is not None)
            }

        found = _has_value(evidence)
        for h in variety_hits:
            if h.node_id in found:
                continue
            try:
                extra = list(store_obj.execute(
                    QuerySpec("shelf_life", params={"variety_ids": [h.node_id], "k": 4})
                ) or [])
            except Exception:
                extra = []
            hit = [e2 for e2 in extra if e2.properties.get("subject_id") == h.node_id and _has_value([e2])]
            if hit:
                evidence = _dedupe(evidence + hit)
                found.add(h.node_id)
            else:
                missing_shelf_ids.add(h.node_id)
        # 补充证据后重新编号/回填（新增行带空 eid，必须重排）
        if evidence:
            evidence = _dedupe(evidence)[: cap + 2]
            _assign_eids(evidence)
            result.evidence = evidence

    # 5) 越界检测
    out_of_range = detect_out_of_range(q, evidence) if evidence else False

    # 6) 生成
    tpl = template_answer(intent, q, evidence, hits, out_of_range, missing_shelf_ids)
    answer = tpl
    result.mode = "template"

    use_llm = bool(allow_llm) and llm is not None and getattr(llm, "available", False)
    if allow_llm and llm is None:
        try:
            llm = LLMClient(settings)
            use_llm = bool(getattr(llm, "available", False))
        except Exception:
            llm = None
            use_llm = False

    if use_llm and evidence:
        messages = build_prompt(q, evidence)
        cache_key = _llm_cache_key(q, evidence)
        try:
            cached_text = _LLM_CACHE.get(cache_key)
            if cached_text is not None:
                text = cached_text
            else:
                text = llm.complete(messages)
                if len(_LLM_CACHE) >= _LLM_CACHE_MAX:
                    _LLM_CACHE.clear()
                _LLM_CACHE[cache_key] = text
            # 全角【E1】/小写 [e1] 先规范成 [E1]，再走引用校验
            answer = _canonicalize_citations(text)
            result.mode = "llm"
            cited, w = verify_citations(answer, evidence)
            corrected_once = False
            if not cited:
                # 不合格 → 纠正一次
                messages2 = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "你的回答没有给出 [E#] 证据引用。请只依据证据重写，每个结论后必须带 [E#]。"},
                ]
                text2 = _canonicalize_citations(llm.complete(messages2))
                cited2, w2 = verify_citations(text2, evidence)
                if cited2:
                    answer, cited = text2, cited2
                    corrected_once = True
                else:
                    warnings.extend(w2)
                    warnings.append(WARN_NO_CITATION)
                    answer, result.mode = tpl, "template"
            if result.mode == "llm":
                # 规则校验（启发式）：引用不匹配/关键数值错误/仅凭 anchor 给高风险参数
                issues, critical = validate_llm_answer(answer, evidence, q)
                mismatch = [code for code in issues if code.startswith(WARN_CITATION_MISMATCH)]
                if mismatch and not corrected_once:
                    # 引用编号存在但与事实句不匹配 → 只纠正引用一次；失败则回退模板
                    detail = "、".join(sorted({code.split(":", 1)[-1] for code in mismatch}))
                    fix_messages = _citation_fix_messages(messages, answer, detail)
                    fixed_text = _canonicalize_citations(llm.complete(fix_messages))
                    fixed_cited, fixed_w = verify_citations(fixed_text, evidence)
                    fixed_issues, fixed_critical = validate_llm_answer(fixed_text, evidence, q)
                    fixed_mismatch = [
                        code for code in fixed_issues if code.startswith(WARN_CITATION_MISMATCH)
                    ]
                    if fixed_cited and not fixed_mismatch and not fixed_critical:
                        answer, cited = fixed_text, fixed_cited
                        issues, critical = fixed_issues, fixed_critical
                        corrected_once = True
                    else:
                        warnings.extend(mismatch)
                        for code in fixed_w:
                            if code not in warnings:
                                warnings.append(code)
                        warnings.append(WARN_LLM_ANSWER_REJECTED)
                        answer, result.mode = tpl, "template"
                        result.cited_ids = []
                        issues, critical = [], False
                elif mismatch and corrected_once:
                    # 已用掉一次纠正（无引用纠正）后仍不匹配 → 直接回退模板
                    warnings.extend(mismatch)
                    warnings.append(WARN_LLM_ANSWER_REJECTED)
                    answer, result.mode = tpl, "template"
                    result.cited_ids = []
                    issues, critical = [], False
                if result.mode == "llm":
                    for code in issues:
                        if code not in warnings:
                            warnings.append(code)
                    if critical:
                        warnings.append(WARN_LLM_ANSWER_REJECTED)
                        answer, result.mode = tpl, "template"
                        result.cited_ids = []
            result.cited_ids = cited if result.mode == "llm" else []
        except LLMUnavailable as exc:
            warnings.append(WARN_LLM_TIMEOUT if "timeout" in str(exc).lower() else WARN_LLM_UNAVAILABLE)
            answer, result.mode = tpl, "template"
        except Exception:
            warnings.append(WARN_LLM_UNAVAILABLE)
            answer, result.mode = tpl, "template"

    if result.mode == "llm":
        cleaned, invalid_ids, remaining = _sanitize_invalid_citations(answer, evidence)
        if invalid_ids:
            for cid in invalid_ids:
                code = f"invalid_citation:{cid}"
                if code not in warnings:
                    warnings.append(code)
            if remaining:
                answer = cleaned
                result.cited_ids = remaining
            else:
                warnings.append(WARN_LLM_ANSWER_REJECTED)
                answer = tpl
                result.mode = "template"
                result.cited_ids = []

    if result.mode == "template":
        cited, _w = verify_citations(answer, evidence)
        result.cited_ids = cited


    # 7) 分步动作（LLM 文本里已含「现在该做什么」则抽出，否则由证据派生）
    if steps:
        head, llm_steps = _split_llm_text(answer) if result.mode == "llm" else ("", [])
        if head:
            answer = head
        result.steps = llm_steps[:3] if (result.mode == "llm" and llm_steps) else compose_steps(evidence, intent)
        result.answer = answer
        if result.steps:
            result.answer = answer + "\n\n现在该做什么：\n" + "\n".join(
                f"{i}. {s}" for i, s in enumerate(result.steps, start=1)
            )
    else:
        result.answer = answer

    # 7.5) 步骤可能引用额外证据（如第 3 步引用 E6），最终答案确定后重算引用
    cited_final, cite_warnings = verify_citations(result.answer, evidence)
    if cited_final:
        result.cited_ids = cited_final
    for code in cite_warnings:
        if code not in warnings:
            warnings.append(code)
    # 最终兜底：无论哪条路径，用户看到的答案都不得含无效引用编号。
    invalid_final = [code for code in cite_warnings if code.startswith("invalid_citation:")]
    if invalid_final:
        warnings.append(WARN_LLM_ANSWER_REJECTED)
        result.answer = tpl
        result.steps = compose_steps(evidence, intent) if steps else []
        if steps and result.steps:
            result.answer += "\n\n现在该做什么：\n" + "\n".join(
                f"{i}. {step}" for i, step in enumerate(result.steps, start=1)
            )
        result.mode = "template"
        cited_final, _ = verify_citations(result.answer, evidence)
        result.cited_ids = cited_final

    # 8) 数值校验 + 越界告警
    if out_of_range:
        warnings.append(WARN_OUT_OF_RANGE)
    warnings.extend(check_numbers(result.answer, evidence, q))

    # 8.5) 证据分级告警：LLM 答案引用了待核验证据 / 证据集中含高风险待核验参数
    if result.mode == "llm":
        cited_set = set(result.cited_ids or [])
        if any(e.status != "verified" and e.eid in cited_set for e in evidence):
            warnings.append(WARN_ANCHOR_UNVERIFIED)
    cited_set_h = set(result.cited_ids or [])
    if any(
        e.status != "verified" and _is_high_risk(e) and e.eid in cited_set_h for e in evidence
    ):
        warnings.append(WARN_ANCHOR_HIGH_RISK)

    # 8.8) 常温“放几天”类问题：数据只有方向/区间时，明确未收录具体天数，避免过度回答。
    if "room_temp" in topics and re.search(r"(几天|多久|多长时间|几天会坏)", q):
        if "未收录具体天数" not in result.answer:
            result.answer += "\n\n说明：图谱数据未给出具体天数；以上为常温下品质指标的变化方向。"

    # 9) 元信息（告警去重保序）
    result.warnings = list(dict.fromkeys(warnings))
    if llm is not None and hasattr(llm, "last_usage"):
        result.llm_meta = dict(llm.last_usage or {})
    result.elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return result


# ------------------------------------------------------------------ CLI
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="鲜食葡萄储藏知识图谱问答 CLI")
    parser.add_argument("question", nargs="*", help="用户问题")
    parser.add_argument("--k", type=int, default=6, help="证据条数上限")
    parser.add_argument("--no-llm", action="store_true", help="强制离线模板模式")
    args = parser.parse_args(argv)

    q = " ".join(args.question).strip() or "阳光玫瑰放冷库该调到多少度？"
    res = answer_question(q, k=args.k, allow_llm=not args.no_llm)
    payload = {
        "question": res.question,
        "intent": res.intent,
        "intent_confidence": res.intent_confidence,
        "entities": [{"id": h.node_id, "label": h.label, "surface": h.surface} for h in res.entities],
        "mode": res.mode,
        "context_note": res.context_note,
        "answer": res.answer,
        "steps": res.steps,
        "cited_ids": res.cited_ids,
        "warnings": res.warnings,
        "elapsed_ms": res.elapsed_ms,
        "evidence": [
            {
                "eid": e.eid,
                "triple": f"{e.subject} {e.predicate} {e.object}",
                "value": e.value,
                "unit": e.unit,
                "sources": e.source_ids,
                "status": e.status,
                "confidence": e.confidence,
            }
            for e in res.evidence
        ],
        "cypher": res.query_cypher,
        "llm_meta": res.llm_meta,
    }
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
