"""Streamlit 演示界面（DeepSeek 网页版风格）。

设计参考 DeepSeek 网页版：
- 左侧极简侧栏（新建对话 / 状态 / 设置 / 最近提问）
- 中间单列对话流（约 820px），用户消息右侧浅蓝气泡、助手回答左侧留白正文
- 底部圆角输入框（st.chat_input 固定底部）
- 空态欢迎页 + 建议问题卡片
- 浅色/深色跟随系统；可选大字模式

功能不变：只渲染 `app.contracts.AnswerResult`；不自行调用 DeepSeek、不改写 answer 文本。
安全约定：
- 所有来自 answer / steps / evidence / warnings / CSV 词表 / 设置 / 模型名的动态文本，
  进入 ``unsafe_allow_html`` 前一律 ``_esc()``；只有本文件生成的 ds-* 标签是 HTML。
- qa / config / store 未就绪时明确返回「不可用」结果（不返回固定答案）；
  演示桩仅在显式设置环境变量 ``APP_DEMO_MODE=1`` 时启用，并标记为模拟数据。
"""
from __future__ import annotations

import csv
import html
import inspect
import os
import re
import sys
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import streamlit.components.v1 as components

from app.contracts import (
    WARN_ANCHOR_HIGH_RISK,
    WARN_ANCHOR_UNVERIFIED,
    WARN_CITATION_MISMATCH,
    WARN_LLM_ANSWER_REJECTED,
    WARN_SYSTEM_UNAVAILABLE,
    WARN_UNSUPPORTED_FACT,
    AnswerResult,
    Evidence,
)
from app.graph_interactive import interactive_html
from app.graph_view import ego_graph, graph_summary, load_graph

DATA = ROOT / "data"

