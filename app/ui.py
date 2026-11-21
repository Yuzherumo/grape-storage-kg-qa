"""Streamlit 演示界面（S4，写区：app/ui.py）。

职责边界（docs/api.md §8）：
- 只渲染 `app.contracts.AnswerResult`；不自行调用 DeepSeek、不改写 answer 文本。
- `app.qa` / `app.config` / `app.store` 未就绪时使用内置「演示桩」，页面仍可启动与交互。

启动：
    streamlit run app/ui.py --server.port 8501 --server.headless true
"""
from __future__ import annotations

import csv
import html
import inspect
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

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
)

APP_TITLE = "鲜食葡萄储藏知识图谱问答"
APP_SUBTITLE = (
    "农客松 2026 · 主赛道 方向二「生命系统」｜面向种植户与冷库管理员的鲜食葡萄采后贮藏问答："
    "结论 + 可溯源证据 [E#] + 现在该做什么；未配置 API Key 时自动离线模板作答。"
)

# 6 个示例问题（按钮文案, 实际提问）
EXAMPLES: List[Tuple[str, str]] = [
    ("① 阳光玫瑰放冷库该调到多少度？", "阳光玫瑰放冷库该调到多少度？"),
    ("② 冷库里葡萄长白毛了怎么办？", "冷库里葡萄长白毛了怎么办？"),
    ("③ 葡萄发软掉粒是咋回事？", "葡萄发软掉粒是咋回事？"),
    ("④ 用 SO₂ 熏阳光玫瑰行不行？", "用 SO₂ 熏阳光玫瑰行不行？"),
    ("⑤ 阳光玫瑰和巨峰哪个更能放？", "阳光玫瑰和巨峰哪个更能放？"),
    ("⑥ -18℃ 冻起来能存一年吗？", "-18℃ 冻起来能存一年吗？"),
]

INTENT_LABELS: Dict[str, str] = {
    "temperature": "贮藏温度",
    "humidity": "贮藏湿度",
    "atmosphere": "气调贮藏",
    "shelf_life": "耐贮性",
    "disease_control": "病害处置",
    "disease_risk": "病害风险",
    "quality_indicator": "品质指标",
    "variety_compare": "品种对比",
    "contraindication": "禁忌/不建议",
    "general": "通用问答",
}

PREDICATE_LABELS: Dict[str, str] = {
    "REQUIRES": "要求",
    "CONTRA_INDICATED_FOR": "禁忌",
    "AFFECTS": "影响",
    "SUSCEPTIBLE_TO": "易感",
    "PREVENTED_BY": "可预防",
    "INDUCED_BY": "诱发",
    "ALTERNATIVE_TO": "可替代",
    "INDICATES": "指示",
    "HAS_INDICATOR_VALUE": "指标值",
}

STAT_LABELS: Dict[str, str] = {
    "nodes": "节点",
    "rels": "关系",
    "relationships": "关系",
    "edges": "关系",
    "triples": "三元组",
    "varieties": "品种",
    "conditions": "条件",
    "indicators": "指标",
    "quality_indicators": "指标",
    "diseases": "病害",
    "sources": "来源",
    "backend": "后端",
    "unresolved_edges": "未解析边",
    "data_files": "数据文件",
}

SPEC_VARIETIES = ["阳光玫瑰", "巨峰", "红地球", "夏黑", "玫瑰香", "克瑞森无核", "户太八号", "维多利亚"]
SPEC_DISEASES = ["灰霉病", "根霉病", "青霉病", "炭疽病", "酸腐病", "黑霉病"]

_EID_RE = re.compile(r"\[(E\d+)\]")

# ---------------------------------------------------------------- 基础工具


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _rerun() -> None:
    rerun = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if rerun is not None:
        rerun()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip())
    except (TypeError, ValueError):
        return default


def _setting(settings: Any, names: Sequence[str], default: Any = None) -> Any:
    """从 Settings（dataclass/对象/dict）里按候选字段名取值。"""
    if settings is None:
        return default
    for name in names:
        if isinstance(settings, dict):
            value = settings.get(name)
        else:
            value = getattr(settings, name, None)
        if value not in (None, ""):
            return value
    return default


def _llm_key_configured(runtime: "Runtime") -> bool:
    """API Key 是否已配置（优先看 Settings，其次环境变量）。"""
    settings = getattr(runtime, "settings", None)
    if settings is not None:
        try:
            if bool(getattr(settings, "llm_configured", False)):
                return True
        except Exception:
            pass
        key = str(getattr(settings, "deepseek_api_key", "") or "").strip()
        if key:
            return True
    return bool(os.getenv("DEEPSEEK_API_KEY"))


def resolve_model(settings: Any) -> str:
    return str(
        _setting(
            settings,
            ("deepseek_model", "model", "llm_model", "chat_model"),
            os.getenv("DEEPSEEK_MODEL") or "deepseek-chat",
        )
    )


def resolve_backend(settings: Any, store_name: str) -> str:
    if store_name and store_name != "stub":
        return store_name
    return str(_setting(settings, ("graph_backend", "backend"), os.getenv("GRAPH_BACKEND") or "local"))


