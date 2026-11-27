"""第四轮交付修复回归（Phase 2，8+1 项定点修复）。

覆盖：
1. 禁忌路由：明确禁忌分数必须压倒 packaging/precool/transport 与 HOWTO 兜底；
2. 多轮追问：「那多少度」「还有呢」继承上一轮实体/意图，只答上一轮品种；
3. LLM 错误分类：按 ``LLMUnavailable.kind`` 映射 timeout/network 与其余错误，写入 llm_meta；
4. 无效引用：首答 [E9] 先清理、不得再触发「没给引用」的重写；
5. 告警码契约：contracts 中所有 WARN_* 在 ui 映射中有中文文案；
6. graph_interactive source_url 只允许 http(s)；
7. LocalStore 默认路径复用（连续两次不重建）+ ui 统计/词表缓存；
8. 品种对比补查后端异常不得写成「图谱未收录」；
9. 非葡萄果品离域拒答，-18℃ 探针保持原行为。

全部离线（allow_llm=False 或假 LLM），不触网。
"""
from __future__ import annotations

import pytest
from _support import DATA, link, make_local_store

from app import contracts, qa, ui
from app.contracts import (
    WARN_LLM_TIMEOUT,
    WARN_LLM_UNAVAILABLE,
    WARN_NO_CITATION,
    WARN_NO_EVIDENCE,
    WARN_OUT_OF_DOMAIN,
    WARN_OUT_OF_RANGE,
    WARN_OUT_OF_SCOPE,
    WARN_STORE_ERROR,
)
from app.llm import LLMUnavailable
from app.qa import answer_question


@pytest.fixture(scope="module")
def store():
    assert (DATA / "triples.csv").is_file()
    return make_local_store()


def _context_from(result) -> dict:
    return {
        "intent": result.intent,
        "entities": [
            {"node_id": hit.node_id, "label": hit.label, "surface": hit.surface}
            for hit in result.entities
        ],
    }


# ---------------------------------------------------------------- 1) 禁忌路由
@pytest.mark.parametrize(
    "question",
    [
        "冷库消毒时能用SO2吗",
        "包装前SO2熏蒸有什么禁忌",
        "运输中SO2熏蒸行不行",
    ],
)
def test_explicit_contraindication_beats_topic_fallbacks(question: str) -> None:
    from app.planner import route

    intent, confidence, candidates = route(question, link(question))
    assert intent == "contraindication", f"{question!r} 应路由禁忌，实际 {intent}（{candidates}）"
    assert 0.0 <= confidence <= 1.0


def test_packaging_question_without_contra_still_general() -> None:
    from app.planner import route

    question = "采后包装有什么要求"
    intent, _confidence, _candidates = route(question, link(question))
    assert intent == "general", f"无禁忌信号的包装题仍应走实体中心检索，实际 {intent}"


def test_contraindication_question_reaches_contra_evidence(store) -> None:
    result = answer_question("用SO2熏阳光玫瑰行不行？", store=store, allow_llm=False)
    assert result.intent == "contraindication", result.intent
    assert result.evidence, "禁忌问句应返回禁忌/替代证据"


# ---------------------------------------------------------------- 1b) 禁忌快捷分支 vs 用法问法（task-5）
@pytest.mark.parametrize("question", ["SO2怎么用", "SO2熏蒸怎么操作"])
def test_so2_howto_question_stays_general(question: str) -> None:
    from app.planner import route

    intent, _confidence, _candidates = route(question, link(question))
    assert intent == "general", f"纯用法问法 {question!r} 不应被禁忌快捷分支抢走，实际 {intent}"


@pytest.mark.parametrize("question", ["SO2熏蒸有什么禁忌", "冷库消毒时能用SO2吗"])
def test_so2_contraindication_question_still_forced(question: str) -> None:
    from app.planner import route

    intent, _confidence, _candidates = route(question, link(question))
    assert intent == "contraindication", f"{question!r} 有明确禁忌词，应强制禁忌，实际 {intent}"


