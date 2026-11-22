# -*- coding: utf-8 -*-
"""Streamlit 演示界面（DeepSeek 网页版风格）。

设计参考 DeepSeek 网页版：
- 左侧极简侧栏（新建对话 / 状态 / 设置 / 最近提问）
- 中间单列对话流（约 820px），用户消息右侧浅蓝气泡、助手回答左侧留白正文
- 底部圆角输入框（st.chat_input 固定底部）
- 空态欢迎页 + 建议问题卡片
- 浅色/深色跟随系统；可选大字模式

功能不变：只渲染 `app.contracts.AnswerResult`；不自行调用 DeepSeek、不改写 answer 文本；
qa / config / store 未就绪时用演示桩兜底。
"""
from __future__ import annotations

import csv
import html
import inspect
import os
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.contracts import AnswerResult, Evidence
from app.graph_view import ego_graph, graph_summary, load_graph, to_svg

DATA = ROOT / "data"

EXAMPLES: List[str] = [
    "阳光玫瑰放冷库该调到多少度？",
    "冷库里葡萄长白毛了怎么办？",
    "阳光玫瑰库房湿度要调到多少？",
    "阳光玫瑰和巨峰哪个更能放？",
    "用 SO₂ 熏阳光玫瑰行不行？",
    "-18℃ 冻起来能存一年吗？",
]


