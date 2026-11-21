# -*- coding: utf-8 -*-
"""在嵌入式 openCypher 引擎 Kùzu 上实跑图谱查询，并与本地后端做一致性对照。

为什么不是 Neo4j：当前网络对 dist.neo4j.org / dist.neo4j.com 均返回 403，
无法下载 Neo4j 5 分发包（详见 docs/neo4j_verify.md）。Kùzu 是嵌入式 openCypher
引擎，可在无服务端、无账号的环境里真实执行 Cypher，用于验证：
  1) 图数据模型（59+ 节点 / 108 条关系）能正确建表、入图
  2) 10 类意图的等价 Cypher 查询能跑通、返回预期三元组
  3) 与 app/store/local_store.py 的检索结果集合一致（local ⊆ Cypher 结果）

Neo4j 服务端脚本仍完整交付，并用 scripts/validate_cypher.py 做静态校验；
拿到 Neo4j zip 后可用 scripts/setup_neo4j_portable.ps1 一条命令完成真库导入。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\verify_cypher_engine.py [--keep-db]
退出码：0 = 通过；1 = 不一致/失败。
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
GRAPH = BASE / "graph"
DATA = BASE / "data"
DB_DIR = BASE / ".tmp" / "kuzu_graph"

PRED_LABEL_ORDER = [
    "REQUIRES", "CONTRA_INDICATED_FOR", "AFFECTS", "SUSCEPTIBLE_TO",
    "PREVENTED_BY", "INDUCED_BY", "ALTERNATIVE_TO", "INDICATES", "HAS_INDICATOR_VALUE",
]


def rows(name: str):
    with (DATA / name).open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def q(conn, cypher: str, params: dict | None = None):
    return conn.execute(cypher, params or {})


def fetch(conn, cypher: str, params: dict | None = None):
    res = q(conn, cypher, params)
    out = []
    while res.has_next():
        out.append(tuple(res.get_next()))
    return out


def build_db(conn) -> tuple[int, int]:
    schema = json.loads((DATA / "schema.json").read_text(encoding="utf-8"))
    combos = schema.get("predicate_type_combos") or {}
    if not combos:
        combos = {
            "REQUIRES": {"subject_type": "Variety", "object_type": "Condition"},
            "CONTRA_INDICATED_FOR": {"subject_type": "Condition", "object_type": "Variety"},
            "AFFECTS": {"subject_type": "Condition", "object_type": "QualityIndicator"},
            "SUSCEPTIBLE_TO": {"subject_type": "Variety", "object_type": "Disease"},
            "PREVENTED_BY": {"subject_type": "Disease", "object_type": "Condition"},
            "INDUCED_BY": {"subject_type": "Disease", "object_type": "Condition"},
            "ALTERNATIVE_TO": {"subject_type": "Condition", "object_type": "Condition"},
            "INDICATES": {"subject_type": "QualityIndicator", "object_type": "Disease"},
            "HAS_INDICATOR_VALUE": {"subject_type": "Variety", "object_type": "QualityIndicator"},
        }
    labels = ["Variety", "Condition", "QualityIndicator", "Disease", "Source"]
    for label in labels:
        q(conn, f"CREATE NODE TABLE IF NOT EXISTS {label}("
                "id STRING, name STRING, category STRING, value_min DOUBLE, value_max DOUBLE, "
                "unit STRING, PRIMARY KEY(id))")
    for pred, combo in combos.items():
        s, o = combo["subject_type"], combo["object_type"]
        q(conn, f"CREATE REL TABLE IF NOT EXISTS {pred}(FROM {s} TO {o}, "
                "status STRING, confidence DOUBLE, source_ids STRING)")

    ents = rows("entities.csv")
    srcs = rows("sources.csv")
    triples = rows("triples.csv")
    by_name = {}
    for e in ents:
        label = e["label"]
        q(conn, f"CREATE (:{label} {{id: $id, name: $name, category: $cat}})",
          {"id": e["id"], "name": e["name"], "cat": e.get("category", "")})
        by_name[e["name"]] = label
    for s in srcs:
        q(conn, "CREATE (:Source {id: $id, name: $name, category: $cat})",
          {"id": s["id"], "name": s["title"][:60], "cat": s.get("type", "")})
    for r in triples:
        s_label = r["subject_type"]
        o_label = r["object_type"]
        pred = r["predicate"]
        q(conn,
          f"MATCH (a:{s_label}), (b:{o_label}) WHERE a.name = $subj AND b.name = $obj "
          f"CREATE (a)-[:{pred} {{status: $st, confidence: $cf, source_ids: $src}}]->(b)",
          {"subj": r["subject"], "obj": r["object"], "st": r["status"],
           "cf": float(r["confidence"] or 0.5), "src": r["source_ids"]})
    nodes = fetch(conn, "MATCH (n) RETURN count(n)")[0][0]
    rels = fetch(conn, "MATCH ()-[r]->() RETURN count(r)")[0][0]
    return int(nodes), int(rels)


def in_list(ids: list[str]) -> str:
    """把 node id 转成 Cypher 字面量列表（id 均来自我们自己的数据，白名单字符）。"""
    clean = [i for i in ids if i and all(c.isalnum() or c in "_-" for c in i)]
    return "[" + ", ".join(f'"{i}"' for i in clean) + "]"


def intent_queries(intent: str, ids: dict) -> list[str]:
    v, c, d, qid = ids.get("variety_ids") or [], ids.get("condition_ids") or [], \
        ids.get("disease_ids") or [], ids.get("indicator_ids") or []
    every = ids.get("entity_ids") or []
    qs: list[str] = []
    if intent == "temperature":
        qs.append(f"MATCH (s:Variety)-[:REQUIRES]->(c:Condition) "
                  f"WHERE c.category = '温度' RETURN s.name, 'REQUIRES', c.name")
    elif intent == "humidity":
        qs.append("MATCH (s:Variety)-[:REQUIRES]->(c:Condition) "
                  "WHERE c.category = '湿度' RETURN s.name, 'REQUIRES', c.name")
    elif intent == "atmosphere":
        qs.append("MATCH (s:Variety)-[:REQUIRES]->(c:Condition) "
                  "WHERE c.category = '气调' RETURN s.name, 'REQUIRES', c.name")
    elif intent == "shelf_life":
        qs.append("MATCH (c:Condition)-[:AFFECTS]->(q:QualityIndicator) "
                  "WHERE q.name = '耐贮性' RETURN c.name, 'AFFECTS', q.name")
        qs.append("MATCH (v:Variety)-[:HAS_INDICATOR_VALUE]->(q:QualityIndicator) "
                  "WHERE q.name = '耐贮性' RETURN v.name, 'HAS_INDICATOR_VALUE', q.name")
    elif intent == "disease_control":
        qs.append(f"MATCH (x:Disease)-[:PREVENTED_BY]->(c:Condition) "
                  f"WHERE x.id IN {in_list(d)} RETURN x.name, 'PREVENTED_BY', c.name")
        qs.append(f"MATCH (x:Disease)-[:INDUCED_BY]->(c:Condition) "
                  f"WHERE x.id IN {in_list(d)} RETURN x.name, 'INDUCED_BY', c.name")
    elif intent == "disease_risk":
        qs.append(f"MATCH (v:Variety)-[:SUSCEPTIBLE_TO]->(x:Disease) "
                  f"WHERE x.id IN {in_list(d)} RETURN v.name, 'SUSCEPTIBLE_TO', x.name")
        qs.append(f"MATCH (x:Disease)-[:INDUCED_BY]->(c:Condition) "
                  f"WHERE x.id IN {in_list(d)} RETURN x.name, 'INDUCED_BY', c.name")
    elif intent == "quality_indicator":
        qs.append("MATCH (c:Condition)-[:AFFECTS]->(q:QualityIndicator) "
                  "RETURN c.name, 'AFFECTS', q.name")
        qs.append("MATCH (v:Variety)-[:HAS_INDICATOR_VALUE]->(q:QualityIndicator) "
                  "RETURN v.name, 'HAS_INDICATOR_VALUE', q.name")
    elif intent == "variety_compare":
        vs = in_list(v)
        qs.append(f"MATCH (v:Variety)-[:REQUIRES]->(c:Condition) WHERE v.id IN {vs} "
                  f"RETURN v.name, 'REQUIRES', c.name")
        qs.append(f"MATCH (c:Condition)-[:CONTRA_INDICATED_FOR]->(v:Variety) WHERE v.id IN {vs} "
                  f"RETURN c.name, 'CONTRA_INDICATED_FOR', v.name")
        qs.append(f"MATCH (v:Variety)-[:HAS_INDICATOR_VALUE]->(q:QualityIndicator) WHERE v.id IN {vs} "
                  f"RETURN v.name, 'HAS_INDICATOR_VALUE', q.name")
    elif intent == "contraindication":
        vs = in_list(v)
        qs.append(f"MATCH (c:Condition)-[:CONTRA_INDICATED_FOR]->(v:Variety) WHERE v.id IN {vs} "
                  f"RETURN c.name, 'CONTRA_INDICATED_FOR', v.name")
        qs.append("MATCH (c:Condition)-[:ALTERNATIVE_TO]->(c2:Condition) "
                  "RETURN c.name, 'ALTERNATIVE_TO', c2.name")
    elif intent == "general":
        ids_all = in_list(every)
        if ids_all != "[]":
            qs.append(f"MATCH (a)-[r]->(b) WHERE a.id IN {ids_all} OR b.id IN {ids_all} "
                      f"RETURN a.name, type(r), b.name")
    return qs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-db", action="store_true", help="（已废弃，内存库无需保留）")
    args = ap.parse_args()

    try:
        import kuzu  # type: ignore
    except ImportError:
        print("[跳过] 未安装 kuzu（可选依赖）：.\\\\.venv\\\\Scripts\\\\python.exe -m pip install kuzu")
        return 2

    # Kùzu 0.11 对中文路径有编码问题（UnicodeDecodeError），工作区路径含中文，
    # 因此统一用内存库（进程内建表→灌数据→查询，跑完即释放，无需落盘）。
    db = kuzu.Database(":memory:")
    conn = kuzu.Connection(db)

    ents, srcs, triples = rows("entities.csv"), rows("sources.csv"), rows("triples.csv")
    nodes, rels = build_db(conn)
    expect_nodes = len(ents) + len(srcs)
    expect_rels = len(triples)
    print(f"Kùzu 实跑：节点 {nodes}（期望 {expect_nodes}）/ 关系 {rels}（期望 {expect_rels}）")
    ok = nodes == expect_nodes and rels == expect_rels

    # 与本地后端逐题对照
    from app.config import load_settings
    from app.linking import link_entities, load_catalog
    from app.planner import build_query, route
    from app.store import get_store

    st = load_settings()
    store = get_store(st)
    catalog = load_catalog(str(st.data_path / "entities.csv"))
    questions = [
        ("Q1", "阳光玫瑰放冷库该调到多少度？"),
        ("Q2", "冷库里葡萄长白毛了怎么办？"),
        ("Q3", "葡萄发软掉粒是咋回事？"),
        ("Q4", "用 SO₂ 熏阳光玫瑰行不行？"),
        ("Q5", "阳光玫瑰和巨峰哪个更能放？"),
        ("Q6", "-18℃ 冻起来能存一年吗？"),
    ]
    print("\n题号 | 意图 | 本地证据 | Cypher 等价查询 | 覆盖")
    print("-" * 72)
    for tag, question in questions:
        hits = link_entities(question, catalog)
        intent, _, _ = route(question, hits)
        spec = build_query(intent, hits, k=12)
        local = {(e.subject, e.predicate, e.object) for e in store.execute(spec)}
        cypher_rows = set()
        for cypher in intent_queries(intent, spec.params):
            cypher_rows.update(fetch(conn, cypher))
        covered = local <= cypher_rows
        ok = ok and covered
        print(f"{tag} | {intent} | {len(local)} | {len(cypher_rows)} | {'✅' if covered else '❌'}")
        if not covered:
            for miss in sorted(local - cypher_rows)[:3]:
                print(f"    缺失：{miss}")

    # 定点核对：国标条文三元组必须能查出来
    spot = [
        ("阳光玫瑰", "REQUIRES", "相对湿度 90~95%"),
        ("灰霉病", "PREVENTED_BY", "焦亚硫酸盐缓释片"),
        ("巨峰", "HAS_INDICATOR_VALUE", "耐贮性"),
        ("黑斑病", "INDUCED_BY", "采前降雨"),
    ]
    print("\n定点核对（verified 条文三元组）：")
    for s, p, o in spot:
        got = fetch(conn, f"MATCH (a)-[r:{p}]->(b) WHERE a.name = $subj AND b.name = $obj RETURN count(r)",
                    {"subj": s, "obj": o})[0][0]
        flag = "✅" if got else "❌"
        ok = ok and bool(got)
        print(f"  {flag} {s} -[{p}]-> {o}")

    print("\n[通过] Kùzu 实跑 + 与本地后端一致" if ok else "\n[失败] 存在不一致，请查看上面明细")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
