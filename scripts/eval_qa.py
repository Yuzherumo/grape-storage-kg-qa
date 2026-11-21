"""离线评测脚本：data/eval_questions.csv + data/utterances.csv → docs/eval_results.md。

用法（项目根目录）：
    .\\.venv\\Scripts\\python.exe scripts\\eval_qa.py

约束：全程 ``allow_llm=False``，不联网、不需要 API key；模板模式确定性。
退出码：0 = 核心题全过且意图命中 ≥10/12；1 = 有失败（报告仍会生成，便于排查）。
"""
from __future__ import annotations

import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
DOCS = ROOT / "docs"
OUT_PATH = DOCS / "eval_results.md"
INTENT_PASS_FLOOR = 10  # S5 验收：12 条口语变体意图命中 ≥10/12
CORE_QUESTION_IDS = ("Q1", "Q2", "Q3", "Q4", "Q5")


# ---------------------------------------------------------------- 读写
def read_csv(name: str) -> List[Dict[str, str]]:
    path = DATA / name
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def split_list(value: Any) -> List[str]:
    return [part.strip() for part in re.split(r"[;；]", str(value or "")) if part.strip()]


def cell(text: Any) -> str:
    """Markdown 表格单元格转义。"""
    return str(text).replace("|", "/").replace("\n", " ").strip()


def eids_in_answer(answer: str) -> List[str]:
    return re.findall(r"\[(E\d+)\]", str(answer or ""))


def evidence_blob(evidence: List[Any]) -> str:
    parts: List[str] = []
    for item in evidence:
        parts.extend(
            [
                str(getattr(item, "eid", "") or ""),
                str(getattr(item, "subject", "") or ""),
                str(getattr(item, "predicate", "") or ""),
                str(getattr(item, "object", "") or ""),
                str(getattr(item, "unit", "") or ""),
                " ".join(str(title) for title in (getattr(item, "source_titles", None) or [])),
                str(getattr(item, "quote", "") or ""),
            ]
        )
    return "\n".join(parts)


# ---------------------------------------------------------------- 评测逻辑
def evaluate_questions(store) -> List[Dict[str, Any]]:
    from app.qa import answer_question

    rows: List[Dict[str, Any]] = []
    for row in read_csv("eval_questions.csv"):
        question = row["question"]
        kind = str(row.get("kind") or "core").strip()
        result = answer_question(question, store=store, allow_llm=False)

        eids = {str(item.eid) for item in result.evidence}
        refs = eids_in_answer(result.answer)
        cited = set(str(item) for item in result.cited_ids)
        citation_ok = (
            all(ref in eids for ref in refs)
            and set(refs) <= cited
            and cited <= eids
            and (bool(refs) if kind == "core" else True)
        )
        number_warnings = [
            warning
            for warning in result.warnings
            if "out_of_range" in warning or "unsourced_number" in warning
        ]
        if kind == "probe":
            # 越界探针：out_of_range 是「正确识别越界」的预期告警，不算数值错误
            out_of_range_warnings = [w for w in number_warnings if "out_of_range" in w]
            number_warnings = [w for w in number_warnings if "unsourced_number" in w]
            number_ok = not number_warnings
            if number_warnings:
                number_detail = ",".join(number_warnings)
            elif out_of_range_warnings:
                number_detail = "out_of_range（预期）"
            else:
                number_detail = "通过"
        else:
            number_ok = not number_warnings
            number_detail = "通过" if number_ok else ",".join(number_warnings)

        reasons: List[str] = []
        if kind == "core":
            if not result.evidence:
                reasons.append("证据为空")
            if not result.answer.strip():
                reasons.append("答案为空")
            if not citation_ok:
                reasons.append("引用无效")
            if result.intent != row["expected_intent"]:
                reasons.append(f"意图不符(期望 {row['expected_intent']})")
            predicates = {item.predicate for item in result.evidence}
            if row["expected_predicate"] not in predicates:
                reasons.append(f"缺谓词 {row['expected_predicate']}")
            haystack = (result.answer + "\n" + evidence_blob(result.evidence)).lower()
            for keyword in split_list(row.get("must_keywords")):
                if keyword.lower() not in haystack:
                    reasons.append(f"缺关键词 {keyword}")
        for keyword in split_list(row.get("forbidden_keywords")):
            if keyword.lower() in result.answer.lower():
                reasons.append(f"出现禁用词 {keyword}")
        if number_warnings:
            reasons.append("数值告警: " + ",".join(number_warnings))

        rows.append(
            {
                "id": row["id"],
                "question": question,
                "intent": result.intent,
                "mode": result.mode,
                "evidence_n": len(result.evidence),
                "cited_n": len(refs),
                "citation_ok": citation_ok,
                "number_ok": number_ok,
                "number_detail": number_detail,
                "steps_n": len(result.steps),
                "warnings": list(result.warnings),
                "verdict": "通过" if not reasons else "失败：" + "；".join(reasons),
                "pass": not reasons,
                "kind": kind,
            }
        )
    return rows


