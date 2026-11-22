"""实体链接（``docs/api.md`` §3，store-builder 写区）。

流程：``data/entities.csv`` → 词表 Catalog → 在问句里做**最长匹配** → ``list[EntityHit]``。

规则（冻结）
------------
- 词表只来自 CSV（``name`` + ``aliases``，外加 Disease 的 ``symptom`` 口语症状词），
  **不写死任何实体名**；
- 预处理：全角 ASCII 转半角、下标/上标数字转 ASCII、去空白/标点、去语气词（啊/呢/吧/吗/呗/呀）；
- 最长匹配优先（"香印青提" 命中 ``shine_muscat`` 后不会再单独命中 "青提"），
  命中区间互不重叠（扫描时从起点向左到右、同起点取最长、命中后跳过整个区间）；
- **拉丁词边界**：纯拉丁/数字别名若左/右紧邻另一个拉丁字母或数字，视为词内误命中丢弃
  （"SO2"/"CO2" 里的 "O2" 不会命中 ``ca_o2``；详见 :func:`_latin_boundary_ok`）；
- 同一 ``node_id`` 多处命中只保留 score 最高的一条；
- 不做拼音 / 编辑距离（不在本期范围）。
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # 兼容 `python app/ui.py`（sys.path[0] 为 app/）
    from app.contracts import EntityHit
except ImportError:  # pragma: no cover
    from contracts import EntityHit  # type: ignore[no-redef]

__all__ = [
    "Catalog",
    "CatalogEntry",
    "LINKABLE_LABELS",
    "load_catalog",
    "link_entities",
    "normalize_text",
    "FACILITY_TERMS",
]

# 只有这四类节点参与问答实体链接（Source 不参与）
LINKABLE_LABELS = ("Variety", "Condition", "QualityIndicator", "Disease")

# 语气词（问句尾部常见，去掉后再匹配）
PARTICLES = "啊呢吧吗呗呀"

# 分词用的分隔符（名称里附带数值/单位时会切出中文名词段）
_SEGMENT_SPLIT = re.compile(r"[\s、，,；;/|·•~～\-—()（）\[\]【】<>《》“”\"'’]+")

# 词表条目权重：规范名 > 别名 > 连续中文片段 > 名称切段 > 病害口语症状
WEIGHT_CANONICAL = 1.0
WEIGHT_ALIAS = 0.92
WEIGHT_RUN = 0.82
WEIGHT_SEGMENT = 0.85
WEIGHT_SYMPTOM = 0.80

# 设施/场景词：只作为问句上下文，不绑定到某个具体温度条件（避免「冷库湿度」被 cold_0 劫持）。
FACILITY_TERMS = frozenset({"冷库", "冷藏库", "冷藏", "库房", "保鲜库", "气调库"})

# 代码层补充的同义词（不修改 data/entities.csv；只补明确、低歧义的词）。
# 模糊词（保鲜剂/防腐剂/出库/运输/分级/采后等）不绑定实体，由 planner 的 topic 识别处理。
EXTRA_ALIASES: dict[str, str] = {
    "SO2": "so2_fumigation",
    "SO₂": "so2_fumigation",
    "1MCP": "mcp_1",
    "潮气": "rh_90_95",
    "发软": "firmness",
    "软化": "firmness",
    "包装": "package_weight",
    "保鲜袋": "package_weight",
}

# 类别词默认不作为实体别名；仅允许明确指向包装条件的「包装」保留，
# 否则「采后包装」会因类别过滤丢失唯一可用的包装条件。
CATEGORY_ALIAS_ALLOW = frozenset({("包装", "package_weight")})

FULLWIDTH_START = 0xFF01
FULLWIDTH_END = 0xFF5E
FULLWIDTH_SPACE = 0x3000
FULLWIDTH_OFFSET = 0xFEE0

# 下标/上标数字 → ASCII 数字：让 "O₂"/"CO₂"/"SO₂" 与 "O2"/"CO2"/"SO2" 归一到同一匹配键，
# 避免下标写法漏链（如 eval 里的「SO₂熏蒸」）。
_SUBSCRIPT_SUPERSCRIPT = {
    0x2080: "0", 0x2081: "1", 0x2082: "2", 0x2083: "3", 0x2084: "4",
    0x2085: "5", 0x2086: "6", 0x2087: "7", 0x2088: "8", 0x2089: "9",
    0x208A: "+", 0x208B: "-",
    0x2070: "0", 0x00B9: "1", 0x00B2: "2", 0x00B3: "3", 0x2074: "4",
    0x2075: "5", 0x2076: "6", 0x2077: "7", 0x2078: "8", 0x2079: "9",
    0x207A: "+", 0x207B: "-",
}

_CJK_RANGE = (0x4E00, 0x9FFF)


@dataclass(frozen=True)
class CatalogEntry:
    """词表条目：一个可匹配词 → 一个节点。"""

    node_id: str
    label: str
    canonical: str       # 节点规范名
    raw_term: str        # 词表原始词形（规范名/别名/症状词/切段）
    normalized: str      # 归一化后的匹配键
    weight: float
    source_kind: str     # name | alias | segment | symptom


@dataclass
class Catalog:
    """实体词表（启动时由 :func:`load_catalog` 构建，可跨多轮问答复用）。"""

    path: str = ""
    entries: list[CatalogEntry] = field(default_factory=list)
    terms: dict[str, list[CatalogEntry]] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)  # node_id -> 规范名
    max_term_len: int = 0

    def __len__(self) -> int:
        return len(self.entries)

    def add(self, entry: CatalogEntry) -> None:
        if not entry.normalized:
            return
        bucket = self.terms.setdefault(entry.normalized, [])
        for existing in bucket:
            if existing.node_id == entry.node_id and existing.source_kind == entry.source_kind:
                return
        bucket.append(entry)
        self.entries.append(entry)
        self.max_term_len = max(self.max_term_len, len(entry.normalized))


# ---------------------------------------------------------------- 归一化
def _to_halfwidth(ch: str) -> str:
    code = ord(ch)
    if code == FULLWIDTH_SPACE:
        return " "
    if FULLWIDTH_START <= code <= FULLWIDTH_END:
        return chr(code - FULLWIDTH_OFFSET)
    return _SUBSCRIPT_SUPERSCRIPT.get(code, ch)


def _is_ascii_word_char(ch: str) -> bool:
    """拉丁字母/数字/下划线（用于英文别名的词边界判定）。"""
    return bool(ch) and ch.isascii() and (ch.isalnum() or ch == "_")


def _latin_boundary_ok(text: str, start: int, end: int) -> bool:
    """拉丁/数字别名的词边界检查（供 ``link_entities`` 与单测直接 import）。

    规则：别名首/尾若是拉丁字母或数字，则其**外侧紧邻**不得是另一个拉丁字母/数字，
    否则视为「词内子串误命中」丢弃。中文/符号边界不受影响：

    - ``"so2熏蒸"`` 中的 ``"o2"``（1..3）→ False（左侧 's' 是拉丁字母）
    - ``"co2调到"`` 中的 ``"o2"``（1..3）→ False（左侧 'c'）
    - ``"气调o2调到"`` 中的 ``"o2"`` → True（左侧中文、右侧中文）
    - ``"o2%"`` 中的 ``"o2"`` → True（右侧 '%' 是符号，不是字母数字）
    """
    if text is None or start < 0 or end > len(text) or start >= end:
        return False
    first = text[start]
    last = text[end - 1]
    if _is_ascii_word_char(first) and start > 0 and _is_ascii_word_char(text[start - 1]):
        return False
    if _is_ascii_word_char(last) and end < len(text) and _is_ascii_word_char(text[end]):
        return False
    return True


def normalize_text(text: Any) -> tuple[str, list[int]]:
    """归一化问句，返回 ``(归一化文本, 每个字符对应的原文下标)``。

    用于把匹配位置映射回原始问句（``EntityHit.start/end``）。
    """
    raw = str(text or "")
    chars: list[str] = []
    mapping: list[int] = []
    for index, original in enumerate(raw):
        ch = _to_halfwidth(original)
        if ch.isspace():
            continue
        if ch.isascii() and ch.isalpha():
            ch = ch.lower()
        if ch in PARTICLES:
            continue
        chars.append(ch)
        mapping.append(index)
    return "".join(chars), mapping


def _segments(text: str) -> list[str]:
    """把 "低温冷藏 0±0.5℃" / "Shine Muscat" 切成口语可能说出的中文名词段。"""
    parts = [part.strip() for part in _SEGMENT_SPLIT.split(str(text or ""))]
    result: list[str] = []
    for part in parts:
        if len(part) < 2:
            continue
        if not any(_CJK_RANGE[0] <= ord(ch) <= _CJK_RANGE[1] for ch in part):
            continue  # 纯拉丁/数值段不做二次切分，避免 "0.5" 之类噪声
        result.append(part)
    return result


def _cjk_runs(text: str) -> list[str]:
    """抽出词条里的**连续中文片段**（≥2 字），用于召回带数值/化学式的别名。

    例：``"0℃冷藏" -> ["冷藏"]``、``"SO2熏蒸" -> ["熏蒸"]``、
    ``"1甲基环丙烯" -> ["甲基环丙烯"]``。这样「冷藏温度多少」能命中 ``cold_0``，
    但不会把 ``0.5``/``90`` 之类的数字噪声放进词表。
    """
    runs: list[str] = []
    buffer: list[str] = []
    for ch in str(text or ""):
        if _CJK_RANGE[0] <= ord(ch) <= _CJK_RANGE[1]:
            buffer.append(ch)
        else:
            if len(buffer) >= 2:
                runs.append("".join(buffer))
            buffer = []
    if len(buffer) >= 2:
        runs.append("".join(buffer))
    return runs


# ---------------------------------------------------------------- 构建词表
def load_catalog(entities_csv_path: str | Path) -> Catalog:
    """从 ``data/entities.csv`` 构建词表（name + aliases，长词优先在匹配时体现）。

    传目录时自动拼接 ``entities.csv``。文件缺失/缺列抛 ``FileNotFoundError``/``ValueError``，
    消息写明路径与期望列，方便现场排查。
    """
    path = Path(entities_csv_path)
    if path.is_dir():
        path = path / "entities.csv"
    if not path.is_file():
        raise FileNotFoundError(
            f"实体词表文件不存在：{path}。请传入 data/entities.csv（docs/api.md §1.1），"
            "或等待 kg-builder 产出后重试。"
        )
    catalog = Catalog(path=str(path))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [str(name or "").strip() for name in (reader.fieldnames or [])]
        missing = [name for name in ("id", "label", "name") if name not in fieldnames]
        if missing:
            raise ValueError(
                f"{path} 缺少必需列：{', '.join(missing)}；实际表头：{', '.join(fieldnames) or '(空)'}。"
            )
        rows = [
            {str(key or "").strip(): value for key, value in raw.items() if key is not None}
            for raw in reader
        ]

    # Condition.category 是「类别词」（温度/湿度/气调/化学/物理/包装/采后操作/环境风险），
    # 只表达类别级别语义，不应绑定成某个具体条件的实体别名（否则「气调库 CO2」里的
    # “气调” 会把 ca_o2 误带进结果）。这类词不进词表；类别语义交给 planner 触发词 +
    # store 的 category 过滤。
    category_terms = {
        normalize_text(str(row.get("category") or "").strip())[0]
        for row in rows
        if str(row.get("category") or "").strip()
    }

    rows_by_id = {str(row.get("id") or "").strip(): row for row in rows}
    for row in rows:
        node_id = str(row.get("id") or "").strip()
        label = str(row.get("label") or "").strip()
        name = str(row.get("name") or "").strip()
        if not node_id or not name or label not in LINKABLE_LABELS:
            continue
        catalog.names.setdefault(node_id, name)
        aliases = _split_aliases(row.get("aliases"))

        _add_term(catalog, node_id, label, name, name, "name", WEIGHT_CANONICAL, category_terms)
        for alias in aliases:
            _add_term(catalog, node_id, label, name, alias, "alias", WEIGHT_ALIAS, category_terms)
        # 名称/别名里带数值单位时切出中文名词段（如 "低温冷藏"）与连续中文片段（如 "冷藏"）
        for term in [name, *aliases]:
            for segment in _segments(term):
                _add_term(catalog, node_id, label, name, segment, "segment", WEIGHT_SEGMENT, category_terms)
            for run in _cjk_runs(term):
                _add_term(catalog, node_id, label, name, run, "run", WEIGHT_RUN, category_terms)
        if label == "Disease":
            symptom = str(row.get("symptom") or "").strip()
            for symptom_term in _split_aliases(symptom):
                if len(symptom_term) >= 2:
                    _add_term(catalog, node_id, label, name, symptom_term, "symptom", WEIGHT_SYMPTOM, category_terms)

    # 代码层同义词（明确、低歧义；ambiguous terms 交给 planner TOPIC_TERMS）
    for raw_term, node_id in EXTRA_ALIASES.items():
        row = rows_by_id.get(node_id)
        if not row:
            continue
        _add_term(
            catalog, node_id, str(row.get("label") or ""), str(row.get("name") or ""),
            raw_term, "alias", WEIGHT_ALIAS, category_terms,
        )
    return catalog


def _add_term(
    catalog: Catalog,
    node_id: str,
    label: str,
    canonical: str,
    raw_term: str,
    source_kind: str,
    weight: float,
    category_terms: set | None = None,
) -> None:
    normalized, _ = normalize_text(raw_term)
    if len(normalized) < 2:  # 单字词极易误命中，直接丢弃（中文实体名最短 2 字）
        return
    if normalized in FACILITY_TERMS:
        return  # 设施/场景词不作为实体别名（见 FACILITY_TERMS 注释）
    if (
        category_terms
        and normalized in category_terms
        and (normalized, node_id) not in CATEGORY_ALIAS_ALLOW
    ):
        return  # 通用类别词不作为实体别名（见 load_catalog 注释）
    catalog.add(
        CatalogEntry(
            node_id=node_id,
            label=label,
            canonical=canonical,
            raw_term=str(raw_term).strip(),
            normalized=normalized,
            weight=weight,
            source_kind=source_kind,
        )
    )


def _split_aliases(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    for sep in ("；", ";", "，", ",", "|"):
        text = text.replace(sep, ";")
    return [part.strip() for part in text.split(";") if part.strip()]


# ---------------------------------------------------------------- 链接
def _entry_score(entry: CatalogEntry, term_len: int) -> float:
    """条目分：权重 + 长度微调（长词更可信），上限 1.0。"""
    bonus = 0.02 * min(max(term_len - 2, 0), 4)
    return min(1.0, entry.weight + bonus)


def link_entities(
    question: str,
    catalog: Catalog,
    *,
    max_hits: int = 8,
) -> list[EntityHit]:
    """在问句中做最长匹配，返回按分数降序的 ``EntityHit`` 列表。

    - 命中区间互不重叠（最长优先，"香印青提" 不会退化成 "青提"）；
    - 同一 ``node_id`` 只保留最高分一条；
    - ``surface`` 为原文片段，``alias_hit`` 为命中的词表词形；
    - 不做拼音/编辑距离。
    """
    if catalog is None or not question:
        return []
    normalized, mapping = normalize_text(question)
    if not normalized:
        return []
    candidates: list[tuple[float, int, int, CatalogEntry, str]] = []
    length = len(normalized)
    max_term_len = min(catalog.max_term_len, length)
    index = 0
    while index < length:
        matched: tuple[int, list[CatalogEntry]] | None = None
        # 同起点按「最长别名」优先尝试；词边界不合法就缩到更短的别名
        for span in range(min(max_term_len, length - index), 0, -1):
            entries = catalog.terms.get(normalized[index : index + span])
            if not entries:
                continue
            if not _latin_boundary_ok(normalized, index, index + span):
                continue  # 词内子串误命中（"SO2"/"CO2" 里的 "O2"）→ 丢弃，试更短别名
            matched = (span, entries)
            break
        if matched is None:
            index += 1
            continue
        span, entries = matched
        start = mapping[index]
        end = mapping[index + span - 1] + 1
        surface = str(question)[start:end]
        for entry in entries:
            candidates.append((_entry_score(entry, span), start, end, entry, surface))
        index += span  # 命中后跳过整个区间，保证命中区间互不重叠

    if not candidates:
        return []

    # 同一 node_id 取最高分（同分取更早出现）
    best: dict[str, tuple[float, int, int, CatalogEntry, str]] = {}
    for candidate in candidates:
        score, start, _, entry, _surface = candidate
        previous = best.get(entry.node_id)
        if previous is None or score > previous[0] or (score == previous[0] and start < previous[1]):
            best[entry.node_id] = candidate

    hits = [
        EntityHit(
            node_id=entry.node_id,
            label=entry.label,
            surface=surface,
            alias_hit=entry.raw_term,
            score=round(score, 6),
            start=start,
            end=end,
        )
        for score, start, end, entry, surface in best.values()
    ]
    hits.sort(key=lambda hit: (-hit.score, hit.start, hit.node_id))
    try:
        limit = max(1, int(max_hits))
    except (TypeError, ValueError):
        limit = 8
    return hits[:limit]