def _num(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _fmt_value(ev: Evidence) -> str:
    unit = (getattr(ev, "unit", "") or "").strip()
    vmin = getattr(ev, "value_min", None)
    vmax = getattr(ev, "value_max", None)
    value = getattr(ev, "value", None)
    if vmin is not None and vmax is not None:
        return f"{_num(vmin)}~{_num(vmax)} {unit}".strip()
    if value is not None:
        return f"{_num(value)} {unit}".strip()
    return ""


def _fmt_conf(conf: Any) -> str:
    try:
        return f"{float(conf):.2f}"
    except (TypeError, ValueError):
        return "—"


def _eid_of(ev: Evidence) -> str:
    return str(getattr(ev, "eid", "") or "").strip() or "E?"


# ---------------------------------------------------------------- 数据读取（只读）


def load_vocab() -> Tuple[List[str], List[str], str]:
    """读取 data/entities.csv 的品种/病害名；文件未就绪时回落到 spec 预置词表。"""
    varieties: List[str] = []
    diseases: List[str] = []
    path = ROOT / "data" / "entities.csv"
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                label = (row.get("label") or "").strip()
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                if label == "Variety":
                    varieties.append(name)
                elif label == "Disease":
                    diseases.append(name)
    except Exception:
        pass
    origin = "csv"
    if not varieties:
        varieties = list(SPEC_VARIETIES)
        origin = "fallback"
    if not diseases:
        diseases = list(SPEC_DISEASES)
        origin = "fallback"
    return varieties, diseases, origin


def _count_csv_rows(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            return sum(1 for _ in reader)
    except Exception:
        return 0


def count_graph() -> Dict[str, Any]:
    """演示桩用的图谱规模统计（直接读 CSV，只读）。"""
    data_dir = ROOT / "data"
    nodes = _count_csv_rows(data_dir / "entities.csv")
    triples = _count_csv_rows(data_dir / "triples.csv")
    if not triples:
        for extra in sorted(data_dir.glob("triples*.csv")):
            if extra.name == "triples.csv":
                continue
            triples += _count_csv_rows(extra)
    varieties, diseases, origin = load_vocab()
    return {
        "nodes": nodes,
        "rels": triples,
        "varieties": len(varieties) if origin == "csv" else 0,
        "diseases": len(diseases) if origin == "csv" else 0,
        "_data_ready": bool(nodes or triples),
    }


# ---------------------------------------------------------------- 运行时装配


@dataclass
class Runtime:
    """UI 依赖的问答运行时；任一部分缺失都在 errors 中说明。"""

    ready: bool = False
    settings: Any = None
    store: Any = None
    answer_question: Any = None
    store_name: str = "stub"
    errors: List[str] = field(default_factory=list)


class StubStore:
    """演示桩：不依赖图谱数据，提供 stats() 与 name。"""

    name = "stub"

    def stats(self) -> Dict[str, Any]:
        return count_graph()

    def health(self) -> Tuple[bool, str]:
        return False, "图谱后端未就绪（演示桩）"


def build_stub_result(question: str) -> AnswerResult:
    """qa 未就绪时的示例 AnswerResult（界面结构演示，不代表真实结论）。"""
    asked = (question or "").strip() or EXAMPLES[0][1]
    ev1 = Evidence(
        eid="E1",
        subject="阳光玫瑰",
        predicate="REQUIRES",
        object="低温冷藏 0±0.5℃",
        value=0.0,
        unit="℃",
        value_min=-0.5,
        value_max=0.5,
        source_ids=["gbt16862_2026"],
        source_titles=["GB/T 16862-2026《鲜食葡萄冷藏技术》"],
        locator="演示桩占位：真实 locator 待 data/triples.csv 接入",
        quote="",
        status="anchor",
        confidence=0.6,
        score=0.9,
    )
    ev2 = Evidence(
        eid="E2",
        subject="阳光玫瑰",
        predicate="REQUIRES",
        object="相对湿度 90~95%",
        value=92.5,
        unit="%",
        value_min=90,
        value_max=95,
        source_ids=["gbt16862_2026"],
        source_titles=["GB/T 16862-2026《鲜食葡萄冷藏技术》"],
        locator="演示桩占位：真实 locator 待 data/triples.csv 接入",
        quote="",
        status="anchor",
        confidence=0.55,
        score=0.8,
    )
    ev3 = Evidence(
        eid="E3",
        subject="1-MCP 处理",
        predicate="AFFECTS",
        object="落粒率",
        value=None,
        unit="%",
        source_ids=["review_shine_muscat"],
        source_titles=["阳光玫瑰葡萄贮藏保鲜研究进展（综述）"],
        locator="演示桩占位：真实 locator 待 data/triples.csv 接入",
        quote="",
        status="anchor",
        confidence=0.5,
        score=0.7,
    )
    answer = "\n".join(
        [
            "**结论**：演示桩示例——页面结构已连通，但问答管线（app.qa）尚未就绪，"
            "以下数值仅用于展示界面排版，不作真实结论。阳光玫瑰冷库贮藏适宜温度约 0±0.5 ℃ [E1]，"
            "相对湿度保持 90~95% [E2]，1-MCP 处理可降低落粒率 [E3]。",
            "",
            "**依据**：",
            "- [E1] 阳光玫瑰 —要求→ 低温冷藏 0±0.5 ℃（GB/T 16862-2026《鲜食葡萄冷藏技术》）",
            "- [E2] 阳光玫瑰 —要求→ 相对湿度 90~95%（GB/T 16862-2026《鲜食葡萄冷藏技术》）",
            "- [E3] 1-MCP 处理 —影响→ 落粒率（阳光玫瑰葡萄贮藏保鲜研究进展，综述）",
            "",
            "**现在该做什么**：",
            "1. 入库前 12 小时内完成预冷，果心温度尽快降到 0 ℃ 附近。",
            "2. 冷库设定 0±0.5 ℃、相对湿度 90~95%，减少开门频次，避免温度波动。",
            "3. 每批次抽检，发现长白毛或软烂果立即剔除隔离，防止交叉感染。",
        ]
    )
    return AnswerResult(
        question=asked,
        entities=[
            EntityHit(node_id="shine_muscat", label="Variety", surface="阳光玫瑰", alias_hit="阳光玫瑰", score=1.0, start=0, end=4)
        ],
        intent="temperature",
        intent_confidence=0.55,
        evidence=[ev1, ev2, ev3],
        answer=answer,
        steps=[
            "入库前 12 小时内完成预冷，果心温度尽快降到 0 ℃ 附近。",
            "冷库设定 0±0.5 ℃、相对湿度 90~95%，减少开门频次，避免温度波动。",
            "每批次抽检，发现长白毛或软烂果立即剔除隔离，防止交叉感染。",
        ],
        cited_ids=["E1", "E2"],
        mode="template",
        elapsed_ms=0,
        query_cypher=[
            "// 演示桩占位：真实模板见 graph/queries/*.cypher\n"
            "MATCH (v:Variety {id: $variety})-[r:REQUIRES]->(c:Condition)\n"
            "WHERE c.category = '温度'\n"
            "RETURN v.name AS subject, type(r) AS predicate, c.name AS object,\n"
            "       c.value_min, c.value_max, c.unit, r.status, r.confidence\n"
            "ORDER BY r.confidence DESC\n"
            "LIMIT $k"
        ],
        warnings=[WARN_SINGLE_SOURCE],
        llm_meta={"stub": True, "note": "app.qa 未就绪，UI 内置演示桩返回", "model": None},
    )


def _call_store_factory(factory: Any, settings: Any) -> Any:
    """兼容 get_store(settings) / get_store() / get_store(settings, **kw) 等工厂签名。"""
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return factory(settings)
    takes_settings = "settings" in signature.parameters
    required = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]
    if settings is not None and takes_settings:
        return factory(settings)
    if required:
        return factory(settings)
    return factory()


def _build_runtime() -> Runtime:
    errors: List[str] = []
    settings: Any = None
    store: Any = None
    store_name = "stub"
    answer_question: Any = None

    try:
        from app.config import load_settings

        settings = load_settings()
    except Exception as exc:
        errors.append(f"app.config 加载失败：{type(exc).__name__}: {exc}")

    try:
        from app.store import get_store

        produced = _call_store_factory(get_store, settings)
        if isinstance(produced, tuple):
            store = produced[0] if produced else None
            if len(produced) > 1:
                errors.append("store 工厂备注：" + " / ".join(str(x) for x in produced[1:]))
        else:
            store = produced
        if store is None:
            raise RuntimeError("get_store() 返回 None")
        if not hasattr(store, "stats"):
            raise RuntimeError("store 缺少 stats() 方法")
        store_name = str(getattr(store, "name", "local"))
    except Exception as exc:
        errors.append(f"app.store 初始化失败：{type(exc).__name__}: {exc}")
        store = StubStore()
        store_name = "stub"

    try:
        from app.qa import answer_question as qa_answer_question

        answer_question = qa_answer_question
    except Exception as exc:
        errors.append(f"app.qa 导入失败：{type(exc).__name__}: {exc}")

    ready = answer_question is not None and not isinstance(store, StubStore)
    if answer_question is not None and isinstance(store, StubStore):
        errors.append("问答模块已导入但图谱后端未就绪：UI 仍使用演示桩答案。")
    return Runtime(
        ready=ready,
        settings=settings,
        store=store,
        answer_question=answer_question,
        store_name=store_name,
        errors=errors,
    )


@st.cache_resource(show_spinner=False)
def load_runtime() -> Runtime:
    return _build_runtime()


def _call_supported(func: Any, *args: Any, **kwargs: Any) -> Any:
    """按函数签名过滤 kwargs，避免 qa 签名细节变化直接炸 UI。"""
    try:
        signature = inspect.signature(func)
        parameters = signature.parameters
        accepts_var_kw = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
        if not accepts_var_kw:
            kwargs = {key: value for key, value in kwargs.items() if key in parameters}
    except (TypeError, ValueError):
        pass
    return func(*args, **kwargs)


def _ask(
    runtime: Runtime,
    question: str,
    *,
    topk: int,
    allow_llm: bool,
) -> Tuple[Optional[AnswerResult], Optional[str]]:
    """只调用一次 qa.answer_question；异常交给 UI 友好提示，绝不向上抛。"""
    if not runtime.ready or runtime.answer_question is None:
        return build_stub_result(question), None
    try:
        result = _call_supported(
            runtime.answer_question,
            question,
            store=runtime.store,
            llm=None,
            k=topk,
            allow_llm=allow_llm,
            steps=True,
            settings=runtime.settings,
        )
        if isinstance(result, AnswerResult):
            return result, None
        if hasattr(result, "answer") and hasattr(result, "evidence"):
            return result, None  # 兼容未来同字段实现
        raise TypeError(f"answer_question 返回类型不支持：{type(result).__name__}")
    except Exception:
        return None, traceback.format_exc()


# ---------------------------------------------------------------- 样式


BASE_CSS = """<style>
:root {
  --grape-green: #2e7d32;
  --grape-deep: #1b5e20;
  --grape-soft: #e8f5e9;
  --grape-line: #c8e6c9;
}
.block-container { padding-top: 1.5rem; padding-bottom: 2.5rem; }
.grape-sub { color: var(--text-color, #455a45); opacity: .8; font-size: .95rem; margin: -.4rem 0 .5rem; }
.badge-row, .chip-row, .stat-row { display: flex; flex-wrap: wrap; gap: .4rem; margin: .3rem 0 .7rem; }
.badge { display: inline-flex; align-items: center; gap: .25rem; padding: .18rem .6rem; border-radius: 999px; font-size: .85rem; font-weight: 600; color: var(--grape-deep); background: var(--grape-soft); border: 1px solid var(--grape-line); }
.badge-muted { color: #37474f; background: #eceff1; border-color: #cfd8dc; }
.badge-llm { color: #4527a0; background: #ede7f6; border-color: #d1c4e9; }
.badge-warn { color: #e65100; background: #fff3e0; border-color: #ffe0b2; }
.chip { display: inline-block; padding: .14rem .55rem; border-radius: .4rem; font-size: .82rem; background: #f1f8e9; border: 1px solid #dcedc8; color: #33691e; }
.chip b { color: var(--grape-deep); }
.chip-dim { color: #7b8a6f; margin-left: .3rem; font-size: .75rem; }
.stat-chip { display: inline-block; padding: .16rem .5rem; border-radius: .4rem; font-size: .82rem; background: #f5f5f5; border: 1px solid #e0e0e0; color: #37474f; }
.stat-chip b { color: var(--grape-deep); font-size: .9rem; }
.eid-badge { display: inline-block; font-size: .7em; line-height: 1.35; padding: 0 .32em; margin: 0 .1em; border-radius: .35em; background: #fff59d; color: #5d4037; border: 1px solid #fbc02d; vertical-align: .3em; font-weight: 700; }
.eid-badge.muted { background: #eeeeee; color: #757575; border-color: #bdbdbd; }
.warn-bar { padding: .55rem .8rem; border-radius: .5rem; margin: .35rem 0; border-left: 5px solid; font-size: .92rem; }
.warn-amber { background: #fff8e1; border-color: #f9a825; color: #5d4037; }
.warn-red { background: #ffebee; border-color: #c62828; color: #b71c1c; }
.warn-gray { background: #f5f5f5; border-color: #9e9e9e; color: #424242; }
.warn-blue { background: #e3f2fd; border-color: #1565c0; color: #0d47a1; }
.warn-code { font-family: ui-monospace, Consolas, monospace; font-size: .76rem; opacity: .75; margin-left: .45rem; }
.ev-card { border: 1px solid #dbe8dc; border-left: 5px solid #a5d6a7; border-radius: .55rem; padding: .5rem .75rem; margin: .4rem 0; background: #fbfdfb; color: #1f2a1f; }
.ev-card.cited { border-left-color: var(--grape-green); }
.ev-card.uncited { opacity: .62; border-left-color: #bdbdbd; background: #fafafa; }
.ev-head { font-weight: 600; font-size: 1rem; }
.ev-pred { color: var(--grape-green); font-family: ui-monospace, Consolas, monospace; font-size: .85em; margin: 0 .2rem; }
.ev-val { color: var(--grape-deep); font-weight: 700; margin-left: .35rem; }
.ev-meta { font-size: .82rem; color: #455a64; margin-top: .15rem; }
.ev-loc { font-size: .78rem; color: #78909c; margin-top: .1rem; }
.ev-quote { font-size: .82rem; color: #5d4037; margin-top: .15rem; font-style: italic; }
.ev-table { width: 100%; border-collapse: collapse; font-size: .88rem; }
.ev-table th, .ev-table td { border: 1px solid #e0e0e0; padding: .35rem .5rem; text-align: left; vertical-align: top; }
.ev-table th { background: #f1f8e9; color: #33691e; }
</style>"""

BIG_CSS = """<style>
html { font-size: 20px !important; }
[data-testid="stMarkdownContainer"] p, .stMarkdown p, [data-testid="stMarkdownContainer"] li, .stMarkdown li { font-size: 1.15rem !important; line-height: 1.9 !important; color: var(--text-color, inherit); }
[data-testid="stMarkdownContainer"] strong, .stMarkdown strong { font-weight: 750; }
[data-testid="stMarkdownContainer"] td, [data-testid="stMarkdownContainer"] th { font-size: 1.05rem !important; line-height: 1.7 !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p, [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li { font-size: 1.05rem !important; line-height: 1.75 !important; }
[data-testid="stSidebar"] label { font-size: 1.05rem !important; }
.stTextInput input { font-size: 1.2rem !important; }
.stButton button, .stFormSubmitButton button { min-height: 3rem; font-size: 1.05rem !important; }
[data-testid="stCaptionContainer"], .stCaption { font-size: 1rem !important; line-height: 1.7 !important; }
[data-testid="stMetricValue"] { font-size: 1.8rem !important; }
[data-testid="stTable"] table { font-size: 1.05rem !important; }
[data-testid="stTable"] th, [data-testid="stTable"] td { padding: .5rem .65rem !important; line-height: 1.6 !important; }
.ev-head { font-size: 1.18rem; }
.ev-meta { font-size: 1rem; }
.ev-loc, .ev-quote { font-size: .95rem; }
.warn-bar { font-size: 1.05rem; line-height: 1.7; }
.badge, .chip, .stat-chip { font-size: .95rem; }
</style>"""


# ---------------------------------------------------------------- 渲染：通用


def render_top_badges(runtime: Runtime, last_result: Optional[AnswerResult], offline: bool) -> None:
    backend = resolve_backend(runtime.settings, runtime.store_name)
    backend_text = {"local": "local（内存图谱）", "neo4j": "neo4j（图数据库）"}.get(backend, backend)
    backend_class = "badge badge-warn" if backend == "stub" else "badge"
    model = resolve_model(runtime.settings)
    key_ok = _llm_key_configured(runtime)
    model_text = f"{model}（{'已配置 Key' if key_ok else '未配置 Key → 模板'}）"
    mode = getattr(last_result, "mode", None)
    if mode == "llm":
        mode_text, mode_class = "llm（DeepSeek 生成）", "badge badge-llm"
    elif mode == "template":
        mode_text, mode_class = "template（离线模板）", "badge badge-muted"
    else:
        mode_text, mode_class = ("template（离线模板）" if not key_ok else "待提问"), "badge badge-muted"
    badges = [
        f'<span class="{backend_class}">🔌 后端：{_esc(backend_text)}</span>',
        f'<span class="badge badge-llm">🤖 模型：{_esc(model_text)}</span>',
        f'<span class="{mode_class}">🧩 模式：{_esc(mode_text)}</span>',
    ]
    if offline:
        badges.append('<span class="badge badge-warn">📴 离线演示</span>')
    if not runtime.ready:
        badges.append('<span class="badge badge-warn">🧪 演示桩模式</span>')
    st.markdown('<div class="badge-row">' + "".join(badges) + "</div>", unsafe_allow_html=True)


def _render_stats(runtime: Runtime) -> None:
    stats: Dict[str, Any] = {}
    try:
        if runtime.store is not None and hasattr(runtime.store, "stats"):
            produced = runtime.store.stats()
            if isinstance(produced, dict):
                stats = produced
    except Exception as exc:
        st.caption(f"图谱统计不可用：{type(exc).__name__}: {exc}")
        return
    if not stats:
        st.caption("图谱统计不可用（后端未就绪）")
        return
    items = []
    data_files: List[str] = []
    for key, value in stats.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, (list, tuple, set)):
            if str(key) == "data_files":
                data_files = [str(item) for item in value]
            continue
        if isinstance(value, dict):
            continue
        label = STAT_LABELS.get(str(key), str(key))
        items.append(f'<span class="stat-chip">{_esc(label)} <b>{_esc(value)}</b></span>')
    if not items:
        st.caption("图谱统计为空（数据未就绪）")
        return
    st.markdown('<div class="stat-row">' + "".join(items) + "</div>", unsafe_allow_html=True)
    if data_files:
        st.caption("数据文件：" + "、".join(data_files))
    if not stats.get("_data_ready", True):
        st.caption("data/ 尚未产出，统计为 0（演示桩模式）。")


