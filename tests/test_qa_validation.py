"""第二轮加固：引用 / 事实句 / 数值校验（app/qa.py）。

覆盖：
- 引用规范：全角【E1】、小写 [e1] 与半角 [E1] 等价（编号体系不变）；
- 事实句缺少引用 → unsupported_fact（规则启发式，非语义蕴含）；
- 有效编号但与句子字面无关 → citation_mismatch:E#；
- LLM 关键数值错误（越界/无来源）不能只加 warning，必须回退模板；
- 有效引用 + 证据内数值的 LLM 答案保留（不误杀）；
- 问题里的数字不再进入数值白名单（复述用户错误数字仍会告警）；
- 越界问句（零下 / 冷冻口语）能触发 out_of_range。
"""
from __future__ import annotations

import pytest
from _support import DATA, make_local_store

from app.contracts import (
    WARN_ANCHOR_HIGH_RISK,
    WARN_LLM_ANSWER_REJECTED,
    WARN_OUT_OF_RANGE,
    WARN_UNSUPPORTED_FACT,
    Evidence,
)
from app.qa import (
    _canonicalize_citations,
    check_numbers,
    validate_llm_answer,
    verify_citations,
)


@pytest.fixture(scope="module")
def store():
    assert (DATA / "triples.csv").is_file()
    return make_local_store()


@pytest.fixture(autouse=True)
def _clear_llm_cache():
    from app import qa

    qa._LLM_CACHE.clear()
    yield
    qa._LLM_CACHE.clear()


class _StubLLM:
    """离线 Stub：固定返回文本，不触网。"""

    available = True
    last_usage = {"model": "stub-offline"}

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def complete(self, messages, **kwargs):  # noqa: ANN001 - 与 LLMClient 同签名
        self.calls += 1
        return self.text


def _temp_evidence() -> Evidence:
    return Evidence(
        eid="E1",
        subject="阳光玫瑰",
        predicate="REQUIRES",
        object="低温冷藏 0±0.5℃",
        value_min=-0.5,
        value_max=0.5,
        unit="℃",
        source_ids=["gbt16862_2026"],
        source_titles=["GB/T 16862-2026 鲜食葡萄冷藏技术"],
        status="verified",
        confidence=0.9,
    )


# ---------------------------------------------------------------- 引用规范
def test_canonicalize_fullwidth_and_lowercase_citations() -> None:
    assert _canonicalize_citations("见【E1】与 [e2] 以及 [E3]") == "见[E1]与 [E2] 以及 [E3]"


def test_verify_citations_accepts_fullwidth_and_lowercase() -> None:
    ev = _temp_evidence()
    cited, warnings = verify_citations("结论：0±0.5℃ 冷藏（【E1】）。", [ev])
    assert cited == ["E1"]
    assert "no_citation" not in warnings

    cited2, warnings2 = verify_citations("结论：0±0.5℃ 冷藏（[e1]）。", [ev])
    assert cited2 == ["E1"]
    assert warnings2 == []


def test_verify_citations_still_flags_invalid_id() -> None:
    ev = _temp_evidence()
    cited, warnings = verify_citations("结论：0±0.5℃（[E1]），另见【E9】。", [ev])
    assert cited == ["E1"]
    assert "invalid_citation:E9" in warnings


# ---------------------------------------------------------------- 事实句 / 引用相关性
def test_fact_sentence_without_citation_is_flagged() -> None:
    issues, critical = validate_llm_answer("结论：阳光玫瑰冷藏温度 0±0.5℃。", [_temp_evidence()])
    assert WARN_UNSUPPORTED_FACT in issues
    assert critical is False, "缺引用属规则告警，不应触发模板回退（关键数值才回退）"


def test_valid_citation_but_irrelevant_to_sentence_is_flagged() -> None:
    issues, critical = validate_llm_answer("结论：巨峰比较耐放 [E1]。", [_temp_evidence()])
    assert any(code.startswith("citation_mismatch:") for code in issues), issues
    assert critical is False


def test_related_citation_has_no_mismatch_warning() -> None:
    issues, _critical = validate_llm_answer("结论：阳光玫瑰冷藏温度 0±0.5℃ [E1]。", [_temp_evidence()])
    assert not any(code.startswith("citation_mismatch:") for code in issues), issues


# ---------------------------------------------------------------- 数值校验（问题数字不豁免）
def test_question_number_is_not_whitelisted_temperature() -> None:
    warnings = check_numbers("建议在 -18℃ 冷冻。", [_temp_evidence()], "零下18度")
    assert any(w.startswith("out_of_range") for w in warnings), warnings


def test_question_number_is_not_whitelisted_percent() -> None:
    ev = Evidence(
        eid="E1", subject="阳光玫瑰", predicate="REQUIRES", object="低温冷藏 0±0.5℃",
        value_min=-0.5, value_max=0.5, unit="℃",
    )
    warnings = check_numbers("湿度保持 45% 就行。", [ev], "45%湿度行吗")
    assert any(w.startswith("unsourced_number") for w in warnings), warnings


