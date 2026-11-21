"""把 CSV 生成的 Cypher 导入 Neo4j（可选路径，演示默认走 local 后端）。

用法：
    # 1) 安装驱动（可选依赖）
    .\\.venv\\Scripts\\python.exe -m pip install neo4j

    # 2) 在 .env 里配置 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
    # 3) 导入并校验
    .\\.venv\\Scripts\\python.exe scripts\\load_neo4j.py
    .\\.venv\\Scripts\\python.exe scripts\\load_neo4j.py --database neo4j

行为：
- 依次执行 graph/schema.cypher → graph/init_nodes.cypher → graph/init_rels.cypher；
- 每个文件按「行尾分号」切分为独立语句（生成物每条语句一行）；
- 执行前后打印 count(n)/count(r) 并与 CSV 行数比对；
- 驱动缺失 / 连不上 / 认证失败 → 友好中文提示并返回非 0（不抛原始 traceback）。
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "graph"
DATA = ROOT / "data"
FILES = ["schema.cypher", "init_nodes.cypher", "init_rels.cypher"]


def _load_env() -> dict:
    """优先 python-dotenv，其次极简解析 .env。"""
    env = {}
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def split_statements(text: str) -> list[str]:
    """按行尾分号切分；保留 // 注释行，丢弃空语句。"""
    stmts, buf = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or not stripped:
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).rstrip().rstrip(";").strip()
            if stmt:
                stmts.append(stmt)
            buf = []
    if buf:
        stmt = "\n".join(buf).strip()
        if stmt:
            stmts.append(stmt)
    return stmts


def _expected_counts() -> tuple[int, int]:
    def rows(name: str) -> int:
        p = DATA / name
        if not p.exists():
            return -1
        with p.open(encoding="utf-8-sig", newline="") as f:
            return max(0, sum(1 for _ in csv.DictReader(f)))

    ent = rows("entities.csv")
    src = rows("sources.csv")
    tri = rows("triples.csv")
    return (ent + src if ent >= 0 and src >= 0 else -1), tri


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="导入图谱到 Neo4j（可选）")
    ap.add_argument("--database", default="neo4j", help="目标数据库名（默认 neo4j）")
    ap.add_argument("--uri", default=None)
    ap.add_argument("--user", default=None)
    ap.add_argument("--password", default=None)
    args = ap.parse_args(argv)

    env = _load_env()
    uri = args.uri or env.get("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = args.user or env.get("NEO4J_USER", "neo4j")
    password = args.password or env.get("NEO4J_PASSWORD", "")

    try:
        from neo4j import GraphDatabase  # type: ignore
    except ImportError:
        print("[提示] 未安装 neo4j 驱动，导入被跳过（不影响本地后端演示）。")
        print("       需要时执行：.\\.venv\\Scripts\\python.exe -m pip install neo4j")
        return 2

    if not password:
        print("[提示] 未配置 NEO4J_PASSWORD（.env），无法连接 Neo4j。")
        return 2

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception as exc:  # 连接/认证失败 → 友好提示
        print(f"[提示] 连接 Neo4j 失败（{type(exc).__name__}）：{exc}")
        print(f"       目标 {uri}；请确认服务已启动、账号密码正确（.env 的 NEO4J_*）。")
        return 2

    total = 0
    try:
        with driver.session(database=args.database) as session:
            for name in FILES:
                path = GRAPH / name
                if not path.exists():
                    print(f"[跳过] 缺少文件：{path}")
                    continue
                stmts = split_statements(path.read_text(encoding="utf-8"))
                for stmt in stmts:
                    session.run(stmt).consume()
                total += len(stmts)
                print(f"[执行] {name}: {len(stmts)} 条语句")

            nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            labels = [r["label"] for r in session.run("CALL db.labels() YIELD label RETURN label")]

        exp_nodes, exp_rels = _expected_counts()
        print(f"\n[结果] 节点 {nodes} / 关系 {rels}；语句 {total} 条；标签 {labels}")
        ok = True
        if exp_nodes >= 0 and nodes != exp_nodes:
            print(f"[告警] 节点数 {nodes} != 期望 {exp_nodes}（entities+sources）")
            ok = False
        if exp_rels >= 0 and rels != exp_rels:
            print(f"[告警] 关系数 {rels} != 期望 {exp_rels}（triples.csv 行数）")
            ok = False
        print("[通过] 计数校验一致，Neo4j 图谱可用。" if ok else "[失败] 计数不一致，请检查导入脚本。")
        return 0 if ok else 1
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
