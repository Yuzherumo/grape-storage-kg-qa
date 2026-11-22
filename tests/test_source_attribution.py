"""第三轮：国标来源关联核对（只读断言，不修改任何数据/文档）。

背景：``data/triples.csv`` 中 7 条记录的 locator/quote 引用 GB/T 16862-2026
条款/附录 A/B（第 34/37/38/41/42/60/61 行），但原 ``source_ids`` 未挂
``gbt16862_2026``。第三轮逐条回查国标 PDF 提取文本后补齐来源关联，本测试锁定
修复后的不变量，防止回归：

1. ``status=verified`` 且 locator/quote 明确引用国标条款或附录 A/B 的三元组，
   必须挂 ``gbt16862_2026``（杜绝「引国标却无国标来源」再次出现）；
2. 本轮 7 个 sid 的最终处置必须与数据一致（补挂国标来源，或降为 anchor 且
   note 写明「待核验」）；
3. ``docs/sources.md`` 宣称的「verified 且 source_ids 含国标来源」条数与 CSV
   实际值一致（用可推导口径，不硬编码脆弱数字）；
4. 若本机存在国标 PDF 提取文本 ``.tmp/std_text.txt``，则复核 7 条 quote 的
   关键片段确实出自该文本；该文件 gitignore、不入库，缺失时仅跳过本项。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from _support import DATA, DOCS, read_csv, read_text, split_ids

ROOT = Path(__file__).resolve().parents[1]
TRIPLES = DATA / "triples.csv"
SOURCES_MD = DOCS / "sources.md"
# 国标 PDF 文本（用户提供，pdfminer 提取；.tmp/ 已 gitignore，仅本机可复核）
GBT_TEXT = ROOT / ".tmp" / "std_text.txt"

GBT_SOURCE_ID = "gbt16862_2026"
# 「明确引用国标」的特征：标准号，或附录 A/B、表 A.1/表 B.1
GBT_REF_RE = re.compile(r"(GB/?T\s*16862|16862[—\-–]2026|附录\s*[AB]|表\s*[AB]\.1)")
# docs/sources.md §2.1 的口径句（数量由 CSV 推导，不写死）
DOCS_COUNT_RE = re.compile(r"含 `gbt16862_2026` 的三元组共 \*\*(\d+)\*\* 条")

# 第三轮逐条回查的 7 条（CSV 物理行号 34/37/38/41/42/60/61）
ROUND3_SIDS = (
    "e_gray_so2pad",
    "f_black_hot",
    "f_blue_wound",
    "f_gray_wound",
    "f_rhizopus_mech",
    "sm_ind_ssc",
    "sm_ind_ta",
)
# quote 去掉「附录X 表X.1:」前缀后应在国标原文中逐字出现（去空白后比对）
VERBATIM_QUOTE_SIDS = frozenset(
    {"e_gray_so2pad", "f_black_hot", "f_blue_wound", "f_gray_wound", "f_rhizopus_mech"}
)
# 附录A 表A.1 的 quote 为表头+行值的还原写法（非逐字摘录），复核表头与行值片段
TABLE_A_FRAGMENTS = {
    "sm_ind_ssc": ("可溶性固形物/%≥", "阳光玫瑰16.00.35"),
    "sm_ind_ta": ("可滴定酸/%≤", "阳光玫瑰16.00.35"),
}
QUOTE_PREFIX_RE = re.compile(r"^附录[AB] 表[AB]\.1[:：]")


def _triples() -> list[dict[str, str]]:
    assert TRIPLES.is_file(), f"缺少 {TRIPLES}（S2a 交付物）"
    return read_csv(TRIPLES)


def _by_sid() -> dict[str, dict[str, str]]:
    return {str(row.get("sid") or "").strip(): row for row in _triples()}


def _has_gbt_source(row: dict[str, str]) -> bool:
    return GBT_SOURCE_ID in split_ids(row.get("source_ids"))


def _cites_gbt(row: dict[str, str]) -> bool:
    return bool(GBT_REF_RE.search(str(row.get("locator") or "") + "\n" + str(row.get("quote") or "")))


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


# ---------------------------------------------------------------- 不变量 1
def test_verified_rows_citing_gbt_must_declare_gbt_source() -> None:
    """verified 且 locator/quote 引用国标条款或附录 A/B 的行，必须挂国标来源。"""
    rows = _triples()
    offenders = [
        str(row.get("sid") or "").strip()
        for row in rows
        if str(row.get("status") or "").strip() == "verified" and _cites_gbt(row) and not _has_gbt_source(row)
    ]
    assert not offenders, (
        "以下 verified 三元组的 locator/quote 引用 GB/T 16862-2026 条款或附录 A/B，"
        f"但 source_ids 缺 {GBT_SOURCE_ID}：{offenders}"
    )
    # 反向守卫：引用特征正则必须真的命中本轮 7 条，避免正则失效后断言空转
    cited = {
        str(row.get("sid") or "").strip()
        for row in rows
        if str(row.get("status") or "").strip() == "verified" and _cites_gbt(row) and _has_gbt_source(row)
    }
    assert set(ROUND3_SIDS) <= cited, f"本轮 7 条未被识别为「引用国标且含国标来源」：{set(ROUND3_SIDS) - cited}"


# ---------------------------------------------------------------- 不变量 2
def test_round3_seven_rows_have_disposition_matching_data() -> None:
    """7 个 sid 的最终处置二选一：补挂国标来源（verified+quote），或 anchor+待核验。"""
    by_sid = _by_sid()
    problems: list[str] = []
    for sid in ROUND3_SIDS:
        row = by_sid.get(sid)
        if row is None:
            problems.append(f"{sid}: 在 triples.csv 中不存在")
            continue
        status = str(row.get("status") or "").strip()
        quote = str(row.get("quote") or "").strip()
        note = str(row.get("note") or "")
        handled_by_source = _has_gbt_source(row) and status == "verified" and bool(quote)
        handled_by_anchor = status == "anchor" and "待核验" in note
        if not (handled_by_source or handled_by_anchor):
            problems.append(f"{sid}: 既未补挂 {GBT_SOURCE_ID}（要求 verified+quote），也非 anchor+note「待核验」")
        if not GBT_REF_RE.search(str(row.get("locator") or "")):
            problems.append(f"{sid}: locator 未指向国标条款/附录：{row.get('locator')!r}")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------- 不变量 3
def test_sources_md_declared_gbt_verified_count_matches_csv() -> None:
    """docs/sources.md 的「verified 且含国标来源」条数必须等于 CSV 实际值。"""
    assert SOURCES_MD.is_file(), f"缺少 {SOURCES_MD}"
    actual = sum(
        1
        for row in _triples()
        if str(row.get("status") or "").strip() == "verified" and _has_gbt_source(row)
    )
    text = read_text(SOURCES_MD)
    match = DOCS_COUNT_RE.search(text)
    assert match, (
        "docs/sources.md §2.1 缺少口径句「…含 `gbt16862_2026` 的三元组共 **N** 条」；"
        "请同步来源统计后再改数据"
    )
    declared = int(match.group(1))
    assert declared == actual, (
        f"docs/sources.md 宣称含国标来源的 verified 三元组 {declared} 条，CSV 实际 {actual} 条（需同步文档）"
    )
    missing_sids = [sid for sid in ROUND3_SIDS if sid not in text]
    assert not missing_sids, f"docs/sources.md §2.1 未登记本轮补挂来源的 sid：{missing_sids}"


# ---------------------------------------------------------------- 不变量 4
@pytest.mark.skipif(
    not GBT_TEXT.is_file(),
    reason="本机无 .tmp/std_text.txt（国标 PDF 提取文本，gitignore 不入库），跳过原文片段复核",
)
def test_round3_quotes_traceable_to_standard_text() -> None:
    """7 条 quote 必须能在国标 PDF 提取文本中找到对应原文/表值片段。"""
    standard = _normalized(read_text(GBT_TEXT))
    by_sid = _by_sid()
    missing: dict[str, list[str]] = {}
    for sid in ROUND3_SIDS:
        row = by_sid[sid]
        quote = str(row.get("quote") or "").strip()
        if sid in VERBATIM_QUOTE_SIDS:
            body = QUOTE_PREFIX_RE.sub("", quote)
            if _normalized(body) not in standard:
                missing.setdefault(sid, []).append("quote 正文未在国标原文中逐字出现")
            continue
        for fragment in TABLE_A_FRAGMENTS[sid]:
            if _normalized(fragment) not in standard:
                missing.setdefault(sid, []).append(f"缺少表A.1 片段 {fragment!r}")
    assert not missing, f"以下 quote 无法在 GB/T 16862-2026 提取文本中溯源：{missing}"