def evaluate_variants() -> List[Dict[str, Any]]:
    from app.linking import link_entities, load_catalog
    from app.planner import route

    catalog = load_catalog(str(DATA / "entities.csv"))
    rows: List[Dict[str, Any]] = []
    for row in read_csv("utterances.csv"):
        utterance = row["utterance"]
        hits = list(link_entities(utterance, catalog))
        intent, confidence, candidates = route(utterance, hits)
        expected = str(row.get("expected_intent") or "").strip()
        expected_entities = split_list(row.get("expected_entity_ids"))
        hit_ids = {str(hit.node_id) for hit in hits}
        entity_ok = all(entity_id in hit_ids for entity_id in expected_entities)
        rows.append(
            {
                "id": row["id"],
                "utterance": utterance,
                "expected_intent": expected,
                "actual_intent": intent,
                "confidence": float(confidence),
                "candidates": candidates,
                "intent_ok": intent == expected,
                "entities": sorted(hit_ids),
                "expected_entities": expected_entities,
                "entity_ok": entity_ok,
            }
        )
    return rows


# ---------------------------------------------------------------- 报告
def render_report(question_rows: List[Dict[str, Any]], variant_rows: List[Dict[str, Any]], store) -> str:
    core = [row for row in question_rows if row["id"] in CORE_QUESTION_IDS]
    probe = [row for row in question_rows if row["id"] not in CORE_QUESTION_IDS]
    core_passed = sum(1 for row in core if row["pass"])
    probe_passed = sum(1 for row in probe if row["pass"])
    intent_passed = sum(1 for row in variant_rows if row["intent_ok"])
    entity_passed = sum(1 for row in variant_rows if row["entity_ok"])
    stats = store.stats() if hasattr(store, "stats") else {}
    ok_msg = (
        "PASS"
        if core_passed == len(core) and intent_passed >= INTENT_PASS_FLOOR
        else "FAIL"
    )

    lines: List[str] = []
    lines.append("# 问答评测报告（docs/eval_results.md）")
    lines.append("")
    lines.append("> 由 `scripts/eval_qa.py` 自动生成（离线模式：`allow_llm=False`，不联网、不需 API key）。")
    lines.append("> 重新生成：`.\\.venv\\Scripts\\python.exe scripts\\eval_qa.py`")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 后端：`{getattr(store, 'name', 'unknown')}`；图谱统计：`{stats}`")
    lines.append(f"- 总判定：**{ok_msg}** —— 核心题 {core_passed}/{len(core)} 通过；"
                 f"越界探针 {probe_passed}/{len(probe)} 通过；"
                 f"口语变体意图命中 {intent_passed}/{len(variant_rows)}（门槛 {INTENT_PASS_FLOOR}）；"
                 f"实体命中 {entity_passed}/{len(variant_rows)}")
    lines.append("")
    lines.append("## 表 1：典型问题与越界探针（Q1~Q6）")
    lines.append("")
    lines.append("问题 | 意图 | 证据数 | 引用数 | 引用有效 | 数值校验 | 步骤数 | 结论")
    lines.append("---|---|---|---|---|---|---|---")
    for row in question_rows:
        lines.append(
            " | ".join(
                [
                    cell(row["question"]),
                    cell(row["intent"]),
                    str(row["evidence_n"]),
                    str(row["cited_n"]),
                    "是" if row["citation_ok"] else "否",
                    cell(row["number_detail"]),
                    str(row["steps_n"]),
                    cell(row["verdict"]),
                ]
            )
        )
    lines.append("")
    lines.append("## 表 2：12 条农户口语变体（意图路由命中）")
    lines.append("")
    lines.append("变体 | 期望意图 | 实际意图 | 命中")
    lines.append("---|---|---|---")
    for row in variant_rows:
        mark = "✅" if row["intent_ok"] else "❌"
        entity_note = ""
        missing = [item for item in row["expected_entities"] if item not in row["entities"]]
        if missing:
            entity_note = f"（实体缺 {'/'.join(missing)}）"
        lines.append(
            " | ".join(
                [
                    cell(f"{row['id']} {row['utterance']}"),
                    cell(row["expected_intent"]),
                    cell(f"{row['actual_intent']} ({row['confidence']:.2f})"),
                    cell(mark + entity_note),
                ]
            )
        )
    lines.append("")

    failures = [row for row in question_rows if not row["pass"]]
    variant_failures = [row for row in variant_rows if not row["intent_ok"] or not row["entity_ok"]]
    lines.append("## 失败明细")
    lines.append("")
    if not failures and not variant_failures:
        lines.append("无。")
    else:
        for row in failures:
            lines.append(f"- {row['id']} {row['question']} → {row['verdict']}")
        for row in variant_failures:
            detail = []
            if not row["intent_ok"]:
                detail.append(f"意图 {row['expected_intent']}→{row['actual_intent']}")
            if not row["entity_ok"]:
                detail.append(f"实体 {row['expected_entities']}→{row['entities']}")
            lines.append(f"- {row['id']} {row['utterance']} → {'；'.join(detail)}")
    lines.append("")
    lines.append("## 判定口径")
    lines.append("")
    lines.append("- 核心题（Q1~Q5）：证据 ≥1、答案带有效 `[E#]` 且落在 `cited_ids`、意图正确、"
                 "期望谓词存在、必需关键词命中、无 `out_of_range`/`unsourced_number` 数值告警。")
    lines.append("- 越界探针（Q6）：答案不得出现证据外温度，不得宣称证据外的存放条件。")
    lines.append(f"- 口语变体：意图与 `data/utterances.csv` 标注一致；12 条中命中 ≥{INTENT_PASS_FLOOR} 为通过。")
    lines.append("- 该报告与 `pytest tests/test_e2e_questions.py tests/test_planner.py tests/test_linking.py` 口径一致。")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 入口
