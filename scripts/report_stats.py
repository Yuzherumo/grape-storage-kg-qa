#!/usr/bin/env python
"""规范统计口径：从 ``data/*.csv`` 计算知识图谱规模，供文档与 CI 统一引用。

背景：README / docs 里的「63 实体 / 108 节点 / 125 关系 / 69 verified / 56 anchor」
等数字过去靠人工同步，出现过 30 vs 35 个条件、77 vs 108 节点、50 vs 56 anchor 之类的漂移。
本脚本是这些数字的**唯一计算入口**：文档改数字前先跑它；CI 用
``scripts/check_docs_consistency.py`` 比对。

用法（项目根目录）：
    .\\.venv\\Scripts\\python.exe scripts\\report_stats.py            # 人读摘要
    .\\.venv\\Scripts\\python.exe scripts\\report_stats.py --json     # 机器可读
    .\\.venv\\Scripts\\python.exe scripts\\report_stats.py --markdown # Markdown 表格

仅用标准库，不依赖 app/，CI 与任意 python3 均可运行。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"

#: 知识实体类别（与 data/schema.json 一致）
ENTITY_LABELS = ("Variety", "Condition", "QualityIndicator", "Disease")
#: 来源类别（与 data/schema.json 一致）
SOURCE_TYPES = ("国标", "综述", "论文", "行业资料")


def read_csv(path: Path) -> list[dict[str, str]]:
    """读 data/ 下的 CSV；文件缺失或无法解析时返回空列表（由调用方决定是否报错）。"""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, UnicodeDecodeError):
        return []


def _split_ids(value: str) -> list[str]:
    """兼容 ``;`` / ``,`` / `，` 分隔的 source_ids。"""
    normalized = (value or "").replace(";", ",").replace("，", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def compute_stats(data_dir: Path | str | None = None) -> dict[str, Any]:
    """计算规范口径统计（纯函数，供 CLI / 校验脚本 / 测试复用）。"""
    data = Path(data_dir) if data_dir else DATA
    entities = read_csv(data / "entities.csv")
    sources = read_csv(data / "sources.csv")
    triples = read_csv(data / "triples.csv")
    snapshot = read_csv(data / "triples_shine_muscat.csv")
    descriptions = read_csv(data / "descriptions.csv")
    evaluations = read_csv(data / "eval_questions.csv")
    utterances = read_csv(data / "utterances.csv")

    by_label = Counter(row.get("label", "") for row in entities)
    by_type = Counter(row.get("type", "") for row in sources)
    by_status = Counter(row.get("status", "") for row in triples)
    by_predicate = Counter(row.get("predicate", "") for row in triples)

    referenced_sources: set[str] = set()
    for triple in triples:
        referenced_sources.update(_split_ids(triple.get("source_ids", "")))

    used_entities: set[str] = set()
    for triple in triples:
        for key in ("subject", "object"):
            value = (triple.get(key) or "").strip()
            if value:
                used_entities.add(value)
    isolated = sorted(
        row.get("name", "")
        for row in entities
        if row.get("name") and row.get("name") not in used_entities
    )

    anchor_rows = [row for row in triples if row.get("status") == "anchor"]
    anchor_with_quote = sum(1 for row in anchor_rows if (row.get("quote") or "").strip())
    anchor_placeholder_locator = sum(
        1
        for row in anchor_rows
        if any(mark in (row.get("locator") or "") for mark in ("待补", "待获取"))
    )

    eval_refusals = sum(
        1
        for row in evaluations
        if (row.get("expected_status") or "").strip().lower() == "refuse"
    )

    return {
        "entities": len(entities),
        "entities_by_label": {label: by_label.get(label, 0) for label in ENTITY_LABELS},
        "sources": len(sources),
        "sources_by_type": {name: by_type.get(name, 0) for name in SOURCE_TYPES},
        "nodes": len(entities) + len(sources),
        "triples": len(triples),
        "triples_by_status": {
            "verified": by_status.get("verified", 0),
            "anchor": by_status.get("anchor", 0),
        },
        "predicates": dict(sorted(by_predicate.items())),
        "snapshot_rows": len(snapshot),
        "descriptions": len(descriptions),
        "eval_questions": len(evaluations),
        "eval_refusals": eval_refusals,
        "utterances": len(utterances),
        "anchor_with_quote": anchor_with_quote,
        "anchor_placeholder_locator": anchor_placeholder_locator,
        "orphan_sources": len(
            [row for row in sources if row.get("id") and row.get("id") not in referenced_sources]
        ),
        "isolated_entities": isolated,
    }


def render_markdown(stats: dict[str, Any]) -> str:
    """输出 Markdown 表格（可直接贴进文档）。"""
    labels = stats["entities_by_label"]
    types = stats["sources_by_type"]
    status = stats["triples_by_status"]
    lines = [
        "| 口径 | 数值 |",
        "|---|---|",
        f"| 知识实体 | {stats['entities']}（品种 {labels.get('Variety', 0)} / "
        f"条件 {labels.get('Condition', 0)} / 指标 {labels.get('QualityIndicator', 0)} / "
        f"病害 {labels.get('Disease', 0)}） |",
        f"| 来源节点 | {stats['sources']}（国标 {types.get('国标', 0)} / 综述 {types.get('综述', 0)} / "
        f"论文 {types.get('论文', 0)} / 行业资料 {types.get('行业资料', 0)}） |",
        f"| 图谱节点 | {stats['nodes']}（{stats['entities']} 实体 + {stats['sources']} 来源） |",
        f"| 关系 | {stats['triples']}（verified {status.get('verified', 0)} / "
        f"anchor {status.get('anchor', 0)}） |",
        f"| 阳光玫瑰快照 | {stats['snapshot_rows']} 条 |",
        f"| 节点描述 | {stats['descriptions']} 个 |",
        f"| 评测题 | {stats['eval_questions']} 题（该拒答 {stats['eval_refusals']} 题） |",
        f"| 口语变体 | {stats['utterances']} 条 |",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="知识图谱规范统计口径")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--markdown", action="store_true", help="输出 Markdown 表格")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - 非 TTY / 老版本 python
        pass

    stats = compute_stats()
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    elif args.markdown:
        print(render_markdown(stats))
    else:
        print("知识图谱规范统计（data/ 单一真相）")
        print("=" * 56)
        print(render_markdown(stats))
        print("-" * 56)
        print(
            f"anchor 中已有逐字 quote：{stats['anchor_with_quote']}；"
            f"locator 为占位符：{stats['anchor_placeholder_locator']}"
        )
        print(f"未被任何三元组引用的来源：{stats['orphan_sources']}")
        if stats["isolated_entities"]:
            print("孤立知识实体：" + "、".join(stats["isolated_entities"]))
    if stats["entities"] == 0 or stats["triples"] == 0:
        print("[错误] 数据文件缺失或为空，请检查 data/ 目录。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