def _render_vocab() -> None:
    varieties, diseases, origin = load_vocab()
    st.markdown(f"**品种（{len(varieties)}）**")
    st.caption(" / ".join(varieties))
    st.markdown(f"**病害（{len(diseases)}）**")
    st.caption(" / ".join(diseases))
    if origin != "csv":
        st.caption("⚠️ data/entities.csv 未就绪，以上为 spec 预置词表。")


# ---------------------------------------------------------------- 渲染：答案


def _render_md(text: str, cited_ids: Sequence[str]) -> str:
    """把 [E#] 渲染为小角标高亮（保留原 Markdown 文本，不改写答案）。"""
    if not text:
        return ""
    safe = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    cited = {str(item) for item in (cited_ids or [])}

    def _replace(match: re.Match) -> str:
        eid = match.group(1)
        muted = "" if eid in cited else " muted"
        return f'<sup class="eid-badge{muted}" title="证据 {eid}">{eid}</sup>'

    return _EID_RE.sub(_replace, safe)


def _find_heading(text: str, names: Sequence[str]) -> Optional[re.Match]:
    """定位行首小节标题（如「依据：」「现在该做什么：」，兼容 **加粗** 与 ### 标题）。"""
    joined = "|".join(re.escape(name) for name in names)
    pattern = re.compile(
        r"(?m)^[ \t>*#\-•·]*(?:\*\*)?[ \t]*(?:" + joined + r")[ \t]*(?:\*\*)?[ \t]*(?:[：:]|$)"
    )
    return pattern.search(text)


