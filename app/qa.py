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
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.contracts import (
    WARN_BACKEND_FALLBACK,
    WARN_LLM_TIMEOUT,
    WARN_LLM_UNAVAILABLE,
    WARN_LOW_CONFIDENCE_INTENT,
    WARN_NO_CITATION,
    WARN_NO_EVIDENCE,
    WARN_OUT_OF_RANGE,
    WARN_SINGLE_SOURCE,
    AnswerResult,
    EntityHit,
    Evidence,
    QuerySpec,
)
from app.llm import LLMClient, LLMUnavailable
from app.planner import build_query, normalize_question, route

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

SINGLE_SOURCE_PREDS = {"CONTRA_INDICATED_FOR", "ALTERNATIVE_TO", "INDICATES"}


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
        return f"{lo}~{hi}{e.unit}"
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
    return (
        f"[{e.eid}] {e.subject} —{PRED_LABEL.get(e.predicate, e.predicate)}→ {e.object}{tail}；"
        f"来源：{_sources_cn(e)}；{_status_cn(e)}；置信 {e.confidence:.2f}"
    )


def _assign_eids(evidence: List[Evidence]) -> List[Evidence]:
    for i, e in enumerate(evidence, start=1):
        e.eid = f"E{i}"
    return evidence


def _dedupe(evidence: Sequence[Evidence]) -> List[Evidence]:
    seen = set()
    out: List[Evidence] = []
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
        return f"{e.subject}的{e.object}基线为{_fmt_value(e) or e.object}"
    if p == "CONTRA_INDICATED_FOR":
        sev = e.properties.get("severity") or "需注意"
        return f"{e.object}对{e.subject}属{sev}风险，不宜使用"
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


def compose_steps(evidence: Sequence[Evidence], intent: str, limit: int = 3) -> List[str]:
    """由证据派生「现在该做什么」，≤3 步；无证据返回 []。"""
    steps: List[str] = []
    for e in evidence:
        cat = e.properties.get("category") or ""
        if e.predicate == "CONTRA_INDICATED_FOR":
            alt = next((x.object for x in evidence if x.predicate == "ALTERNATIVE_TO"), "")
            txt = f"不要用 {e.object}"
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
                    steps.append(tpl.format(obj=e.object) + f"（[{e.eid}]）")
                    break
    # 去重保序
    out: List[str] = []
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


