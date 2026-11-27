"""离线评测脚本（Phase 4 扩展版）：data/eval_questions.csv + data/utterances.csv。

用法（项目根目录）::

    .\\.venv\\Scripts\\python.exe scripts\\eval_qa.py

约束：全程 ``allow_llm=False``，不联网、不需要 API key；模板模式确定性。

覆盖指标：
- 意图准确率（expected_status=answer 的题）；
- 主实体覆盖（问题链到的品种/病害/指标是否在答案或证据中出现）；
- 引用有效率（答案中每个 [E#] 都来自证据且进入 cited_ids）；
- 数值一致率（无 out_of_range / unsourced_number；越界探针允许且要求 out_of_range）；
- 拒答准确率（expected_status=refuse 时必须 no_evidence、无证据、无引用）；
- 关键词通过率（must_keywords 命中、forbidden_keywords 不出现）；
- 口语变体意图命中（门槛 10/12，沿用 S5 验收口径）。

产物：docs/eval_results.md（人读）+ docs/eval_results.json（机器可读）。
退出码：0 = 全部硬性检查通过；1 = 存在硬性失败（报告仍会写出，便于排查）。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
DOCS = ROOT / "docs"
OUT_MD = DOCS / "eval_results.md"
OUT_JSON = DOCS / "eval_results.json"

INTENT_PASS_FLOOR = 10  # 口语变体意图命中门槛：12 条中 ≥10
VALID_STATUS = ("answer", "refuse")

# 当前真实剩余的行为/能力缺口（T1 两轮修复后更新）。仅记录，不影响本评测判定。
KNOWN_DEFECTS = [
    "包装×禁忌组合在 local 后端 0 证据：如「包装前SO2熏蒸有什么禁忌」走 contraindication，"
    "但禁忌检索按 condition_ids 过滤（SO2 熏蒸与包装容重无交集），属数据/模板缺口而非路由缺陷",
    "无上下文追问仍走 temperature 全库例外：「那多少度」在无上文时返回全库温度证据（有上下文时已正确继承，见多轮测试）",
    "Neo4j 服务端仍未实跑：双后端一致性用例默认 skip（缺 neo4j 驱动/运行中服务），本地后端与 CSV 一致",
    "LLM 语义级忠实度仍靠规则启发式校验（引用/数值/关键词/字面相关），不是 NLI 语义蕴含判定",
]

# ---------------------------------------------------------------- 基础工具
from app.contracts import INTENTS, WARN_NO_EVIDENCE  # noqa: E402


def read_csv(name: str) -> list[dict[str, str]]:
    path = DATA / name
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def split_list(value: Any) -> list[str]:
    return [part.strip() for part in re.split(r"[;；]", str(value or "")) if part.strip()]


def cell(text: Any) -> str:
    """Markdown 表格单元格转义。"""
    return str(text).replace("|", "/").replace("\n", " ").strip()


def cited_refs(text: Any) -> list[str]:
    """答案正文中的 [E#] 引用（去重保序）。"""
    seen: list[str] = []
    for eid in re.findall(r"\[(E\d+)\]", str(text or "")):
        if eid not in seen:
            seen.append(eid)
    return seen


def evidence_blob(evidence: list[Any]) -> str:
    parts: list[str] = []
    for item in evidence:
        parts.extend(
            [
                str(getattr(item, "eid", "") or ""),
                str(getattr(item, "subject", "") or ""),
                str(getattr(item, "predicate", "") or ""),
                str(getattr(item, "object", "") or ""),
                str(getattr(item, "unit", "") or ""),
                str(getattr(item, "quote", "") or ""),
                " ".join(str(title) for title in (getattr(item, "source_titles", None) or [])),
            ]
        )
    return "\n".join(parts)


def _normalize_status(row: dict[str, str]) -> str:
    status = str(row.get("expected_status") or "").strip()
    if status in VALID_STATUS:
        return status
    return "refuse" if str(row.get("kind") or "").strip() == "refuse" else "answer"


def _entity_covered(hit: Any, result: Any, store: Any) -> bool:
    """主实体覆盖：问题链到的实体是否在答案或证据的主/客体文本中出现。"""
    names = {str(getattr(hit, "node_id", "") or ""), str(getattr(hit, "surface", "") or "")}
    entity = (getattr(store, "entities", None) or {}).get(getattr(hit, "node_id", ""))
    if isinstance(entity, dict) and entity.get("name"):
        names.add(str(entity["name"]))
    blob = str(result.answer or "") + "\n" + "\n".join(
        f"{getattr(item, 'subject', '')} {getattr(item, 'object', '')}" for item in result.evidence
    )
    return any(name and name in blob for name in names)


# ---------------------------------------------------------------- 评测逻辑
def evaluate_questions(store: Any) -> list[dict[str, Any]]:
    from app.qa import answer_question

    rows: list[dict[str, Any]] = []
    for row in read_csv("eval_questions.csv"):
        question = row["question"]
        kind = str(row.get("kind") or "core").strip()
        expected_status = _normalize_status(row)
        expected_intent = str(row.get("expected_intent") or "").strip()
        expected_predicate = str(row.get("expected_predicate") or "").strip()
        result = answer_question(question, store=store, allow_llm=False)

        eids = {str(item.eid) for item in result.evidence}
        refs = cited_refs(result.answer)
        cited = {str(item) for item in result.cited_ids}
        predicates = {str(item.predicate) for item in result.evidence}
        haystack = (str(result.answer or "") + "\n" + evidence_blob(result.evidence)).lower()
        forbidden_hit = [
            kw for kw in split_list(row.get("forbidden_keywords")) if kw.lower() in str(result.answer or "").lower()
        ]
        missing_keywords = [kw for kw in split_list(row.get("must_keywords")) if kw.lower() not in haystack]
        keyword_applicable = bool(split_list(row.get("must_keywords")) or split_list(row.get("forbidden_keywords")))
        keyword_ok = not missing_keywords and not forbidden_hit

        number_warnings = [
            warning for warning in result.warnings if "out_of_range" in warning or "unsourced_number" in warning
        ]
        out_of_range_seen = any("out_of_range" in warning for warning in result.warnings)
        unsourced = [warning for warning in number_warnings if "unsourced_number" in warning]
        if kind == "probe":
            number_ok = not unsourced and out_of_range_seen
            number_detail = "out_of_range（预期）" if number_ok else (",".join(number_warnings) or "缺 out_of_range")
        else:
            number_ok = not number_warnings
            number_detail = "通过" if number_ok else ",".join(number_warnings)

        hit_rows = list(result.entities)
        coverage_flags = [_entity_covered(hit, result, store) for hit in hit_rows]
        primary_entity_ok = all(coverage_flags) if coverage_flags else None

        if expected_status == "refuse":
            refusal_ok = not result.evidence and not refs and not cited and WARN_NO_EVIDENCE in result.warnings
            intent_ok = result.intent == expected_intent
            citation_ok = not refs and not cited
            hard_ok = refusal_ok
            reasons: list[str] = []
            if result.evidence:
                reasons.append(f"应拒答但返回 {len(result.evidence)} 条证据")
            if refs or cited:
                reasons.append(f"应拒答但出现引用 {sorted(set(refs) | cited)}")
            if WARN_NO_EVIDENCE not in result.warnings:
                reasons.append("缺少 no_evidence 告警")
        else:
            intent_ok = result.intent == expected_intent
            predicate_ok = bool(expected_predicate) and expected_predicate in predicates
            citation_ok = bool(refs) and set(refs) <= eids and set(refs) <= cited and cited <= eids
            evidence_ok = bool(result.evidence)
            hard_ok = all([evidence_ok, intent_ok, predicate_ok, citation_ok, keyword_ok, number_ok])
            reasons = []
            if not evidence_ok:
                reasons.append("证据为空")
            if not result.answer.strip():
                reasons.append("答案为空")
            if not intent_ok:
                reasons.append(f"意图不符(期望 {expected_intent} 实际 {result.intent})")
            if not predicate_ok:
                reasons.append(f"缺谓词 {expected_predicate or '(未定义)'}")
            if not citation_ok:
                reasons.append("引用无效")
            if missing_keywords:
                reasons.append("缺关键词 " + "/".join(missing_keywords))
            if forbidden_hit:
                reasons.append("出现禁用词 " + "/".join(forbidden_hit))
            if not number_ok:
                reasons.append("数值告警: " + number_detail)

        rows.append(
            {
                "id": row["id"],
                "question": question,
                "kind": kind,
                "expected_status": expected_status,
                "expected_intent": expected_intent,
                "actual_intent": result.intent,
                "intent_ok": intent_ok,
                "expected_predicate": expected_predicate,
                "predicates": sorted(predicates),
                "predicate_ok": expected_predicate in predicates if expected_predicate else None,
                "mode": result.mode,
                "evidence_n": len(result.evidence),
                "cited_n": len(refs),
                "citation_ok": citation_ok,
                "number_ok": number_ok,
                "number_detail": number_detail,
                "keyword_ok": keyword_ok,
                "keyword_applicable": keyword_applicable,
                "missing_keywords": missing_keywords,
                "forbidden_hit": forbidden_hit,
                "primary_entity_ok": primary_entity_ok,
                "primary_entities": [str(getattr(hit, "node_id", "")) for hit in hit_rows],
                "steps_n": len(result.steps),
                "warnings": list(result.warnings),
                "verdict": "通过" if hard_ok else "失败：" + "；".join(reasons),
                "pass": hard_ok,
                "note": str(row.get("note") or ""),
            }
        )
    return rows


def evaluate_variants() -> list[dict[str, Any]]:
    from app.linking import link_entities, load_catalog
    from app.planner import route

    catalog = load_catalog(str(DATA / "entities.csv"))
    rows: list[dict[str, Any]] = []
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
                "confidence": round(float(confidence), 4),
                "candidates": candidates,
                "intent_ok": intent == expected,
                "entities": sorted(hit_ids),
                "expected_entities": expected_entities,
                "entity_ok": entity_ok,
            }
        )
    return rows


