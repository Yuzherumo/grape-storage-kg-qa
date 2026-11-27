#!/usr/bin/env python
"""文档数字一致性检查：防止 README / docs 里的图谱规模与 data/ 真实数据漂移。

设计取舍：文档里的数字大量是「子集陈述」（如「4 条 verified 条文定点命中」
「46 条 anchor 的 quote 为空」），简单地把所有数字和总数比对会产生大量误报。
因此本脚本做两件事，都能低误报地拦住真实漂移：

1. **旧口径黑名单**：把历史上出现过的过期总数（77 节点 / 115 关系 / 58 实体 /
   19 条来源 / 30 个条件 / 50 条 anchor / 51 条国标 …）列为禁止短语，出现在
   非历史行即失败；
2. **README 总数锚点**：README 必须逐字包含当前规范总数（知识实体 63 个、
   图谱节点 108 个、关系 125 条、verified 69 条、anchor 56 条），值不对即失败。

规范值由 ``scripts/report_stats.py`` 的 ``compute_stats()`` 实时计算。
行内出现 ``docs-consistency: ignore`` 或含「历史/当时/旧口径/曾/不要把」的行跳过；
``` 围栏内的代码块跳过。

用法：
    python scripts/check_docs_consistency.py        # 0 = 一致；1 = 有漂移
    python scripts/check_docs_consistency.py --all  # 列出所有被检查的文件
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
DOCS = BASE / "docs"

if str(BASE / "scripts") not in sys.path:
    sys.path.insert(0, str(BASE / "scripts"))

from report_stats import compute_stats  # noqa: E402

#: 明确要检查的文档（README + 公开技术文档 + 外部数据说明）
DOC_FILES = [
    BASE / "README.md",
    DOCS / "technical_notes.md",
    DOCS / "submission.md",
    DOCS / "limitations.md",
    DOCS / "validation.md",
    DOCS / "data.md",
    DOCS / "sources.md",
    DOCS / "demo_script.md",
    DOCS / "neo4j_verify.md",
    DOCS / "packaging.md",
    DOCS / "deploy.md",
    DOCS / "README.md",
    BASE / "data" / "external" / "agridata" / "README.md",
    BASE / "data" / "external" / "web_grape_storage" / "README.md",
]

#: 过期总数黑名单：(正则, 统计字段, 说明)。命中即说明文档在讲旧口径。
STALE_PHRASES: list[tuple[str, str, str]] = [
    (r"77\s*个?节点", "nodes", "旧口径 77 节点"),
    (r"115\s*条\s*(?:关系|三元组|边)", "triples", "旧口径 115 条关系"),
    (r"115\s*关系", "triples", "旧口径 115 关系"),
    (r"58\s*个?\s*知识实体", "entities", "旧口径 58 实体"),
    (r"19\s*条\s*来源", "sources", "旧口径 19 条来源"),
    (r"19\s*个\s*来源(?!节点)", "sources", "旧口径 19 个来源"),
    (r"20\s*个\s*来源节点", "sources", "旧口径 20 个来源节点"),
    (r"30\s*个\s*条件", "Condition", "旧口径 30 个条件"),
    (r"50\s*条\s*anchor", "anchor", "旧口径 50 条 anchor"),
    (r"119\s*条\s*关系", "triples", "旧口径 119 条关系"),
    (r"78\s*个?\s*节点", "nodes", "旧口径 78 节点"),
]


def _expected_values(stats: dict[str, Any]) -> dict[str, int]:
    labels = stats["entities_by_label"]
    return {
        "entities": int(stats["entities"]),
        "Variety": int(labels.get("Variety", 0)),
        "Condition": int(labels.get("Condition", 0)),
        "QualityIndicator": int(labels.get("QualityIndicator", 0)),
        "Disease": int(labels.get("Disease", 0)),
        "sources": int(stats["sources"]),
        "nodes": int(stats["nodes"]),
        "triples": int(stats["triples"]),
        "verified": int(stats["triples_by_status"].get("verified", 0)),
        "anchor": int(stats["triples_by_status"].get("anchor", 0)),
        "snapshot_rows": int(stats["snapshot_rows"]),
        "descriptions": int(stats["descriptions"]),
    }


def _is_exempt(line: str) -> bool:
    markers = ("docs-consistency: ignore", "历史", "当时", "旧口径", "曾", "不要把")
    return any(marker in line for marker in markers)


def _read(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def check_stale_phrases(path: Path, expected: dict[str, int]) -> list[str]:
    text = _read(path)
    if text is None:
        return []
    problems: list[str] = []
    in_code = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or _is_exempt(line):
            continue
        for pattern, key, label in STALE_PHRASES:
            match = re.search(pattern, line)
            if match:
                problems.append(
                    f"{path.relative_to(BASE)}:{lineno}: {label}（应为 {expected.get(key)}）"
                    f" → 「{match.group(0)}」"
                )
    return problems


#: README 必须出现的「总数锚点」：(正则, 统计字段, 说明)
README_ANCHORS: list[tuple[str, str, str]] = [
    (r"知识实体\s*(\d+)\s*个", "entities", "知识实体总数"),
    (r"来源节点\s*(\d+)\s*个", "sources", "来源节点总数"),
    (r"关系\s*(\d+)\s*条", "triples", "关系总数"),
    (r"verified[`*\s]*(\d+)\s*条", "verified", "verified 总数"),
    (r"anchor[`*\s]*(\d+)\s*条", "anchor", "anchor 总数"),
]


def check_readme_anchors(path: Path, expected: dict[str, int]) -> list[str]:
    text = _read(path)
    if text is None:
        return []
    problems: list[str] = []
    for pattern, key, label in README_ANCHORS:
        matches = [int(m.group(1)) for m in re.finditer(pattern, text)]
        if not matches:
            problems.append(f"{path.relative_to(BASE)}: 未找到「{label}」锚点（正则 {pattern}）")
            continue
        wrong = sorted({value for value in matches if value != expected.get(key)})
        if wrong:
            problems.append(
                f"{path.relative_to(BASE)}: {label} 出现 {wrong}，应为 {expected.get(key)}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档数字一致性检查")
    parser.add_argument("--all", action="store_true", help="列出所有被检查的文件")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    stats = compute_stats()
    expected = _expected_values(stats)
    if args.all:
        print("检查文件：")
        for path in DOC_FILES:
            if path.exists():
                print("  -", path.relative_to(BASE))

    problems: list[str] = []
    for path in DOC_FILES:
        problems.extend(check_stale_phrases(path, expected))
    problems.extend(check_readme_anchors(BASE / "README.md", expected))

    if problems:
        print(f"[失败] 发现 {len(problems)} 处文档数字与 data/ 不一致：")
        for item in problems:
            print("  -", item)
        print("\n修正后可重跑；历史记录请在行内加 `docs-consistency: ignore` 或写明「历史」。")
        return 1

    print(
        "[通过] 文档规模数字与 data/ 一致："
        + "、".join(f"{k}={v}" for k, v in expected.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
