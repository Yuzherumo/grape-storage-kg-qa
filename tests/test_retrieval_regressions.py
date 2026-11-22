"""第一轮低风险修复的回归测试：跨类别兜底、意图/主题、实体链接、证据一致性。"""
from __future__ import annotations

import pytest
from _support import make_local_store

from app.config import load_settings
from app.contracts import WARN_NO_EVIDENCE
from app.linking import link_entities, load_catalog
from app.planner import detect_topics, route
from app.qa import answer_question


@pytest.fixture(scope="module")
def store():
    return make_local_store()


@pytest.fixture(scope="module")
def catalog():
    settings = load_settings()
    return load_catalog(str(settings.data_path / "entities.csv"))


def _ask(store, question: str):
    return answer_question(question, store=store, allow_llm=False)


def _ids(hits) -> set[str]:
    return {hit.node_id for hit in hits}


# ---------------------------------------------------------------- 实体链接
def test_facility_words_do_not_link_to_specific_temperature(catalog) -> None:
    for word in ("冷库", "冷藏库", "库房", "气调库"):
        assert _ids(link_entities(word, catalog)) == set(), f"{word} 不应绑定具体温度条件"
    assert "cold_0" not in _ids(link_entities("冷库湿度要调到多少？", catalog))


def test_extra_synonyms_link_without_false_entity(catalog) -> None:
    expected = {
        "SO2": "so2_fumigation",
        "SO₂": "so2_fumigation",
        "1MCP": "mcp_1",
        "包装": "package_weight",
        "潮气": "rh_90_95",
        "发软": "firmness",
    }
    for text, node_id in expected.items():
        assert node_id in _ids(link_entities(text, catalog)), f"{text!r} 应命中 {node_id}"


# ---------------------------------------------------------------- 路由/主题
@pytest.mark.parametrize(
    "question, expected_topic",
    [
        ("巨峰预冷要多久？", "precool"),
        ("阳光玫瑰采后多久要预冷完？", "precool"),
        ("葡萄运输温度多少？", "transport"),
        ("采后包装有什么要求？", "packaging"),
        ("常温放几天会坏？", "room_temp"),
    ],
)
def test_topics_are_detected(question: str, expected_topic: str) -> None:
    assert expected_topic in detect_topics(question)


@pytest.mark.parametrize(
    "question, expected_intent",
    [
        ("巨峰预冷要多久？", "general"),
        ("阳光玫瑰采后多久要预冷完？", "general"),
        ("葡萄运输温度多少？", "general"),
        ("采后包装有什么要求？", "general"),
        ("常温放几天会坏？", "general"),
    ],
)
def test_condition_questions_do_not_enter_wrong_intent(question: str, expected_intent: str) -> None:
    hits = link_entities(question, load_catalog(str(load_settings().data_path / "entities.csv")))
    intent, _confidence, _candidates = route(question, hits)
    assert intent == expected_intent, question


# ---------------------------------------------------------------- 原报告重点场景
def test_q04_generic_humidity_uses_humidity_category(store) -> None:
    result = _ask(store, "冷库湿度要调到多少？")
    assert result.intent == "humidity"
    assert result.evidence, "通用湿度应该有类别证据"
    assert all("湿度" in (e.subject + e.object) for e in result.evidence)
    assert result.cited_ids
    assert WARN_NO_EVIDENCE not in result.warnings
    assert "90~95%" in result.answer


def test_q06_missing_variety_humidity_is_explicit_not_cross_category(store) -> None:
    result = _ask(store, "巨峰贮藏湿度要求？")
    assert result.intent == "humidity"
    assert result.evidence == []
    assert WARN_NO_EVIDENCE in result.warnings
    text = result.answer
    assert "巨峰" in text and ("未收录" in text or "没有" in text)
    assert "预冷" not in text and "低温冷藏" not in text, "不得用温度/预冷兜底回答湿度"


def test_q07_q08_precool_retrieves_precool_evidence(store) -> None:
    for question, variety in (("巨峰预冷要多久？", "巨峰"), ("阳光玫瑰采后多久要预冷完？", "阳光玫瑰")):
        result = _ask(store, question)
        assert result.evidence, question
        assert any("预冷" in (e.subject + e.object) for e in result.evidence), question
        assert any(variety in (e.subject + e.object) for e in result.evidence), question
        assert "预冷" in result.answer
        assert not any("耐贮性" in e.object for e in result.evidence), "预冷问题不应召回耐贮性证据"


def test_q12_transport_temperature_refuses_generic_cold_storage(store) -> None:
    result = _ask(store, "葡萄运输温度多少？")
    assert result.evidence == []
    assert WARN_NO_EVIDENCE in result.warnings
    assert "运输温度" in result.answer and ("未收录" in result.answer or "不能" in result.answer)
    assert "低温冷藏 -1~0℃" not in result.answer, "不能用一般冷藏温度冒充运输温度"


def test_q17_room_temp_quality_not_contraindication(store) -> None:
    result = _ask(store, "常温放几天会坏？")
    assert result.intent == "general"
    assert result.evidence
    assert all("常温" in (e.subject + e.object) for e in result.evidence)
    assert "禁忌" not in result.answer
    assert "失重率" in result.answer or "腐烂率" in result.answer


def test_x01_packaging_query_retrieves_packaging(store) -> None:
    result = _ask(store, "采后包装有什么要求？")
    assert result.evidence
    assert any("包装" in (e.subject + e.object) or "膜" in e.object for e in result.evidence)
    assert "包装" in result.answer or "膜" in result.answer


def test_x05_humidity_synonym_retrieves_humidity(store) -> None:
    result = _ask(store, "库房潮气要控制在多少？")
    assert result.intent == "humidity"
    assert result.evidence
    assert all("湿度" in (e.subject + e.object) for e in result.evidence)
    assert "90~95%" in result.answer


def test_numbers_are_still_strict_after_fix(store) -> None:
    result = _ask(store, "-18℃ 冻起来能存一年吗？")
    assert "out_of_range" in result.warnings
    assert "低温冷藏" in result.answer  # 引用证据内温度，而不是复述 -18℃ 当建议值

def test_q09_so2_contraindication_still_works_after_synonym_fix(store) -> None:
    result = _ask(store, '香印青提用SO₂熏行不行？')
    assert result.intent == 'contraindication'
    assert result.evidence
    assert result.cited_ids
    assert WARN_NO_EVIDENCE not in result.warnings
    assert 'SO₂' in result.answer or '二氧化硫' in result.answer