# ---------------------------------------------------------------- 2) 多轮追问
def test_followup_duoshaodu_inherits_only_previous_variety(store) -> None:
    first = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, allow_llm=False)
    second = answer_question("那多少度", store=store, allow_llm=False, context=_context_from(first))
    assert "承接上一轮" in second.context_note and "阳光玫瑰" in second.context_note
    subjects = {item.subject for item in second.evidence}
    assert subjects == {"阳光玫瑰"}, f"只应回答上一轮品种，实际证据主体：{subjects}"
    for other in ("户太八号", "维多利亚", "巨峰", "红地球"):
        assert other not in second.answer, f"「那多少度」不得列出 {other}：{second.answer!r}"


def test_followup_haizai_ne_inherits_intent_not_variety_compare(store) -> None:
    first = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, allow_llm=False)
    second = answer_question("还有呢", store=store, allow_llm=False, context=_context_from(first))
    assert second.intent == "temperature", f"「还有呢」应继承 temperature，实际 {second.intent}"
    assert {item.subject for item in second.evidence} == {"阳光玫瑰"}, "不得混入其它品种"


def test_followup_duoshaodu_with_new_entity_uses_new_entity(store) -> None:
    result = answer_question("那巨峰呢", store=store, allow_llm=False, context=None)
    assert any(hit.node_id == "kyoho" for hit in result.entities), "新实体走实体链接"


# ---------------------------------------------------------------- 3) LLM 错误分类
class _RaisingLLM:
    available = True

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.last_usage: dict = {"model": "fake-model", "attempts": 1, "error": "x"}
        self.calls = 0

    def complete(self, messages, **kwargs):  # noqa: ANN001
        self.calls += 1
        raise self.exc


@pytest.mark.parametrize("kind", ["timeout", "network"])
def test_llm_timeout_and_network_map_to_llm_timeout(store, kind: str) -> None:
    qa._LLM_CACHE.clear()
    llm = _RaisingLLM(LLMUnavailable("boom", kind=kind))
    result = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, llm=llm, allow_llm=True)
    assert result.mode == "template"
    assert WARN_LLM_TIMEOUT in result.warnings, result.warnings
    assert result.llm_meta.get("error_kind") == kind
    assert result.llm_meta.get("model") == "fake-model", "last_usage 不能被 error_kind 覆盖掉"


@pytest.mark.parametrize("kind", ["auth", "rate_limit", "server", "bad_request", "unknown"])
def test_llm_other_kinds_map_to_llm_unavailable(store, kind: str) -> None:
    qa._LLM_CACHE.clear()
    llm = _RaisingLLM(LLMUnavailable("boom", kind=kind, status_code=429 if kind == "rate_limit" else None))
    result = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, llm=llm, allow_llm=True)
    assert result.mode == "template"
    assert WARN_LLM_UNAVAILABLE in result.warnings, result.warnings
    assert WARN_LLM_TIMEOUT not in result.warnings
    assert result.llm_meta.get("error_kind") == kind


def test_llm_unexpected_exception_is_traced_not_mislabeled(store) -> None:
    qa._LLM_CACHE.clear()
    llm = _RaisingLLM(ValueError("cache bug"))
    result = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, llm=llm, allow_llm=True)
    assert result.mode == "template"
    assert WARN_LLM_UNAVAILABLE in result.warnings
    assert result.llm_meta.get("error_kind") == "ValueError", result.llm_meta
    assert "sk-" not in repr(result.llm_meta)


# ---------------------------------------------------------------- 4) 无效引用
class _CiteLLM:
    available = True
    last_usage: dict = {}

    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.calls = 0

    def complete(self, messages, **kwargs):  # noqa: ANN001
        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return text


def test_invalid_citation_does_not_trigger_missing_citation_rewrite(store) -> None:
    qa._LLM_CACHE.clear()
    llm = _CiteLLM(["结论：冷藏温度 0±0.5℃ 即可 [E9]。"])
    result = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, llm=llm, allow_llm=True)
    assert llm.calls == 1, f"无效编号不应被当成「没给引用」再重写一次，实际调用 {llm.calls} 次"
    assert result.mode == "template"
    assert "invalid_citation:E9" in result.warnings
    assert WARN_NO_CITATION in result.warnings