def test_fake_llm_number_is_critical() -> None:
    issues, critical = validate_llm_answer("结论：阳光玫瑰在 25℃ 下可存放 6 个月 [E1]。", [_temp_evidence()])
    assert critical is True, f"编造数值必须判为关键错误：{issues}"
    assert any(w.startswith(("out_of_range", "unsourced_number")) for w in issues), issues


# ---------------------------------------------------------------- LLM 回退 / 保留
def test_llm_critical_number_error_falls_back_to_template(store) -> None:
    from app.qa import answer_question

    stub = _StubLLM("结论：阳光玫瑰在 25℃ 下可存放 6 个月 [E1]。")
    result = answer_question(
        "阳光玫瑰放冷库该调到多少度？", store=store, llm=stub, allow_llm=True
    )
    assert stub.calls >= 1, "应走 LLM 分支"
    assert result.mode == "template", f"关键数值错误必须回退模板，实际 mode={result.mode}"
    assert WARN_LLM_ANSWER_REJECTED in result.warnings, result.warnings
    assert any(w.startswith(("out_of_range", "unsourced_number")) for w in result.warnings), result.warnings
    assert "25" not in result.answer, f"回退后的答案不得保留编造数值：{result.answer!r}"


def test_llm_valid_answer_with_fullwidth_citation_is_kept(store) -> None:
    from app.qa import answer_question

    stub = _StubLLM("结论：阳光玫瑰冷藏温度 0±0.5℃ 【E1】。")
    result = answer_question(
        "阳光玫瑰放冷库该调到多少度？", store=store, llm=stub, allow_llm=True
    )
    assert result.mode == "llm", f"引用有效、数值在证据内的答案不应回退：{result.warnings}"
    assert "E1" in result.cited_ids
    assert "【E1】" not in result.answer, "全角引用应规范成半角 [E1]"


def test_llm_invalid_citation_falls_back(store) -> None:
    from app.qa import answer_question

    stub = _StubLLM("结论：冷藏温度 0±0.5℃ 即可 [E9]。")
    result = answer_question(
        "阳光玫瑰放冷库该调到多少度？", store=store, llm=stub, allow_llm=True
    )
    assert result.mode == "template"
    assert any("invalid_citation:E9" in w for w in result.warnings), result.warnings


# ---------------------------------------------------------------- 越界问句（口语）
@pytest.mark.parametrize(
    "question",
    ["零下18度能放吗？", "阳光玫瑰零下18度能放吗", "冻起来能存一年吗？"],
)
def test_colloquial_below_zero_questions_are_out_of_range(store, question: str) -> None:
    from app.qa import answer_question

    result = answer_question(question, store=store, allow_llm=False)
    assert result.intent == "temperature", f"{question!r} 应优先按 temperature 处理，实际 {result.intent}"
    assert WARN_OUT_OF_RANGE in result.warnings, f"{question!r} 应触发 out_of_range：{result.warnings}"
    assert "不可行" in result.answer, f"{question!r} 应明确不可行：{result.answer!r}"


# ---------------------------------------------------------------- 证据分级（anchor）
def test_anchor_high_risk_param_is_critical() -> None:
    anchor = Evidence(
        eid="E1", subject="1-MCP 处理", predicate="REQUIRES", object="1-MCP 熏蒸 1 μL/L",
        value=1.0, unit="μL/L", source_ids=["paper_so2_1mcp_shine", "review_sqs_2024"],
        status="anchor", confidence=0.6,
    )
    issues, critical = validate_llm_answer("结论：按 1 μL/L 浓度熏蒸 4h [E1]。", [anchor])
    assert WARN_ANCHOR_HIGH_RISK in issues, issues
    assert critical is True


def test_verified_high_risk_param_can_be_used() -> None:
    verified = Evidence(
        eid="E1", subject="1-MCP 处理", predicate="REQUIRES", object="1-MCP 熏蒸 1 μL/L",
        value=1.0, unit="μL/L", source_ids=["paper_so2_1mcp_shine", "review_sqs_2024"],
        status="verified", confidence=0.8,
    )
    issues, critical = validate_llm_answer("结论：按 1 μL/L 浓度熏蒸 4h [E1]。", [verified])
    assert WARN_ANCHOR_HIGH_RISK not in issues, issues


# ---------------------------------------------------------------- 引用不匹配 → 纠正一次 → 失败回退
class _FakeStore:
    """只返回固定证据的最小 store（不查库，便于构造跨品种/跨病害引用场景）。"""

    name = "fake"

    def __init__(self, evidence: list[Evidence]) -> None:
        self._evidence = evidence

    def execute(self, spec):  # noqa: ANN001 - 与被测协议一致
        return list(self._evidence)