# ---------------------------------------------------------------- 基础工具
def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _num(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return ""


def _fmt_value(ev: Evidence) -> str:
    if ev.value is not None:
        return f"{_num(ev.value)}{ev.unit}"
    lo, hi = _num(ev.value_min), _num(ev.value_max)
    if lo and hi:
        return f"{lo}~{hi}{ev.unit}"
    if lo:
        return f"≥{lo}{ev.unit}"
    if hi:
        return f"≤{hi}{ev.unit}"
    return ""


def _cite_html(text: str) -> str:
    """把 [E1] 渲染成小角标（仅用于正文 markdown）。"""
    return re.sub(r"\[(E\d+)\]", r'<span class="ds-cite">\1</span>', text or "")


def _split_answer(answer: str) -> Tuple[str, str, str]:
    """拆成 结论 / 依据 / 行动 三段，兼容模板与 LLM 输出。"""
    raw = (answer or "").strip()
    if not raw:
        return "", "", ""
    cut = re.search(r"(现在该做什么|现在要做什么|该做什么|操作建议|下一步建议)[:：]?", raw)
    head, tail = (raw, "") if not cut else (raw[: cut.start()], raw[cut.start():])
    tail = re.sub(r"^.*?(现在该做什么|现在要做什么|该做什么|操作建议|下一步建议)[:：]?", "", tail)
    bcut = re.search(r"依据[:：]", head)
    if bcut:
        concl, basis = head[: bcut.start()], head[bcut.start():]
    else:
        concl, basis = head, ""
    basis = re.sub(r"^依据[:：]\s*", "", basis)
    basis = "\n".join(line.lstrip("- ").strip() for line in basis.splitlines() if line.strip())
    return concl.strip(), basis.strip(), tail.strip()


def _order_evidence(evidence: Sequence[Evidence], cited: Sequence[str]) -> List[Evidence]:
    cited_set = set(cited or [])
    return sorted(evidence or [], key=lambda e: (e.eid not in cited_set, -float(e.confidence or 0)))


# ---------------------------------------------------------------- 运行环境
@dataclass
class Runtime:
    settings: Any = None
    store: Any = None
    answer_question: Any = None
    store_name: str = "未接入"
    ready: bool = False
    error: str = ""


def _stub_result(question: str) -> AnswerResult:
    ev = Evidence(
        eid="E1", subject="阳光玫瑰", predicate="REQUIRES", object="低温冷藏 0±0.5℃",
        value=0.0, unit="℃", value_min=-0.5, value_max=0.5,
        source_ids=["gbt16862_2026"], source_titles=["GB/T 16862-2026 鲜食葡萄冷藏技术"],
        locator="7.3 冷藏条件", status="verified", confidence=0.9,
    )
    return AnswerResult(
        question=question, entities=[], intent="temperature", intent_confidence=0.8,
        evidence=[ev],
        answer=("结论：阳光玫瑰适宜冷藏温度为 0±0.5℃（[E1]）。\n\n"
                "依据：\n- [E1] 阳光玫瑰 —需要条件→ 低温冷藏 0±0.5℃；已核验\n\n"
                "现在该做什么：\n1. 把冷库温控设到 0±0.5℃，每天记录两次库温（[E1]）"),
        steps=["把冷库温控设到 0±0.5℃，每天记录两次库温（[E1]）"],
        cited_ids=["E1"], mode="template", warnings=["stub"],
    )


def _resolve(module: str, attr: str) -> Any:
    try:
        mod = __import__(module, fromlist=[attr])
        return getattr(mod, attr)
    except Exception:  # noqa: BLE001
        return None


_SECRET_KEYS = (
    "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL",
    "GRAPH_BACKEND", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD",
    "UI_TOPK", "UI_LARGE_FONT", "UI_SHOW_CYPHER", "LLM_TIMEOUT",
)


def _bridge_secrets() -> None:
    """云端部署（Streamlit Cloud / 魔搭创空间）用 st.secrets 注入配置。

    本地有 .env 时以 .env 为准；云端没有 .env，就把 secrets 写进环境变量，
    再交给 app.config.load_settings() 统一读取。
    """
    try:
        secrets = st.secrets
    except Exception:  # noqa: BLE001  （无 secrets.toml 时抛异常）
        return
    for key in _SECRET_KEYS:
        if os.getenv(key):
            continue
        try:
            value = secrets[key]
        except Exception:  # noqa: BLE001
            continue
        if value is not None and str(value).strip() != "":
            os.environ[key] = str(value)


@st.cache_resource(show_spinner=False)
def load_runtime() -> Runtime:
    _bridge_secrets()
    rt = Runtime()
    try:
        from app.config import load_settings

        rt.settings = load_settings()
        try:
            from app.store import get_store

            rt.store = get_store(rt.settings)
            rt.store_name = getattr(rt.store, "name", "local")
        except Exception as exc:  # noqa: BLE001
            rt.error = f"store: {exc}"
        rt.answer_question = _resolve("app.qa", "answer_question")
        rt.ready = rt.answer_question is not None
    except Exception as exc:  # noqa: BLE001
        rt.error = f"config: {exc}"
    return rt


def _call_supported(func: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        sig = inspect.signature(func).parameters
        if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.values()):
            kwargs = {k: v for k, v in kwargs.items() if k in sig}
    except (TypeError, ValueError):
        pass
    return func(*args, **kwargs)


def _ask(rt: Runtime, question: str, *, topk: int, allow_llm: bool,
         context: Optional[dict]) -> Tuple[Optional[AnswerResult], Optional[str]]:
    if not rt.ready or rt.answer_question is None:
        return _stub_result(question), None
    try:
        return _call_supported(
            rt.answer_question, question,
            store=rt.store, llm=None, k=topk, allow_llm=allow_llm,
            steps=True, settings=rt.settings, context=context,
        ), None
    except Exception:  # noqa: BLE001
        return None, traceback.format_exc()


# ---------------------------------------------------------------- 图谱统计 / 词表
def _rows(path: Path) -> int:
    try:
        with path.open(encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in csv.DictReader(f)))
    except Exception:  # noqa: BLE001
        return 0


@st.cache_data(show_spinner=False)
def build_graph_svg(view: str) -> Tuple[str, Dict[str, int]]:
    """生成知识图谱 SVG（纯标准库布局；view=all|shine）。"""
    try:
        graph = load_graph(DATA)
        if view == "shine":
            graph = ego_graph(graph, "shine_muscat")
            svg = to_svg(graph, width=1400, height=820,
                         title="阳光玫瑰（Shine Muscat）子图",
                         subtitle="与该品种直接相连的储藏条件、品质指标、病害与禁忌关系；悬停节点看详情")
        else:
            svg = to_svg(graph, width=1600, height=980,
                         title="鲜食葡萄储藏知识图谱",
                         subtitle="GB/T 16862-2026 条文 + 5 篇综述；实线=已核验，虚线=待核验；来源通过 source_ids 关联")
        return svg, graph_summary(graph)
    except Exception as exc:  # noqa: BLE001
        return "<p>图谱渲染失败：" + _esc(exc) + "</p>", {}