def main() -> int:
    try:
        from app.store.local_store import LocalStore
    except Exception as exc:  # noqa: BLE001 - 实现未就绪时给出友好提示
        print(f"[eval_qa] app.store 未就绪，无法评测：{exc}", file=sys.stderr)
        return 1

    try:
        store = LocalStore(str(DATA))
    except Exception as exc:  # noqa: BLE001
        print(f"[eval_qa] 无法加载本地图谱数据（data/）：{exc}", file=sys.stderr)
        return 1

    try:
        question_rows = evaluate_questions(store)
        variant_rows = evaluate_variants()
    except Exception as exc:  # noqa: BLE001 - qa/planner 未就绪
        print(f"[eval_qa] 问答/路由实现未就绪，无法评测：{exc}", file=sys.stderr)
        return 1

    DOCS.mkdir(parents=True, exist_ok=True)
    report = render_report(question_rows, variant_rows, store)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"[eval_qa] 报告已写入：{OUT_PATH}")

    core = [row for row in question_rows if row["id"] in CORE_QUESTION_IDS]
    core_passed = sum(1 for row in core if row["pass"])
    intent_passed = sum(1 for row in variant_rows if row["intent_ok"])
    print(f"[eval_qa] 核心题通过 {core_passed}/{len(core)}；口语变体意图命中 {intent_passed}/{len(variant_rows)}")
    return 0 if core_passed == len(core) and intent_passed >= INTENT_PASS_FLOOR else 1


if __name__ == "__main__":
    raise SystemExit(main())