def test_invalid_citation_sentence_removed_valid_kept(store) -> None:
    qa._LLM_CACHE.clear()
    llm = _CiteLLM(["结论：阳光玫瑰冷藏温度 0±0.5℃ [E1]。另见 [E9]。"])
    result = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, llm=llm, allow_llm=True)
    assert result.mode == "llm"
    assert "[E9]" not in result.answer
    assert "0±0.5" in result.answer


# ---------------------------------------------------------------- 5) 告警码契约
def test_every_contract_warn_code_has_ui_mapping() -> None:
    codes = [
        value
        for name, value in vars(contracts).items()
        if name.startswith("WARN_") and isinstance(value, str)
    ]
    assert len(codes) >= 15, f"contracts 告警码数量异常：{codes}"
    for code in codes:
        assert code in ui._WARN_LABELS or code in ui._WARN_TEXT, (
            f"contracts 告警码 {code!r} 在 app/ui.py 中没有中文映射（用户会看到英文码）"
        )
        text = ui._warn_text(code)
        assert text and text != code, f"告警码 {code!r} 的 UI 文案不应回退成英文码：{text!r}"
        cls, label = ui._warn_cls(code)
        assert cls in {"red", "amber", "gray", "blue"} and label


def test_anchor_overclaim_code_comes_from_contracts() -> None:
    assert contracts.WARN_ANCHOR_OVERCLAIM == "anchor_overclaim"
    assert qa.WARN_ANCHOR_OVERCLAIM is contracts.WARN_ANCHOR_OVERCLAIM
    assert "anchor_overclaim" in ui._WARN_TEXT


# ---------------------------------------------------------------- 6) source_url scheme
def test_safe_source_url_allows_only_http_s():
    from app.graph_interactive import _safe_source_url

    assert _safe_source_url("https://example.com/a") == "https://example.com/a"
    assert _safe_source_url("http://example.com") == "http://example.com"
    for bad in ("javascript:alert(1)", "data:text/html,<script>", "file:///etc/passwd", "", None):
        assert _safe_source_url(bad) == "", f"{bad!r} 不应被渲染为链接"


def test_interactive_html_drops_javascript_source_url(monkeypatch) -> None:
    from app import graph_interactive
    from app.graph_view import GEdge, GNode, Graph

    descs = {
        "a": {"summary": "摘要", "detail": "详情", "source_name": "坏链接",
              "source_url": "javascript:alert(1)", "license_note": ""},
        "b": {"summary": "摘要", "detail": "详情", "source_name": "好链接",
              "source_url": "https://example.com/doc", "license_note": ""},
    }
    monkeypatch.setattr(graph_interactive, "load_descriptions", lambda _data_dir: descs)
    graph = Graph(
        nodes=[GNode(id="a", name="节点A", label="Variety", degree=1),
               GNode(id="b", name="节点B", label="Variety", degree=1)],
        edges=[GEdge(source="a", target="b", predicate="REQUIRES", status="verified")],
    )
    doc = graph_interactive.interactive_html(graph)
    assert "javascript:alert" not in doc, "javascript: URL 不得进入内联数据/链接"
    assert "https://example.com/doc" in doc, "合法 http(s) 链接应保留"


# ---------------------------------------------------------------- 7) store / ui 缓存
def test_default_store_reused_between_two_questions(monkeypatch, store) -> None:
    import app.store as store_module

    real_get_store = store_module.get_store
    calls: list[int] = []

    def counting_get_store(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append(1)
        return real_get_store(*args, **kwargs)

    monkeypatch.setattr(store_module, "get_store", counting_get_store)
    qa._STORE_CACHE.clear()
    try:
        first = answer_question("阳光玫瑰放冷库该调到多少度？", allow_llm=False)
        second = answer_question("阳光玫瑰和巨峰哪个更能放？", allow_llm=False)
        assert first.evidence and second.evidence
        assert len(calls) == 1, f"连续两次默认查询只应构造一次 store，实际 {len(calls)} 次"
    finally:
        qa._STORE_CACHE.clear()


def test_explicit_store_is_preferred_over_cache(monkeypatch, store) -> None:
    import app.store as store_module

    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("显式传入 store 时不得再构造新 store")

    monkeypatch.setattr(store_module, "get_store", boom)
    qa._STORE_CACHE.clear()
    result = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, allow_llm=False)
    assert result.evidence