def graph_stats(rt: Runtime) -> Dict[str, int]:
    out = {"entities": _rows(DATA / "entities.csv"), "sources": _rows(DATA / "sources.csv"),
           "triples": _rows(DATA / "triples.csv")}
    out["nodes"] = out["entities"] + out["sources"]
    try:
        s = rt.store.stats() if rt.store is not None else {}
        out["varieties"] = int(s.get("varieties", 0))
        out["diseases"] = int(s.get("diseases", 0))
        out["conditions"] = int(s.get("conditions", 0))
    except Exception:  # noqa: BLE001
        pass
    return out


def load_vocab() -> Tuple[List[str], List[str]]:
    varieties: List[str] = []
    diseases: List[str] = []
    try:
        with (DATA / "entities.csv").open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("label") == "Variety":
                    varieties.append(row["name"])
                elif row.get("label") == "Disease":
                    diseases.append(row["name"])
    except Exception:  # noqa: BLE001
        pass
    return varieties, diseases


# ---------------------------------------------------------------- 样式
CSS = """
<style>
:root{
  --ds-accent:#4d6bfe; --ds-accent-soft:#eef2ff;
  --ds-bg:#ffffff; --ds-sidebar:#f9fafb; --ds-border:#e6e8eb;
  --ds-text:#1f2328; --ds-muted:#6b7280; --ds-bubble:#eef2ff;
  --ds-ok:#15803d; --ds-okbg:#e8f5ec; --ds-warn:#b45309; --ds-warnbg:#fef3c7;
  --ds-err:#b91c1c; --ds-errbg:#fee2e2;
}
@media (prefers-color-scheme: dark){
  :root{ --ds-bg:#17181b; --ds-sidebar:#111214; --ds-border:#2a2c31; --ds-text:#e8eaed;
         --ds-muted:#9aa0a6; --ds-bubble:#23263a; --ds-accent-soft:#1e2340; }
}
.stApp{ background:var(--ds-bg); color:var(--ds-text); }
.block-container{ max-width:820px; padding-top:1.2rem; padding-bottom:7rem; }
#MainMenu, footer{ visibility:hidden; }
h1,h2,h3,h4{ color:var(--ds-text); letter-spacing:-.01em; }

section[data-testid="stSidebar"]{ background:var(--ds-sidebar); border-right:1px solid var(--ds-border); }
section[data-testid="stSidebar"] .block-container{ padding-top:1rem; }
.ds-logo{ display:flex; align-items:center; gap:.55rem; font-weight:800; font-size:1.12rem; color:var(--ds-text); margin:.2rem 0 .9rem; }
.ds-logo span.mark{ display:inline-flex; width:30px; height:30px; border-radius:9px; align-items:center; justify-content:center;
  background:linear-gradient(135deg,#4d6bfe,#7c5cff); color:#fff; font-size:1rem; }
.ds-side-title{ font-size:.75rem; color:var(--ds-muted); text-transform:uppercase; letter-spacing:.08em; margin:.9rem 0 .4rem; }
.ds-chip{ display:flex; align-items:center; gap:.45rem; padding:.42rem .6rem; border:1px solid var(--ds-border);
  border-radius:10px; font-size:.82rem; color:var(--ds-text); background:var(--ds-bg); margin-bottom:.35rem; }
.ds-chip small{ color:var(--ds-muted); }
.ds-dot{ width:8px; height:8px; border-radius:50%; background:var(--ds-muted); }
.ds-dot.on{ background:#22c55e; } .ds-dot.off{ background:#f59e0b; }
.ds-vocab{ font-size:.78rem; color:var(--ds-muted); line-height:1.6; }

.ds-top{ display:flex; align-items:center; justify-content:space-between; margin-bottom:.4rem; }
.ds-top .title{ font-size:1.15rem; font-weight:800; }
.ds-top .badge{ font-size:.75rem; color:var(--ds-muted); border:1px solid var(--ds-border); padding:.18rem .55rem; border-radius:999px; }

.ds-hero{ text-align:center; padding:2.2rem 0 .6rem; }
.ds-hero h1{ font-size:2rem; margin:0 0 .45rem; }
.ds-hero p{ color:var(--ds-muted); font-size:.95rem; margin:0; }
div[class*="st-key-examples"] button{ text-align:left; justify-content:flex-start; min-height:3.6rem; border-radius:14px;
  border:1px solid var(--ds-border); background:var(--ds-bg); color:var(--ds-text); font-size:.9rem; line-height:1.4; }
div[class*="st-key-examples"] button:hover{ border-color:var(--ds-accent); background:var(--ds-accent-soft); }

.ds-user{ display:flex; justify-content:flex-end; margin:1.15rem 0 .3rem; }
.ds-user .bubble{ max-width:78%; background:var(--ds-bubble); border-radius:16px 16px 4px 16px;
  padding:.62rem .9rem; font-size:.95rem; color:var(--ds-text); }
.ds-assistant{ margin:.2rem 0 1.1rem; }
.ds-role{ display:inline-flex; align-items:center; gap:.4rem; font-size:.78rem; color:var(--ds-muted); margin-bottom:.35rem; }
.ds-role .mark{ width:20px; height:20px; border-radius:6px; display:inline-flex; align-items:center; justify-content:center;
  background:linear-gradient(135deg,#4d6bfe,#7c5cff); color:#fff; font-size:.7rem; }

.ds-md{ font-size:.96rem; line-height:1.75; color:var(--ds-text); }
.ds-md p{ margin:.2rem 0 .45rem; }
.ds-cite{ display:inline-block; margin:0 1px; padding:0 .3rem; border-radius:5px; font-size:.72rem; font-weight:700;
  color:var(--ds-accent); background:var(--ds-accent-soft); vertical-align:super; line-height:1.4; }
.ds-steps{ list-style:none; padding:0 0 0 .1rem; margin:.35rem 0 .2rem; counter-reset:step; }
.ds-steps li{ position:relative; padding:.38rem 0 .38rem 2.1rem; font-size:.93rem; border-bottom:1px dashed var(--ds-border); }
.ds-steps li:last-child{ border-bottom:0; }
.ds-steps li::before{ counter-increment:step; content:counter(step); position:absolute; left:0; top:.42rem;
  width:1.45rem; height:1.45rem; border-radius:50%; background:var(--ds-accent-soft); color:var(--ds-accent);
  font-weight:800; font-size:.78rem; display:flex; align-items:center; justify-content:center; }

.ds-warn{ display:inline-flex; align-items:center; gap:.35rem; padding:.26rem .6rem; border-radius:999px;
  font-size:.78rem; margin:.15rem .3rem .15rem 0; border:1px solid transparent; }
.ds-warn.amber{ color:var(--ds-warn); background:var(--ds-warnbg); border-color:#fde68a; }
.ds-warn.red{ color:var(--ds-err); background:var(--ds-errbg); border-color:#fecaca; }
.ds-warn.gray{ color:var(--ds-muted); background:var(--ds-sidebar); border-color:var(--ds-border); }
.ds-warn.blue{ color:var(--ds-accent); background:var(--ds-accent-soft); border-color:#c7d2fe; }

.ds-ev{ border:1px solid var(--ds-border); border-radius:12px; padding:.6rem .7rem; margin:.4rem 0; background:var(--ds-bg); }
.ds-ev.cited{ border-color:#c7d2fe; }
.ds-ev .hd{ display:flex; align-items:center; gap:.45rem; margin-bottom:.25rem; flex-wrap:wrap; }
.ds-ev .eid{ font-family:ui-monospace,Consolas,monospace; font-size:.72rem; font-weight:800; color:var(--ds-accent);
  background:var(--ds-accent-soft); padding:.08rem .38rem; border-radius:6px; }
.ds-ev .trip{ font-size:.88rem; color:var(--ds-text); font-weight:600; }
.ds-ev .meta{ font-size:.76rem; color:var(--ds-muted); line-height:1.55; }
.ds-tag{ font-size:.7rem; padding:.05rem .4rem; border-radius:999px; border:1px solid var(--ds-border); color:var(--ds-muted); }
.ds-tag.ok{ color:var(--ds-ok); background:var(--ds-okbg); border-color:#bbf7d0; }
.ds-tag.wait{ color:var(--ds-warn); background:var(--ds-warnbg); border-color:#fde68a; }

[data-testid="stChatInput"]{ max-width:820px; margin:0 auto; }
[data-testid="stChatInput"] > div{ border-radius:18px !important; border:1px solid var(--ds-border) !important;
  box-shadow:0 2px 14px rgba(15,23,42,.06) !important; background:var(--ds-bg) !important; }
[data-testid="stChatInput"] textarea{ font-size:.95rem !important; }
.ds-foot{ text-align:center; color:var(--ds-muted); font-size:.72rem; margin-top:.35rem; }
.ds-meta{ color:var(--ds-muted); font-size:.74rem; margin-top:.15rem; }
.ds-graph{ width:100%; overflow:auto; border:1px solid var(--ds-border); border-radius:14px; padding:.4rem; background:var(--ds-bg); }
.ds-graph svg{ width:100%; height:auto; display:block; }
</style>
"""
LARGE_CSS = """
<style>
html{ font-size:18px; }
.block-container{ max-width:880px; }
.ds-md{ font-size:1.18rem; line-height:1.95; }
.ds-steps li{ font-size:1.14rem; line-height:1.8; }
.ds-user .bubble{ font-size:1.14rem; }
.ds-ev .trip{ font-size:1.06rem; }
.ds-ev .meta{ font-size:.92rem; }
</style>
"""


