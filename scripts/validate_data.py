#!/usr/bin/env python
"""data/ 数据校验器（十项检查，中文报告，非 0 退出即失败）。

用法：
    python scripts/validate_data.py            # 校验 CSV 与 schema.json
    python scripts/validate_data.py --quiet    # 只输出错误/告警
    python scripts/validate_data.py --json     # 机器可读结果（供 CI 用）

归属：kg-builder。契约来源：docs/api.md §1、docs/spec.md §1~§5、data/schema.json。
仅用标准库，venv 或系统 python 均可运行。
退出码：0 = 全部通过；1 = 存在错误（error）；2 = 数据文件缺失/无法解析。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"

# Windows 控制台/管道统一用 UTF-8 输出中文报告（venv 与系统 python 一致）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# 表头兜底（schema.json 缺失时仍可运行；正常情况以 schema.json 为准）
DEFAULT_COLUMNS = {
    "entities": ["id", "label", "name", "aliases", "category", "value_min", "value_max", "unit", "stage",
                 "direction", "method", "species", "berry_color", "seedless", "maturity", "region",
                 "pathogen_latin", "symptom", "source_ids", "note"],
    "triples": ["sid", "subject", "subject_type", "predicate", "object", "object_type", "value", "value_min",
                "value_max", "unit", "stage", "effect", "level", "severity", "efficacy", "reason",
                "source_ids", "locator", "quote", "status", "confidence", "note"],
    "sources": ["id", "title", "authors", "year", "venue", "type", "doi_url", "access", "note"],
}

DEFAULT_SCHEMA = {
    "labels": {k: {} for k in ("Variety", "Condition", "QualityIndicator", "Disease", "Source")},
    "predicates": {
        "REQUIRES": {"subject_type": "Variety", "object_type": "Condition"},
        "CONTRA_INDICATED_FOR": {"subject_type": "Condition", "object_type": "Variety"},
        "AFFECTS": {"subject_type": "Condition", "object_type": "QualityIndicator"},
        "SUSCEPTIBLE_TO": {"subject_type": "Variety", "object_type": "Disease"},
        "PREVENTED_BY": {"subject_type": "Disease", "object_type": "Condition"},
        "INDUCED_BY": {"subject_type": "Disease", "object_type": "Condition"},
        "ALTERNATIVE_TO": {"subject_type": "Condition", "object_type": "Condition"},
        "INDICATES": {"subject_type": "QualityIndicator", "object_type": "Disease"},
        "HAS_INDICATOR_VALUE": {"subject_type": "Variety", "object_type": "QualityIndicator"},
    },
    "condition_categories": ["温度", "湿度", "气调", "化学", "物理", "包装", "采后操作", "环境风险"],
    "indicator_directions": ["higher_better", "lower_better", "target"],
    "stages": ["预冷", "贮藏", "出库"],
    "effect_enum": ["increase", "decrease", "none"],
    "severity_enum": ["高", "中", "低"],
    "efficacy_enum": ["高", "中", "低"],
    "source_types": ["国标", "综述", "论文", "行业资料"],
    "access_enum": ["public", "paywalled"],
    "status": {"enum": ["verified", "anchor"]},
    "confidence": {"min": 0.0, "max": 1.0},
    "source_rules": {"multi_source_predicates": ["CONTRA_INDICATED_FOR", "ALTERNATIVE_TO", "INDICATES"],
                     "single_source_note_keyword": "单来源，建议后续实验验证"},
    "entity_targets": {"Variety": 8, "Condition": 21, "QualityIndicator": 13, "Disease": 6, "Source": "10~12"},
    "triple_targets": {"target": 68, "floor": 50, "shine_muscat_min": 20},
}

CHECK_NAMES = {
    1: "列完整性 / 实体规模",
    2: "枚举合法性",
    3: "数值区间",
    4: "类型-谓词组合",
    5: "来源外键",
    6: "B/G/H 双来源",
    7: "阳光玫瑰行数",
    8: "locator 覆盖率",
    9: "实体名称/类型对应",
    10: "S2a 快照与主数据一致",
}

NUMERIC_TOL = 1e-9


class Report:
    def __init__(self) -> None:
        self.errors: list[tuple[int, str]] = []
        self.warnings: list[tuple[int, str]] = []
        self.notes: list[tuple[int, str]] = []

    def err(self, check: int, msg: str) -> None:
        self.errors.append((check, msg))

    def warn(self, check: int, msg: str) -> None:
        self.warnings.append((check, msg))

    def note(self, check: int, msg: str) -> None:
        self.notes.append((check, msg))

    def check_errors(self, check: int) -> int:
        return sum(1 for c, _ in self.errors if c == check)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [{k: (v if v is not None else "") for k, v in row.items()} for row in reader]
        return list(reader.fieldnames or []), rows


def to_float(value: str) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def split_ids(value: str) -> list[str]:
    return [x.strip() for x in str(value or "").split(";") if x.strip()]


def load_schema(rep: Report) -> dict[str, Any]:
    path = DATA / "schema.json"
    if not path.exists():
        rep.warn(1, "data/schema.json 不存在，使用内置兜底枚举（建议补齐 S1 产物）")
        return dict(DEFAULT_SCHEMA)
    try:
        with path.open("r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as exc:  # noqa: BLE001
        rep.err(1, f"data/schema.json 无法解析为 JSON：{exc}")
        return dict(DEFAULT_SCHEMA)
    merged = json.loads(json.dumps(DEFAULT_SCHEMA))
    merged.update(schema or {})
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="鲜食葡萄知识图谱数据校验（十项）")
    parser.add_argument("--quiet", action="store_true", help="只输出错误/告警")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    args = parser.parse_args(argv)

    rep = Report()
    schema = load_schema(rep)
    cols = schema.get("csv_columns") or DEFAULT_COLUMNS
    cols = {**DEFAULT_COLUMNS, **cols}
    labels = set(schema.get("labels") or DEFAULT_SCHEMA["labels"])
    predicates: dict[str, Any] = schema.get("predicates") or DEFAULT_SCHEMA["predicates"]
    combos = schema.get("predicate_type_combos") or {
        p: {"subject_type": v.get("subject_type"), "object_type": v.get("object_type")}
        for p, v in predicates.items()
    }
    categories = set(schema.get("condition_categories") or [])
    directions = set(schema.get("indicator_directions") or [])
    stages = set(schema.get("stages") or [])
    effects = set(schema.get("effect_enum") or [])
    severities = set(schema.get("severity_enum") or [])
    efficacies = set(schema.get("efficacy_enum") or [])
    source_types = set(schema.get("source_types") or [])
    access_enum = set(schema.get("access_enum") or [])
    status_enum = set((schema.get("status") or {}).get("enum") or ["verified", "anchor"])
    conf_min = float((schema.get("confidence") or {}).get("min", 0.0))
    conf_max = float((schema.get("confidence") or {}).get("max", 1.0))
    src_rules = schema.get("source_rules") or {}
    multi_predicates = set(src_rules.get("multi_source_predicates") or [])
    single_kw = src_rules.get("single_source_note_keyword") or "单来源，建议后续实验验证"
    target = schema.get("entity_targets") or {}
    triple_targets = schema.get("triple_targets") or {}

    # ---------------------------------------------------------------- 读文件
    files = {
        "entities": DATA / "entities.csv",
        "triples": DATA / "triples.csv",
        "sources": DATA / "sources.csv",
        "triples_shine_muscat": DATA / "triples_shine_muscat.csv",
    }
    missing = [str(p.relative_to(BASE)) for p in files.values() if not p.exists()]
    if missing:
        print("[失败] 数据文件缺失：" + ", ".join(missing))
        return 2

    data: dict[str, list[dict[str, str]]] = {}
    headers: dict[str, list[str]] = {}
    for key, path in files.items():
        try:
            headers[key], data[key] = read_csv(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[失败] 无法读取 {path.name}（UTF-8/CSV 格式问题）：{exc}")
            return 2

    entities, triples, sources, shine = data["entities"], data["triples"], data["sources"], data["triples_shine_muscat"]
    source_ids = {r.get("id", "").strip() for r in sources}

    # ============================================================ 检查 1
    for key, expected in cols.items():
        path_key = key if key in headers else None
        if path_key is None:
            continue
        actual = headers[path_key]
        expected_list = list(expected)
        if actual != expected_list:
            miss = [c for c in expected_list if c not in actual]
            extra = [c for c in actual if c not in expected_list]
            rep.err(1, f"{path_key}.csv 表头与契约不一致（缺失={miss or '无'}，多出={extra or '无'}）")
        if any((h or "").strip() == "" for h in actual):
            rep.err(1, f"{path_key}.csv 存在空列名")
    # 实体规模
    from collections import Counter
    label_count = Counter((r.get("label") or "").strip() for r in entities)
    for label, want in target.items():
        if label == "Source":
            continue
        got = label_count.get(label, 0)
        if isinstance(want, int) and got != want:
            rep.err(1, f"实体规模：{label} 期望 {want} 个，实际 {got} 个（docs/spec.md §1）")
    if not (10 <= len(sources) <= 20):
        rep.err(1, f"来源规模：期望 10~20 条，实际 {len(sources)} 条（docs/spec.md §1.5）")
    # 唯一性
    dup = [i for i, n in Counter((r.get("id") or "").strip() for r in entities).items() if n > 1]
    if dup:
        rep.err(1, f"entities.csv id 重复：{dup[:5]}")
    dup = [i for i, n in Counter((r.get("id") or "").strip() for r in sources).items() if n > 1]
    if dup:
        rep.err(1, f"sources.csv id 重复：{dup[:5]}")
    dup = [i for i, n in Counter((r.get("sid") or "").strip() for r in triples).items() if n > 1]
    if dup:
        rep.err(1, f"triples.csv sid 重复：{dup[:5]}")
    dup = [i for i, n in Counter((r.get("sid") or "").strip() for r in shine).items() if n > 1]
    if dup:
        rep.err(1, f"triples_shine_muscat.csv sid 重复：{dup[:5]}")

    # 分组条数（A~I 九组目标取自 schema.json 的 groups，不达标仅告警，便于 S2b 进度可见）
    pred_counts = Counter((r.get("predicate") or "").strip() for r in triples)
    for g, info in (schema.get("groups") or {}).items():
        pred_name = (info or {}).get("predicate")
        want = (info or {}).get("target")
        if not pred_name or not isinstance(want, int):
            continue
        got = pred_counts.get(pred_name, 0)
        if got != want:
            rep.warn(1, f"分组 {g}（{pred_name}）条数 {got} ≠ 目标 {want}（docs/spec.md §4）")

    # ============================================================ 检查 2
    for i, r in enumerate(entities, 2):
        label = (r.get("label") or "").strip()
        if label not in labels:
            rep.err(2, f"entities.csv 第{i}行 label='{label}' 不在枚举 {sorted(labels)}")
        if not (r.get("name") or "").strip():
            rep.err(2, f"entities.csv 第{i}行 name 为空")
        cat = (r.get("category") or "").strip()
        if label == "Condition":
            if not cat:
                rep.err(2, f"entities.csv 第{i}行 Condition 缺 category")
            elif cat not in categories:
                rep.err(2, f"entities.csv 第{i}行 category='{cat}' 不在枚举 {sorted(categories)}")
        if label == "QualityIndicator":
            d = (r.get("direction") or "").strip()
            if not d:
                rep.err(2, f"entities.csv 第{i}行 QualityIndicator 缺 direction")
            elif d not in directions:
                rep.err(2, f"entities.csv 第{i}行 direction='{d}' 不在枚举 {sorted(directions)}")
        st = (r.get("stage") or "").strip()
        if st and st not in stages:
            rep.err(2, f"entities.csv 第{i}行 stage='{st}' 不在枚举 {sorted(stages)}")
        conf = (r.get("confidence") or "").strip() if "confidence" in r else ""
        if conf and to_float(conf) is None:
            rep.err(2, f"entities.csv 第{i}行 confidence 非数值")

    for sheet_name, rows in (("triples.csv", triples), ("triples_shine_muscat.csv", shine)):
        for i, r in enumerate(rows, 2):
            pred = (r.get("predicate") or "").strip()
            if pred not in predicates:
                rep.err(2, f"{sheet_name} 第{i}行 predicate='{pred}' 不在 9 种枚举")
            st = (r.get("status") or "").strip()
            if st not in status_enum:
                rep.err(2, f"{sheet_name} 第{i}行 status='{st}' 不在枚举 {sorted(status_enum)}")
            conf_s = (r.get("confidence") or "").strip()
            conf_v = to_float(conf_s)
            if conf_v is None:
                rep.err(2, f"{sheet_name} 第{i}行 confidence='{conf_s}' 非数值")
            elif not (conf_min - NUMERIC_TOL <= conf_v <= conf_max + NUMERIC_TOL):
                rep.err(2, f"{sheet_name} 第{i}行 confidence={conf_v} 超出 [{conf_min}, {conf_max}]")
            for key in ("subject_type", "object_type"):
                t = (r.get(key) or "").strip()
                if t not in labels:
                    rep.err(2, f"{sheet_name} 第{i}行 {key}='{t}' 不在标签枚举 {sorted(labels)}")
            st = (r.get("stage") or "").strip()
            if st and st not in stages:
                rep.err(2, f"{sheet_name} 第{i}行 stage='{st}' 不在枚举 {sorted(stages)}")
            eff = (r.get("effect") or "").strip()
            if eff and eff not in effects:
                rep.err(2, f"{sheet_name} 第{i}行 effect='{eff}' 不在枚举 {sorted(effects)}")
            sev = (r.get("severity") or "").strip()
            if sev and sev not in severities:
                rep.err(2, f"{sheet_name} 第{i}行 severity='{sev}' 不在枚举 {sorted(severities)}")
            efc = (r.get("efficacy") or "").strip()
            if efc and efc not in efficacies:
                rep.err(2, f"{sheet_name} 第{i}行 efficacy='{efc}' 不在枚举 {sorted(efficacies)}")

    for i, r in enumerate(sources, 2):
        typ = (r.get("type") or "").strip()
        if typ not in source_types:
            rep.err(2, f"sources.csv 第{i}行 type='{typ}' 不在枚举 {sorted(source_types)}")
        acc = (r.get("access") or "").strip()
        if acc not in access_enum:
            rep.err(2, f"sources.csv 第{i}行 access='{acc}' 不在枚举 {sorted(access_enum)}")
        year = (r.get("year") or "").strip()
        if year and not year.isdigit():
            rep.warn(2, f"sources.csv 第{i}行 year='{year}' 不是 4 位数字")

    # ============================================================ 检查 3
    for i, r in enumerate(entities, 2):
        vmin, vmax = to_float(r.get("value_min", "")), to_float(r.get("value_max", ""))
        if (r.get("value_min") or "").strip() and vmin is None:
            rep.err(3, f"entities.csv 第{i}行 value_min='{r.get('value_min')}' 非数值")
        if (r.get("value_max") or "").strip() and vmax is None:
            rep.err(3, f"entities.csv 第{i}行 value_max='{r.get('value_max')}' 非数值")
        if vmin is not None and vmax is not None and vmin > vmax + NUMERIC_TOL:
            rep.err(3, f"entities.csv 第{i}行 value_min({vmin}) > value_max({vmax})")

    for sheet_name, rows in (("triples.csv", triples), ("triples_shine_muscat.csv", shine)):
        for i, r in enumerate(rows, 2):
            vals = {}
            for key in ("value", "value_min", "value_max"):
                raw = (r.get(key) or "").strip()
                if raw == "":
                    vals[key] = None
                    continue
                fv = to_float(raw)
                if fv is None:
                    rep.err(3, f"{sheet_name} 第{i}行 {key}='{raw}' 非数值")
                vals[key] = fv
            v, lo, hi = vals["value"], vals["value_min"], vals["value_max"]
            if lo is not None and hi is not None and lo > hi + NUMERIC_TOL:
                rep.err(3, f"{sheet_name} 第{i}行 value_min({lo}) > value_max({hi})")
            if v is not None and lo is not None and v < lo - NUMERIC_TOL:
                rep.err(3, f"{sheet_name} 第{i}行 value({v}) < value_min({lo})")
            if v is not None and hi is not None and v > hi + NUMERIC_TOL:
                rep.err(3, f"{sheet_name} 第{i}行 value({v}) > value_max({hi})")

    # ============================================================ 检查 4
    for sheet_name, rows in (("triples.csv", triples), ("triples_shine_muscat.csv", shine)):
        for i, r in enumerate(rows, 2):
            pred = (r.get("predicate") or "").strip()
            rule = combos.get(pred)
            if not rule:
                continue  # 检查 2 已报谓词非法
            exp_s = rule.get("subject_type")
            exp_o = rule.get("object_type")
            got_s = (r.get("subject_type") or "").strip()
            got_o = (r.get("object_type") or "").strip()
            if got_s != exp_s or got_o != exp_o:
                rep.err(4, f"{sheet_name} 第{i}行 {pred} 要求 {exp_s}→{exp_o}，实际 {got_s}→{got_o}")

    # ============================================================ 检查 5
    for i, r in enumerate(entities, 2):
        for sid in split_ids(r.get("source_ids", "")):
            if sid not in source_ids:
                rep.err(5, f"entities.csv 第{i}行 source_ids 引用不存在来源 '{sid}'")
    for sheet_name, rows in (("triples.csv", triples), ("triples_shine_muscat.csv", shine)):
        for i, r in enumerate(rows, 2):
            ids = split_ids(r.get("source_ids", ""))
            if not ids:
                rep.err(5, f"{sheet_name} 第{i}行 source_ids 为空（每条三元组必须可溯源）")
            for sid in ids:
                if sid not in source_ids:
                    rep.err(5, f"{sheet_name} 第{i}行 source_ids 引用不存在来源 '{sid}'")

    # ============================================================ 检查 6
    for sheet_name, rows in (("triples.csv", triples), ("triples_shine_muscat.csv", shine)):
        for i, r in enumerate(rows, 2):
            pred = (r.get("predicate") or "").strip()
            if pred not in multi_predicates:
                continue
            ids = split_ids(r.get("source_ids", ""))
            note = r.get("note") or ""
            if len(ids) < 2 and single_kw not in note:
                rep.err(6, f"{sheet_name} 第{i}行 {pred} 仅 {len(ids)} 个来源，且 note 未声明「{single_kw}」")

    # ============================================================ 检查 7
    need = int(triple_targets.get("shine_muscat_min", 20))
    name = "阳光玫瑰"
    shine_sids = {(r.get("sid") or "").strip() for r in shine}
    # 阳光玫瑰语境 = 品种名直接出现，或该条属于 S2a 阳光玫瑰三元组集合（C/E 组条件侧条目亦在此列）
    shine_in_triples = [
        r for r in triples
        if r.get("subject") == name or r.get("object") == name or (r.get("sid") or "").strip() in shine_sids
    ]
    if len(shine_in_triples) < need:
        rep.err(7, f"triples.csv 中阳光玫瑰相关三元组 {len(shine_in_triples)} 条 < {need} 条")
    if len(shine) < need:
        rep.err(7, f"triples_shine_muscat.csv 仅 {len(shine)} 行 < {need} 行")
    literal_hits = sum(1 for r in shine if r.get("subject") == name or r.get("object") == name)
    if literal_hits < 1:
        rep.err(7, "triples_shine_muscat.csv 无任何直接以「阳光玫瑰」为主/宾语的条目，与 S2a 口径不符")
    missing_in_main = shine_sids - {(r.get("sid") or "").strip() for r in triples}
    if missing_in_main:
        rep.err(7, f"triples_shine_muscat.csv 的 {len(missing_in_main)} 条未同步进 triples.csv：{sorted(missing_in_main)[:5]}")

    # ============================================================ 检查 8
    for sheet_name, rows in (("triples.csv", triples), ("triples_shine_muscat.csv", shine)):
        empty = [i for i, r in enumerate(rows, 2) if not (r.get("locator") or "").strip()]
        if empty:
            rep.err(8, f"{sheet_name} 有 {len(empty)} 行 locator 为空（应为 100%）：行号 {empty[:10]}")
        empty_q = [i for i, r in enumerate(rows, 2) if not (r.get("quote") or "").strip()]
        if empty_q:
            rep.warn(8, f"{sheet_name} 有 {len(empty_q)} 行 quote 为空（status=anchor 时须在 note 写明待核验点，已有人工核对）")
        # verified 必须能引用原文摘录；anchor 空 quote 必须在 note 声明待核验
        for i, r in enumerate(rows, 2):
            st = (r.get("status") or "").strip()
            q = (r.get("quote") or "").strip()
            note = r.get("note") or ""
            if st == "verified" and len(q) < 8:
                rep.err(8, f"{sheet_name} 第{i}行 status=verified 但 quote 为空/过短（verified 必须可引用原文）")
            if st == "anchor" and not q and "待核验" not in note:
                rep.warn(8, f"{sheet_name} 第{i}行 anchor 且 quote 为空，note 未写「待核验」")

    # ============================================================ 检查 9
    name_to_labels: dict[str, set] = {}
    for r in entities:
        n = (r.get("name") or "").strip()
        name_to_labels.setdefault(n, set()).add((r.get("label") or "").strip())
    for sheet_name, rows in (("triples.csv", triples), ("triples_shine_muscat.csv", shine)):
        for i, r in enumerate(rows, 2):
            for key, tkey in (("subject", "subject_type"), ("object", "object_type")):
                n = (r.get(key) or "").strip()
                t = (r.get(tkey) or "").strip()
                if n not in name_to_labels:
                    rep.err(9, f"{sheet_name} 第{i}行 {key}='{n}' 在 entities.csv 中找不到同名节点")
                    continue
                if t not in name_to_labels[n]:
                    rep.err(9, f"{sheet_name} 第{i}行 {key}='{n}' 的类型应为 {sorted(name_to_labels[n])}，实际声明 {t}")

    # ============================================================ 检查 10
    # S2a 快照必须是 triples.csv 的严格子集，防止两文件口径漂移（如 confidence 不一致）
    main_by_sid = {(r.get("sid") or "").strip(): r for r in triples}
    for i, r in enumerate(shine, 2):
        sid = (r.get("sid") or "").strip()
        main_row = main_by_sid.get(sid)
        if main_row is None:
            continue  # 检查 7 已报「未同步进 triples.csv」
        diff_fields = [k for k in main_row if main_row[k] != r.get(k, "")]
        if diff_fields:
            rep.err(10, f"triples_shine_muscat.csv 第{i}行 sid={sid} 与 triples.csv 不一致：{diff_fields[:5]}")

    # ============================================================ 输出报告
    total_rows = len(entities) + len(triples) + len(sources)
    if not args.quiet and not args.json:
        print("=" * 72)
        print("鲜食葡萄采后贮藏知识图谱 · 数据校验报告（十项）")
        print(f"数据目录：{DATA}")
        print(f"规模：entities {len(entities)} 行 / triples {len(triples)} 行 / triples_shine_muscat {len(shine)} 行 / sources {len(sources)} 行")
        print("=" * 72)
        for no in range(1, 11):
            errs = rep.check_errors(no)
            mark = "✅ 通过" if errs == 0 else f"❌ {errs} 个错误"
            print(f"检查{no} {CHECK_NAMES[no]}：{mark}")
    for no in range(1, 11):
        errs = [(c, m) for c, m in rep.errors if c == no]
        for _, msg in errs:
            print(f"[错误][检查{no}] {msg}")
    for no, msg in rep.warnings:
        print(f"[告警][检查{no}] {msg}")

    exit_code = 1 if rep.errors else 0
    if args.json:
        print(json.dumps({
            "ok": exit_code == 0,
            "counts": {"entities": len(entities), "triples": len(triples),
                       "shine_muscat": len(shine), "sources": len(sources)},
            "errors": [{"check": c, "message": m} for c, m in rep.errors],
            "warnings": [{"check": c, "message": m} for c, m in rep.warnings],
        }, ensure_ascii=False, indent=2))
    elif not args.quiet:
        print("-" * 72)
        if exit_code == 0:
            print(f"[通过] 十项检查全部通过（错误 0，告警 {len(rep.warnings)}）—— 数据可入库。")
        else:
            print(f"[失败] 共 {len(rep.errors)} 个错误、{len(rep.warnings)} 个告警，请修正后重跑。")
        print(f"总数据行：{total_rows}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