# ---------------------------------------------------------------- 汇总
def _rate(flags: list[bool]) -> float | None:
    return round(sum(1 for flag in flags if flag) / len(flags), 4) if flags else None


def summarize(question_rows: list[dict[str, Any]], variant_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    answer_rows = [row for row in question_rows if row["expected_status"] == "answer"]
    refuse_rows = [row for row in question_rows if row["expected_status"] == "refuse"]
    passed = [row for row in question_rows if row["pass"]]
    failed = [row for row in question_rows if not row["pass"]]
    coverage_rows = [row for row in answer_rows if row["primary_entity_ok"] is not None]
    keyword_rows = [row for row in question_rows if row["keyword_applicable"]]
    variant_rows = variant_rows or []
    intent_passed = sum(1 for row in variant_rows if row["intent_ok"])
    summary: dict[str, Any] = {
        "total": len(question_rows),
        "passed": len(passed),
        "failed": len(failed),
        "failed_ids": [row["id"] for row in failed],
        "answer_rows": len(answer_rows),
        "refuse_rows": len(refuse_rows),
        "intent_accuracy": _rate([row["intent_ok"] for row in answer_rows]),
        "refusal_accuracy": _rate([row["pass"] for row in refuse_rows]),
        "refusal_intent_accuracy": _rate([row["intent_ok"] for row in refuse_rows]),
        "primary_entity_coverage": _rate([bool(row["primary_entity_ok"]) for row in coverage_rows]),
        "primary_entity_rows": len(coverage_rows),
        "citation_valid_rate": _rate([row["citation_ok"] for row in answer_rows]),
        "number_consistency_rate": _rate([row["number_ok"] for row in answer_rows]),
        "keyword_pass_rate": _rate([row["keyword_ok"] for row in keyword_rows]),
        "keyword_rows": len(keyword_rows),
        "predicate_coverage_rate": _rate([bool(row["predicate_ok"]) for row in answer_rows]),
        "variant_total": len(variant_rows),
        "variant_intent_passed": intent_passed,
        "variant_intent_accuracy": _rate([row["intent_ok"] for row in variant_rows]),
        "variant_entity_accuracy": _rate([row["entity_ok"] for row in variant_rows]),
        "variant_intent_floor": INTENT_PASS_FLOOR,
        "intent_coverage": {
            intent: sum(1 for row in question_rows if row["expected_intent"] == intent) for intent in INTENTS
        },
        "by_kind": {
            kind: {
                "total": sum(1 for row in question_rows if row["kind"] == kind),
                "passed": sum(1 for row in question_rows if row["kind"] == kind and row["pass"]),
            }
            for kind in ("core", "probe", "refuse")
        },
    }
    summary["hard_failures"] = [
        {"id": row["id"], "expected_status": row["expected_status"], "verdict": row["verdict"]} for row in failed
    ]
    # 未提供口语变体（例如只对题目行做聚合）时，变体门槛不适用；避免把「没跑」误判为失败。
    summary["variant_floor_ok"] = (intent_passed >= INTENT_PASS_FLOOR) if variant_rows else True
    summary["ok"] = not failed and summary["variant_floor_ok"]
    return summary


# ---------------------------------------------------------------- 报告
def render_report(
    question_rows: list[dict[str, Any]],
    variant_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    store: Any,
) -> str:
    stats = store.stats() if hasattr(store, "stats") else {}

    def fmt(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:.2%}"
        return str(value)

    lines: list[str] = []
    lines.append("# 问答评测报告（docs/eval_results.md）")
    lines.append("")
    lines.append("> 由 `scripts/eval_qa.py` 自动生成（离线模式：`allow_llm=False`，不联网、不需 API key）。")
    lines.append("> 重新生成：`.\\\\.venv\\\\Scripts\\\\python.exe scripts\\\\eval_qa.py`")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 后端：`{getattr(store, 'name', 'unknown')}`；图谱统计：`{stats}`")
    lines.append(
        f"- 总判定：**{'PASS' if summary['ok'] else 'FAIL'}** —— 题目 {summary['passed']}/{summary['total']} 通过；"
        f"答对 {summary['answer_rows']} 题 / 拒答 {summary['refuse_rows']} 题"
    )
    lines.append("")
    lines.append("## 1. 汇总指标")
    lines.append("")
    lines.append("指标 | 数值 | 说明")
    lines.append("---|---|---")
    lines.append(f"意图准确率 | {fmt(summary['intent_accuracy'])} | expected_status=answer 的题，意图须与期望一致")
    lines.append(
        f"主实体覆盖 | {fmt(summary['primary_entity_coverage'])} | "
        f"{summary['primary_entity_rows']} 道题链到实体，且实体出现在答案/证据中"
    )
    lines.append(f"引用有效率 | {fmt(summary['citation_valid_rate'])} | 答案中每个 [E#] 都属于证据且进入 cited_ids")
    lines.append(
        f"数值一致率 | {fmt(summary['number_consistency_rate'])} | "
        "无 out_of_range / unsourced_number（越界探针要求 out_of_range）"
    )
    lines.append(f"拒答准确率 | {fmt(summary['refusal_accuracy'])} | refuse 题须 no_evidence、无证据、无引用")
    lines.append(
        f"关键词通过率 | {fmt(summary['keyword_pass_rate'])} | "
        f"must_keywords 命中且 forbidden_keywords 不出现（{summary['keyword_rows']} 题适用）"
    )
    lines.append(f"谓词覆盖率 | {fmt(summary['predicate_coverage_rate'])} | 证据中须出现该意图的期望谓词")
    lines.append(
        f"口语变体意图命中 | {summary['variant_intent_passed']}/{summary['variant_total']}"
        f"（{fmt(summary['variant_intent_accuracy'])}，门槛 {summary['variant_intent_floor']}） | "
        f"实体命中 {fmt(summary['variant_entity_accuracy'])}"
    )
    lines.append(
        f"题目通过/失败 | {summary['passed']}/{summary['failed']} | 失败：{', '.join(summary['failed_ids']) or '无'}"
    )
    lines.append("")
    lines.append("意图覆盖（题数）：")
    lines.append("")
    lines.append(" | ".join(["意图", *INTENTS]))
    lines.append("---|" + "---|" * len(INTENTS))
    lines.append(" | ".join(["题数", *[str(summary["intent_coverage"][intent]) for intent in INTENTS]]))
    lines.append("")
    lines.append("## 2. 逐题结果")
    lines.append("")
    lines.append("题目 | 类型 | 状态 | 意图（期望/实际） | 证据 | 引用 | 引用有效 | 数值 | 关键词 | 主实体 | 结论")
    lines.append("---|---|---|---|---|---|---|---|---|---|---")
    for row in question_rows:
        lines.append(
            " | ".join(
                [
                    cell(f"{row['id']} {row['question']}"),
                    cell(row["kind"]),
                    cell(row["expected_status"]),
                    cell(f"{row['expected_intent']} / {row['actual_intent']}"),
                    str(row["evidence_n"]),
                    str(row["cited_n"]),
                    "是" if row["citation_ok"] else "否",
                    cell(row["number_detail"]),
                    "是" if row["keyword_ok"] else "否",
                    "—" if row["primary_entity_ok"] is None else ("是" if row["primary_entity_ok"] else "否"),
                    cell(row["verdict"]),
                ]
            )
        )
    lines.append("")
    lines.append("## 3. 拒答题明细（expected_status=refuse）")
    lines.append("")
    lines.append("题目 | 期望意图 | 实际意图 | 证据数 | 引用数 | 结论")
    lines.append("---|---|---|---|---|---")
    for row in question_rows:
        if row["expected_status"] != "refuse":
            continue
        lines.append(
            " | ".join(
                [
                    cell(f"{row['id']} {row['question']}"),
                    cell(row["expected_intent"]),
                    cell(row["actual_intent"]),
                    str(row["evidence_n"]),
                    str(row["cited_n"]),
                    cell(row["verdict"]),
                ]
            )
        )
    lines.append("")
    lines.append("## 4. 12 条农户口语变体（意图路由命中）")
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
    lines.append("## 5. 已知缺陷（记录，不在 Phase 4 写区修复）")
    lines.append("")
    for defect in KNOWN_DEFECTS:
        lines.append(f"- {defect}")
    lines.append("")
    lines.append("## 6. 判定口径")
    lines.append("")
    lines.append(
        "1. 答对题（expected_status=answer）：证据 ≥1、答案含有效 `[E#]` 且引用落在 evidence/cited_ids 内、"
        "意图与期望一致、证据含期望谓词、关键词命中、数值无告警（越界探针必须有 out_of_range）。"
    )
    lines.append(
        "2. 拒答题（expected_status=refuse）：必须 `no_evidence`、证据为空、答案无 `[E#]` 引用；"
        "不得为了「看起来完整」而返回别的品种/条件。"
    )
    lines.append("3. 期望值来源：`data/triples.csv` 的关系与数值 + 行为目标（离域/未收录必须拒答），不为让脚本变绿而放宽。")
    lines.append("4. 口语变体：意图与 `data/utterances.csv` 标注一致，12 条中命中 ≥10 为通过。")
    lines.append("5. 硬性失败 = 任一题不通过或口语变体命中 < 门槛；此时退出码为 1。")
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

    summary = summarize(question_rows, variant_rows)
    DOCS.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_report(question_rows, variant_rows, summary, store), encoding="utf-8")
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "backend": getattr(store, "name", "unknown"),
        "graph_stats": store.stats() if hasattr(store, "stats") else {},
        "summary": summary,
        "questions": question_rows,
        "variants": variant_rows,
        "known_defects": KNOWN_DEFECTS,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[eval_qa] 报告已写入：{OUT_MD} 与 {OUT_JSON}")
    print(
        f"[eval_qa] 通过 {summary['passed']}/{summary['total']}；意图 {summary['intent_accuracy']}；"
        f"引用 {summary['citation_valid_rate']}；数值 {summary['number_consistency_rate']}；"
        f"拒答 {summary['refusal_accuracy']}；关键词 {summary['keyword_pass_rate']}；"
        f"口语变体 {summary['variant_intent_passed']}/{summary['variant_total']}"
    )
    if summary["failed"]:
        print(f"[eval_qa] 失败题：{summary['failed_ids']}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