EXAMPLES: list[str] = [
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


# 演示桩开关：启动时快照 + 运行时环境变量双读取（测试可 monkeypatch 本模块属性或 env）。
APP_DEMO_MODE: bool = _env_bool("APP_DEMO_MODE", False)


def _demo_enabled() -> bool:
    """演示桩开关：只有显式 ``APP_DEMO_MODE=1`` 时启用。

    默认关闭：未就绪时返回「不可用」，绝不静默返回固定答案。
    """
    return bool(APP_DEMO_MODE) or _env_bool("APP_DEMO_MODE", False)


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


def _cite_html(text: Any) -> str:
    """把 ``[E#]`` 渲染成引用角标；**先转义全文**，再只替换 ``[E数字]``。

    任何 answer / 步骤文本里的 HTML 都会被当作普通文本输出，
    只有 ``<span class="ds-cite">E#</span>`` 是本文件生成的合法标记。
    """
    escaped = _esc(text)
    return re.sub(r"\[(E\d+)\]", r'<span class="ds-cite">\1</span>', escaped)


def _md_html(text: Any, *, style: str = "") -> str:
    attr = f' style="{style}"' if style else ""
    return f'<div class="ds-md"{attr}>{_cite_html(text)}</div>'


def _steps_html(steps: Sequence[str]) -> str:
    lis = "".join(f"<li>{_cite_html(step)}</li>" for step in steps or [])
    return f'<ul class="ds-steps">{lis}</ul>'


def _user_bubble_html(question: Any) -> str:
    return f'<div class="ds-user"><div class="bubble">{_esc(question)}</div></div>'


def _split_answer(answer: str) -> tuple[str, str, str]:
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


def _order_evidence(evidence: Sequence[Evidence], cited: Sequence[str]) -> list[Evidence]:
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
    """演示桩：**仅在显式 APP_DEMO_MODE=1 时**使用，明确标记模拟数据。

    数据不得进入正式评测/图谱统计（graph_stats 不读取本函数结果）。
    """
    ev = Evidence(
        eid="E1", subject="阳光玫瑰", predicate="REQUIRES", object="低温冷藏 0±0.5℃",
        value=0.0, unit="℃", value_min=-0.5, value_max=0.5,
        source_ids=["gbt16862_2026"], source_titles=["GB/T 16862-2026 鲜食葡萄冷藏技术"],
        locator="7.3 冷藏条件", status="verified", confidence=0.9,
    )
    return AnswerResult(
        question=question, entities=[], intent="temperature", intent_confidence=0.8,
        evidence=[ev],
        answer=("【演示桩数据 · 模拟内容，非正式问答】\n\n"
                "结论：阳光玫瑰适宜冷藏温度为 0±0.5℃（[E1]）。\n\n"
                "依据：\n- [E1] 阳光玫瑰 —需要条件→ 低温冷藏 0±0.5℃；已核验\n\n"
                "现在该做什么：\n1. 把冷库温控设到 0±0.5℃，每天记录两次库温（[E1]）"),
        steps=["把冷库温控设到 0±0.5℃，每天记录两次库温（[E1]）"],
        cited_ids=["E1"], mode="demo", warnings=["stub", "simulated_data"],
    )


def _unavailable_result(question: str) -> AnswerResult:
    """问答模块未就绪时的明确「不可用」结果：不返回任何固定答案。"""
    return AnswerResult(
        question=question, entities=[], intent="general", intent_confidence=0.0,
        evidence=[], answer=(
            "系统问答模块未就绪（app/qa.py 或数据/图谱后端不可用），本次不会返回固定答案。"
            "请检查配置与数据文件后刷新页面重试。"
        ),
        steps=[], cited_ids=[], mode="unavailable",
        warnings=[WARN_SYSTEM_UNAVAILABLE],
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
         context: dict | None) -> tuple[AnswerResult | None, str | None]:
    if not rt.ready or rt.answer_question is None:
        # 默认明确不可用；演示桩必须显式开启 APP_DEMO_MODE=1，绝不静默兜底固定答案。
        if _demo_enabled():
            return _stub_result(question), None
        return _unavailable_result(question), None
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
def build_graph_html(view: str) -> tuple[str, dict[str, int]]:
    """生成可交互知识图谱 HTML（点击节点看邻居；view=all|shine）。"""
    try:
        graph = load_graph(DATA)
        if view == "shine":
            graph = ego_graph(graph, "shine_muscat")
            html_doc = interactive_html(
                graph, width=1400, height=820,
                title="阳光玫瑰（Shine Muscat）子图",
                subtitle="点击节点查看关联条件/指标/病害；滚轮缩放，拖拽平移",
            )
        else:
            html_doc = interactive_html(
                graph, width=1600, height=980,
                title="鲜食葡萄储藏知识图谱",
                subtitle="点击节点看关联；实线=已核验，虚线=待核验；来源通过 source_ids 关联",
            )
        return html_doc, graph_summary(graph)
    except Exception as exc:  # noqa: BLE001
        return "<p>图谱渲染失败：" + _esc(exc) + "</p>", {}


def graph_stats(rt: Runtime) -> dict[str, int]:
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


def load_vocab() -> tuple[list[str], list[str]]:
    varieties: list[str] = []
    diseases: list[str] = []
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
def render_sidebar(rt: Runtime) -> dict[str, Any]:
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
                f'<div class="ds-vocab">实体 {_esc(stats.get("entities", 0))} + 来源 {_esc(stats.get("sources", 0))} = '
                f'<b>{_esc(stats.get("nodes", 0))}</b> 节点<br/>关系 <b>{_esc(stats.get("triples", 0))}</b> 条<br/>'
                f'品种 {_esc(stats.get("varieties", 0))} · 病害 {_esc(stats.get("diseases", 0))} · '
                f'条件 {_esc(stats.get("conditions", 0))}</div>',
                unsafe_allow_html=True,
            )
        varieties, diseases = load_vocab()
        with st.expander("已收录词表", expanded=False):
            st.markdown(
                f'<div class="ds-vocab">品种：{_esc("、".join(varieties) or "—")}'
                f'<br/>病害：{_esc("、".join(diseases) or "—")}</div>',
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
# 新告警码（app/contracts.py 定义）→ (颜色, 短标签)
_WARN_LABELS: dict[str, tuple[str, str]] = {
    WARN_SYSTEM_UNAVAILABLE: ("red", "系统不可用"),
    WARN_ANCHOR_UNVERIFIED: ("amber", "待核验"),
    WARN_ANCHOR_HIGH_RISK: ("red", "高风险参数待核验"),
    WARN_UNSUPPORTED_FACT: ("amber", "事实缺引用"),
    WARN_CITATION_MISMATCH: ("amber", "引用与内容不匹配"),
    WARN_LLM_ANSWER_REJECTED: ("amber", "已回退证据模板"),
}

_WARN_TEXT: dict[str, str] = {
    "no_evidence": "图谱未收录该问题",
    "no_citation": "答案未给出有效证据引用",
    "llm_timeout": "模型超时，已降级离线模板",
    "llm_unavailable": "模型不可用，已降级离线模板",
    "single_source": "仅单个来源",
    "out_of_range": "数值超出证据区间",
    "stub": "演示桩数据（模拟内容）",
    "simulated_data": "模拟数据，非正式问答",
    WARN_SYSTEM_UNAVAILABLE: "问答系统未就绪，不返回固定答案",
    WARN_ANCHOR_UNVERIFIED: "使用了待核验证据",
    WARN_ANCHOR_HIGH_RISK: "仅待核验证据给出高风险参数",
    WARN_UNSUPPORTED_FACT: "事实句缺少证据引用",
    WARN_CITATION_MISMATCH: "引用与内容不匹配",
    WARN_LLM_ANSWER_REJECTED: "大模型答案未通过校验，已回退证据模板",
}


def _warn_base(raw: Any) -> str:
    return str(raw or "").split(":", 1)[0].strip()


def _warn_detail(raw: Any) -> str:
    text = str(raw or "")
    return text.split(":", 1)[1].strip() if ":" in text else ""


def _warn_cls(raw: Any) -> tuple[str, str]:
    base = _warn_base(raw)
    if base in _WARN_LABELS:
        return _WARN_LABELS[base]
    if base.startswith("unsourced_number") or base.startswith("out_of_range"):
        return "amber", "越界"
    if base in ("no_evidence", "no_citation") or base.startswith("invalid_citation"):
        return "red", "未收录"
    if base in ("llm_timeout", "llm_unavailable"):
        return "amber", "超时"
    if base == "single_source":
        return "gray", "单来源"
    return "blue", "提示"


def _warn_text(raw: Any) -> str:
    base = _warn_base(raw)
    detail = _warn_detail(raw)
    if base.startswith("unsourced_number"):
        return "含证据外数字" + (f"：{detail}" if detail else "")
    if base.startswith("invalid_citation"):
        return "引用无效" + (f"：{detail}" if detail else "")
    if base == "out_of_range" and detail:
        return f"数值超出证据区间：{detail}"
    return _WARN_TEXT.get(base, str(raw or ""))


def _warn_pills_html(warnings: Sequence[str]) -> str:
    """告警胶囊 HTML（纯函数，测试可直接断言）：告警文本全部先转义。"""
    parts: list[str] = []
    for raw in warnings or []:
        cls, label = _warn_cls(raw)
        parts.append(f'<span class="ds-warn {cls}">{_esc(label)} · {_esc(_warn_text(raw))}</span>')
    return "".join(parts)


def _render_warnings(warnings: Sequence[str]) -> None:
    pills = _warn_pills_html(warnings)
    if pills:
        st.markdown(pills, unsafe_allow_html=True)


def _evidence_card_html(ev: Evidence, cited: bool) -> str:
    """证据卡片 HTML（纯函数）：图谱字段一律转义，只有 ds-* 标签是 HTML。"""
    status = ('<span class="ds-tag ok">已核验</span>' if ev.status == "verified"
              else '<span class="ds-tag wait">待核验</span>')
    sources = "；".join(ev.source_titles[:2]) if ev.source_titles else ("；".join(ev.source_ids[:2]) or "来源未标注")
    value = _fmt_value(ev)
    locator = f'<br/>条款：{_esc(ev.locator)}' if (ev.locator or "").strip() else ""
    return (
        f'<div class="ds-ev{" cited" if cited else ""}">'
        f'<div class="hd"><span class="eid">{_esc(ev.eid)}</span>'
        f'<span class="trip">{_esc(ev.subject)} —{_esc(ev.predicate)}→ {_esc(ev.object)}</span>{status}</div>'
        f'<div class="meta">{("值：" + _esc(value) + "　") if value else ""}来源：{_esc(sources)}　'
        f'置信 {float(ev.confidence or 0):.2f}{locator}</div></div>'
    )


def _render_evidence(ev: Evidence, *, cited: bool) -> None:
    st.markdown(_evidence_card_html(ev, cited=cited), unsafe_allow_html=True)


_MODE_LABELS = {"llm": "在线", "template": "离线模板", "unavailable": "不可用", "demo": "演示桩"}


def _mode_label(mode: Any) -> str:
    key = str(mode or "")
    return _MODE_LABELS.get(key, _esc(key))


def _assistant_meta_html(result: AnswerResult) -> str:
    """回答下方 meta 行（纯函数）：仅程序标签是 HTML，动态值全部转义。"""
    meta = [
        f"意图 {_esc(result.intent)}",
        f"模式 {_mode_label(result.mode)}",
        f"耗时 {_esc(result.elapsed_ms)} ms",
        f"证据 {_esc(len(result.evidence or []))} 条",
    ]
    if result.llm_meta:
        p, c = result.llm_meta.get("prompt_tokens"), result.llm_meta.get("completion_tokens")
        if p is not None and c is not None:
            meta.append(f"tokens {_esc(p)}/{_esc(c)}")
    return f'<div class="ds-meta">{" · ".join(meta)}</div>'


def render_assistant(result: AnswerResult, *, show_cypher: bool, large: bool) -> None:
    st.markdown('<div class="ds-role"><span class="mark">葡</span>葡萄冷库助手</div>', unsafe_allow_html=True)
    _render_warnings(result.warnings)

    concl, basis, action = _split_answer(result.answer)
    if concl:
        st.markdown(_md_html(concl), unsafe_allow_html=True)
    if result.steps:
        st.markdown(_steps_html(result.steps), unsafe_allow_html=True)
    elif action:
        st.markdown(_md_html(action), unsafe_allow_html=True)

    cited = set(result.cited_ids or [])
    ordered = _order_evidence(result.evidence, result.cited_ids)
    if ordered:
        with st.expander(f"依据 · {len(ordered)} 条证据", expanded=False):
            for ev in ordered:
                _render_evidence(ev, cited=ev.eid in cited)
            if basis:
                st.markdown(_md_html(basis, style="font-size:.85rem;opacity:.85"), unsafe_allow_html=True)

    if result.context_note:
        st.caption(f"承接上一轮 · {result.context_note}")

    st.markdown(_assistant_meta_html(result), unsafe_allow_html=True)

    if show_cypher and result.query_cypher:
        with st.expander("查询详情（Cypher / 参数）", expanded=False):
            for block in result.query_cypher:
                if str(block).strip():
                    st.code(str(block), language="cypher")
            st.caption(f"耗时 {result.elapsed_ms} ms · 意图 {result.intent} · 置信 {result.intent_confidence:.2f}")


def render_user(question: str) -> None:
    st.markdown(_user_bubble_html(question), unsafe_allow_html=True)


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
        graph_html, summary = build_graph_html(view_key)
        st.markdown('<div class="ds-side-title">知识图谱</div>', unsafe_allow_html=True)
        components.html(graph_html, height=800, scrolling=False)
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
        st.error(
            "问答模块不可用：系统问答模块未就绪（app/qa.py 或数据/图谱后端加载失败），"
            "任意问题都不会返回固定答案。请检查配置与数据文件后刷新页面。"
        )
        if _demo_enabled():
            st.info("已显式启用演示桩（APP_DEMO_MODE=1）：以下结果为模拟数据，非正式问答。")

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
