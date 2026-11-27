"""UI 安全（HTML 注入防护）与演示桩隔离测试（离线；不启动 Streamlit server）。

只调用 ``app/ui.py`` 中不依赖 Streamlit 运行时的纯函数与 ``_ask``，
因此不需要 ScriptRunContext；``import app.ui`` 时 Streamlit 打印的
``No runtime found`` 警告属正常现象。

覆盖点：
1. ``_cite_html``：先转义全文，再把合法的 ``[E#]`` 换回引用角标（样式保留）。
2. answer / 步骤 / 证据字段 / 来源标题 / locator / 用户问题 / warnings 中的
   ``<script>``、``onerror=``、``"><svg onload=...>`` 等只能作为文本输出。
3. 演示桩隔离：``APP_DEMO_MODE`` 未显式开启时，``rt.ready=False`` 一律返回
   ``mode=unavailable``（不得返回固定的阳光玫瑰 0±0.5℃ 答案）；只有
   ``APP_DEMO_MODE=1`` 才返回 ``mode=demo`` 并明确标记模拟数据。
4. 新告警码的中文/颜色映射。
"""
from __future__ import annotations

import pytest

from app import ui
from app.contracts import (
    WARN_ANCHOR_HIGH_RISK,
    WARN_ANCHOR_UNVERIFIED,
    WARN_CITATION_MISMATCH,
    WARN_LLM_ANSWER_REJECTED,
    WARN_SYSTEM_UNAVAILABLE,
    WARN_UNSUPPORTED_FACT,
    AnswerResult,
    Evidence,
)

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    '"><svg onload=alert(1)>',
    "<iframe src=javascript:alert(1)></iframe>",
    "<style>body{display:none}</style>",
]

# 只检查这些「可执行标签」不以裸标签形式出现；合法的 ds-* 标签不在此列。
EXECUTABLE_TAGS = (
    "<script",
    "<img",
    "<svg",
    "<iframe",
    "<object",
    "<embed",
    "<style",
    "<form",
    "<input",
)


def _assert_no_raw_tags(markup: str) -> None:
    lowered = markup.lower()
    for token in EXECUTABLE_TAGS:
        assert token not in lowered, f"注入文本未被转义：{token!r} 出现在 {markup!r}"


def _evil_evidence() -> Evidence:
    payload = '<script>alert(1)</script><img src=x onerror="alert(1)">'
    return Evidence(
        eid=payload,
        subject=payload,
        predicate=payload,
        object=payload,
        value=0.0,
        unit=payload,
        value_min=0.0,
        value_max=0.0,
        source_ids=[payload],
        source_titles=[payload],
        locator=payload,
        quote=payload,
        status="verified",
        confidence=0.9,
    )


@pytest.fixture
def no_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """确保演示桩默认关闭（环境里即使残留 APP_DEMO_MODE 也不影响断言）。"""
    monkeypatch.delenv("APP_DEMO_MODE", raising=False)


# ---------------------------------------------------------------- 引用角标
def test_cite_html_keeps_citation_badge() -> None:
    assert ui._cite_html("见 [E1]") == '见 <span class="ds-cite">E1</span>'
    assert ui._cite_html("双引用 [E1][E12]") == (
        '双引用 <span class="ds-cite">E1</span><span class="ds-cite">E12</span>'
    )


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_cite_html_escapes_before_citation_rewrite(payload: str) -> None:
    markup = ui._cite_html(f"结论：{payload}（[E2]）")
    _assert_no_raw_tags(markup)
    assert '<span class="ds-cite">E2</span>' in markup


def test_cite_html_does_not_trust_preexisting_markup() -> None:
    markup = ui._cite_html('<span class="ds-cite">E1</span>')
    assert "<span" not in markup
    assert "&lt;span" in markup


def test_cite_html_escapes_script_as_entities() -> None:
    markup = ui._cite_html("<script>alert(1)</script>")
    assert "&lt;script&gt;" in markup
    assert "<script" not in markup


# ---------------------------------------------------------------- 正文 / 步骤
def test_md_and_steps_keep_citation_style() -> None:
    assert '<span class="ds-cite">E1</span>' in ui._md_html("结论 [E1]")
    assert '<span class="ds-cite">E1</span>' in ui._steps_html(["步骤 [E1]"])


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_answer_and_steps_are_text_not_html(payload: str) -> None:
    result = AnswerResult(
        question=payload,
        answer=f"结论：{payload}（[E1]）\n\n现在该做什么：\n1. {payload}",
        steps=[payload],
        evidence=[],
    )
    concl, basis, action = ui._split_answer(result.answer)
    markup = "".join(
        [
            ui._user_bubble_html(result.question),
            ui._md_html(concl),
            ui._steps_html(result.steps),
            ui._md_html(action),
            ui._md_html(basis),
        ]
    )
    _assert_no_raw_tags(markup)
    assert '<span class="ds-cite">E1</span>' in markup


