"""第二轮加固：verified / anchor 证据分级的一致性（模板答案 vs LLM Prompt）。

要求对应：
- anchor 必须明确标「待核验」，不得描述成已证实事实；
- 涉及药剂/浓度/剂量/处理时间的 anchor 证据不得生成具体执行参数，需提示人工确认；
- verified 证据可正常生成执行建议；
- 模板答案与 LLM Prompt 采用同一套证据等级规则（prompt 证据行、规则、模板说明一致）。
"""
from __future__ import annotations

from app.contracts import WARN_ANCHOR_HIGH_RISK, Evidence
from app.qa import build_prompt, compose_steps, template_answer, validate_llm_answer


def _high_risk(status: str) -> Evidence:
    return Evidence(
        eid="E1",
        subject="1-MCP 处理",
        predicate="REQUIRES",
        object="1-MCP 熏蒸 1 μL/L",
        value=1.0,
        unit="μL/L",
        source_ids=["paper_so2_1mcp_shine", "review_sqs_2024"],
        source_titles=["1-MCP 和 SO₂ 处理对阳光玫瑰葡萄贮藏品质及风味的影响"],
        locator="PDF p3 1.2.2",
        status=status,
        confidence=0.8 if status == "verified" else 0.6,
    )


def _temp(status: str = "anchor") -> Evidence:
    return Evidence(
        eid="E1",
        subject="阳光玫瑰",
        predicate="REQUIRES",
        object="低温冷藏 0±0.5℃",
        value_min=-0.5,
        value_max=0.5,
        unit="℃",
        source_ids=["gbt16862_2026", "review_grape_storage"],
        source_titles=["GB/T 16862-2026 鲜食葡萄冷藏技术"],
        locator="7.3 冷藏条件",
        status=status,
        confidence=0.9 if status == "verified" else 0.6,
    )


# ---------------------------------------------------------------- 模板动作
def test_template_steps_do_not_use_anchor_high_risk_params() -> None:
    steps = compose_steps([_high_risk("anchor")], "disease_control")
    assert steps, "应给出方向性步骤（而不是照搬数值）"
    joined = "\n".join(steps)
    assert "1 μL/L" not in joined, f"不得把 anchor 的具体浓度当执行参数：{steps}"
    assert "产品标签" in joined and "技术员" in joined, f"应提示人工/标签确认：{steps}"


def test_template_steps_allow_verified_high_risk_params() -> None:
    steps = compose_steps([_high_risk("verified")], "disease_control")
    joined = "\n".join(steps)
    assert "1 μL/L" in joined, f"已核验证据可生成具体执行参数：{steps}"


# ---------------------------------------------------------------- 模板答案与 LLM Prompt
def test_template_answer_marks_anchor_unverified() -> None:
    answer = template_answer("temperature", "阳光玫瑰几度", [_temp("anchor")], [], False)
    assert "待核验" in answer, f"anchor 证据必须显式标注待核验：{answer!r}"
    assert "说明：" in answer


def test_template_answer_high_risk_anchor_adds_manual_confirmation() -> None:
    answer = template_answer("disease_control", "1-MCP 怎么用", [_high_risk("anchor")], [], False)
    assert "待核验" in answer
    assert ("产品标签" in answer) or ("技术员" in answer), (
        f"高风险 anchor 证据应提示人工确认：{answer!r}"
    )


def test_prompt_and_template_share_anchor_rule() -> None:
    prompt = build_prompt("1-MCP 怎么用", [_high_risk("anchor")])
    system = prompt[0]["content"]
    evidence_block = system.split("【证据】", 1)[-1]
    # Prompt 规则：待核验不得当已证实事实、高风险不得给具体参数
    assert "待核验" in system
    assert "不得给出具体执行参数" in system
    assert "高风险待核验" in evidence_block, evidence_block
    # 模板同样把 anchor 标成待核验（两边口径一致）
    answer = template_answer("disease_control", "1-MCP 怎么用", [_high_risk("anchor")], [], False)
    assert "待核验" in answer


def test_prompt_marks_verified_evidence_as_confirmed() -> None:
    prompt = build_prompt("阳光玫瑰几度", [_temp("verified")])
    evidence_block = prompt[0]["content"].split("【证据】", 1)[-1]
    assert "已核验" in evidence_block
    assert "高风险待核验" not in evidence_block


# ---------------------------------------------------------------- 混合 verified / anchor 反例（第三轮加固）
def _hr(eid: str, status: str, *, value: float = 1.0) -> Evidence:
    return Evidence(
        eid=eid, subject="1-MCP 处理", predicate="REQUIRES", object=f"1-MCP 熏蒸 {value:g} μL/L",
        value=value, unit="μL/L",
        source_ids=["paper_so2_1mcp_shine", "review_sqs_2024"],
        source_titles=["1-MCP 和 SO₂ 处理对阳光玫瑰葡萄贮藏品质及风味的影响"],
        locator="PDF p3 1.2.2", status=status,
        confidence=0.8 if status == "verified" else 0.6,
    )


def _unrelated_verified_temp() -> Evidence:
    return Evidence(
        eid="E9", subject="阳光玫瑰", predicate="REQUIRES", object="低温冷藏 0±0.5℃",
        value_min=-0.5, value_max=0.5, unit="℃",
        source_ids=["gbt16862_2026"], status="verified", confidence=0.9,
    )


def test_anchor_high_risk_not_cleared_by_uncited_verified_in_evidence() -> None:
    """verified 证据只在 evidence 列表里、未被本句引用 → 不能为 anchor 参数背书。"""
    anchor = _hr("E1", "anchor")
    issues, critical = validate_llm_answer("结论：按 1 μL/L 浓度熏蒸 4h [E1]。", [anchor, _unrelated_verified_temp()])
    assert WARN_ANCHOR_HIGH_RISK in issues, issues
    assert critical is True


def test_anchor_high_risk_not_cleared_by_cited_but_unrelated_verified() -> None:
    """引用了 verified 证据，但它是温度证据、不支撑该药剂参数 → 仍告警。"""
    anchor = _hr("E1", "anchor")
    unrelated = _unrelated_verified_temp()
    issues, _critical = validate_llm_answer(
        "结论：按 1 μL/L 浓度熏蒸 4h [E1][E9]。", [anchor, unrelated]
    )
    assert WARN_ANCHOR_HIGH_RISK in issues, issues


def test_anchor_high_risk_cleared_by_cited_verified_same_param() -> None:
    """本句实际引用 + 已核验 + 同为高风险参数且数值一致 → 放行。"""
    anchor = _hr("E1", "anchor", value=1.0)
    verified = _hr("E2", "verified", value=1.0)
    issues, _critical = validate_llm_answer(
        "结论：按 1 μL/L 浓度熏蒸 [E1][E2]。", [anchor, verified]
    )
    assert WARN_ANCHOR_HIGH_RISK not in issues, issues


def test_anchor_high_risk_not_cleared_by_cited_verified_different_param() -> None:
    """引用的 verified 也是高风险证据、但数值不同（2 vs 1 μL/L）→ 不能背书。"""
    anchor = _hr("E1", "anchor", value=1.0)
    verified = _hr("E2", "verified", value=2.0)
    issues, _critical = validate_llm_answer(
        "结论：按 1 μL/L 浓度熏蒸 [E1][E2]。", [anchor, verified]
    )
    assert WARN_ANCHOR_HIGH_RISK in issues, issues
