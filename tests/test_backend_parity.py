"""双后端证据一致性测试（docs/api.md §5：local / neo4j 证据一致）。

无 neo4j 驱动或无 Neo4j 服务时 ``pytest.skip``（验收允许）。
本地后端健康检查始终运行。
"""
from __future__ import annotations

import os

import pytest
from _support import link, make_local_store

from app.contracts import INTENTS, QuerySpec


def test_local_store_health_and_stats() -> None:
    store = make_local_store()
    ok, message = store.health()
    assert ok is True, f"LocalStore.health() 应为 True：{ok} / {message}"
    assert isinstance(message, str)
    stats = store.stats()
    assert isinstance(stats, dict)
    assert stats.get("nodes", 0) > 0, f"stats.nodes 应 >0：{stats}"
    assert stats.get("rels", 0) > 0, f"stats.rels 应 >0：{stats}"
    assert stats.get("varieties", 0) == 8, f"stats.varieties 应为 8：{stats}"


def _specs_for_parity() -> list[tuple[str, QuerySpec]]:
    """用同一套 planner 生成三组代表性 QuerySpec（温度/禁忌/品种对比）。"""
    from app.planner import build_query

    questions = {
        "temperature": "阳光玫瑰冷藏温度多少合适",
        "contraindication": "SO₂熏蒸对阳光玫瑰有什么禁忌",
        "variety_compare": "巨峰和红提哪个更耐贮藏",
    }
    specs: list[tuple[str, QuerySpec]] = []
    for intent, question in questions.items():
        spec = build_query(intent, link(question), k=10)
        assert isinstance(spec, QuerySpec)
        specs.append((intent, spec))
    return specs


def _neo4j_store_or_skip():
    pytest.importorskip("neo4j", reason="未安装 neo4j 驱动：双后端一致性测试跳过")
    from app.store.neo4j_store import Neo4jStore

    uri = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    try:
        store = Neo4jStore(uri, user, password)
    except Exception as exc:  # noqa: BLE001 - 环境原因一律跳过
        pytest.skip(f"Neo4j 服务不可用（{uri}）：{exc}")
    try:
        ok, message = store.health()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Neo4j health() 失败（{uri}）：{exc}")
    if not ok:
        pytest.skip(f"Neo4j 服务不可用或图谱未导入：{message}")
    return store


def test_local_and_neo4j_evidence_match() -> None:
    neo = _neo4j_store_or_skip()
    local = make_local_store()

    neo_stats = neo.stats()
    if neo_stats.get("nodes", 0) == 0:
        pytest.skip("Neo4j 已连接但图谱为空（未执行 load_neo4j），跳过一致性对比")

    mismatches = []
    for intent, spec in _specs_for_parity():
        local_evidence = local.execute(spec)
        neo_evidence = neo.execute(spec)
        local_keys = {(item.subject, item.predicate, item.object) for item in local_evidence}
        neo_keys = {(item.subject, item.predicate, item.object) for item in neo_evidence}
        if local_keys != neo_keys:
            mismatches.append(
                f"{intent}: local_only={sorted(local_keys - neo_keys)} "
                f"neo4j_only={sorted(neo_keys - local_keys)}"
            )
        for item in local_evidence + neo_evidence:
            assert item.eid == "", "store 层证据 eid 必须留空（由 qa 层分配 E1..En，api.md §5）"
    assert not mismatches, "local 与 neo4j 证据不一致：\n" + "\n".join(mismatches)


def test_all_intents_are_queryable_on_local_store() -> None:
    """每个意图都应能在本地后端执行且返回 list[Evidence]（不抛异常）。"""
    from app.planner import build_query

    store = make_local_store()
    hits = link("阳光玫瑰冷藏温度湿度气调储存病害落粒品种")
    for intent in INTENTS:
        spec = build_query(intent, hits, k=6)
        evidence = store.execute(spec)
        assert isinstance(evidence, list), f"{intent} 返回类型错误：{type(evidence).__name__}"
        for item in evidence:
            assert item.eid == ""
            assert item.subject and item.predicate and item.object