# ---------------------------------------------------------------- 侧栏
def render_sidebar(rt: Runtime) -> Dict[str, Any]:
    with st.sidebar:
        st.markdown('<div class="ds-logo"><span class="mark">葡</span>葡萄冷库知识库</div>', unsafe_allow_html=True)
        if st.button("＋ 新建对话", use_container_width=True, key="new_chat"):
            st.session_state["turns"] = []
            st.rerun()

        online = bool(rt.settings and getattr(rt.settings, "llm_configured", False))
        model = getattr(rt.settings, "deepseek_model", "deepseek-chat") if rt.settings else "deepseek-chat"
        dot_cls = "on" if online else "off"
        st.markdown(
            f'<div class="ds-chip"><span class="ds-dot on"></span>后端 <b>{_esc(rt.store_name)}</b></div>'
            f'<div class="ds-chip"><span class="ds-dot {dot_cls}"></span>模型 <b>{_esc(model)}</b>'
            f'<small>{"在线" if online else "离线模板"}</small></div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="ds-side-title">设置</div>', unsafe_allow_html=True)
        default_topk = min(12, max(4, _env_int("UI_TOPK", 6)))
        if default_topk not in (4, 6, 8, 10, 12):
            default_topk = 6
        offline = st.toggle("离线模式（不调用 DeepSeek）", value=(not online) or _env_bool("UI_OFFLINE"),
                            key="offline")
        large = st.toggle("大字模式（农户/投影）", value=_env_bool("UI_LARGE_FONT"), key="large")
        topk = st.select_slider("证据条数 Top-K", options=[4, 6, 8, 10, 12], value=default_topk, key="topk")
        show_cypher = st.toggle("显示查询 Cypher", value=_env_bool("UI_SHOW_CYPHER"), key="show_cypher")
        show_graph = st.toggle("知识图谱视图", value=False, key="show_graph")
        graph_view = (st.selectbox("图谱范围", ["全图", "阳光玫瑰子图"], index=0, key="graph_view")
                      if show_graph else "全图")

        stats = graph_stats(rt)
        with st.expander("图谱规模", expanded=False):
            st.markdown(
                f'<div class="ds-vocab">实体 {stats.get("entities", 0)} + 来源 {stats.get("sources", 0)} = '
                f'<b>{stats.get("nodes", 0)}</b> 节点<br/>关系 <b>{stats.get("triples", 0)}</b> 条<br/>'
                f'品种 {stats.get("varieties", 0)} · 病害 {stats.get("diseases", 0)} · 条件 {stats.get("conditions", 0)}</div>',
                unsafe_allow_html=True,
            )
        varieties, diseases = load_vocab()
        with st.expander("已收录词表", expanded=False):
            st.markdown(
                f'<div class="ds-vocab">品种：{"、".join(varieties) or "—"}<br/>病害：{"、".join(diseases) or "—"}</div>',
                unsafe_allow_html=True,
            )

        turns = st.session_state.get("turns") or []
        if turns:
            st.markdown('<div class="ds-side-title">最近提问</div>', unsafe_allow_html=True)
            for i, turn in enumerate(reversed(turns[-8:])):
                q = turn.get("question") or ""
                label = q if len(q) <= 22 else q[:22] + "…"
                if st.button(label, key=f"recent_{i}", use_container_width=True):
                    st.session_state["pending_question"] = q
                    st.rerun()

        st.markdown('<div class="ds-foot">离线可用 · 答案带 [E#] 证据引用</div>', unsafe_allow_html=True)

    return {"offline": offline, "large": large, "topk": topk, "show_cypher": show_cypher,
            "show_graph": show_graph, "graph_view": graph_view}


