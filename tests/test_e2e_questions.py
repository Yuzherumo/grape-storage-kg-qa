"""端到端问答测试（Q1~Q6，docs/api.md §6/§10）。

约束：``allow_llm=False``，无网络、无 API key 也必须可跑；模板模式确定性。
- 核心题：证据 ≥1、答案含有效 [E#] 且引用落在 evidence/cited_ids 内、意图与谓词正确、
  关键词命中、模板答案数值自洽、Q1/Q3 有分步动作。
- 越界探针 Q6：答案不得出现证据外温度、不得宣称 -18℃ 适宜。
- LLM 分支打 ``@pytest.mark.llm``，默认由 conftest 跳过。
"""
from __future__ import annotations

import pytest

from _support import (
    DATA,
    cited_refs,
    keyword_present,
    load_eval_questions,
    make_local_store,
    split_keywords,
    unsupported_temperatures,
)
from app.contracts import INTENTS, WARN_OUT_OF_RANGE, AnswerResult


@pytest.fixture(scope="module")
def store():
    assert (DATA / "entities.csv").is_file(), f"缺少 {DATA / 'entities.csv'}（S1 交付物）"
    assert (DATA / "triples.csv").is_file(), f"缺少 {DATA / 'triples.csv'}（S2a 交付物）"
    return make_local_store()


def _ask(store, question: str) -> AnswerResult:
    from app.qa import answer_question

    return answer_question(question, store=store, allow_llm=False)


_EVAL_ROWS = load_eval_questions()


def _row(row_id: str) -> dict:
    for row in _EVAL_ROWS:
        if row["id"] == row_id:
            return row
    raise KeyError(row_id)