def _find_heading_inline(text: str, names: Sequence[str]) -> Optional[re.Match]:
    """兜底：小节标题与正文挤在同一行时，按「标题＋冒号」定位。"""
    joined = "|".join(re.escape(name) for name in names)
    pattern = re.compile(r"(?:" + joined + r")[ \t]*(?:\*\*)?[ \t]*[：:]")
    return pattern.search(text)


_EVIDENCE_HEADINGS = ("依据", "证据依据", "参考依据", "支撑证据")
_ACTION_HEADINGS = (
    "现在该做什么",
    "现在该怎么做",
    "现在怎么做",
    "建议这样做",
    "操作建议",
    "行动建议",
    "下一步",
)


def _strip_action_tail(text: str) -> str:
    """仅控制显示：正文里若仍带「现在该做什么：」段，截断它（不修改 AnswerResult.answer）。"""
    if not text:
        return text
    marker = _find_heading(text, _ACTION_HEADINGS) or _find_heading_inline(text, _ACTION_HEADINGS)
    if marker is None:
        return text
    return text[: marker.start()].rstrip()


def _split_answer(answer: str) -> Tuple[str, str, str]:
    """把 answer 拆成（结论, 依据段, 行动段）。只做版面分段，不改写原始 answer。"""
    text = (answer or "").strip()
    if not text:
        return "", "", ""
    evidence_match = _find_heading(text, _EVIDENCE_HEADINGS) or _find_heading_inline(
        text, _EVIDENCE_HEADINGS
    )
    action_match = _find_heading(text, _ACTION_HEADINGS) or _find_heading_inline(
        text, _ACTION_HEADINGS
    )
    markers: List[Tuple[str, re.Match]] = []
    if evidence_match is not None:
        markers.append(("evidence", evidence_match))
    if action_match is not None:
        markers.append(("action", action_match))
    markers.sort(key=lambda item: item[1].start())
    conclusion = text[: markers[0][1].start()].strip() if markers else text
    evidence_text = ""
    action_text = ""
    for index, (kind, match) in enumerate(markers):
        end = markers[index + 1][1].start() if index + 1 < len(markers) else len(text)
        body = text[match.end() : end].strip()
        if kind == "evidence":
            evidence_text = body
        else:
            action_text = body
    stripped = re.sub(
        r"^[ \t>*#\-]*(?:\*\*)?[ \t]*结论[ \t]*(?:\*\*)?[ \t]*[：:][ \t]*", "", conclusion
    ).strip()
    if stripped:
        conclusion = stripped
    return conclusion, evidence_text, action_text


