"""qa-tester 测试共享工具（只读使用 app/ 与 data/，不修改任何他人写区文件）。

设计原则
--------
- 路径一律从本文件位置推导，测试不依赖 ``cwd``。
- 期望值尽量从 ``data/*.csv`` 与 ``app/contracts.py`` 派生，避免硬编码漂移；
  spec.md 中冻结的 id/枚举才写常量。
- 数值校验类断言**独立实现**一份（不复用被测 ``qa.check_numbers``），
  避免「用被测实现验证被测实现」。
"""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
GRAPH = ROOT / "graph"
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"

# ---------------------------------------------------------------- 文件 / CSV
def read_csv(path: Path | str) -> List[Dict[str, str]]:
    """读 UTF-8（容忍 BOM）CSV，返回 dict 行列表。相对路径按 ``data/`` 解析。"""
    target = Path(path)
    if not target.is_absolute():
        target = DATA / target
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def csv_header(path: Path | str) -> List[str]:
    target = Path(path)
    if not target.is_absolute():
        target = DATA / target
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def read_text(path: Path | str) -> str:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    return target.read_text(encoding="utf-8-sig")


def split_ids(value: Any) -> List[str]:
    """``"a;b"`` / ``"a；b"`` → ``["a", "b"]``（api.md §1.5 分号分隔）。"""
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[;；]", text) if part.strip()]


def split_keywords(value: Any) -> List[str]:
    """忽略大小写与空白的弱关键词比较用列表。"""
    return [item.strip().lower() for item in split_ids(value)]


# ---------------------------------------------------------------- app 侧构造
def make_local_store(data_dir: Path | str | None = None):
    """按 docs/api.md §5 构造本地后端：``LocalStore(data_dir)``。"""
    from app.store.local_store import LocalStore

    return LocalStore(str(data_dir or DATA))


_catalog_cache: Dict[str, Any] = {}


def get_catalog():
    """``load_catalog(entities.csv)`` 结果按路径缓存（只读，可跨用例复用）。"""
    from app.linking import load_catalog

    key = str(DATA / "entities.csv")
    if key not in _catalog_cache:
        _catalog_cache[key] = load_catalog(key)
    return _catalog_cache[key]


def link(question: str, *, max_hits: int = 8):
    """``link_entities(question, catalog, max_hits=...)`` 的便捷封装。"""
    from app.linking import link_entities

    return list(link_entities(question, get_catalog(), max_hits=max_hits))


def hit_ids(hits: Iterable[Any]) -> List[str]:
    return [str(getattr(hit, "node_id", "")) for hit in hits]


def make_evidence(**overrides: Any):
    """构造合成 :class:`app.contracts.Evidence`（单测 check_numbers 用，不读数据）。"""
    from app.contracts import Evidence

    payload = dict(
        eid="E1",
        subject="阳光玫瑰",
        predicate="REQUIRES",
        object="低温冷藏 0±0.5℃",
        value=None,
        unit="℃",
        value_min=-0.5,
        value_max=0.5,
        source_ids=["gbt16862_2026"],
        source_titles=["GB/T 16862-2026 鲜食葡萄冷藏技术"],
        locator="4.2 冷藏温度",
        quote="冷藏温度宜控制在 0±0.5 ℃",
        status="verified",
        confidence=0.9,
    )
    payload.update(overrides)
    return Evidence(**payload)


# ---------------------------------------------------------------- 答案文本工具
EID_REF_RE = re.compile(r"\[(E\d+)\]")


def cited_refs(text: str) -> List[str]:
    """答案正文中出现的 ``[E#]`` 引用编号（去重保序）。"""
    seen: List[str] = []
    for eid in EID_REF_RE.findall(str(text or "")):
        if eid not in seen:
            seen.append(eid)
    return seen


def _normalize_text(text: Any) -> str:
    """NFKC 归一（全角→半角、全角数字/符号），便于关键词与温度抽取。"""
    return unicodedata.normalize("NFKC", str(text or ""))