@pytest.mark.parametrize("row", _EVAL_ROWS, ids=[row["id"] for row in _EVAL_ROWS])
def test_eval_question_pipeline(store, row: dict) -> None:
    question = row["question"]
    kind = str(row.get("kind") or "core").strip()
    result = _ask(store, question)

    # ---- 结构契约（api.md §2/§10）
    assert isinstance(result, AnswerResult)
    assert isinstance(result.question, str) and result.question.strip()
    assert result.mode == "template", f"allow_llm=False 应走模板模式，实际 mode={result.mode}"
    assert result.intent in INTENTS, f"意图 {result.intent!r} 不在枚举内"
    assert isinstance(result.warnings, list) and all(isinstance(w, str) for w in result.warnings)
    assert isinstance(result.steps, list) and all(isinstance(step, str) for step in result.steps)
    assert isinstance(result.cited_ids, list)
    assert isinstance(result.elapsed_ms, int) and result.elapsed_ms >= 0

    evidence = list(result.evidence)
    eids = {str(item.eid) for item in evidence}
    refs = cited_refs(result.answer)

    if kind == "core":
        # ---- 证据与引用
        assert evidence, f"{row['id']} 核心题必须有 ≥1 条证据（实际 0 条）"
        assert result.answer.strip(), f"{row['id']} 答案为空"
        assert refs, f"{row['id']} 模板答案必须带 [E#] 引用，实际答案：{result.answer!r}"
        missing_refs = [ref for ref in refs if ref not in eids]
        assert not missing_refs, f"{row['id']} 引用了不存在的证据编号 {missing_refs}；eids={sorted(eids)}"
        assert set(refs) <= set(result.cited_ids), (
            f"{row['id']} 答案中的 [E#] 必须出现在 cited_ids：refs={refs} cited={result.cited_ids}"
        )
        assert set(result.cited_ids) <= eids, f"{row['id']} cited_ids 含非法编号：{result.cited_ids}"

        # ---- 意图与谓词（期望值来自 eval_questions.csv，非硬编码）
        assert result.intent == row["expected_intent"], (
            f"{row['id']} 期望意图 {row['expected_intent']}，实际 {result.intent}"
        )
        predicates = {item.predicate for item in evidence}
        assert row["expected_predicate"] in predicates, (
            f"{row['id']} 证据需含 {row['expected_predicate']} 关系，实际 {sorted(predicates)}"
        )

        # ---- 关键词（弱断言：答案或证据命中即可）
        for keyword in split_keywords(row.get("must_keywords")):
            assert keyword_present(keyword, result.answer, evidence), (
                f"{row['id']} 缺少必需关键词 {keyword!r}；答案={result.answer!r}"
            )
        for keyword in split_keywords(row.get("forbidden_keywords")):
            assert keyword not in result.answer.lower(), (
                f"{row['id']} 答案出现禁用关键词 {keyword!r}：{result.answer!r}"
            )

        # ---- 模板答案数值自洽（不得出现证据外温度，也不得报出证据外数字）
        assert WARN_OUT_OF_RANGE not in result.warnings, (
            f"{row['id']} 模板答案触发 out_of_range：{result.warnings}"
        )
        assert not any("unsourced_number" in warning for warning in result.warnings), (
            f"{row['id']} 模板答案出现证据外数字告警（模板答案由证据拼装，不应有假告警）：{result.warnings}"
        )
        assert not unsupported_temperatures(result.answer, evidence), (
            f"{row['id']} 模板答案出现证据外温度：{unsupported_temperatures(result.answer, evidence)}"
        )

        # ---- 分步动作（api.md §6 compose_steps ≤3 步）
        if row["id"] in {"Q1", "Q3"}:
            assert result.steps, f"{row['id']} 应给出分步动作，实际 steps 为空"
            assert len(result.steps) <= 3, f"{row['id']} steps 超过 3 步（api.md §6）"

        # ---- 品种对比卖点：证据必须覆盖 ≥2 个品种（方向二硬证据）
        if result.intent == "variety_compare":
            measured = {
                item.subject
                for item in evidence
                if item.predicate in {"HAS_INDICATOR_VALUE", "REQUIRES", "SUSCEPTIBLE_TO"}
            }
            assert len(measured) >= 2, (
                f"{row['id']} 品种对比题证据只覆盖 {sorted(measured)}（<2 个品种），"
                f"store.variety_compare 应返回双品种证据"
            )
    else:
        # ---- 越界探针：证据只覆盖 0±0.5℃ 一档，答案不得给出证据外温度
        assert isinstance(result.answer, str) and result.answer.strip()
        outside = unsupported_temperatures(result.answer, evidence)
        assert not outside, f"{row['id']} 越界题答案出现证据外温度 {outside}：{result.answer!r}"
        for keyword in split_keywords(row.get("forbidden_keywords")):
            assert keyword not in result.answer.lower(), (
                f"{row['id']} 越界题答案出现禁用关键词 {keyword!r}：{result.answer!r}"
            )
        # 越界请求必须被识别并告警（api.md §8：out_of_range 黄），而不是照单全收
        assert WARN_OUT_OF_RANGE in result.warnings, (
            f"{row['id']} 越界请求（-18℃ vs 证据 0±0.5℃）应触发 out_of_range 告警，"
            f"实际 warnings={result.warnings}"
        )
        # 引用仍须完整：答案（含「现在该做什么」步骤）里的 [E#] 都属于证据且进入 cited_ids
        assert refs, f"{row['id']} 越界题答案也应带 [E#] 引用：{result.answer!r}"
        assert set(refs) <= eids, f"{row['id']} 越界题引用了不存在的证据编号：{refs} vs {sorted(eids)}"
        assert set(refs) <= set(result.cited_ids), (
            f"{row['id']} 越界题答案中的 [E#] 未进入 cited_ids：refs={refs} cited={result.cited_ids}"
        )


def test_template_mode_is_deterministic(store) -> None:
    """api.md §10：同输入两次结果完全一致（elapsed_ms 除外）。"""
    question = _row("Q1")["question"]
    first = _ask(store, question)
    second = _ask(store, question)
    assert first.answer == second.answer, "模板模式答案不确定（两次不同）"
    assert first.intent == second.intent
    assert first.cited_ids == second.cited_ids
    assert [(item.subject, item.predicate, item.object) for item in first.evidence] == [
        (item.subject, item.predicate, item.object) for item in second.evidence
    ]