# ---------------------------------------------------------------- 渲染
def _warn_cls(raw: str) -> Tuple[str, str]:
    if raw.startswith("unsourced_number") or raw.startswith("out_of_range") or raw == "out_of_range":
        return "amber", "越界"
    if raw in ("no_evidence", "no_citation") or raw.startswith("invalid_citation"):
        return "red", "未收录"
    if raw in ("llm_timeout", "llm_unavailable"):
        return "amber", "超时"
    if raw == "single_source":
        return "gray", "单来源"
    return "blue", "提示"


def _warn_text(raw: str) -> str:
    table = {
        "no_evidence": "图谱未收录该问题",
        "no_citation": "答案未给出有效证据引用",
        "llm_timeout": "模型超时，已降级离线模板",
        "llm_unavailable": "模型不可用，已降级离线模板",
        "single_source": "仅单个来源",
        "out_of_range": "数值超出证据区间",
        "stub": "演示桩数据",
    }
    if raw.startswith("unsourced_number"):
        return "含证据外数字：" + raw.split(":", 1)[-1]
    if raw.startswith("invalid_citation"):
        return "引用无效：" + raw.split(":", 1)[-1]
    if raw.startswith("out_of_range:"):
        return "超出证据区间：" + raw.split(":", 1)[-1]
    return table.get(raw, raw)


