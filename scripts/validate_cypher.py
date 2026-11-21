# -*- coding: utf-8 -*-
"""Cypher 脚本静态校验（无需 Neo4j 服务端）。

检查项：
1) graph/*.cypher 里出现的节点标签 ⊆ schema.json 标签枚举
2) 关系类型 ⊆ 9 种谓词枚举
3) 查询模板里的 $ 参数 ⊆ 已知参数集合；每个模板必须有 RETURN 与 LIMIT
4) init_nodes/init_rels 的 MERGE 数与 CSV 行数一致；schema.cypher 覆盖 5 类唯一约束
5) 每条三元组的 subject/object 名称都能在 entities.csv 找到（与 validate_data 检查9 呼应）

退出码：0 = 通过；1 = 有错误。
用法：python scripts/validate_cypher.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
GRAPH = BASE / "graph"
DATA = BASE / "data"

LABELS = {"Variety", "Condition", "QualityIndicator", "Disease", "Source"}
PREDICATES = {
    "REQUIRES", "CONTRA_INDICATED_FOR", "AFFECTS", "SUSCEPTIBLE_TO", "PREVENTED_BY",
    "INDUCED_BY", "ALTERNATIVE_TO", "INDICATES", "HAS_INDICATOR_VALUE",
}
ALLOWED_PARAMS = {
    "variety_ids", "condition_ids", "indicator_ids", "disease_ids", "entity_ids",
    "keywords", "limit",
}

NODE_RE = re.compile(r"\(\s*[A-Za-z_]*\s*:\s*([A-Za-z_][A-Za-z0-9_]*)")
REL_RE = re.compile(r"\[\s*[A-Za-z_]*\s*:\s*([A-Z_][A-Z0-9_]*)")
PARAM_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")


def rows(path: Path):
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not GRAPH.is_dir():
        print("[失败] 缺少 graph/ 目录")
        return 1

    files = sorted(GRAPH.glob("*.cypher")) + sorted((GRAPH / "queries").glob("*.cypher"))
    if not files:
        errors.append("graph/ 下没有 cypher 文件")

    for path in files:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(BASE)
        # 注释里的占位符（如「MERGE (n:Label …)」「[r:PREDICATE]」）不算真实标签/关系
        code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))
        labels = set(NODE_RE.findall(code))
        bad_labels = labels - LABELS
        if bad_labels:
            errors.append(f"{rel}: 未定义节点标签 {sorted(bad_labels)}")
        rels = set(REL_RE.findall(code))
        bad_rels = rels - PREDICATES
        if bad_rels:
            errors.append(f"{rel}: 未定义关系类型 {sorted(bad_rels)}")
        params = set(PARAM_RE.findall(code))
        bad_params = params - ALLOWED_PARAMS
        if bad_params:
            errors.append(f"{rel}: 未知参数 {sorted(bad_params)}（允许 {sorted(ALLOWED_PARAMS)}）")
        if path.parent.name == "queries":
            if "RETURN" not in code.upper():
                errors.append(f"{rel}: 查询模板缺少 RETURN")
            if "LIMIT" not in code.upper():
                errors.append(f"{rel}: 查询模板缺少 LIMIT（防止全图扫描）")

    # schema.cypher：5 类唯一约束
    schema = GRAPH / "schema.cypher"
    if schema.exists():
        s = schema.read_text(encoding="utf-8").upper()
        for label in LABELS:
            if f"REQUIRE N.ID IS UNIQUE" in s and f":{label.upper()}" not in s:
                errors.append(f"schema.cypher: 缺少 {label} 的唯一约束")
        if "CONSTRAINT" not in s:
            errors.append("schema.cypher: 没有 CONSTRAINT 语句")
    else:
        errors.append("缺少 graph/schema.cypher")

    # MERGE 计数与数据一致
    triples = rows(DATA / "triples.csv")
    entities = rows(DATA / "entities.csv")
    sources = rows(DATA / "sources.csv")
    init_nodes = GRAPH / "init_nodes.cypher"
    init_rels = GRAPH / "init_rels.cypher"
    if init_nodes.exists():
        n = len(re.findall(r"^\s*MERGE\b", init_nodes.read_text(encoding="utf-8"), flags=re.MULTILINE | re.IGNORECASE))
        expect = len(entities) + len(sources)
        if n != expect:
            errors.append(f"init_nodes.cypher MERGE 数 {n} != entities+sources = {expect}")
    else:
        errors.append("缺少 graph/init_nodes.cypher")
    if init_rels.exists():
        n = len(re.findall(r"^\s*MERGE\b", init_rels.read_text(encoding="utf-8"), flags=re.MULTILINE | re.IGNORECASE))
        if n != len(triples):
            errors.append(f"init_rels.cypher MERGE 数 {n} != triples.csv 行数 {len(triples)}")
    else:
        errors.append("缺少 graph/init_rels.cypher")

    # subject/object 必须能对应到实体（与数据校验器一致）
    names = {e["name"] for e in entities}
    for r in triples:
        for k in ("subject", "object"):
            if r[k] not in names:
                errors.append(f"triples.csv {r['sid']}: {k}='{r[k]}' 在 entities.csv 中无同名节点")

    # 查询模板覆盖全部意图
    queries = {p.stem for p in (GRAPH / "queries").glob("*.cypher")}
    try:
        schema_json = json.loads((DATA / "schema.json").read_text(encoding="utf-8"))
        intents = set((schema_json.get("intents") or {}).keys()) or {
            "temperature", "humidity", "atmosphere", "shelf_life", "disease_control",
            "disease_risk", "quality_indicator", "variety_compare", "contraindication", "general",
        }
    except Exception:
        intents = {"temperature", "humidity", "atmosphere", "shelf_life", "disease_control",
                   "disease_risk", "quality_indicator", "variety_compare", "contraindication", "general"}
    missing = intents - queries
    if missing:
        warnings.append(f"缺少意图模板：{sorted(missing)}")

    print(f"扫描 cypher 文件 {len(files)} 个；triples {len(triples)} 条；entities {len(entities)} 条")
    for w in warnings:
        print(f"[告警] {w}")
    for e in errors:
        print(f"[错误] {e}")
    if errors:
        print(f"[失败] {len(errors)} 个错误")
        return 1
    print("[通过] Cypher 标签/关系/参数/计数/覆盖 校验全部通过")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