# ---------------------------------------------------------------- 最近 5 轮历史


HISTORY_LIMIT = 5


def _conclusion_preview(result: AnswerResult, limit: int = 88) -> str:
    """历史条目用的一句话结论（仅预览，不修改原答案）。"""
    conclusion, _, _ = _split_answer(str(getattr(result, "answer", "") or ""))
    text = re.sub(r"[*`#>]", "", conclusion).replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _history_append(result: AnswerResult, meta: Dict[str, Any]) -> None:
    history = list(st.session_state.get("history") or [])
    history.insert(
        0,
        {
            "question": str(getattr(result, "question", "")),
            "conclusion": _conclusion_preview(result),
            "evidence_count": len(list(getattr(result, "evidence", []) or [])),
            "cited_count": len(list(getattr(result, "cited_ids", []) or [])),
            "mode": str(getattr(result, "mode", "template")),
            "intent": str(getattr(result, "intent", "")),
            "topk": meta.get("topk"),
            "offline": meta.get("offline"),
            "result": result,
        },
    )
    st.session_state["history"] = history[:HISTORY_LIMIT]


def render_history() -> None:
    """主区底部：最近 5 轮问答折叠区；「回看」直接复用已存 AnswerResult，不重跑问答。"""
    history = list(st.session_state.get("history") or [])
    with st.expander(f"🕘 历史记录（最近 {len(history)} 轮，最多保留 {HISTORY_LIMIT} 轮）", expanded=False):
        if not history:
            st.caption("暂无历史记录：提出一个问题后会自动保存最近 5 轮问答。")
            return
        st.caption("点击「回看」可直接展示该轮结果（结果会显示在页面上方，不重新调用问答管线）。")
        for index, entry in enumerate(history):
            question = str(entry.get("question", ""))
            columns = st.columns([6, 2, 1])
            with columns[0]:
                st.markdown(f"**{index + 1}. {_esc(question)}**", unsafe_allow_html=True)
                st.caption(str(entry.get("conclusion", "")) or "（无结论预览）")
            with columns[1]:
                st.caption(
                    f"证据 {entry.get('evidence_count', 0)} 条 · 引用 {entry.get('cited_count', 0)} 条"
                )
                st.caption(f"mode {entry.get('mode', 'template')} · Top-K {entry.get('topk', '—')}")
            with columns[2]:
                if st.button("回看", key=f"history_view_{index}", use_container_width=True):
                    st.session_state["last_result"] = entry.get("result")
                    st.session_state["last_meta"] = {
                        "topk": entry.get("topk"),
                        "offline": entry.get("offline"),
                        "history": True,
                        "round": index + 1,
                    }
                    _rerun()
            if index < len(history) - 1:
                st.divider()


