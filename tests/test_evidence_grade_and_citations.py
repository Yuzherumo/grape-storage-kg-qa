"""第三轮：anchor 确定性措辞 + 无效引用清理的回归测试。"""
from __future__ import annotations

import re

import pytest
from _support import make_local_store

from app import qa
from app.qa import answer_question


@pytest.fixture(scope="module")
def store():
    return make_local_store()


class FakeLLM:
    available = True
    last_usage = {}

    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    def complete(self, messages, **kwargs):  # noqa: ANN001
        self.calls += 1
        return self.text


def _ask(store, question: str, text: str):
    qa._LLM_CACHE.clear()
    return answer_question(question, store=store, llm=FakeLLM(text), allow_llm=True)


def _refs(answer: str) -> set[str]:
    return set(re.findall(r"\[(E\d+)\]", answer or ""))


def _eids(result) -> set[str]:
    return {e.eid for e in result.evidence}


def _assert_no_invalid_refs(result) -> None:
    assert _refs(result.answer) <= _eids(result), (
        f"最终答案出现本轮证据之外的引用：{_refs(result.answer)} vs {sorted(_eids(result))}"
    )


# ---------------------------------------------------------------- anchor 等级
def test_anchor_with_hedge_is_accepted(store) -> None:
    result = _ask(
        store,
        "阳光玫瑰和巨峰哪个更耐放？",
        "结论：阳光玫瑰耐贮性 2~4 月，待核验 [E11]；巨峰耐贮性 3~4 月，待核验 [E13]。",
    )
    assert result.mode == "llm"
    assert "anchor_unverified" in result.warnings
    assert "anchor_overclaim" not in result.warnings
    _assert_no_invalid_refs(result)


def test_anchor_described_as_verified_is_rejected(store) -> None:
    result = _ask(
        store,
        "阳光玫瑰和巨峰哪个更耐放？",
        "结论：根据已核验证据，阳光玫瑰耐贮性 2~4 月 [E11]，巨峰耐贮性 3~4 月 [E13]。",
    )
    assert result.mode == "template"
    assert "anchor_overclaim" in result.warnings
    assert "llm_answer_rejected" in result.warnings
    _assert_no_invalid_refs(result)


def test_verified_certainty_is_allowed(store) -> None:
    result = _ask(
        store,
        "巨峰预冷要多久？",
        "结论：巨峰应在 12h 内预冷到 0℃，已核验 [E1]。",
    )
    assert result.mode == "llm"
    assert "anchor_overclaim" not in result.warnings
    _assert_no_invalid_refs(result)


def test_verified_and_anchor_in_separate_sentences_are_judged_separately(store) -> None:
    result = _ask(
        store,
        "阳光玫瑰和巨峰哪个更耐放？",
        "结论：巨峰可溶性固形物≥14%，已核验 [E1]。阳光玫瑰耐贮性 2~4 月，待核验 [E11]。",
    )
    assert result.mode == "llm"
    assert "anchor_unverified" in result.warnings
    assert "anchor_overclaim" not in result.warnings
    _assert_no_invalid_refs(result)


# ---------------------------------------------------------------- 无效引用
def test_nonexistent_citation_only_is_rejected(store) -> None:
    result = _ask(store, "巨峰预冷要多久？", "结论：巨峰应在 12h 内预冷到 0℃ [E9]。")
    assert result.mode == "template"
    assert "no_citation" in result.warnings
    assert "invalid_citation:E9" in result.warnings
    assert "[E9]" not in result.answer
    _assert_no_invalid_refs(result)


def test_mixed_valid_and_invalid_in_same_sentence_falls_back(store) -> None:
    result = _ask(store, "巨峰预冷要多久？", "结论：巨峰应在 12h 内预冷到 0℃ [E1][E9]。")
    assert result.mode == "template"
    assert "invalid_citation:E9" in result.warnings
    assert "[E9]" not in result.answer
    _assert_no_invalid_refs(result)