# ---------------------------------------------------------------- 用户气泡
@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_user_bubble_escapes_question(payload: str) -> None:
    markup = ui._user_bubble_html(payload)
    _assert_no_raw_tags(markup)
    assert 'class="ds-user"' in markup
    assert "&lt;" in markup or "&quot;" in markup


def test_user_bubble_handles_empty_and_none() -> None:
    assert ui._user_bubble_html(None) == '<div class="ds-user"><div class="bubble"></div></div>'
    assert ui._user_bubble_html("") == '<div class="ds-user"><div class="bubble"></div></div>'


# ---------------------------------------------------------------- 告警胶囊
@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_warn_pills_escape_warning_text(payload: str) -> None:
    markup = ui._warn_pills_html([payload])
    _assert_no_raw_tags(markup)
    assert 'class="ds-warn ' in markup


def test_warn_pills_escape_warning_detail() -> None:
    markup = ui._warn_pills_html(["unsourced_number:" + XSS_PAYLOADS[0]])
    _assert_no_raw_tags(markup)
    assert "含证据外数字" in markup


def test_warn_pills_empty() -> None:
    assert ui._warn_pills_html([]) == ""
    assert ui._warn_pills_html(None) == ""


def test_new_warning_codes_mapping() -> None:
    expected = {
        WARN_SYSTEM_UNAVAILABLE: ("red", "系统不可用"),
        WARN_ANCHOR_UNVERIFIED: ("amber", "待核验"),
        WARN_ANCHOR_HIGH_RISK: ("red", "高风险参数待核验"),
        WARN_UNSUPPORTED_FACT: ("amber", "事实缺引用"),
        WARN_CITATION_MISMATCH: ("amber", "引用与内容不匹配"),
        WARN_LLM_ANSWER_REJECTED: ("amber", "已回退证据模板"),
    }
    for code, (cls, label) in expected.items():
        assert ui._warn_cls(code) == (cls, label), code
        markup = ui._warn_pills_html([code])
        assert f'class="ds-warn {cls}"' in markup
        assert label in markup
        assert ui._warn_text(code)


def test_warning_code_with_detail_keeps_base_mapping() -> None:
    cls, label = ui._warn_cls(WARN_ANCHOR_UNVERIFIED + ":E1")
    assert (cls, label) == ("amber", "待核验")


# ---------------------------------------------------------------- 证据卡片
@pytest.mark.parametrize("cited", [True, False])
def test_evidence_card_escapes_kg_fields(cited: bool) -> None:
    markup = ui._evidence_card_html(_evil_evidence(), cited)
    _assert_no_raw_tags(markup)
    if cited:
        assert 'class="ds-ev cited"' in markup
    else:
        assert 'class="ds-ev"' in markup
    assert 'class="ds-tag ok"' in markup
    assert "&lt;script&gt;" in markup


def test_evidence_card_anchor_and_missing_source() -> None:
    ev = Evidence(eid="E9", subject="巨峰", predicate="REQUIRES", object="冷藏", status="anchor")
    markup = ui._evidence_card_html(ev, cited=False)
    assert "待核验" in markup
    assert "来源未标注" in markup
    assert 'class="ds-ev"' in markup


def test_evidence_card_locator_escaped() -> None:
    payload = '"><svg onload=alert(1)>'
    ev = Evidence(eid="E1", subject="a", predicate="b", object="c", locator=payload)
    markup = ui._evidence_card_html(ev, cited=False)
    _assert_no_raw_tags(markup)
    assert "条款：" in markup


# ---------------------------------------------------------------- meta 行
def test_assistant_meta_mode_labels() -> None:
    for mode, label in {"llm": "在线", "template": "离线模板",
                        "unavailable": "不可用", "demo": "演示桩"}.items():
        markup = ui._assistant_meta_html(AnswerResult(question="q", mode=mode))
        assert f"模式 {label}" in markup


def test_assistant_meta_escapes_dynamic_values() -> None:
    result = AnswerResult(
        question="q",
        intent=XSS_PAYLOADS[0],
        mode="llm",
        elapsed_ms=12,
        llm_meta={
            "prompt_tokens": XSS_PAYLOADS[1],
            "completion_tokens": XSS_PAYLOADS[2],
        },
    )
    markup = ui._assistant_meta_html(result)
    _assert_no_raw_tags(markup)
    assert "在线" in markup


# ---------------------------------------------------------------- 演示桩隔离
QUESTIONS = [
    "巨峰放冷库几度",
    "阳光玫瑰放冷库该调到多少度？",
    "冷库里葡萄长白毛了怎么办？",
    "随便问一个系统没收录的问题",
]


def test_unavailable_result_shape(no_demo_mode: None) -> None:
    result = ui._unavailable_result("巨峰放冷库几度")
    assert result.mode == "unavailable"
    assert WARN_SYSTEM_UNAVAILABLE in result.warnings
    assert result.evidence == []
    assert result.steps == []
    assert "系统问答模块未就绪" in result.answer
    assert "不会返回固定答案" in result.answer


