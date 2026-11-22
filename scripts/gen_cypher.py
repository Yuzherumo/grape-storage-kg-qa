#!/usr/bin/env python
"""CSV → Cypher 生成器（MERGE 幂等）。

输入：data/entities.csv、data/sources.csv、data/triples.csv
输出：graph/init_nodes.cypher、graph/init_rels.cypher

用法：
    python scripts/gen_cypher.py              # 生成/覆盖两个 cypher 文件
    python scripts/gen_cypher.py --check      # 只比对，不写盘；有漂移则退出码 1
    python scripts/gen_cypher.py --stats      # 打印节点/关系统计

归属：kg-builder。契约：docs/api.md §1.2、docs/spec.md §6。
仅用标准库；中文内容以 UTF-8 写出。
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, OrderedDict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
GRAPH = BASE / "graph"

# Windows 控制台/管道统一用 UTF-8 输出（venv 与系统 python 一致）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

NODE_LABELS = ["Variety", "Condition", "QualityIndicator", "Disease"]
REL_PROP_ORDER = [
    "sid", "subject", "predicate", "object", "value", "value_min", "value_max", "unit",
    "stage", "effect", "level", "severity", "efficacy", "reason",
    "source_ids", "locator", "quote", "status", "confidence", "note",
]
NUMERIC_REL_PROPS = {"value", "value_min", "value_max", "confidence"}
LIST_REL_PROPS = {"source_ids"}

NODE_COMMON_PROPS = ["label", "name", "aliases", "category", "value_min", "value_max", "unit",
                     "stage", "direction", "method", "species", "berry_color", "seedless",
                     "maturity", "region", "pathogen_latin", "symptom", "source_ids", "note"]
NUMERIC_NODE_PROPS = {"value_min", "value_max"}
LIST_NODE_PROPS = {"aliases", "source_ids", "symptom"}
SOURCE_PROPS = ["title", "authors", "year", "venue", "type", "doi_url", "access", "note"]

HEADER_NODES = """// =============================================================================
// graph/init_nodes.cypher —— 图谱节点初始化（自动生成，请勿手改）
// 由 scripts/gen_cypher.py 从 data/entities.csv + data/sources.csv 生成
// 幂等：MERGE (n:Label {{id: ...}}) —— 可重复执行
// 统计：共 {total} 个节点（{breakdown}）
// 生成后校验：python scripts/gen_cypher.py --check
// =============================================================================

// 先执行 graph/schema.cypher 建立唯一约束/索引（可重复执行）
// cypher-shell -f graph/schema.cypher

"""

HEADER_RELS = """// =============================================================================
// graph/init_rels.cypher —— 图谱关系初始化（自动生成，请勿手改）
// 由 scripts/gen_cypher.py 从 data/triples.csv 生成
// 幂等：MERGE (a)-[r:PREDICATE {{sid: ...}}]->(b) —— 可重复执行
// 统计：共 {total} 条关系（{breakdown}）
// 关系属性含 source_ids/locator/quote/status/confidence（证据溯源必需）
// =============================================================================

// 节点须先由 graph/init_nodes.cypher 建立；按谓词分组，顺序执行即可
MATCH (n) RETURN count(n) AS node_count_before;