def test_invalid_sentence_is_removed_but_valid_sentences_are_kept(store) -> None:
    result = _ask(
        store,
        "巨峰预冷要多久？",
        "结论：巨峰应在 12h 内预冷到 0℃ [E1]。另外请参考不存在的证据 [E9]。",
    )
    assert result.mode == "llm"
    assert "[E9]" not in result.answer
    assert "12h" in result.answer, "有有效引用支持的句子不应被误删"
    assert "invalid_citation:E9" in result.warnings
    _assert_no_invalid_refs(result)


def test_invalid_statement_is_not_kept_without_citation(store) -> None:
    result = _ask(store, "巨峰预冷要多久？", "结论：巨峰不需要预冷 [E9]。")
    assert result.mode == "template"
    assert "巨峰不需要预冷" not in result.answer
    assert "[E9]" not in result.answer
    _assert_no_invalid_refs(result)


def test_fallback_template_has_no_invalid_citations(store) -> None:
    result = _ask(store, "巨峰预冷要多久？", "结论：巨峰应在 12h 内预冷到 0℃ [E9]。")
    assert result.mode == "template"
    assert _refs(result.answer) <= _eids(result)

def test_anchor_uncited_claim_is_rejected(store) -> None:
    result = _ask(
        store,
        '阳光玫瑰和巨峰哪个更耐放？',
        '结论：阳光玫瑰耐贮性 2~4 月，待核验 [E11]。另外阳光玫瑰可以存放一年。',
    )
    assert result.mode == 'template'
    assert 'unsupported_fact' in result.warnings
    assert 'llm_answer_rejected' in result.warnings
    assert '一年' not in result.answer
    _assert_no_invalid_refs(result)


def test_verified_and_anchor_mixed_sentence_with_hedge_is_accepted(store) -> None:
    result = _ask(
        store,
        '阳光玫瑰和巨峰哪个更耐放？',
        '结论：巨峰可溶性固形物≥14%，已核验 [E1]；阳光玫瑰耐贮性 2~4 月，待核验 [E11]。',
    )
    assert result.mode == 'llm'
    assert 'anchor_unverified' in result.warnings
    assert 'anchor_overclaim' not in result.warnings
    _assert_no_invalid_refs(result)

@pytest.mark.parametrize("hedge", ["待核验", "尚需验证", "初步线索"])
def test_anchor_with_various_hedges_is_accepted(store, hedge: str) -> None:
    result = _ask(
        store,
        "阳光玫瑰和巨峰哪个更耐放？",
        f"结论：阳光玫瑰耐贮性 2~4 月，{hedge} [E11]；巨峰耐贮性 3~4 月，{hedge} [E13]。",
    )
    assert result.mode == "llm"
    assert "anchor_overclaim" not in result.warnings
    _assert_no_invalid_refs(result)


@pytest.mark.parametrize("certainty", ["已验证", "已证实", "研究已经证明"])
def test_anchor_with_various_certainty_words_is_rejected(store, certainty: str) -> None:
    result = _ask(
        store,
        "阳光玫瑰和巨峰哪个更耐放？",
        f"结论：阳光玫瑰耐贮性 2~4 月 {certainty} [E11]；巨峰耐贮性 3~4 月 {certainty} [E13]。",
    )
    assert result.mode == "template"
    assert "anchor_overclaim" in result.warnings
    _assert_no_invalid_refs(result)


def test_verified_and_anchor_mixed_sentence_with_anchor_certainty_is_rejected(store) -> None:
    result = _ask(
        store,
        "阳光玫瑰和巨峰哪个更耐放？",
        "结论：巨峰可溶性固形物≥14% [E1]；阳光玫瑰耐贮性 2~4 月已证实 [E11]。",
    )
    assert result.mode == "template"
    assert "anchor_overclaim" in result.warnings
    _assert_no_invalid_refs(result)