class _SeqLLM:
    """按顺序返回预设文本；耗尽后重复最后一条。"""

    available = True
    last_usage: dict = {}

    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.calls = 0

    def complete(self, messages, **kwargs):  # noqa: ANN001
        index = min(self.calls, len(self.texts) - 1)
        self.calls += 1
        return self.texts[index]


def _shine_temp() -> Evidence:
    return Evidence(
        eid="", subject="阳光玫瑰", predicate="REQUIRES", object="低温冷藏 0±0.5℃",
        value_min=-0.5, value_max=0.5, unit="℃",
        properties={"subject_id": "shine_muscat", "object_id": "cold_0"},
        source_ids=["gbt16862_2026", "review_grape_storage"], status="verified", confidence=0.9,
    )


def _kyoho_temp() -> Evidence:
    return Evidence(
        eid="", subject="巨峰", predicate="REQUIRES", object="低温冷藏 -1~0℃",
        value_min=-1.0, value_max=0.0, unit="℃",
        properties={"subject_id": "kyoho", "object_id": "cold_neg1"},
        source_ids=["gbt16862_2026"], status="verified", confidence=0.8,
    )


def _wrong_disease() -> Evidence:
    return Evidence(
        eid="", subject="灰霉病", predicate="PREVENTED_BY", object="焦亚硫酸盐缓释片",
        properties={"subject_id": "gray_mold", "object_id": "so2_pad"},
        source_ids=["paper_so2_pad_1mcp_shine", "ops_grape_ny1199"], status="verified", confidence=0.7,
    )


def test_cross_variety_wrong_citation_triggers_one_correction(store) -> None:
    from app.qa import answer_question

    llm = _SeqLLM([
        "结论：阳光玫瑰适宜冷藏温度 0±0.5℃ [E2]。",  # E2=巨峰，跨品种错引
        "结论：阳光玫瑰适宜冷藏温度 0±0.5℃ [E1]。",  # 纠正为正确证据
    ])
    result = answer_question(
        "阳光玫瑰放冷库该调到多少度？",
        store=_FakeStore([_shine_temp(), _kyoho_temp()]),
        llm=llm,
        allow_llm=True,
    )
    assert llm.calls == 2, f"引用不匹配应触发一次纠正（共 2 次调用），实际 {llm.calls}"
    assert result.mode == "llm", result.warnings
    assert "E1" in result.cited_ids
    assert not any(w.startswith("citation_mismatch") for w in result.warnings), result.warnings


def test_cross_variety_wrong_citation_correction_failure_falls_back(store) -> None:
    from app.qa import answer_question

    llm = _SeqLLM(["结论：阳光玫瑰适宜冷藏温度 0±0.5℃ [E2]。"])  # 始终错引
    result = answer_question(
        "阳光玫瑰放冷库该调到多少度？",
        store=_FakeStore([_shine_temp(), _kyoho_temp()]),
        llm=llm,
        allow_llm=True,
    )
    assert llm.calls == 2, f"纠正一次后应停止（共 2 次），实际 {llm.calls}"
    assert result.mode == "template", "纠正失败必须回退模板"
    assert WARN_LLM_ANSWER_REJECTED in result.warnings, result.warnings
    assert any(w.startswith("citation_mismatch") for w in result.warnings), result.warnings


def test_wrong_disease_citation_triggers_correction(store) -> None:
    from app.qa import answer_question

    llm = _SeqLLM([
        "结论：阳光玫瑰适宜冷藏温度 0±0.5℃ [E2]。",  # E2=灰霉病处置，用病害证据支撑温度事实
        "结论：阳光玫瑰适宜冷藏温度 0±0.5℃ [E1]。",
    ])
    result = answer_question(
        "阳光玫瑰放冷库该调到多少度？",
        store=_FakeStore([_shine_temp(), _wrong_disease()]),
        llm=llm,
        allow_llm=True,
    )
    assert llm.calls == 2
    assert result.mode == "llm", result.warnings
    assert "E1" in result.cited_ids


def test_numeric_correct_but_wrong_citation_is_still_mismatch() -> None:
    """数值落在某条证据区间内（check_numbers 通过），但引用的是错误品种 → 仍判不匹配。"""
    shine = _shine_temp()
    shine.eid = "E1"
    kyoho = _kyoho_temp()
    kyoho.eid = "E2"
    issues, critical = validate_llm_answer(
        "结论：阳光玫瑰冷藏温度 0±0.5℃ [E2]。",
        [shine, kyoho],
    )
    assert any(code.startswith("citation_mismatch:E2") for code in issues), issues
    assert not any(code.startswith(("out_of_range", "unsourced_number")) for code in issues), issues
    assert critical is False, "纯引用不匹配不应直接判 critical（应先纠正一次）"