def _order_evidence(evidence: Sequence[Evidence], cited_ids: Sequence[str]) -> List[Evidence]:
    """被引用的证据在前（按 cited_ids 顺序），其余按原顺序；未引用卡片灰显。"""
    ordered: List[Evidence] = []
    seen: set = set()
    by_eid: Dict[str, Evidence] = {}
    for ev in evidence:
        eid = _eid_of(ev)
        if eid not in by_eid:
            by_eid[eid] = ev
    for eid in cited_ids or []:
        ev = by_eid.get(str(eid))
        if ev is not None and _eid_of(ev) not in seen:
            ordered.append(ev)
            seen.add(_eid_of(ev))
    for ev in evidence:
        eid = _eid_of(ev)
        if eid not in seen:
            ordered.append(ev)
            seen.add(eid)
    return ordered


def _evidence_cards_html(ordered: Sequence[Evidence], cited_set: set) -> str:
    parts: List[str] = []
    for ev in ordered:
        eid = _eid_of(ev)
        cited = eid in cited_set
        card_class = "ev-card cited" if cited else "ev-card uncited"
        badge_class = "eid-badge" if cited else "eid-badge muted"
        predicate = PREDICATE_LABELS.get(str(ev.predicate), str(ev.predicate))
        value = _fmt_value(ev)
        if ev.source_titles:
            sources = "；".join(str(title) for title in ev.source_titles)
        elif ev.source_ids:
            sources = "；".join(str(source) for source in ev.source_ids)
        else:
            sources = "—"
        status = "已核验" if str(ev.status) == "verified" else "待核验"
        head = (
            f'<span class="{badge_class}">{_esc(eid)}</span>'
            f"<b>{_esc(ev.subject)}</b>"
            f'<span class="ev-pred">{_esc(predicate)}</span>'
            f"<b>{_esc(ev.object)}</b>"
        )
        if value:
            head += f'<span class="ev-val">{_esc(value)}</span>'
        location = f'<div class="ev-loc">定位：{_esc(ev.locator)}</div>' if ev.locator else ""
        quote = f'<div class="ev-quote">“{_esc(ev.quote)}”</div>' if ev.quote else ""
        parts.append(
            f'<div class="{card_class}"><div class="ev-head">{head}</div>'
            f'<div class="ev-meta">来源：{_esc(sources)} · 状态：{status} · 置信 {_fmt_conf(ev.confidence)}</div>'
            f"{location}{quote}</div>"
        )
    return "".join(parts)


