"""意图路由与查询构造测试（docs/api.md §4 + §1.5 黄金集）。

覆盖：12 条口语变体意图命中 ≥10/12、三级路由返回契约、低置信度澄清兜底、
``build_query`` 只产出参数化 QuerySpec（不拼 Cypher 字符串）。
"""
from __future__ import annotations

import json

import pytest

from _support import load_utterances, link, split_ids
from app.contracts import INTENTS, QuerySpec


def _route(question: str):
    from app.planner import route

    return route(question, link(question))


def test_route_contract_shape() -> None:
    result = _route("阳光玫瑰冷藏温度多少合适")
    assert isinstance(result, tuple) and len(result) == 3, f"route 应返回 (intent, confidence, candidates)，实际 {result!r}"
    intent, confidence, candidates = result
    assert intent in INTENTS, f"意图 {intent!r} 不在 INTENTS 枚举内"
    assert 0.0 <= float(confidence) <= 1.0, f"confidence 越界：{confidence}"
    assert isinstance(candidates, list) and candidates, "candidates 应为非空列表"
    scores = []
    for item in candidates:
        assert isinstance(item, tuple) and len(item) == 2, f"candidates 元素应为 (intent, score)：{item!r}"
        candidate_intent, score = item
        assert candidate_intent in INTENTS
        scores.append(float(score))
    assert scores == sorted(scores, reverse=True), f"candidates 未按分数降序：{scores}"


def test_route_low_confidence_falls_back_to_clarification() -> None:
    """api.md §4：最高分 < 0.35 时置信度低（UI 走澄清提示）；无实体无触发词 → general。"""
    for question in ("嗯……这个怎么弄啊", "那啥咋整呢"):
        intent, confidence, _candidates = _route(question)
        assert intent == "general", f"{question!r} 无实体无触发词应路由 general，实际 {intent}"
        assert float(confidence) < 0.35, (
            f"{question!r} 应低置信度（<0.35）以便澄清兜底，实际 confidence={confidence}"
        )


@pytest.mark.parametrize("intent_name", ["temperature", "contraindication", "variety_compare"])
def test_build_query_returns_parameterized_spec_not_cypher_string(intent_name: str) -> None:
    """api.md §4：build_query 只产出参数，不拼 Cypher 字符串。"""
    from app.planner import build_query

    hits = link("阳光玫瑰冷藏温度和SO2禁忌，巨峰红提哪个耐放")
    spec = build_query(intent_name, hits, k=6)
    assert isinstance(spec, QuerySpec), f"build_query 应返回 QuerySpec，实际 {type(spec).__name__}"
    assert spec.intent == intent_name
    assert isinstance(spec.params, dict)
    assert spec.params, f"{intent_name} 的 QuerySpec.params 不应为空"
    blob = json.dumps(spec.params, ensure_ascii=False, default=str).upper()
    for token in ("MATCH", "RETURN", "CREATE", "MERGE", "WHERE", "OPTIONAL"):
        assert token not in blob, f"params 中出现 Cypher 语法 {token!r}（禁止拼接 Cypher）：{spec.params}"
    if spec.cypher_file:
        assert spec.cypher_file.endswith(".cypher"), f"cypher_file 应是文件名：{spec.cypher_file!r}"
    assert isinstance(spec.cypher_params, dict)


def test_build_query_carries_hit_entity_ids_as_parameters() -> None:
    from app.planner import build_query

    hits = link("阳光玫瑰冷藏温度多少合适")
    assert any(hit.node_id == "shine_muscat" for hit in hits)
    spec = build_query("temperature", hits, k=6)
    blob = json.dumps(spec.params, ensure_ascii=False, default=str)
    assert "shine_muscat" in blob, f"temperature 查询参数未携带命中实体 id：{spec.params}"


# ---------------------------------------------------------------- 黄金集意图路由
_UTTERANCES = load_utterances()


@pytest.mark.parametrize(
    "row",
    _UTTERANCES,
    ids=[row["id"] for row in _UTTERANCES],
)
def test_golden_variant_intent_routes_correctly(row: dict) -> None:
    question = row["utterance"]
    expected = str(row.get("expected_intent") or "").strip()
    actual, confidence, candidates = _route(question)
    assert expected in INTENTS, f"{row['id']} expected_intent={expected!r} 不在枚举内"
    assert actual == expected, (
        f"{row['id']} {question!r} 期望意图 {expected}，实际 {actual}（conf={confidence:.2f}，"
        f"候选={candidates[:3]}，note={row.get('note', '')}）"
    )


def test_golden_variant_intent_hit_rate_at_least_10_of_12() -> None:
    passed = 0
    failures = []
    for row in _UTTERANCES:
        expected = str(row.get("expected_intent") or "").strip()
        actual, confidence, _candidates = _route(row["utterance"])
        if actual == expected:
            passed += 1
        else:
            failures.append(f"{row['id']}:{expected}->{actual}({confidence:.2f})")
    assert passed >= 10, f"意图命中 {passed}/12 < 10/12：{failures}"


def test_planner_rules_module_is_importable_and_has_trigger_words() -> None:
    """api.md §4：触发词表放 app/planner_rules.py，供 qa-tester 只读引用做断言。"""
    import app.planner_rules as rules

    blob_parts = []
    for name, value in vars(rules).items():
        if name.startswith("__"):
            continue
        if isinstance(value, str):
            blob_parts.append(value)
        elif isinstance(value, (dict, list, tuple, set)):
            blob_parts.append(json.dumps(value, ensure_ascii=False, default=str))
    blob = "\n".join(blob_parts)
    assert any(word in blob for word in ("几度", "温度", "多少度")), (
        "planner_rules 中找不到温度类触发词（几度/温度/多少度）"
    )
