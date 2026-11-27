"""评测集结构测试：data/eval_questions.csv 的契约与 scripts/eval_qa.py 汇总函数。

归属：Phase 4（eval-set）。只读 data/ 与 scripts/，不修改任何运行产物。
"""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

from app.contracts import INTENTS

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "eval_questions.csv"
EVAL_SCRIPT = ROOT / "scripts" / "eval_qa.py"

EXPECTED_COLUMNS = [
    "id",
    "question",
    "expected_intent",
    "expected_predicate",
    "must_keywords",
    "forbidden_keywords",
    "kind",
    "expected_status",
    "note",
]
VALID_KINDS = {"core", "probe", "refuse"}
VALID_STATUS = {"answer", "refuse"}


def _rows() -> list[dict[str, str]]:
    assert CSV_PATH.is_file(), f"缺少 {CSV_PATH}"
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _load_eval_qa():
    spec = importlib.util.spec_from_file_location("eval_qa_script", EVAL_SCRIPT)
    assert spec and spec.loader, f"无法加载 {EVAL_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- CSV 契约
def test_columns_exact() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == EXPECTED_COLUMNS, f"表头应为 {EXPECTED_COLUMNS}，实际 {header}"


def test_final_scale_is_frozen() -> None:
    """Phase 4 最终规模：28 题 = 19 answer（含 1 越界探针）+ 9 refuse。"""
    rows = _rows()
    assert len(rows) == 28, f"评测集应为 28 题，实际 {len(rows)}"
    assert sum(1 for row in rows if row["expected_status"] == "answer") == 19
    assert sum(1 for row in rows if row["expected_status"] == "refuse") == 9
    assert len(rows) <= 28, "Phase 4 上限 28 题"


def test_id_unique_and_not_blank() -> None:
    rows = _rows()
    ids = [str(row.get("id") or "").strip() for row in rows]
    assert all(ids), "存在空 id"
    assert len(ids) == len(set(ids)), f"id 重复：{[i for i in ids if ids.count(i) > 1]}"


def test_question_not_blank() -> None:
    for row in _rows():
        assert str(row.get("question") or "").strip(), f"{row.get('id')} question 为空"


def test_note_present_for_auditability() -> None:
    for row in _rows():
        assert str(row.get("note") or "").strip(), f"{row.get('id')} note 为空（须写明期望值依据）"


# ---------------------------------------------------------------- 枚举与覆盖
def test_expected_intent_legal() -> None:
    for row in _rows():
        assert row["expected_intent"] in INTENTS, f"{row['id']} 意图 {row['expected_intent']!r} 不在 INTENTS"


def test_all_intents_covered() -> None:
    covered = {row["expected_intent"] for row in _rows()}
    missing = set(INTENTS) - covered
    assert not missing, f"评测集未覆盖意图：{sorted(missing)}"


def test_kind_and_status_legal_and_consistent() -> None:
    for row in _rows():
        kind = str(row.get("kind") or "").strip()
        status = str(row.get("expected_status") or "").strip()
        assert kind in VALID_KINDS, f"{row['id']} kind={kind!r} 不在 {sorted(VALID_KINDS)}"
        assert status in VALID_STATUS, f"{row['id']} expected_status={status!r} 不在 {sorted(VALID_STATUS)}"
        if kind == "refuse":
            assert status == "refuse", f"{row['id']} kind=refuse 必须 expected_status=refuse"
        else:
            assert status == "answer", f"{row['id']} kind={kind} 必须 expected_status=answer"


def test_at_least_six_refuse_questions() -> None:
    refuse = [row for row in _rows() if row.get("kind") == "refuse"]
    assert len(refuse) >= 6, f"至少需要 6 道拒答题（含离域果品），实际 {len(refuse)}"


def test_exactly_one_out_of_range_probe() -> None:
    probes = [row for row in _rows() if row.get("kind") == "probe"]
    assert len(probes) == 1, f"越界探针应恰好 1 道，实际 {len(probes)}：{[row['id'] for row in probes]}"


def test_answer_rows_have_predicate_and_keywords() -> None:
    for row in _rows():
        if row.get("expected_status") == "refuse":
            continue
        assert str(row.get("expected_predicate") or "").strip(), (
            f"{row['id']} 答对题必须声明 expected_predicate（用于断言证据中的关系）"
        )
        if row.get("kind") == "core":
            assert str(row.get("must_keywords") or "").strip(), f"{row['id']} core 题至少 1 个 must_keywords"


# ---------------------------------------------------------------- 汇总函数
def test_summarize_runnable_and_rates() -> None:
    module = _load_eval_qa()
    summary = module.summarize([])
    assert summary["total"] == 0
    assert summary["ok"] is True
    for key in (
        "intent_accuracy",
        "primary_entity_coverage",
        "citation_valid_rate",
        "number_consistency_rate",
        "refusal_accuracy",
        "keyword_pass_rate",
        "failed_ids",
    ):
        assert key in summary, f"summary 缺指标 {key}"

    row_ok = {
        "id": "X1",
        "kind": "core",
        "expected_status": "answer",
        "expected_intent": "temperature",
        "intent_ok": True,
        "predicate_ok": True,
        "primary_entity_ok": True,
        "citation_ok": True,
        "number_ok": True,
        "keyword_applicable": True,
        "keyword_ok": True,
        "pass": True,
        "verdict": "通过",
    }
    row_bad = {**row_ok, "id": "X2", "pass": False, "citation_ok": False, "verdict": "失败：引用无效"}
    two = module.summarize([row_ok, row_bad])
    assert two["total"] == 2 and two["passed"] == 1 and two["failed"] == 1
    assert two["failed_ids"] == ["X2"]
    assert two["ok"] is False
    assert two["intent_accuracy"] == 1.0  # 两题意图都对；失败原因是引用
    assert two["citation_valid_rate"] == 0.5
    assert two["number_consistency_rate"] == 1.0
    assert two["keyword_pass_rate"] == 1.0


def test_refusal_accuracy_aggregates() -> None:
    module = _load_eval_qa()
    base = {
        "kind": "refuse",
        "expected_status": "refuse",
        "expected_intent": "general",
        "intent_ok": True,
        "predicate_ok": None,
        "primary_entity_ok": None,
        "citation_ok": True,
        "number_ok": True,
        "keyword_applicable": False,
        "keyword_ok": True,
        "verdict": "通过",
    }
    passed = dict(base, id="R1", **{"pass": True})
    failed = dict(base, id="R2", **{"pass": False}, verdict="失败：应拒答但返回 6 条证据")
    summary = module.summarize([passed, failed])
    assert summary["refuse_rows"] == 2
    assert summary["refusal_accuracy"] == 0.5
    assert summary["failed_ids"] == ["R2"]