def test_ui_file_counts_and_vocab_are_cached(store) -> None:
    ui._file_counts.clear()
    ui.load_vocab.clear()
    first = ui._file_counts()
    second = ui._file_counts()
    assert first["entities"] > 0 and first["nodes"] == first["entities"] + first["sources"]
    assert first == second
    assert hasattr(ui.load_vocab, "clear"), "load_vocab 应使用 st.cache_data 缓存"
    varieties, diseases = ui.load_vocab()
    assert varieties and diseases
    stats = ui.graph_stats(ui.Runtime(store=store))
    assert stats["entities"] > 0 and stats["varieties"] >= 1


# ---------------------------------------------------------------- 8) 补查失败 != 未收录
class _ShelfFailStore:
    """真实 LocalStore 的代理：shelf_life 补查抛异常，其余查询照常。"""

    name = "local-proxy"
    backend_fallback = False
    fallback_reason = ""

    def __init__(self, real) -> None:
        self._real = real

    def execute(self, spec):  # noqa: ANN001
        if spec.intent == "shelf_life":
            raise RuntimeError("backend boom")
        return self._real.execute(spec)

    def stats(self):
        return self._real.stats()

    def query_cypher(self, spec):  # noqa: ANN001
        return self._real.query_cypher(spec)


def test_variety_compare_lookup_failure_not_reported_as_missing(store) -> None:
    proxy = _ShelfFailStore(store)
    result = answer_question("户太八号和维多利亚哪个更能放？", store=proxy, allow_llm=False)
    assert result.intent == "variety_compare"
    assert any(w.startswith(WARN_STORE_ERROR) for w in result.warnings), result.warnings
    assert "本轮查询" in result.answer and "未能确认" in result.answer, result.answer
    assert "图谱未收录户太八号" not in result.answer, "后端异常不得写成图谱未收录"


# ---------------------------------------------------------------- 9) 离域拒答
def test_non_grape_question_refused_without_evidence(store) -> None:
    result = answer_question("苹果冷藏温度多少合适？", store=store, allow_llm=False)
    assert result.evidence == [], f"不得拿葡萄证据回答苹果：{result.evidence}"
    assert WARN_NO_EVIDENCE in result.warnings
    assert WARN_OUT_OF_DOMAIN in result.warnings
    assert "葡萄" in result.answer and "其他果品" in result.answer


@pytest.mark.parametrize("fruit", ["梨", "桃", "柑橘", "草莓", "香蕉", "猕猴桃", "番茄", "樱桃"])
def test_various_non_grape_fruits_refused(store, fruit: str) -> None:
    result = answer_question(f"{fruit}冷藏温度多少合适？", store=store, allow_llm=False)
    assert result.evidence == [], f"{fruit} 不应返回葡萄证据"
    assert WARN_OUT_OF_DOMAIN in result.warnings


def test_minus18_freeze_probe_keeps_original_behavior(store) -> None:
    result = answer_question("-18℃ 冻起来能存一年吗？", store=store, allow_llm=False)
    assert result.intent == "temperature", result.intent
    assert WARN_OUT_OF_RANGE in result.warnings, result.warnings
    assert WARN_OUT_OF_DOMAIN not in result.warnings
    assert result.evidence, "越界探针仍需温度证据来判区间"