def _render_warnings(warnings: Sequence[str]) -> None:
    if not warnings:
        return
    pills = "".join(
        f'<span class="ds-warn {_warn_cls(w)[0]}">{_esc(_warn_cls(w)[1])} · {_esc(_warn_text(w))}</span>'
        for w in warnings
    )
    st.markdown(pills, unsafe_allow_html=True)


def _render_evidence(ev: Evidence, *, cited: bool) -> None:
    status = ('<span class="ds-tag ok">已核验</span>' if ev.status == "verified"
              else '<span class="ds-tag wait">待核验</span>')
    sources = "；".join(ev.source_titles[:2]) if ev.source_titles else ("；".join(ev.source_ids[:2]) or "来源未标注")
    value = _fmt_value(ev)
    locator = f'<br/>条款：{_esc(ev.locator)}' if (ev.locator or "").strip() else ""
    st.markdown(
        f'<div class="ds-ev{" cited" if cited else ""}">'
        f'<div class="hd"><span class="eid">{_esc(ev.eid)}</span>'
        f'<span class="trip">{_esc(ev.subject)} —{_esc(ev.predicate)}→ {_esc(ev.object)}</span>{status}</div>'
        f'<div class="meta">{("值：" + _esc(value) + "　") if value else ""}来源：{_esc(sources)}　'
        f'置信 {float(ev.confidence or 0):.2f}{locator}</div></div>',
        unsafe_allow_html=True,
    )


def render_assistant(result: AnswerResult, *, show_cypher: bool, large: bool) -> None:
    st.markdown('<div class="ds-role"><span class="mark">葡</span>葡萄冷库助手</div>', unsafe_allow_html=True)
    _render_warnings(result.warnings)

    concl, basis, action = _split_answer(result.answer)
    if concl:
        st.markdown(f'<div class="ds-md">{_cite_html(concl)}</div>', unsafe_allow_html=True)
    if result.steps:
        lis = "".join(f"<li>{_cite_html(s)}</li>" for s in result.steps)
        st.markdown(f'<ul class="ds-steps">{lis}</ul>', unsafe_allow_html=True)
    elif action:
        st.markdown(f'<div class="ds-md">{_cite_html(action)}</div>', unsafe_allow_html=True)

    cited = set(result.cited_ids or [])
    ordered = _order_evidence(result.evidence, result.cited_ids)
    if ordered:
        with st.expander(f"依据 · {len(ordered)} 条证据", expanded=False):
            for ev in ordered:
                _render_evidence(ev, cited=ev.eid in cited)
            if basis:
                st.markdown(
                    f'<div class="ds-md" style="font-size:.85rem;opacity:.85">{_cite_html(basis)}</div>',
                    unsafe_allow_html=True,
                )

    if result.context_note:
        st.caption(f"承接上一轮 · {result.context_note}")

    meta = [f"意图 {result.intent}", f"模式 {'在线' if result.mode == 'llm' else '离线模板'}",
            f"耗时 {result.elapsed_ms} ms", f"证据 {len(result.evidence)} 条"]
    if result.llm_meta:
        p, c = result.llm_meta.get("prompt_tokens"), result.llm_meta.get("completion_tokens")
        if p is not None and c is not None:
            meta.append(f"tokens {p}/{c}")
    st.markdown(f'<div class="ds-meta">{" · ".join(meta)}</div>', unsafe_allow_html=True)

    if show_cypher and result.query_cypher:
        with st.expander("查询详情（Cypher / 参数）", expanded=False):
            for block in result.query_cypher:
                if str(block).strip():
                    st.code(str(block), language="cypher")
            st.caption(f"耗时 {result.elapsed_ms} ms · 意图 {result.intent} · 置信 {result.intent_confidence:.2f}")


