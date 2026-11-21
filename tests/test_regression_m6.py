"""M6 加固回归测试（2026-11 第二轮加固，覆盖 Lead 的 1~8 项新行为）。

约束：全部离线（``allow_llm=False`` 或 StubLLM），无网/无 API key 可跑。
对应关系（与 Lead 的 M6 清单一致）：
1) 覆盖校验：typed 意图证据不触达命中实体 → evidence=[] + no_evidence，不拿别的品种凑答案。
2) 「怎么做/怎么用」+ Condition → general 实体中心检索，且不硬编步骤。
3) 「关系/因果」+ Disease → disease_risk，证据含诱因边。
4) 中文「零下」归一化 → 负数温度，越界题触发 out_of_range。
5) 空指标值文案「图谱未收录 X 的 Y 数值」，不再出现空值拼接。
6) verify_citations 对不存在编号产出 invalid_citation:E#（LLM 路径）。
7) 证据重排：与命中实体相连的证据优先（首条应同时触达两个命中实体）。
8) validate_data 十项全绿 + S2a 快照必须是主数据严格子集。
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from _support import DATA, ROOT, SCRIPTS, csv_header, link, make_local_store, read_csv
from app.contracts import WARN_NO_EVIDENCE


@pytest.fixture(scope="module")
def store():
    assert (DATA / "triples.csv").is_file(), f"缺少 {DATA / 'triples.csv'}（S2 数据就绪后才能测）"
    return make_local_store()


def _ask(store, question: str):
    from app.qa import answer_question

    return answer_question(question, store=store, allow_llm=False)


def _touched_ids(evidence) -> set:
    return {
        evidence.properties.get("subject_id"),
        evidence.properties.get("object_id"),
    } - {None}


# ---------------------------------------------------------------- 1) 覆盖校验
# M8 数据扩充后：维多利亚已有 REQUIRES 温度/湿度 + SSC/TA 证据（不再是无数据实体），
# 但「耐贮性」基线仍缺失 → 用 shelf_life 意图做负例。
@pytest.mark.parametrize("question", ["维多利亚能放多久"])
def test_coverage_check_refuses_unrelated_evidence(store, question: str) -> None:
    result = _ask(store, question)
    assert result.evidence == [], (
        f"{question!r} 命中的维多利亚没有耐贮性基线证据，证据必须为空（不拿别品种凑），"
        f"实际 {len(result.evidence)} 条：{[(e.predicate, e.subject, e.object) for e in result.evidence]}"
    )
    assert WARN_NO_EVIDENCE in result.warnings, f"{question!r} 应告警 no_evidence：{result.warnings}"
    assert "图谱未收录" in result.answer, f"{question!r} 答案应明确「图谱未收录」：{result.answer!r}"
    assert not re.search(r"\[E\d+\]", result.answer), (
        f"{question!r} 无证据时不得引用任何 [E#]：{result.answer!r}"
    )
    # 不得把别品种的三元组事实当答案（模板事实句标志词）
    for marker in ("需要条件", "易感", "可使"):
        assert marker not in result.answer, (
            f"{question!r} 答案混入了其他品种/条件的事实（{marker}）：{result.answer!r}"
        )


def test_coverage_check_accepts_new_victoria_evidence(store) -> None:
    """M8 正例：维多利亚已入图（REQUIRES 温度 + SSC/TA），覆盖校验不得误杀。"""
    result = _ask(store, "维多利亚怎么存")
    assert result.evidence, "维多利亚已有图谱证据（M8 扩充），不应被覆盖校验清空"
    assert WARN_NO_EVIDENCE not in result.warnings, f"维多利亚正例不应报 no_evidence：{result.warnings}"
    subjects = {item.subject for item in result.evidence}
    assert "维多利亚" in subjects, f"证据应以维多利亚为主体：{sorted(subjects)}"


def test_coverage_check_keeps_covered_evidence(store) -> None:
    result = _ask(store, "阳光玫瑰放冷库该调到多少度？")
    assert len(result.evidence) >= 2, f"Q1 应有多条低温冷藏证据，实际 {len(result.evidence)}"
    object_ids = {item.properties.get("object_id") for item in result.evidence}
    assert {"cold_0", "ice_temp"} <= object_ids, (
        f"Q1 证据应覆盖 cold_0（0±0.5℃）与 ice_temp（冰温），实际 object_ids={sorted(x for x in object_ids if x)}"
    )
    assert WARN_NO_EVIDENCE not in result.warnings, f"正例不应被覆盖校验误杀：{result.warnings}"


# ---------------------------------------------------------------- 2) HOWTO 路由
@pytest.mark.parametrize(
    "question, entity_id, marker",
    [
        ("1-MCP怎么用", "mcp_1", "1-MCP"),
        ("臭氧处理怎么做", "ozone", "臭氧"),
    ],
)
def test_howto_with_condition_routes_general(store, question: str, entity_id: str, marker: str) -> None:
    hits = link(question)
    assert any(hit.node_id == entity_id for hit in hits), f"{question!r} 应命中 {entity_id}：{[h.node_id for h in hits]}"

    from app.planner import route

    intent, _confidence, _candidates = route(question, hits)
    assert intent == "general", f"{question!r}「怎么做/怎么用」+ Condition 应路由 general，实际 {intent}"

    result = _ask(store, question)
    assert result.intent == "general"
    assert result.evidence, f"{question!r} general 实体中心检索应有证据"
    for item in result.evidence:
        ids = {item.properties.get("subject_id"), item.properties.get("object_id")}
        assert entity_id in ids or marker in item.subject or marker in item.object, (
            f"{question!r} 证据未围绕 {marker}：{item.predicate} {item.subject}->{item.object}"
        )
    assert result.steps == [], f"{question!r} general 意图不应硬编「现在该做什么」步骤：{result.steps}"


# ---------------------------------------------------------------- 3) 因果路由
def test_disease_relation_routes_to_disease_risk(store) -> None:
    result = _ask(store, "灰霉病和结露有什么关系")
    assert result.intent == "disease_risk", f"「有什么关系」+ 病害应路由 disease_risk，实际 {result.intent}"
    triples = {(item.predicate, item.subject, item.object) for item in result.evidence}
    assert ("INDUCED_BY", "灰霉病", "高湿结露") in triples, (
        f"证据应包含「高湿结露 → 灰霉病」诱因边，实际 {sorted(triples)}"
    )


# ---------------------------------------------------------------- 4) 零下归一化
@pytest.mark.parametrize(
    "raw, expected",
    [("零下18度", "-18度"), ("零下十八度", "-18度"), ("零下2度", "-2度"), ("负2度", "-2度")],
)
def test_normalize_below_zero(raw: str, expected: str) -> None:
    from app.planner import normalize_question

    assert expected in normalize_question(raw), f"{raw!r} 应归一为含 {expected} 的文本"


@pytest.mark.parametrize("question", ["零下2度可以吗", "零下18度能存吗"])
def test_below_zero_request_is_flagged_out_of_range(store, question: str) -> None:
    result = _ask(store, question)
    assert result.intent == "temperature", f"{question!r} 应路由 temperature，实际 {result.intent}"
    assert "out_of_range" in result.warnings, (
        f"{question!r} 证据只到 -1~0℃，-2℃/-18℃ 应触发 out_of_range，实际 warnings={result.warnings}"
    )
    # 答案里不得出现证据温度区间之外的「温度值」（用独立实现抽取，排除标准号 -2026 之类）
    from _support import unsupported_temperatures

    outside = unsupported_temperatures(result.answer, result.evidence)
    assert not outside, f"{question!r} 答案出现证据外温度 {outside}：{result.answer!r}"


# ---------------------------------------------------------------- 5) 空指标值文案
def test_variety_compare_missing_value_uses_placeholder() -> None:
    """M8 后真实数据里所有指标基线都有值，用合成 Evidence 单测占位文案本身。"""
    from app.contracts import Evidence
    from app.qa import template_answer

    evidence = [
        Evidence(
            eid="E1", subject="巨峰", predicate="HAS_INDICATOR_VALUE", object="耐贮性",
            unit="月", value_min=2.0, value_max=4.0,
        ),
        # 玫瑰香无耐贮性数值 → 应输出「图谱未收录…数值」占位，而不是空值拼接
        Evidence(eid="E2", subject="玫瑰香", predicate="HAS_INDICATOR_VALUE", object="耐贮性"),
    ]
    answer = template_answer("variety_compare", "玫瑰香和巨峰哪个更能放", evidence, [], False)
    assert "图谱未收录玫瑰香的耐贮性数值" in answer, f"空值指标应输出占位文案：{answer!r}"
    assert "耐贮性 耐贮性" not in answer, "出现「指标名 指标名」破相拼接"
    assert not re.search(r"耐贮性\s+（", answer), f"出现「耐贮性 （」空值拼接：{answer!r}"


def test_variety_compare_real_data_has_no_broken_value_join(store) -> None:
    """真实数据回归：M8 后玫瑰香/户太八号有 SSC/TA 但无耐贮性，答案不得出现空值拼接。"""
    for question in ("玫瑰香和巨峰哪个更能放", "户太八号和巨峰哪个更能放"):
        result = _ask(store, question)
        assert result.intent == "variety_compare", f"{question!r} 应路由 variety_compare，实际 {result.intent}"
        assert result.answer.strip(), f"{question!r} 答案为空"
        assert "耐贮性 耐贮性" not in result.answer, f"{question!r} 出现「指标名 指标名」破相拼接：{result.answer!r}"
        assert not re.search(r"耐贮性\s+（", result.answer), (
            f"{question!r} 出现「耐贮性 （」空值拼接：{result.answer!r}"
        )


# ---------------------------------------------------------------- 6) 无效引用
def test_verify_citations_flags_invalid_ids() -> None:
    from app.contracts import Evidence
    from app.qa import verify_citations

    evidence = [
        Evidence(eid="E1", subject="阳光玫瑰", predicate="REQUIRES", object="低温冷藏 0±0.5℃"),
    ]
    cited, warnings = verify_citations("结论：0±0.5℃ 冷藏（[E1]），另见 [E9]。", evidence)
    assert cited == ["E1"], f"有效引用应保留 [E1]，实际 {cited}"
    assert "invalid_citation:E9" in warnings, f"不存在的 [E9] 应产出 invalid_citation:E9：{warnings}"

    cited_only_invalid, warnings2 = verify_citations("只引用了 [E9]。", evidence)
    assert cited_only_invalid == []
    assert "invalid_citation:E9" in warnings2 and "no_citation" in warnings2


class _StubLLM:
    """离线 Stub：不触网，返回固定文本。"""

    available = True
    last_usage = {"model": "stub-offline"}

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def complete(self, messages, **kwargs):  # noqa: ANN001 - 与 LLMClient 同签名
        self.calls += 1
        return self.text


def test_llm_invalid_citation_falls_back_to_template(store) -> None:
    from app.qa import answer_question

    stub = _StubLLM("结论：冷藏温度 0±0.5℃ 即可 [E9]。")
    result = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, llm=stub, allow_llm=True)
    assert stub.calls >= 1, "应至少调用一次 StubLLM（验证走的是 LLM 分支）"
    assert result.mode == "template", f"引用全部无效时应降级模板，实际 mode={result.mode}"
    assert any("invalid_citation:E9" in warning for warning in result.warnings), (
        f"LLM 无效引用应告警 invalid_citation:E9：{result.warnings}"
    )


def test_llm_valid_citation_is_kept(store) -> None:
    from app.qa import answer_question

    stub = _StubLLM("结论：阳光玫瑰冷藏温度 0±0.5℃ [E1]。")
    result = answer_question("阳光玫瑰放冷库该调到多少度？", store=store, llm=stub, allow_llm=True)
    assert result.mode == "llm", f"引用有效时应保留 LLM 答案，实际 mode={result.mode}"
    eids = {item.eid for item in result.evidence}
    assert result.cited_ids and set(result.cited_ids) <= eids, (
        f"LLM 引用必须可核验：cited={result.cited_ids} eids={sorted(eids)}"
    )
    assert not any("invalid_citation" in warning for warning in result.warnings)


# ---------------------------------------------------------------- 7) 证据重排
def test_rerank_prefers_evidence_touching_all_hit_entities(store) -> None:
    question = "灰霉病和结露有什么关系"
    hits = link(question)
    hit_ids = {hit.node_id for hit in hits}
    assert {"gray_mold", "high_humid_condensation"} <= hit_ids, f"应命中灰霉病+结露：{sorted(hit_ids)}"

    result = _ask(store, question)
    first = result.evidence[0]
    touched = _touched_ids(first) & hit_ids
    all_rows = [(item.predicate, item.subject, item.object) for item in result.evidence]
    assert touched == hit_ids, (
        f"重排后首条证据应同时触达命中实体 {sorted(hit_ids)}，实际首条 "
        f"{first.predicate} {first.subject}->{first.object} 只触达 {sorted(touched)}；"
        f"全量证据={all_rows}"
    )


# ---------------------------------------------------------------- 8) 数据十项校验 + S2a 快照子集
def test_validate_data_reports_ten_checks_green() -> None:
    script = SCRIPTS / "validate_data.py"
    assert script.is_file(), f"缺少 {script}"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = (proc.stdout or b"").decode("utf-8", errors="replace")
    assert proc.returncode == 0, f"validate_data.py 退出码 {proc.returncode}：\n{output[-3000:]}"
    assert "十项" in output, f"校验报告应声明十项：\n{output[-2000:]}"
    for index in range(1, 11):
        assert f"检查{index}" in output, f"缺少「检查{index}」：\n{output[-2000:]}"
    assert "检查10" in output and "S2a" in output, f"缺少检查10（S2a 快照与主数据一致）：\n{output[-2000:]}"
    assert "❌" not in output, f"十项校验出现失败项：\n{output[-3000:]}"


def test_shine_snapshot_is_strict_subset_of_triples() -> None:
    """检查10 的独立复算：triples_shine_muscat.csv 每行必须与 triples.csv 逐字段一致。"""
    header = csv_header("triples.csv")
    assert csv_header("triples_shine_muscat.csv") == header, "两张表列不一致"
    main_rows = {tuple(row.get(column, "") for column in header) for row in read_csv("triples.csv")}
    snapshot = read_csv("triples_shine_muscat.csv")
    assert len(snapshot) >= 20, f"S2a 快照应 ≥20 行，实际 {len(snapshot)}"
    for row in snapshot:
        frozen = tuple(row.get(column, "") for column in header)
        assert frozen in main_rows, (
            f"快照行未与主数据逐字段一致（违规行 sid={row.get('sid')!r}）："
            f"{dict(zip(header, frozen))}"
        )


# ---------------------------------------------------------------- 9) 其它（配置）
def test_config_llm_timeout_default_and_env_override(monkeypatch) -> None:
    from app import config

    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    assert config.load_settings().llm_timeout > 0, "llm_timeout 默认应为正数"
    monkeypatch.setenv("LLM_TIMEOUT", "7.5")
    assert config.load_settings().llm_timeout == 7.5, "LLM_TIMEOUT 环境变量应可覆盖 llm_timeout"