# ---------------------------------------------------------------- 10) 农残/限量域外拒答
@pytest.mark.parametrize(
    "question",
    [
        "阳光玫瑰的农药残留限量？",
        "阳光玫瑰农残多少？",
        "葡萄最大残留限量是多少",
        "葡萄重金属超标吗",
    ],
)
def test_pesticide_residue_questions_refused(store, question: str) -> None:
    result = answer_question(question, store=store, allow_llm=False)
    assert result.evidence == [], f"农残/限量类问题不得返回图谱证据：{question}"
    assert WARN_NO_EVIDENCE in result.warnings
    assert WARN_OUT_OF_SCOPE in result.warnings
    assert "农残" in result.answer or "农药残留" in result.answer, result.answer
    assert "限量" in result.answer


def test_residue_refusal_not_routed_to_variety_compare(store) -> None:
    result = answer_question("阳光玫瑰的农药残留限量？", store=store, allow_llm=False)
    assert result.intent != "variety_compare", f"农残题不应被路由成品种对比：{result.intent}"


# ---------------------------------------------------------------- 11) 未收录品种不顶替
@pytest.mark.parametrize("variety", ["妮娜皇后", "蓝宝石", "金手指", "美人指", "藤稔"])
def test_unlisted_variety_not_replaced_by_other_baseline(store, variety: str) -> None:
    result = answer_question(f"{variety}能放多久？", store=store, allow_llm=False)
    assert result.evidence == [], f"未收录品种不得返回其它品种证据：{[(e.subject, e.object) for e in result.evidence]}"
    assert WARN_NO_EVIDENCE in result.warnings
    assert "暂未收录" in result.answer and variety in result.answer, result.answer
    conclusion = result.answer.split("依据：", 1)[0]
    for other in ("玫瑰香", "巨峰", "红地球", "夏黑", "阳光玫瑰"):
        assert other not in conclusion, f"不得用 {other} 的基线顶替：{conclusion!r}"


def test_known_variety_shelf_life_still_answered(store) -> None:
    result = answer_question("阳光玫瑰能放多久？", store=store, allow_llm=False)
    assert result.intent == "shelf_life"
    assert result.evidence, "已收录品种的耐贮性应正常回答"
    assert "耐贮性" in result.answer


# ---------------------------------------------------------------- 11b) 未收录品种通用守卫（task-6）
@pytest.mark.parametrize(
    ("question", "variety"),
    [
        ("妮娜皇后冷藏温度多少？", "妮娜皇后"),
        ("蓝宝石放冷库几度？", "蓝宝石"),
        ("金手指湿度要求？", "金手指"),
        ("藤稔和巨峰哪个更耐放？", "藤稔"),
    ],
)
def test_unlisted_variety_guard_covers_all_intents(store, question: str, variety: str) -> None:
    result = answer_question(question, store=store, allow_llm=False)
    assert result.evidence == [], f"未收录品种不得返回其他品种证据：{[(e.subject, e.object) for e in result.evidence]}"
    assert WARN_NO_EVIDENCE in result.warnings, result.warnings
    assert WARN_OUT_OF_SCOPE in result.warnings, result.warnings
    assert "暂未收录" in result.answer and variety in result.answer, result.answer
    conclusion = result.answer.split("依据：", 1)[0]
    for other in ("户太八号", "维多利亚", "阳光玫瑰", "巨峰", "红地球", "夏黑"):
        assert other not in conclusion, f"不得用 {other} 的数据顶替：{conclusion!r}"


@pytest.mark.parametrize(
    "question",
    ["阳光玫瑰放冷库几度？", "巨峰和红地球哪个更耐放？"],
)
def test_known_varieties_unaffected_by_unlisted_guard(store, question: str) -> None:
    result = answer_question(question, store=store, allow_llm=False)
    assert result.evidence, f"已收录品种应正常回答：{question}"
    assert WARN_OUT_OF_SCOPE not in result.warnings, result.warnings


# ---------------------------------------------------------------- 12) 档案记录条文（C：主题误判）
def test_archive_record_question_returns_fact(store) -> None:
    result = answer_question("葡萄档案记录保存多久？", store=store, allow_llm=False)
    assert result.evidence, "档案记录条文事实存在，不应误报 no_evidence"
    assert "档案记录" in result.answer
    assert WARN_NO_EVIDENCE not in result.warnings, result.warnings