def _table_rows(ordered: Sequence[Evidence]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for ev in ordered:
        predicate = PREDICATE_LABELS.get(str(ev.predicate), str(ev.predicate))
        if ev.source_titles:
            sources = "；".join(str(title) for title in ev.source_titles)
        elif ev.source_ids:
            sources = "；".join(str(source) for source in ev.source_ids)
        else:
            sources = "—"
        rows.append(
            {
                "eid": _eid_of(ev),
                "三元组": f"{ev.subject} —{predicate}→ {ev.object}",
                "值": _fmt_value(ev) or "—",
                "来源": sources,
                "状态": "已核验" if str(ev.status) == "verified" else "待核验",
                "置信": _fmt_conf(ev.confidence),
            }
        )
    return rows


def _html_table(rows: Sequence[Dict[str, Any]]) -> str:
    headers = list(rows[0].keys())
    head_html = "".join(f"<th>{_esc(header)}</th>" for header in headers)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{_esc(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return f'<table class="ev-table"><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>'


def _render_evidence_table(ordered: Sequence[Evidence], cited_set: set, *, large: bool) -> None:
    st.markdown("#### 🧾 证据表（可溯源明细）")
    st.caption("列：eid / 三元组 / 值 / 来源 / 状态 / 置信。依据区灰色卡片 = 未被答案引用的证据。")
    rows = _table_rows(ordered)
    if not rows:
        st.caption("本次无证据可列。")
        return
    if large:
        try:
            import pandas as pd

            st.table(pd.DataFrame(rows))
            return
        except Exception:
            pass
    try:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    except Exception:
        try:
            st.dataframe(rows)
        except Exception:
            st.markdown(_html_table(rows), unsafe_allow_html=True)


def _classify_warning(raw: Any) -> Tuple[str, str, str, str]:
    text = str(raw)
    code = text.split(":", 1)[0].strip()
    detail = text.split(":", 1)[1].strip() if ":" in text else ""
    known: Dict[str, Tuple[str, str, str]] = {
        WARN_OUT_OF_RANGE: ("amber", "数值越界", "答案中的数值超出证据给出的区间，请以证据表为准"),
        WARN_NO_EVIDENCE: ("red", "无证据", "本次未检索到图谱证据，答案仅作澄清提示"),
        WARN_SINGLE_SOURCE: ("gray", "单来源证据", "部分证据仅有一个来源，结论需谨慎采纳"),
        WARN_NO_CITATION: ("amber", "引用校验未通过", "答案引用未能与证据对应，已降级为模板答案"),
        WARN_LLM_TIMEOUT: ("amber", "模型超时", "大模型调用超时，已降级为离线模板答案"),
        WARN_LLM_UNAVAILABLE: ("amber", "模型不可用", "未配置或无法连接 DeepSeek，已使用离线模板"),
        WARN_BACKEND_FALLBACK: ("blue", "后端回落", "图数据库不可用，已自动回落本地内存图谱"),
        WARN_LOW_CONFIDENCE_INTENT: ("blue", "意图低置信", "问题意图不够明确，答案可能偏离，请补充品种/条件"),
    }
    if code.startswith("unsourced_number"):
        message = detail or "答案中的数值未能对应到证据来源"
        return "amber", "无来源数值", message, code
    if code in known:
        level, title, default_message = known[code]
        return level, title, detail or default_message, code
    return "gray", code or "告警", detail or text, code


def _render_warnings(warnings: Sequence[str]) -> None:
    for raw in warnings or []:
        level, title, message, code = _classify_warning(raw)
        st.markdown(
            f'<div class="warn-bar warn-{level}"><b>{_esc(title)}</b>：{_esc(message)}'
            f'<span class="warn-code">{_esc(code)}</span></div>',
            unsafe_allow_html=True,
        )


def _render_chip_row(result: AnswerResult) -> None:
    chips: List[str] = []
    intent = str(getattr(result, "intent", "") or "")
    if intent:
        labels = INTENT_LABELS.get(intent, intent)
        chips.append(f'<span class="chip">意图 <b>{_esc(labels)}</b><span class="chip-dim">{_esc(intent)}</span></span>')
    try:
        chips.append(f'<span class="chip">意图置信 {float(getattr(result, "intent_confidence", 0.0) or 0.0):.2f}</span>')
    except (TypeError, ValueError):
        pass
    for hit in list(getattr(result, "entities", []) or [])[:8]:
        surface = getattr(hit, "surface", "") or getattr(hit, "node_id", "")
        label = getattr(hit, "label", "")
        chips.append(f'<span class="chip">{_esc(surface)}<span class="chip-dim">{_esc(label)}</span></span>')
    if chips:
        st.markdown('<div class="chip-row">' + "".join(chips) + "</div>", unsafe_allow_html=True)


def render_result(result: AnswerResult, *, show_cypher: bool, large: bool) -> None:
    st.markdown("---")
    st.markdown(f"#### 🙋 问题：{_esc(getattr(result, 'question', ''))}", unsafe_allow_html=True)
    mode = str(getattr(result, "mode", "template") or "template")
    if mode == "llm":
        mode_html = '<span class="badge badge-llm">🤖 llm（DeepSeek 生成）</span>'
    else:
        mode_html = '<span class="badge badge-muted">🧩 template（离线模板）</span>'
    try:
        elapsed = int(getattr(result, "elapsed_ms", 0) or 0)
    except (TypeError, ValueError):
        elapsed = 0
    st.markdown(
        f'<div class="badge-row">{mode_html}<span class="badge badge-muted">⏱ 耗时 {elapsed} ms</span></div>',
        unsafe_allow_html=True,
    )
    _render_chip_row(result)
    _render_warnings(list(getattr(result, "warnings", []) or []))

    cited_ids = [str(item) for item in (getattr(result, "cited_ids", []) or [])]
    cited_set = set(cited_ids)
    evidence = list(getattr(result, "evidence", []) or [])
    ordered = _order_evidence(evidence, cited_ids)
    conclusion, evidence_text, action_text = _split_answer(str(getattr(result, "answer", "") or ""))
    steps = list(getattr(result, "steps", []) or [])
    # 防重复渲染：answer 里若仍残留「现在该做什么」段，而 steps 列表也要渲染，
    # 则只在显示层截断 answer 里的该段（不改写 result.answer 原文）。
    if steps:
        conclusion = _strip_action_tail(conclusion)

    st.markdown("#### 🧠 结论")
    if conclusion.strip():
        st.markdown(_render_md(conclusion, cited_ids), unsafe_allow_html=True)
    else:
        st.caption("（答案缺少结论段落）")

    cited_count = sum(1 for ev in ordered if _eid_of(ev) in cited_set)
    st.markdown(f"#### 📚 依据（共 {len(ordered)} 条证据 · 答案引用 {cited_count} 条）")
    if ordered:
        st.markdown(_evidence_cards_html(ordered, cited_set), unsafe_allow_html=True)
    elif evidence_text:
        st.markdown(_render_md(evidence_text, cited_ids), unsafe_allow_html=True)
    else:
        st.caption("本次未检索到图谱证据。")

    st.markdown("#### ✅ 现在该做什么")
    if steps:
        lines = [f"{index}. {_render_md(str(step), cited_ids)}" for index, step in enumerate(steps, 1)]
        st.markdown("\n".join(lines), unsafe_allow_html=True)
    elif action_text:
        st.markdown(_render_md(action_text, cited_ids), unsafe_allow_html=True)
    else:
        st.caption("本次回答未给出操作步骤。")

    if ordered:
        _render_evidence_table(ordered, cited_set, large=large)

    with st.expander("🔍 查询详情（Cypher / 耗时 / 模型元信息）", expanded=False):
        cols = st.columns(4)
        cols[0].metric("意图", INTENT_LABELS.get(str(getattr(result, "intent", "")), str(getattr(result, "intent", "") or "—")))
        try:
            cols[1].metric("意图置信", f"{float(getattr(result, 'intent_confidence', 0.0) or 0.0):.2f}")
        except (TypeError, ValueError):
            cols[1].metric("意图置信", "—")
        cols[2].metric("耗时", f"{elapsed} ms")
        cols[3].metric("证据数", len(evidence))
        st.markdown("**Cypher 查询**")
        cypher_list = list(getattr(result, "query_cypher", []) or [])
        if show_cypher:
            if cypher_list:
                for cypher in cypher_list:
                    st.code(str(cypher), language="text")
            else:
                st.caption("本次未返回 Cypher（本地内存后端或模板降级路径）。")
        else:
            st.caption("已在侧栏关闭 Cypher 显示。")
        st.markdown("**模型元信息（llm_meta）**")
        meta = getattr(result, "llm_meta", None)
        if isinstance(meta, dict) and meta:
            st.json(meta)
        else:
            st.caption("无（离线模板模式，未调用 DeepSeek）。")
        st.markdown("**原始告警码（warnings）**")
        st.code(json.dumps(list(getattr(result, "warnings", []) or []), ensure_ascii=False, indent=2), language="json")
        st.markdown("**证据条数**")
        st.caption(
            f"store 返回 {len(evidence)} 条 · 引用 {cited_count} 条 · "
            f"Top-K 上限以侧栏设置为准（本次提问时）。"
        )


# ---------------------------------------------------------------- 侧栏 / 主区


def _default_offline(runtime: Runtime) -> bool:
    if not runtime.ready:
        return True
    return not _llm_key_configured(runtime)


def _default_large(runtime: Runtime) -> bool:
    value = _setting(runtime.settings, ("ui_large_font", "UI_LARGE_FONT"), None)
    if value is not None:
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    return _env_bool("UI_LARGE_FONT", False)


def _default_topk(runtime: Runtime) -> int:
    value = _setting(runtime.settings, ("top_k", "topk", "UI_TOPK"), None)
    try:
        return max(3, min(10, int(value)))
    except (TypeError, ValueError):
        return max(3, min(10, _env_int("UI_TOPK", 6)))


def render_sidebar(runtime: Runtime) -> Dict[str, Any]:
    with st.sidebar:
        st.markdown("## 🍇 演示控制台")
        backend = resolve_backend(runtime.settings, runtime.store_name)
        model = resolve_model(runtime.settings)
        st.markdown(
            '<div class="badge-row">'
            f'<span class="badge">🔌 后端 {_esc(backend)}</span>'
            f'<span class="badge badge-llm">🤖 模型 {_esc(model)}</span>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "问答模块：✅ 已就绪" if runtime.ready else "问答模块：🧪 演示桩（未就绪，页面仍可用）"
        )
        st.divider()
        offline = st.checkbox(
            "离线模式（强制 allow_llm=False）",
            value=_default_offline(runtime),
            help="勾选后完全不调用 DeepSeek，仅用知识图谱模板作答。",
        )
        large = st.checkbox(
            "大字模式（1.25~1.5× 字号）",
            value=_default_large(runtime),
            help="放大字号、行高与对比度，适配种植户/冷库管理员现场演示。",
        )
        topk = st.slider(
            "证据条数 Top-K",
            min_value=3,
            max_value=10,
            value=_default_topk(runtime),
            step=1,
            help="传给 qa.answer_question 的证据上限。",
        )
        show_cypher = st.checkbox("显示 Cypher 查询", value=True, help="在「查询详情」中展示本次查询的 Cypher。")
        st.divider()
        st.markdown("### 📊 图谱统计")
        _render_stats(runtime)
        st.markdown("### 🏷️ 已收录词表")
        _render_vocab()
        st.divider()
        if st.button("🔄 重新加载后端", use_container_width=True):
            try:
                st.cache_resource.clear()
            except Exception:
                pass
            _rerun()
        st.caption("启动：streamlit run app/ui.py --server.port 8501 --server.headless true")
        st.caption("不占用 64480（DSH GUI）；本界面只渲染 AnswerResult。")
    return {
        "offline": bool(offline),
        "large": bool(large),
        "topk": int(topk),
        "show_cypher": bool(show_cypher),
    }


def _render_stub_notice(runtime: Runtime) -> None:
    if runtime.ready:
        return
    st.warning(
        "⚠️ 演示桩：问答模块尚未就绪 —— 页面可正常启动与交互，但答案来自内置演示桩，"
        "不代表系统真实结论。"
    )
    with st.expander("导入诊断（开发者）", expanded=False):
        st.code("\n".join(runtime.errors) or "未捕获到具体错误信息", language="text")


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🍇",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    runtime = load_runtime()
    config = render_sidebar(runtime)
    st.markdown(BASE_CSS + (BIG_CSS if config["large"] else ""), unsafe_allow_html=True)

    st.title(APP_TITLE)
    st.markdown(f'<div class="grape-sub">{_esc(APP_SUBTITLE)}</div>', unsafe_allow_html=True)
    render_top_badges(runtime, st.session_state.get("last_result"), config["offline"])
    _render_stub_notice(runtime)

    # 示例按钮点击后，把问题写回输入框并自动提问（在 widget 实例化之前写入）
    pending = st.session_state.pop("pending_question", None)
    if pending:
        st.session_state["question_input"] = pending
        st.session_state["auto_ask"] = pending
    st.session_state.setdefault("question_input", "")

    with st.form("ask_form", clear_on_submit=False):
        column_question, column_button = st.columns([5, 1])
        with column_question:
            typed = st.text_input(
                "请输入问题",
                key="question_input",
                placeholder="例如：阳光玫瑰放冷库该调到多少度？",
            )
        with column_button:
            st.markdown('<div style="height:1.75rem"></div>', unsafe_allow_html=True)
            submitted = st.form_submit_button("🔎 提问", type="primary", use_container_width=True)

    st.markdown("**💡 示例问题（点击即刻提问）**")
    for start in range(0, len(EXAMPLES), 3):
        columns = st.columns(3)
        for index in range(start, min(start + 3, len(EXAMPLES))):
            label, full_question = EXAMPLES[index]
            with columns[index - start]:
                if st.button(
                    label,
                    key=f"example_{index}",
                    use_container_width=True,
                    help=f"点击提问：{full_question}",
                ):
                    st.session_state["pending_question"] = full_question
                    _rerun()

    auto_question = st.session_state.pop("auto_ask", None)
    asked: Optional[str] = None
    if auto_question:
        asked = str(auto_question)
    elif submitted and typed and typed.strip():
        asked = typed.strip()

    if asked:
        with st.spinner("正在检索图谱证据并组织答案…"):
            result, error = _ask(
                runtime,
                asked,
                topk=config["topk"],
                allow_llm=not config["offline"],
            )
        if error:
            st.error("问答管线执行时发生异常，已捕获（页面保持可用）。")
            with st.expander("异常详情", expanded=True):
                st.code(error, language="text")
        elif result is not None:
            meta = {"topk": config["topk"], "offline": config["offline"], "history": False}
            st.session_state["last_result"] = result
            st.session_state["last_meta"] = meta
            _history_append(result, meta)

    last_result = st.session_state.get("last_result")
    if last_result is not None:
        last_meta = st.session_state.get("last_meta") or {}
        if last_meta.get("history"):
            st.info(
                f"📜 历史回看：第 {last_meta.get('round', '?')} 轮（直接复用已保存结果，未重新调用问答管线）。"
            )
        elif last_meta and (
            last_meta.get("topk") != config["topk"]
            or bool(last_meta.get("offline")) != bool(config["offline"])
        ):
            st.info("侧栏的 Top-K / 离线模式已变更：重新提问后生效（当前展示的是上一次结果）。")
        render_result(last_result, show_cypher=config["show_cypher"], large=config["large"])
    else:
        st.markdown("---")
        st.caption("👆 在上方输入问题，或点击任一示例问题开始。答案都会附带证据编号 [E1]、来源与操作步骤。")

    render_history()

    st.markdown("---")
    st.caption(
        "说明：本界面只渲染 `AnswerResult`，不自行调用 DeepSeek、不改写答案文本；"
        "全部结论可溯源至 `data/sources.csv` 中的来源。"
    )


if __name__ == "__main__":
    main()
