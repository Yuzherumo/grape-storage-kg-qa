"""数值一致性校验单测（docs/api.md §6 check_numbers、§8 告警码）。

被测：``app.qa.check_numbers(answer, evidence) -> list[str]``
覆盖：± 区间容忍、单位（℃/%/月）、越界 ``out_of_range``、证据外数字 ``unsourced_number:*``。
证据用合成 :class:`app.contracts.Evidence`，不依赖 data/ 与邻居写区。
"""
from __future__ import annotations

import pytest

from _support import make_evidence
from app.contracts import WARN_OUT_OF_RANGE


def _check(answer: str, evidence: list) -> list[str]:
    from app.qa import check_numbers

    warnings = check_numbers(answer, evidence)
    assert isinstance(warnings, list), f"check_numbers 应返回 list[str]，实际 {type(warnings).__name__}"
    for warning in warnings:
        assert isinstance(warning, str), f"告警项应为字符串：{warning!r}"
    return warnings


def _has(warnings: list[str], code: str) -> bool:
    return any(code in str(warning) for warning in warnings)


def _temp_evidence():
    return make_evidence(
        eid="E1",
        subject="阳光玫瑰",
        predicate="REQUIRES",
        object="低温冷藏 0±0.5℃",
        unit="℃",
        value_min=-0.5,
        value_max=0.5,
        quote="冷藏温度宜控制在 0±0.5 ℃",
    )


def _humidity_evidence():
    return make_evidence(
        eid="E2",
        subject="阳光玫瑰",
        predicate="REQUIRES",
        object="相对湿度 90~95%",
        unit="%",
        value_min=90,
        value_max=95,
        quote="相对湿度宜保持在 90~95%",
    )


def test_check_numbers_in_range_answer_has_no_warnings() -> None:
    # 答案同时出现温度与湿度数值 → 证据必须同时提供两类，才能断言「证据内数值不告警」
    warnings = _check(
        "建议在 0±0.5℃ 条件下冷藏，并保持相对湿度 90~95%。",
        [_temp_evidence(), _humidity_evidence()],
    )
    assert not _has(warnings, WARN_OUT_OF_RANGE), f"区间内数值不应报 out_of_range：{warnings}"
    assert not _has(warnings, "unsourced_number"), f"证据内数值不应报 unsourced_number：{warnings}"


def test_check_numbers_boundary_values_are_accepted() -> None:
    low, high = _temp_evidence(), _humidity_evidence()
    for answer in ("温度控制在 -0.5℃ 即可", "温度控制在 0.5℃ 即可", "湿度保持 90%", "湿度保持 95%"):
        warnings = _check(answer, [low, high])
        assert not _has(warnings, WARN_OUT_OF_RANGE), f"{answer!r} 是区间边界，不应报越界：{warnings}"


def test_check_numbers_out_of_range_temperature_is_flagged() -> None:
    warnings = _check("阳光玫瑰放 5℃ 冷藏就行。", [_temp_evidence()])
    assert _has(warnings, WARN_OUT_OF_RANGE), f"5℃ 超出 0±0.5℃ 证据区间，应报 out_of_range：{warnings}"


def test_check_numbers_out_of_range_beyond_pm_range_is_flagged() -> None:
    warnings = _check("冷藏温度 1.2℃ 比较合适。", [_temp_evidence()])
    assert _has(warnings, WARN_OUT_OF_RANGE), f"1.2℃ 超出 ±0.5 区间，应报越界：{warnings}"


def test_check_numbers_out_of_range_humidity_is_flagged() -> None:
    warnings = _check("库房湿度调到 70% 就行。", [_humidity_evidence()])
    assert _has(warnings, WARN_OUT_OF_RANGE), f"70% 低于 90~95%，应报越界：{warnings}"


def test_check_numbers_unsourced_number_is_flagged() -> None:
    """证据里只有温度、没有湿度：答案里的 45% 属证据外数字（§8 unsourced_number:*）。"""
    warnings = _check("温度 0℃，湿度控制在 45% 就行。", [_temp_evidence()])
    assert _has(warnings, "unsourced_number"), f"45% 无证据支撑，应报 unsourced_number：{warnings}"


def test_check_numbers_fake_llm_answer_is_caught() -> None:
    """模拟 LLM 编造：证据是 0±0.5℃ / 耐贮 2~4 月，答案却宣称 25℃ 能放 6 个月。"""
    evidence = [
        _temp_evidence(),
        make_evidence(
            eid="E2",
            subject="阳光玫瑰",
            predicate="HAS_INDICATOR_VALUE",
            object="耐贮性 2~4 月",
            unit="月",
            value_min=2,
            value_max=4,
            quote="阳光玫瑰耐贮性约 2~4 个月",
        ),
    ]
    warnings = _check("阳光玫瑰在 25℃ 常温下可以存放 6 个月，仍然新鲜。", evidence)
    assert _has(warnings, WARN_OUT_OF_RANGE) or _has(warnings, "unsourced_number"), (
        f"编造数值必须被拦住（out_of_range / unsourced_number），实际 {warnings}"
    )


def test_check_numbers_no_numbers_in_answer_has_no_warnings() -> None:
    warnings = _check("可参考图谱证据中的冷藏建议。", [_temp_evidence()])
    assert not _has(warnings, WARN_OUT_OF_RANGE)
    assert not _has(warnings, "unsourced_number")


def test_check_numbers_empty_evidence_and_numeric_answer() -> None:
    """无证据时答案任何数值都不可溯源，应产生告警（不能静默放行）。"""
    warnings = _check("建议 0℃ 冷藏。", [])
    assert warnings, "无证据却出现数值，check_numbers 必须给出告警"