def test_ask_never_falls_back_to_stub_when_not_ready(no_demo_mode: None) -> None:
    runtime = ui.Runtime(ready=False)
    for question in QUESTIONS:
        result, error = ui._ask(runtime, question, topk=6, allow_llm=False, context=None)
        assert error is None
        assert isinstance(result, AnswerResult)
        assert result.mode == "unavailable", question
        assert WARN_SYSTEM_UNAVAILABLE in result.warnings
        assert result.evidence == []
        assert "阳光玫瑰适宜冷藏温度" not in result.answer
        assert "0±0.5" not in result.answer


def test_ask_not_ready_but_answer_question_missing(no_demo_mode: None) -> None:
    result, error = ui._ask(ui.Runtime(ready=True), "巨峰放冷库几度", topk=6,
                            allow_llm=False, context=None)
    assert error is None
    assert result is not None and result.mode == "unavailable"


def test_demo_flag_is_off_by_default(no_demo_mode: None) -> None:
    assert ui._demo_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_demo_flag_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("APP_DEMO_MODE", value)
    assert ui._demo_enabled() is True


def test_demo_flag_module_attribute_is_monkeypatchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """任务书允许用模块级 APP_DEMO_MODE 常量做显式开关（便于测试 monkeypatch）。"""
    monkeypatch.delenv("APP_DEMO_MODE", raising=False)
    monkeypatch.setattr(ui, "APP_DEMO_MODE", True)
    assert ui._demo_enabled() is True
    result, error = ui._ask(ui.Runtime(ready=False), "巨峰放冷库几度", topk=6,
                            allow_llm=False, context=None)
    assert error is None
    assert result is not None and result.mode == "demo"


def test_ask_demo_disabled_by_explicit_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DEMO_MODE", "0")
    result, error = ui._ask(ui.Runtime(ready=False), "巨峰放冷库几度", topk=6,
                            allow_llm=False, context=None)
    assert error is None
    assert result is not None and result.mode == "unavailable"


def test_ask_uses_stub_only_with_explicit_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DEMO_MODE", "1")
    result, error = ui._ask(ui.Runtime(ready=False), "巨峰放冷库几度", topk=6,
                            allow_llm=False, context=None)
    assert error is None
    assert isinstance(result, AnswerResult)
    assert result.mode == "demo"
    assert "stub" in result.warnings
    assert "simulated_data" in result.warnings
    assert result.answer.splitlines()[0] == "【演示桩数据 · 模拟内容，非正式问答】"
    assert result.evidence, "演示桩应自带标记过的模拟证据"


def test_stub_result_is_marked_simulated() -> None:
    result = ui._stub_result("巨峰放冷库几度")
    assert result.mode == "demo"
    assert "stub" in result.warnings
    assert "simulated_data" in result.warnings
    assert "演示桩数据" in result.answer
    assert "非正式问答" in result.answer


def test_ask_passes_through_when_runtime_ready(no_demo_mode: None) -> None:
    expected = AnswerResult(question="q", mode="template", answer="已就绪的回答")

    def fake_answer(question: str, **kwargs: object) -> AnswerResult:
        assert question == "q"
        return expected

    runtime = ui.Runtime(ready=True, answer_question=fake_answer)
    result, error = ui._ask(runtime, "q", topk=6, allow_llm=False, context=None)
    assert error is None
    assert result is expected

# ---------------------------------------------------------------- 知识图谱数据（SVG / 内联 JSON）
def test_graph_view_svg_escapes_knowledge_graph_names() -> None:
    from app.graph_view import GEdge, GNode, Graph, to_svg

    payload = "<script>alert(1)</script>"
    graph = Graph(
        nodes=[
            GNode(id="a", name=payload, label="Variety", degree=1),
            GNode(id="b", name="巨峰", label="Variety", degree=1),
        ],
        edges=[GEdge(source="a", target="b", predicate="REQUIRES", status="verified")],
    )
    svg = to_svg(graph)
    assert "<script" not in svg.lower(), "SVG 中的知识图谱名称必须转义"
    assert "&lt;script&gt;" in svg


def test_interactive_html_json_blocks_cannot_break_out() -> None:
    from app.graph_interactive import interactive_html
    from app.graph_view import GEdge, GNode, Graph

    payload = "</script><script>alert(1)</script>"
    graph = Graph(
        nodes=[GNode(id="a", name=payload, label="Variety", degree=1)],
        edges=[GEdge(source="a", target="a", predicate="REQUIRES", status="verified")],
    )
    doc = interactive_html(graph)
    assert "</script><script>alert" not in doc, "JSON 数据块不得提前闭合 <script>"
    assert "<\\/script>" in doc, "内联 JSON 应把 </ 转义为 <\\/"