def render_user(question: str) -> None:
    st.markdown(f'<div class="ds-user"><div class="bubble">{_esc(question)}</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- 主流程
def main() -> None:
    st.set_page_config(page_title="葡萄冷库知识库", layout="centered", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)

    rt = load_runtime()
    cfg = render_sidebar(rt)
    if cfg["large"]:
        st.markdown(LARGE_CSS, unsafe_allow_html=True)

    turns = st.session_state.setdefault("turns", [])

    st.markdown(
        '<div class="ds-top"><div class="title">鲜食葡萄储藏知识库</div>'
        f'<div class="badge">{"离线演示" if cfg["offline"] else "DeepSeek 在线"} · 答案可溯源</div></div>',
        unsafe_allow_html=True,
    )
    if cfg.get("show_graph"):
        view_key = "shine" if cfg.get("graph_view") == "阳光玫瑰子图" else "all"
        svg, summary = build_graph_svg(view_key)
        st.markdown('<div class="ds-side-title">知识图谱</div>', unsafe_allow_html=True)
        st.markdown('<div class="ds-graph">' + svg + "</div>", unsafe_allow_html=True)
        if summary:
            st.caption(
                "节点 " + str(summary.get("nodes", 0)) + "（品种 " + str(summary.get("Variety", 0)) +
                " / 病害 " + str(summary.get("Disease", 0)) +
                " / 指标 " + str(summary.get("QualityIndicator", 0)) +
                " / 条件 " + str(summary.get("Condition", 0)) + "）· 关系 " +
                str(summary.get("edges", 0)) + "（已核验 " + str(summary.get("verified", 0)) +
                " / 待核验 " + str(summary.get("anchor", 0)) + "）"
            )
        st.divider()

    if not rt.ready:
        st.warning("问答模块未就绪，当前展示演示桩结果（检查 app/qa.py 是否可导入）。")

    if not turns:
        st.markdown(
            '<div class="ds-hero"><h1>种植户和冷库管理员的技术助手</h1>'
            '<p>问一句大白话，答案带国标条款与文献来源；没收录就直说。</p></div>',
            unsafe_allow_html=True,
        )
        with st.container(key="examples"):
            cols = st.columns(2)
            for idx, q in enumerate(EXAMPLES):
                if cols[idx % 2].button(q, key=f"ex_{idx}", use_container_width=True):
                    st.session_state["pending_question"] = q
                    st.rerun()

    for turn in turns:
        render_user(turn["question"])
        render_assistant(turn["result"], show_cypher=cfg["show_cypher"], large=cfg["large"])

    pending = st.session_state.pop("pending_question", None)
    typed = st.chat_input("问一个葡萄冷库的问题，例如：阳光玫瑰放冷库几度？")
    question = pending or (typed.strip() if isinstance(typed, str) else "")
    if question:
        last = turns[-1]["result"] if turns else None
        ctx = None
        if last is not None and getattr(last, "entities", None):
            ctx = {
                "intent": getattr(last, "intent", ""),
                "entities": [{"node_id": h.node_id, "label": h.label, "surface": h.surface} for h in last.entities],
            }
        with st.spinner("正在查图谱、取证据…"):
            result, error = _ask(rt, question, topk=cfg["topk"], allow_llm=not cfg["offline"], context=ctx)
        if error:
            st.error("问答管线异常（已捕获，页面保持可用）")
            with st.expander("异常详情"):
                st.code(error, language="text")
        elif result is not None:
            turns.append({"question": question, "result": result})
            st.session_state["turns"] = turns[-20:]
            st.rerun()

    st.markdown(
        '<div class="ds-foot">内容来自 GB/T 16862-2026 与综述文献 · 未收录会明确拒答 · 离线可用</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