def test_allow_llm_false_never_calls_llm(store) -> None:
    """api.md §10：allow_llm=False 不触网——即使传入可用 LLM 也不能调用。"""

    class _ForbiddenLLM:
        available = True
        last_usage = {}

        def complete(self, *args, **kwargs):  # pragma: no cover - 被调用即失败
            raise AssertionError("allow_llm=False 时不允许调用 LLM（禁止触网）")

    from app.qa import answer_question

    result = answer_question(
        _row("Q1")["question"],
        store=store,
        llm=_ForbiddenLLM(),  # type: ignore[arg-type]
        allow_llm=False,
    )
    assert result.mode == "template"


def test_low_confidence_question_has_no_evidence_and_warns(store) -> None:
    """无实体无触发词的低置信度问题：不硬凑证据，warnings 应该是 list[str]。"""
    result = _ask(store, "嗯……这个怎么弄啊")
    assert result.intent == "general"
    assert float(result.intent_confidence) < 0.35
    assert result.evidence == [] or isinstance(result.evidence, list)
    assert isinstance(result.warnings, list)


def test_contraindication_step_direction(store) -> None:
    """禁忌题的步骤建议方向必须正确：禁的是「条件」，不是「品种」。

    回归（2026-11）：compose_steps/template_answer 曾把 subject/object 用反，
    对 Q4 生成「不要用 阳光玫瑰，改用 SO₂ 熏蒸」这类反向农事建议。
    数据方向冻结为：条件 -CONTRA_INDICATED_FOR-> 品种；替代条件 -ALTERNATIVE_TO-> 被替代条件。
    """
    for question in ("用SO₂熏阳光玫瑰行不行", "玫瑰香能用SO2熏吗"):
        result = _ask(store, question)
        assert result.intent == "contraindication", f"{question} 意图应为 contraindication"
        contra = [e for e in result.evidence if e.predicate == "CONTRA_INDICATED_FOR"]
        assert contra, f"{question} 缺少 CONTRA_INDICATED_FOR 证据"
        joined = "\n".join(result.steps)
        assert joined, f"{question} 禁忌题应给出步骤建议"
        for e in contra:
            banned, variety = e.subject, e.object
            # 步骤指向被禁条件，且绝不能把品种当成被禁对象
            assert f"不要用 {variety}" not in joined, (
                f"{question} 步骤把品种当成了被禁对象（反向建议）：{result.steps}"
            )
            assert any(f"不要用 {banned}" in step for step in result.steps), (
                f"{question} 步骤未包含「不要用 {banned}」：{result.steps}"
            )
        # 有替代证据时，推荐的是 ALTERNATIVE_TO 的 subject（替代条件）
        alts = [e for e in result.evidence if e.predicate == "ALTERNATIVE_TO"]
        for e in contra:
            alt = next((a for a in alts if a.object == e.subject), None)
            if alt is not None:
                assert any("改用" in s and alt.subject in s for s in result.steps), (
                    f"{question} 步骤应给出替代方案「{alt.subject}」：{result.steps}"
                )
        # 来源标题里的标准编号（如 NY/T 1199-2006）不应判为编造数字
        assert not any("unsourced_number" in w for w in result.warnings), (
            f"{question} 来源标题编号被误判为 unsourced_number：{result.warnings}"
        )


@pytest.mark.llm
def test_llm_mode_citations_valid_when_available(store) -> None:
    """LLM 分支（默认跳过）：有 key/联网时 mode=llm 且引用仍必须可核验。"""
    from app.llm import LLMClient

    client = LLMClient()
    if not getattr(client, "available", False):
        pytest.skip("LLM 不可用（无 DEEPSEEK_API_KEY 或导入失败），跳过 @pytest.mark.llm 分支")

    from app.qa import answer_question

    result = answer_question(_row("Q1")["question"], store=store, llm=client, allow_llm=True)
    assert result.mode in {"llm", "template"}
    if result.mode == "llm":
        eids = {str(item.eid) for item in result.evidence}
        refs = cited_refs(result.answer)
        assert refs, "LLM 答案必须带 [E#] 引用"
        assert set(refs) <= eids
        assert set(refs) <= set(result.cited_ids)
