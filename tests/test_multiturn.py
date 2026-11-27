"""第三轮：多轮问答实体继承测试（app/qa.py）。

设计原则：
- 只有「指代式追问」（那/这/它/还有/再…）且本轮未命中实体时才继承上一轮实体；
- 明确的新实体（巨峰/红地球）走实体链接，不继承旧实体；
- 无法识别的新名词（苹果呢）不强行套用旧实体；
- 正常追问（那湿度呢）保留上下文能力。

全部离线（allow_llm=False），不触网。
"""
from __future__ import annotations

import pytest
from _support import DATA, make_local_store

from app.contracts import WARN_NO_EVIDENCE
from app.qa import _is_referential_followup, answer_question


@pytest.fixture(scope="module")
def store():
    assert (DATA / "triples.csv").is_file()
    return make_local_store()


def _ask(store, question: str, context: dict | None = None):
    return answer_question(question, store=store, allow_llm=False, context=context)


def _context(result) -> dict | None:
    """复刻 UI 构造 context 的方式：只有本轮有实体时才传给下一轮。"""
    if not getattr(result, "entities", None):
        return None
    return {
        "intent": result.intent,
        "entities": [
            {"node_id": hit.node_id, "label": hit.label, "surface": hit.surface}
            for hit in result.entities
        ],
    }


def _subjects(result) -> list[str]:
    return [item.subject for item in result.evidence]


# ---------------------------------------------------------------- 指代判定（规则启发式）
@pytest.mark.parametrize(
    "question, expected",
    [
        ("那湿度呢？", True),
        ("那温度呢？", True),
        ("还有呢？", True),
        ("那它呢？", True),
        ("那怎么办？", True),
        ("苹果呢？", False),
        ("那苹果呢？", False),
        ("那巨峰呢？", False),  # 有新实体 → 交给实体链接，不继承
        ("今天天气怎么样", False),
    ],
)
def test_referential_followup_detection(question: str, expected: bool) -> None:
    assert _is_referential_followup(question) is expected, question


# ---------------------------------------------------------------- 场景 1：正常追问继承品种
def test_followup_humidity_inherits_variety(store) -> None:
    first = _ask(store, "阳光玫瑰放冷库该调到多少度？")
    second = _ask(store, "那湿度呢？", _context(first))
    assert second.intent == "humidity"
    assert "承接上一轮" in second.context_note and "阳光玫瑰" in second.context_note
    assert second.evidence, "正常追问应能查到阳光玫瑰湿度证据"
    assert all(item.subject == "阳光玫瑰" for item in second.evidence), _subjects(second)


# ---------------------------------------------------------------- 场景 2：明确新实体不继承旧实体
def test_explicit_new_variety_replaces_old_entity(store) -> None:
    first = _ask(store, "阳光玫瑰放冷库该调到多少度？")
    second = _ask(store, "那巨峰呢？", _context(first))
    assert "承接上一轮" not in second.context_note, "明确新实体不应继承上一轮"
    assert "巨峰" in _subjects(second), f"应回答巨峰：{_subjects(second)}"
    assert "阳光玫瑰" not in _subjects(second), f"不得混入旧品种证据：{_subjects(second)}"


# ---------------------------------------------------------------- 场景 3：无法识别的新话题不套旧实体
def test_unknown_new_topic_does_not_reuse_previous_entities(store) -> None:
    first = _ask(store, "阳光玫瑰放冷库该调到多少度？")
    second = _ask(store, "苹果呢？", _context(first))
    assert "承接上一轮" not in second.context_note, "无法识别的新名词不得继承旧实体"
    assert second.evidence == [], f"不应返回旧品种证据：{[(e.subject, e.object) for e in second.evidence]}"
    assert WARN_NO_EVIDENCE in second.warnings


# ---------------------------------------------------------------- 场景 4：病害追问温度不答品种
def test_disease_followup_temperature_does_not_answer_unrelated_variety(store) -> None:
    first = _ask(store, "冷库里葡萄长白毛了怎么办？")
    second = _ask(store, "那温度呢？", _context(first))
    # 继承的是病害/冷库语境；没有对应证据时应明确拒答，而不是拿阳光玫瑰温度凑答案
    assert not any(item.subject == "阳光玫瑰" for item in second.evidence), _subjects(second)
    if second.evidence == []:
        assert WARN_NO_EVIDENCE in second.warnings


# ---------------------------------------------------------------- 场景 5：新话题后再问湿度
def test_new_topic_then_humidity_does_not_revive_old_variety(store) -> None:
    first = _ask(store, "阳光玫瑰放冷库该调到多少度？")
    apple = _ask(store, "苹果呢？", _context(first))
    third = _ask(store, "那湿度呢？", _context(apple))
    assert "承接上一轮" not in third.context_note, "上一轮没有实体，不应跨话题复活更早的品种"
    assert not any(item.subject == "阳光玫瑰" for item in third.evidence), _subjects(third)


# ---------------------------------------------------------------- 场景 6：连续切换品种
def test_consecutive_variety_switches_use_latest_variety(store) -> None:
    first = _ask(store, "阳光玫瑰放冷库该调到多少度？")
    second = _ask(store, "那巨峰呢？", _context(first))
    third = _ask(store, "那红地球呢？", _context(second))
    fourth = _ask(store, "那湿度呢？", _context(third))
    assert fourth.intent == "humidity"
    assert "承接上一轮" in fourth.context_note and "红地球" in fourth.context_note
    # 红地球没有湿度数据：应明确“暂未收录”，不能拿其他品种凑答案
    assert fourth.evidence == [], _subjects(fourth)
    assert WARN_NO_EVIDENCE in fourth.warnings
    assert "未收录" in fourth.answer or "没有" in fourth.answer