# ------------------------------------------------------------------ 模板答案
def template_answer(
    intent: str,
    question: str,
    evidence: Sequence[Evidence],
    entities: Sequence[EntityHit],
    out_of_range: bool,
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
            "远低于葡萄冰点，会冻伤果肉、解冻后很快腐烂。"
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
            head = "结论：" + "；".join(f"{f}（[{e.eid}]）" for f, e in zip(facts, evidence[:3])) + "。"

    elif intent == "variety_compare":
        vs = [e for e in evidence if e.predicate == "HAS_INDICATOR_VALUE"]
        if len({e.subject for e in vs}) >= 2:
            head = "结论：" + "；".join(f"{e.subject} {e.object} {_fmt_value(e)}（[{e.eid}]）" for e in vs[:3]) + "。"
        else:
            head = "结论：" + "；".join(f"{f}（[{e.eid}]）" for f, e in zip(facts, evidence[:3])) + "。"
    elif intent == "contraindication":
        c = next((e for e in evidence if e.predicate == "CONTRA_INDICATED_FOR"), None)
        alt = next((e for e in evidence if e.predicate == "ALTERNATIVE_TO"), None)
        if c:
            sev = c.properties.get("severity") or "需注意"
            head = f"结论：{c.object} 对 {c.subject} 属于{sev}风险，不建议直接用（[{c.eid}]）。"
            if alt:
                head += f"可考虑用 {alt.subject} 替代 {alt.object}（[{alt.eid}]）。"
            elif c.properties.get("reason"):
                head += f"原因：{c.properties.get('reason')}。"
        else:
            head = "结论：" + "；".join(f"{f}（[{e.eid}]）" for f, e in zip(facts, evidence[:3])) + "。"
    else:
        head = "结论：" + "；".join(f"{f}（[{e.eid}]）" for f, e in zip(facts, evidence[:3])) + "。"

    basis = "依据：\n" + "\n".join(f"- {_evidence_line(e)}" for e in evidence[:5])
    return head + "\n\n" + basis


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


def check_numbers(answer: str, evidence: Sequence[Evidence], question: str = "") -> List[str]:
    """单位感知 + 区间感知的数值一致性校验。

    - 带单位的数字：与证据同单位区间比对，落在区间外 → ``out_of_range:<num><unit>``；
    - 不带单位/证据无同单位区间的数字：与证据文本中的数字比对，否则 ``unsourced_number:<num>``；
    - 先剥 ``[E#]`` 与行首步骤序号，避免把引用编号、列表序号当数字。
    """
    fam_ranges: Dict[str, List[Tuple[float, float]]] = {}
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
    _add_bare(normalize_question(question))

    clean = re.sub(r"\[E\d+\]", "", answer or "")          # [E5] 不是数字 5
    clean = re.sub(r"(?m)^\s*\d+[.、)）]\s*", "", clean)     # 行首步骤序号
    clean = clean.replace("1-MCP", "MCP")                   # 避免把 1-MCP 的 1 当数值

    warnings: List[str] = []

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



def verify_citations(answer: str, evidence: Sequence[Evidence]) -> Tuple[List[str], List[str]]:
    valid_ids = {e.eid for e in evidence}
    cited = re.findall(r"\[(E\d+)\]", answer or "")
    uniq = [c for c in dict.fromkeys(cited) if c in valid_ids]
    warnings = [] if uniq else [WARN_NO_CITATION]
    return uniq, warnings


# ------------------------------------------------------------------ 越界检测
def detect_out_of_range(question: str, evidence: Sequence[Evidence]) -> bool:
    q = normalize_question(question)
    temps = [e for e in evidence if e.unit == "℃"]
    if not temps:
        return False
    lo = min((e.value_min if e.value_min is not None else e.value or 0.0) for e in temps)
    hi = max((e.value_max if e.value_max is not None else e.value or 0.0) for e in temps)
    for m in re.findall(r"-?\d+(?:\.\d+)?", q):
        try:
            v = float(m)
        except ValueError:
            continue
        if v < lo - 2 or v > hi + 2:
            return True
    return False


# ------------------------------------------------------------------ Prompt
def build_prompt(question: str, evidence: Sequence[Evidence]) -> List[Dict[str, str]]:
    ev_lines = "\n".join(f"[{e.eid}] {e.subject} | {PRED_LABEL.get(e.predicate, e.predicate)} | {e.object}"
                         + (f" | 值={_fmt_value(e)}" if _fmt_value(e) else "")
                         + f" | 来源={_sources_cn(e)} | {_status_cn(e)}" for e in evidence)
    system = (
        "你是鲜食葡萄采后贮藏技术助手，服务对象是种植户和冷库管理员。\n"
        "硬性规则：\n"
        "1) 只能依据下面给出的证据回答，不得引入证据之外的事实。\n"
        "2) 每个结论后面必须标注证据编号，格式 [E1][E2]。\n"
        "3) 温度、湿度、浓度、时间、剂量等数字必须原样来自证据，禁止补充或换算成证据里没有的数。\n"
        "4) 证据冲突或标注「待核验」时要如实说明，不要假装确定。\n"
        "5) 证据没覆盖的内容，明确写「图谱未收录」，不要猜。\n"
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


def _split_llm_text(text: str) -> Tuple[str, List[str]]:
    """把「结论/依据/现在该做什么」拆成 answer 与 steps。"""
    raw = (text or "").strip()
    if not raw:
        return "", []
    m = re.search(r"(现在该做什么|现在要做什么|该做什么|操作建议|下一步建议)", raw)
    head, tail = (raw, "") if not m else (raw[: m.start()], raw[m.start():])
    tail = re.sub(r"^.*?(现在该做什么|现在要做什么|该做什么|操作建议|下一步建议)[:：]?", "", tail)
    steps: List[str] = []
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
) -> AnswerResult:
    t0 = time.perf_counter()
    q = (question or "").strip()
    result = AnswerResult(question=q)
    warnings: List[str] = []
    result.warnings = warnings

    if not q:
        result.answer = "请输入一个问题，例如「阳光玫瑰放冷库该调到多少度？」"
        result.warnings.append(WARN_NO_EVIDENCE)
        result.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return result

    # 1) 实体链接
    try:
        from app.config import load_settings as _ls

        st = settings or _ls()
        from app.linking import link_entities, load_catalog

        catalog = load_catalog(str(st.data_path / "entities.csv"))
        hits = link_entities(q, catalog)
    except Exception:
        hits = []
    result.entities = hits

    # 2) 意图路由
    intent, confidence, candidates = route(q, hits)
    result.intent, result.intent_confidence = intent, confidence
    if confidence < 0.35 and intent != "general":
        warnings.append(WARN_LOW_CONFIDENCE_INTENT)

    # 2.5) general 且无实体：不查图谱（否则会返回任意证据，等于瞎答）
    if intent == "general" and not hits:
        warnings.append(WARN_NO_EVIDENCE)
        result.answer = (
            "结论：没识别出具体的品种、病害或指标，我不凭空回答。\n\n"
            "依据：无可用证据。\n\n"
            "可以这样说：「阳光玫瑰放冷库该调到多少度？」「冷库里葡萄长白毛了怎么办？」「阳光玫瑰和巨峰哪个更能放？」"
        )
        result.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return result

    # 3) 查询图谱
    evidence: List[Evidence] = []
    store_obj = None
    try:
        store_obj = _get_store(store, settings)
        spec: QuerySpec = build_query(intent, hits, k=k)
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

    # 4) 证据整理（去重/截断，eid 由本层分配）
    evidence = _dedupe(evidence)[: max(1, int(k or 6))]
    _assign_eids(evidence)
    result.evidence = evidence
    for e in evidence:
        if e.predicate in SINGLE_SOURCE_PREDS and len(e.source_ids) < 2:
            warnings.append(WARN_SINGLE_SOURCE)
            break

    if not evidence:
        warnings.append(WARN_NO_EVIDENCE)

    # 5) 越界检测
    out_of_range = detect_out_of_range(q, evidence) if evidence else False

    # 6) 生成
    tpl = template_answer(intent, q, evidence, hits, out_of_range)
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
        try:
            text = llm.complete(messages)
            answer = text
            result.mode = "llm"
            cited, w = verify_citations(answer, evidence)
            if not cited:
                # 不合格 → 纠正一次
                messages2 = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "你的回答没有给出 [E#] 证据引用。请只依据证据重写，每个结论后必须带 [E#]。"},
                ]
                text2 = llm.complete(messages2)
                cited2, w2 = verify_citations(text2, evidence)
                if cited2:
                    answer, cited, w = text2, cited2, w2
                else:
                    warnings.extend(w2)
                    warnings.append(WARN_NO_CITATION)
                    answer, result.mode = tpl, "template"
            result.cited_ids = cited
        except LLMUnavailable as exc:
            warnings.append(WARN_LLM_TIMEOUT if "timeout" in str(exc).lower() else WARN_LLM_UNAVAILABLE)
            answer, result.mode = tpl, "template"
        except Exception:
            warnings.append(WARN_LLM_UNAVAILABLE)
            answer, result.mode = tpl, "template"

    if result.mode == "template":
        cited, _w = verify_citations(answer, evidence)
        result.cited_ids = cited

    # 7) 分步动作（LLM 文本里已含「现在该做什么」则抽出，否则由证据派生）
    if steps:
        head, llm_steps = _split_llm_text(answer) if result.mode == "llm" else ("", [])
        if head:
            answer = head
        result.steps = llm_steps[:3] if (result.mode == "llm" and llm_steps) else compose_steps(evidence, intent)
        if result.mode == "template":
            result.answer = answer + "\n\n现在该做什么：\n" + "\n".join(
                f"{i}. {s}" for i, s in enumerate(result.steps, start=1)
            )
        else:
            result.answer = answer
            if result.steps:
                result.answer = answer + "\n\n现在该做什么：\n" + "\n".join(
                    f"{i}. {s}" for i, s in enumerate(result.steps, start=1)
                )
    else:
        result.answer = answer

    # 8) 数值校验 + 越界告警
    if out_of_range:
        warnings.append(WARN_OUT_OF_RANGE)
    warnings.extend(check_numbers(result.answer, evidence, q))

    # 9) 元信息
    if llm is not None and hasattr(llm, "last_usage"):
        result.llm_meta = dict(getattr(llm, "last_usage") or {})
    result.elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return result


# ------------------------------------------------------------------ CLI
def main(argv: Optional[Sequence[str]] = None) -> int:
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