"""


def esc(value: str) -> str:
    """转义 Cypher 单引号字符串字面量。"""
    s = str(value)
    s = s.replace("\\", "\\\\").replace("'", "\\'")
    return s


def lit(value: str) -> str:
    return "'" + esc(value) + "'"


def num_lit(raw: str) -> str | None:
    s = str(raw).strip()
    if s == "":
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    if f.is_integer() and "." not in s and "e" not in s.lower():
        return str(int(f))
    return repr(f)


def list_lit(raw: str) -> str:
    items = [x.strip() for x in str(raw).split(";") if x.strip()]
    return "[" + ", ".join(lit(i) for i in items) + "]"


def prop_assignments(row: dict[str, str], keys: list[str], numeric: set, lists: set) -> list[str]:
    parts: list[str] = []
    for k in keys:
        raw = row.get(k, "")
        if raw is None:
            raw = ""
        if k in numeric:
            nv = num_lit(raw)
            if nv is not None:
                parts.append(f"n.{k} = {nv}")
            continue
        if k in lists:
            if str(raw).strip():
                parts.append(f"n.{k} = {list_lit(raw)}")
            continue
        if str(raw).strip():
            parts.append(f"n.{k} = {lit(raw)}")
    return parts


def rel_prop_assignments(row: dict[str, str]) -> list[str]:
    parts: list[str] = []
    for k in REL_PROP_ORDER:
        raw = row.get(k, "")
        if raw is None:
            raw = ""
        if k in NUMERIC_REL_PROPS:
            nv = num_lit(raw)
            if nv is not None:
                parts.append(f"r.{k} = {nv}")
            continue
        if k in LIST_REL_PROPS:
            if str(raw).strip():
                parts.append(f"r.{k} = {list_lit(raw)}")
            continue
        if str(raw).strip():
            parts.append(f"r.{k} = {lit(raw)}")
    return parts


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [{k: (v if v is not None else "") for k, v in row.items()} for row in reader]


def build_nodes(entities: list[dict[str, str]], sources: list[dict[str, str]]) -> str:
    counts = Counter((r.get("label") or "").strip() for r in entities)
    counts["Source"] = len(sources)
    breakdown = "，".join(f"{k} {v}" for k, v in counts.items() if v)
    total = len(entities) + len(sources)
    lines: list[str] = [HEADER_NODES.format(total=total, breakdown=breakdown)]

    for label in NODE_LABELS:
        rows = [r for r in entities if (r.get("label") or "").strip() == label]
        if not rows:
            continue
        lines.append(f"// ---------------- {label}（{len(rows)} 个） ----------------")
        for r in rows:
            node_id = (r.get("id") or "").strip()
            props = prop_assignments(r, NODE_COMMON_PROPS, NUMERIC_NODE_PROPS, LIST_NODE_PROPS)
            prop_str = ",\n         ".join(props)
            lines.append(
                f"MERGE (n:{label} {{id: {lit(node_id)}}})\n"
                f"  SET {prop_str};"
            )
        lines.append("")

    lines.append(f"// ---------------- Source（{len(sources)} 个，来自 data/sources.csv） ----------------")
    for r in sources:
        node_id = (r.get("id") or "").strip()
        props = prop_assignments(r, SOURCE_PROPS, set(), set())
        prop_str = ",\n         ".join(props)
        lines.append(
            f"MERGE (n:Source {{id: {lit(node_id)}}})\n"
            f"  SET {prop_str};"
        )
    lines.append("")
    lines.append("// 节点写入完毕；随后执行 graph/init_rels.cypher")
    lines.append("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt ORDER BY label;")
    lines.append("")
    return "\n".join(lines)


def build_rels(triples: list[dict[str, str]], entities: list[dict[str, str]],
               sources: list[dict[str, str]]) -> tuple[str, list[str]]:
    errors: list[str] = []
    name_to: dict[str, tuple[str, str]] = {}
    for r in entities:
        n = (r.get("name") or "").strip()
        if n:
            name_to[n] = ((r.get("label") or "").strip(), (r.get("id") or "").strip())
    for r in sources:
        title = (r.get("title") or "").strip()
        if title:
            name_to.setdefault(title, ("Source", (r.get("id") or "").strip()))

    counts = Counter((r.get("predicate") or "").strip() for r in triples)
    breakdown = "，".join(f"{k} {v}" for k, v in counts.items())
    lines: list[str] = [HEADER_RELS.format(total=len(triples), breakdown=breakdown)]

    by_pred: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    for r in triples:
        by_pred.setdefault((r.get("predicate") or "").strip(), []).append(r)

    for pred, rows in by_pred.items():
        lines.append(f"// ---------------- {pred}（{len(rows)} 条） ----------------")
        for i, r in enumerate(rows, 2):
            sid = (r.get("sid") or "").strip()
            subj = (r.get("subject") or "").strip()
            obj = (r.get("object") or "").strip()
            st = (r.get("subject_type") or "").strip()
            ot = (r.get("object_type") or "").strip()
            if subj not in name_to:
                errors.append(f"第{i}行 sid={sid}：subject '{subj}' 在 entities 中无同名节点")
                continue
            if obj not in name_to:
                errors.append(f"第{i}行 sid={sid}：object '{obj}' 在 entities 中无同名节点")
                continue
            slabel, sid_node = name_to[subj]
            olabel, oid_node = name_to[obj]
            if slabel != st:
                errors.append(f"第{i}行 sid={sid}：subject '{subj}' 实际标签 {slabel} 与声明 {st} 不符")
            if olabel != ot:
                errors.append(f"第{i}行 sid={sid}：object '{obj}' 实际标签 {olabel} 与声明 {ot} 不符")
            props = rel_prop_assignments(r)
            if sid:
                props = [f"r.sid = {lit(sid)}"] + [p for p in props if not p.startswith("r.sid ")]
            prop_str = ",\n         ".join(props)
            lines.append(
                f"MATCH (a:{slabel} {{id: {lit(sid_node)}}}), (b:{olabel} {{id: {lit(oid_node)}}})\n"
                f"MERGE (a)-[r:{pred}]->(b)\n"
                f"  SET {prop_str};"
            )
        lines.append("")

    lines.append("// 关系写入完毕，做一次统计自检")
    lines.append("MATCH ()-[r]->() RETURN type(r) AS predicate, count(*) AS cnt ORDER BY predicate;")
    lines.append("")
    return "\n".join(lines), errors


def write_if_changed(path: Path, content: str) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def diff_summary(expected: str, actual_path: Path) -> str:
    if not actual_path.exists():
        return f"{actual_path.relative_to(BASE)} 不存在（需先运行 python scripts/gen_cypher.py 生成）"
    actual = actual_path.read_text(encoding="utf-8")
    if actual == expected:
        return ""
    exp_lines = expected.splitlines()
    act_lines = actual.splitlines()
    for idx in range(min(len(exp_lines), len(act_lines))):
        if exp_lines[idx] != act_lines[idx]:
            return (f"{actual_path.relative_to(BASE)} 第 {idx + 1} 行起不一致：\n"
                    f"  期望：{exp_lines[idx][:160]}\n  实际：{act_lines[idx][:160]}")
    return (f"{actual_path.relative_to(BASE)} 行数不同：期望 {len(exp_lines)} 行，实际 {len(act_lines)} 行")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSV → Cypher（MERGE 幂等）生成器")
    parser.add_argument("--check", action="store_true", help="只比对是否漂移，不写盘；有漂移退出码 1")
    parser.add_argument("--stats", action="store_true", help="打印节点/关系统计")
    args = parser.parse_args(argv)

    missing = [str(p.relative_to(BASE)) for p in
               (DATA / "entities.csv", DATA / "sources.csv", DATA / "triples.csv") if not p.exists()]
    if missing:
        print("[失败] 缺少输入文件：" + ", ".join(missing))
        return 2

    entities = read_csv(DATA / "entities.csv")
    sources = read_csv(DATA / "sources.csv")
    triples = read_csv(DATA / "triples.csv")

    nodes_cypher = build_nodes(entities, sources)
    rels_cypher, rel_errors = build_rels(triples, entities, sources)
    if rel_errors:
        print("[失败] 关系生成时发现数据引用错误：")
        for e in rel_errors[:50]:
            print("  - " + e)
        return 2

    node_label_counts = Counter((r.get("label") or "").strip() for r in entities)
    pred_counts = Counter((r.get("predicate") or "").strip() for r in triples)
    if args.stats:
        print("节点统计：" + "，".join(f"{k} {v}" for k, v in node_label_counts.items()) + f"，Source {len(sources)}")
        print("关系统计：" + "，".join(f"{k} {v}" for k, v in pred_counts.items()))
        print(f"合计：{len(entities) + len(sources)} 节点 / {len(triples)} 关系")

    if args.check:
        problems = []
        for path, expected in ((GRAPH / "init_nodes.cypher", nodes_cypher),
                               (GRAPH / "init_rels.cypher", rels_cypher)):
            msg = diff_summary(expected, path)
            if msg:
                problems.append(msg)
        if problems:
            print("[失败] Cypher 与 CSV 存在漂移（请运行 python scripts/gen_cypher.py 重新生成）：")
            for p in problems:
                print("  - " + p)
            return 1
        print("[通过] Cypher 无漂移：graph/init_nodes.cypher、graph/init_rels.cypher 与 CSV 一致。")
        return 0

    changed_nodes = write_if_changed(GRAPH / "init_nodes.cypher", nodes_cypher)
    changed_rels = write_if_changed(GRAPH / "init_rels.cypher", rels_cypher)
    print(f"[完成] graph/init_nodes.cypher：{len(entities) + len(sources)} 个节点"
          f"（{'已更新' if changed_nodes else '无变化'}）")
    print(f"[完成] graph/init_rels.cypher：{len(triples)} 条关系（{'已更新' if changed_rels else '无变化'}）")
    print("提示：先执行 graph/schema.cypher，再执行 init_nodes.cypher、init_rels.cypher。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
