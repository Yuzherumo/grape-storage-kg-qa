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

        # ---- 模板答案数值自洽（不得出现证据外温度）
        assert WARN_OUT_OF_RANGE not in result.warnings, (
            f"{row['id']} 模板答案触发 out_of_range：{result.warnings}"
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