_NUM = r"-?\d+(?:\.\d+)?"
# 支持 "0±0.5℃" / "-1~0℃" / "-18.0 ℃" / "3.5度" / "零下18度"
_TEMP_RE = re.compile(
    rf"({_NUM})\s*(?:±\s*({_NUM}))?\s*(?:[~～]|至|到|-)?\s*({_NUM})?\s*(?:℃|°C|摄氏度|度)"
)
_NEG_MARKERS = (
    "不宜",
    "不要",
    "不能",
    "不可",
    "不应",
    "禁止",
    "切勿",
    "避免",
    "严禁",
    "不推荐",
    "别",
    "非",
)


def temperatures_in(text: str, *, skip_negated: bool = False) -> List[float]:
    """抽取文本中的温度数值（含 ``±`` 的上偏差与区间两端）。"""
    normalized = _normalize_text(text)
    values: List[float] = []
    for match in _TEMP_RE.finditer(normalized):
        if skip_negated:
            prefix = normalized[max(0, match.start() - 10) : match.start()]
            if any(marker in prefix for marker in _NEG_MARKERS):
                continue
        for group in match.groups():
            if group:
                try:
                    values.append(float(group))
                except ValueError:
                    continue
    return values


def evidence_temperature_intervals(evidence: Sequence[Any]) -> List[Tuple[float, float]]:
    """从证据推导「允许出现的温度区间」：优先结构化 value_min/max，其次 value，再次文本。"""
    intervals: List[Tuple[float, float]] = []
    for item in evidence:
        unit = _normalize_text(getattr(item, "unit", "") or "")
        blob = _normalize_text(
            " ".join(
                [
                    str(getattr(item, "subject", "") or ""),
                    str(getattr(item, "object", "") or ""),
                    str(getattr(item, "quote", "") or ""),
                ]
            )
        )
        looks_temperature = (
            "℃" in unit
            or "°C" in unit
            or "摄氏" in unit
            or "℃" in blob
            or "温度" in blob
            or "冷藏" in blob
            or "冰温" in blob
        )
        if not looks_temperature:
            continue
        low = getattr(item, "value_min", None)
        high = getattr(item, "value_max", None)
        single = getattr(item, "value", None)
        if low is not None and high is not None:
            intervals.append((float(low), float(high)))
        elif single is not None:
            intervals.append((float(single), float(single)))
        else:
            values = temperatures_in(blob)
            if len(values) >= 2:
                intervals.append((min(values), max(values)))
            elif values:
                intervals.append((values[0], values[0]))
    return intervals


def unsupported_temperatures(answer: str, evidence: Sequence[Any]) -> List[float]:
    """返回答案中「无法被证据温度区间支撑」的温度数值（独立于 qa.check_numbers）。

    遇到「不宜零下18度」这类否定语境的数值会跳过（否定陈述不是推荐值）。
    """
    intervals = evidence_temperature_intervals(evidence)
    unsupported: List[float] = []
    for value in temperatures_in(answer, skip_negated=True):
        if not any(low - 1e-6 <= value <= high + 1e-6 for low, high in intervals):
            unsupported.append(value)
    return unsupported


def keyword_present(keyword: str, answer: str, evidence: Sequence[Any]) -> bool:
    """弱关键词断言：答案或证据文本命中即可（LLM 自由文本不做强断言）。"""
    needle = str(keyword or "").strip().lower()
    if not needle:
        return True
    haystack = (str(answer or "") + "\n" + evidence_blob(evidence)).lower()
    return needle in haystack


def evidence_blob(evidence: Sequence[Any]) -> str:
    parts: List[str] = []
    for item in evidence:
        parts.extend(
            [
                str(getattr(item, "eid", "") or ""),
                str(getattr(item, "subject", "") or ""),
                str(getattr(item, "predicate", "") or ""),
                str(getattr(item, "object", "") or ""),
                str(getattr(item, "unit", "") or ""),
                " ".join(str(title) for title in (getattr(item, "source_titles", None) or [])),
                str(getattr(item, "quote", "") or ""),
            ]
        )
    return "\n".join(parts)


# ---------------------------------------------------------------- 黄金集
def load_utterances() -> List[Dict[str, str]]:
    return read_csv("utterances.csv")


def load_eval_questions() -> List[Dict[str, str]]:
    return read_csv("eval_questions.csv")


def row_param_id(row: Dict[str, str], id_field: str = "id") -> str:
    return str(row.get(id_field) or "?").strip()
