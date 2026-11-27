#!/usr/bin/env python
"""校验 data/external/agridata 抓取产物的一致性（不联网，纯本地对账）。

检查项：
1. manifest.json 中的计数与各 CSV 实际行数、details/、files/ 文件数一致；
2. A/B/C 每一行都有 gid、tier、tier_reason、detail_url，且来源域名正确；
3. A/B/C 行的 tier 与 evidence 字段自洽（B 必须有 grape 证据，C 必须有 postharvest 证据）；
4. CSV 与 JSON 无乱码特征（U+FFFD、'锟'、'???'）；
5. files/ 下文件存在且 sha256 与 downloads.csv 记录一致；
6. 旧站库 manifest 计数与 CSV 行数一致；
7. doi_resolution.json 的 id 落点与数据集名称存在。

非 0 退出即校验失败。
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "external" / "agridata"
LEGACY = DIR / "legacy_preserve"
BAD_MARKERS = ["\ufffd", "锟", "???"]
errors: list[str] = []
warns: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warns.append(msg)


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        fail(f"缺少文件 {path.name}")
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def check_encoding(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{path.name} 不是合法 UTF-8：{exc}")
        return
    for marker in BAD_MARKERS:
        if marker in text:
            fail(f"{path.name} 含疑似乱码标记 {marker!r}")


def main() -> int:
    manifest = json.loads((DIR / "manifest.json").read_text(encoding="utf-8"))
    all_hits = load_csv(DIR / "datasets_all_hits.csv")
    relevant = load_csv(DIR / "datasets_grape_postharvest.csv")
    datasets_only = load_csv(DIR / "datasets_relevant_only.csv")
    projects = load_csv(DIR / "projects_literature_relevant.csv")
    tier_a = load_csv(DIR / "datasets_tier_a.csv")
    dl_rows = load_csv(DIR / "downloads.csv")

    # 1) 计数对账
    checks = {
        "datasets_all_hits.csv": (len(all_hits), manifest["outputs"]["datasets_all_hits.csv"]),
        "datasets_grape_postharvest.csv": (len(relevant), manifest["outputs"]["datasets_grape_postharvest.csv"]),
        "datasets_relevant_only.csv": (len(datasets_only), manifest["outputs"]["datasets_relevant_only.csv"]),
        "projects_literature_relevant.csv": (len(projects), manifest["outputs"]["projects_literature_relevant.csv"]),
        "datasets_tier_a.csv": (len(tier_a), manifest["outputs"]["datasets_tier_a.csv"]),
    }
    for name, (actual, expected) in checks.items():
        if actual != expected:
            fail(f"{name} 行数 {actual} 与 manifest {expected} 不一致")
        else:
            print(f"[OK] {name}: {actual} 行")

    # 分级计数与 manifest 自洽
    tier_counts: dict[str, int] = {}
    for row in all_hits:
        tier_counts[row["tier"]] = tier_counts.get(row["tier"], 0) + 1
    if tier_counts != manifest["tier_counts"]:
        fail(f"分级计数 {tier_counts} 与 manifest {manifest['tier_counts']} 不一致")
    else:
        print(f"[OK] 分级计数: {tier_counts}")
    if sum(tier_counts.values()) != manifest["unique_hits"]:
        fail("分级计数之和与 unique_hits 不一致")
    if sum(1 for r in all_hits if r["record_kind"] == "dataset") != manifest["record_kind_counts"]["dataset"]:
        fail("record_kind=dataset 计数与 manifest 不一致")
    else:
        print(f"[OK] 记录类型: {manifest['record_kind_counts']}")
    relevant_kinds = {}
    for r in relevant:
        relevant_kinds[r["record_kind"]] = relevant_kinds.get(r["record_kind"], 0) + 1
    if len(datasets_only) + len(projects) != len(relevant):
        fail("相关子表行数之和与汇总表不一致")
    if relevant_kinds.get("dataset", 0) != len(datasets_only):
        fail("datasets_relevant_only 行数与汇总表 dataset 数量不一致")
    if relevant_kinds.get("project", 0) != len(projects):
        fail("projects_literature_relevant 行数与汇总表 project 数量不一致")

    # 2) 必填字段与来源域名
    required = ["tier", "tier_reason", "record_kind", "gid", "name_zh", "detail_url"]
    for i, row in enumerate(relevant, start=2):
        missing = [k for k in required if not (row.get(k) or "").strip()]
        if missing:
            fail(f"datasets_grape_postharvest.csv 第{i}行缺字段 {missing}")
        if not row["detail_url"].startswith("http://www.agridata.cn/dataset/detail/"):
            fail(f"第{i}行 detail_url 异常：{row['detail_url']}")
        if row["tier"] == "B" and not (row["evidence_grape"] or "").strip():
            fail(f"第{i}行 B 级缺少葡萄证据")
        if row["tier"] == "C" and not (row["evidence_postharvest"] or "").strip():
            fail(f"第{i}行 C 级缺少采后证据")
        if row["tier"] == "A" and not row["evidence_postharvest"]:
            fail(f"第{i}行 A 级缺少采后证据")
    print(f"[OK] A/B/C 必填字段与证据检查（{len(relevant)} 行）")

    # 3) 编码
    for path in (DIR / "datasets_grape_postharvest.csv", DIR / "datasets_all_hits.csv",
                 DIR / "manifest.json", DIR / "doi_resolution.json",
                 LEGACY / "preserve_db_grape.csv", LEGACY / "grape_storage_technique.md"):
        check_encoding(path)
    if not errors:
        print("[OK] 关键文件 UTF-8 与乱码检查")

    # 4) 详情与文件
    detail_files = list((DIR / "details").glob("*.json"))
    if len(detail_files) != manifest["outputs"]["details"]:
        fail(f"details 文件数 {len(detail_files)} 与 manifest {manifest['outputs']['details']} 不一致")
    else:
        print(f"[OK] details: {len(detail_files)} 个 JSON")
    for row in dl_rows:
        path = ROOT / row["file"] if row.get("file") else None
        if not path:
            continue
        if not path.exists():
            fail(f"下载文件缺失：{row['file']}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row.get("sha256"):
            fail(f"{path.name} sha256 与 downloads.csv 不一致")
    print(f"[OK] 下载文件哈希核对（{len(dl_rows)} 条）")

    # 5) 旧站库
    legacy_manifest = json.loads((LEGACY / "manifest.json").read_text(encoding="utf-8"))
    legacy_all = load_csv(LEGACY / "preserve_db_all.csv")
    legacy_grape = load_csv(LEGACY / "preserve_db_grape.csv")
    if len(legacy_all) != legacy_manifest["records_total"]:
        fail(f"旧站库行数 {len(legacy_all)} 与 manifest {legacy_manifest['records_total']} 不一致")
    if len(legacy_grape) != legacy_manifest["grape_records"]:
        fail(f"旧站葡萄条目 {len(legacy_grape)} 与 manifest {legacy_manifest['grape_records']} 不一致")
    if len(legacy_grape) == 1 and "葡萄" not in (legacy_grape[0].get("果蔬名称") or ""):
        fail("旧站唯一命中条目的果蔬名称不是葡萄")
    print(f"[OK] 旧站库：{len(legacy_all)} 条，葡萄 {len(legacy_grape)} 条")

    # 6) DOI 落点
    doi = json.loads((DIR / "doi_resolution.json").read_text(encoding="utf-8"))
    landing = doi.get("landing_dataset") or {}
    if landing.get("site_id") != 291300 or not landing.get("id_match"):
        fail(f"DOI 落点 id 校验失败：{landing.get('site_id')} / id_match={landing.get('id_match')}")
    if not landing.get("dataset_name_zh"):
        fail("DOI 落点缺少数据集名称")
    target = (doi.get("registered_at_handle") or {}).get("target_url") or ""
    if "datadetail?id=291300" not in target:
        warn(f"Handle 目标 URL 与预期不同：{target}")
    print(f"[OK] DOI 落点：id={landing.get('site_id')} {landing.get('dataset_name_zh')}")

    print()
    for w in warns:
        print(f"[WARN] {w}")
    if errors:
        print(f"[FAIL] {len(errors)} 项校验失败：")
        for e in errors:
            print("  -", e)
        return 1
    print("[PASS] 外部数据产物校验全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
