#!/usr/bin/env python
"""校验 data/external/web_grape_storage 产物（不联网）。

检查项：
1. manifest 计数与 CSV/文件目录一致；
2. **总下载量 ≤ 3GB 硬约束**，且 ≤ manifest 记录的预算上限；
3. 每个已下载文件存在、大小与记录一致、sha256 可复算；
4. A/C 分级合法，A 级记录必须有葡萄词+贮藏词证据；
5. 记录 URL/DOI/许可能够溯源（DOI 或 landing_url 至少一个）；
6. CSV/JSON 无乱码标记；
7. 未登录/付费痕迹（无 html 错误页冒充数据文件）。
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "external" / "web_grape_storage"
HARD_CAP = 3 * 1024**3
BAD = ["\ufffd", "锟"]
errors: list[str] = []
warns: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def warn(m: str) -> None:
    warns.append(m)


def load_csv(p: Path) -> list[dict]:
    if not p.exists():
        fail(f"缺少 {p.name}")
        return []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    mp = DIR / "manifest.json"
    if not mp.exists():
        print("[FAIL] manifest.json 不存在")
        return 1
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    records = load_csv(DIR / "web_records.csv")
    files = load_csv(DIR / "web_files.csv")
    tier_a = load_csv(DIR / "web_records_tier_a.csv")
    skipped = load_csv(DIR / "download_skipped.csv") if (DIR / "download_skipped.csv").exists() else []

    # 1) 计数
    counts = manifest.get("counts") or {}
    checks = {
        "web_records.csv": (len(records), counts.get("records_total")),
        "web_files.csv": (len(files), counts.get("files_downloaded")),
        "web_records_tier_a.csv": (len(tier_a), counts.get("records_a")),
    }
    for name, (actual, expected) in checks.items():
        if expected is None:
            warn(f"manifest 缺少 {name} 计数")
        elif int(actual) != int(expected):
            fail(f"{name} 行数 {actual} 与 manifest {expected} 不一致")
        else:
            print(f"[OK] {name}: {actual}")
    if sum(1 for r in records if r["tier"] == "A") != counts.get("records_a"):
        fail("A 级计数不一致")
    if sum(1 for r in records if r["tier"] == "C") != counts.get("records_c"):
        fail("C 级计数不一致")

    # 2) 预算
    real_bytes = 0
    for f in files:
        p = ROOT / (f.get("local") or "")
        if not p.exists():
            fail(f"文件缺失：{f.get('local')}")
            continue
        size = p.stat().st_size
        real_bytes += size
        if int(f.get("bytes") or 0) != size:
            fail(f"{p.name} 记录大小 {f.get('bytes')} ≠ 实际 {size}")
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest != (f.get("sha256") or ""):
            fail(f"{p.name} sha256 不一致")
    if real_bytes > HARD_CAP:
        fail(f"实际下载量 {real_bytes / 1024**3:.2f}GiB 超过 3GB 硬约束")
    else:
        print(f"[OK] 下载量 {real_bytes / 1024**2:.1f}MB（{real_bytes / 1024**3:.3f}GiB）≤ 3GB")
    if counts.get("bytes_downloaded") is not None and int(counts["bytes_downloaded"]) != real_bytes:
        fail(f"manifest bytes_downloaded {counts['bytes_downloaded']} ≠ 实际 {real_bytes}")

    # 3) 分级与证据
    for i, r in enumerate(records, 2):
        if r["tier"] not in ("A", "C"):
            fail(f"web_records.csv 第{i}行非法 tier={r['tier']}")
        if r["tier"] == "A" and (not r.get("grape_terms") or not r.get("storage_terms")):
            fail(f"第{i}行 A 级缺少葡萄/贮藏证据")
        if not (r.get("doi") or r.get("landing_url")):
            fail(f"第{i}行缺少 DOI/landing_url，无法溯源")
    print(f"[OK] 分级与证据检查（{len(records)} 条）")

    # 4) 许可
    no_lic = [r for r in records if not (r.get("license") or "").strip()]
    if no_lic:
        warn(f"{len(no_lic)} 条记录未标注许可证（如 Zenodo 未填 license）")

    # 5) 编码与错误页
    for name in ("web_records.csv", "web_files.csv", "manifest.json"):
        p = DIR / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for mark in BAD:
            if mark in text:
                fail(f"{name} 含乱码标记 {mark!r}")
    for f in files:
        p = ROOT / (f.get("local") or "")
        if not p.exists():
            continue
        head = p.open("rb").read(256).lstrip().lower()
        if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            fail(f"{p.name} 是 HTML 错误页，不是数据文件")
    print("[OK] 编码与错误页检查")

    print()
    # 7) 论文 PDF（可选，若已采集）
    paper_path = DIR / "paper_records.csv"
    paper_bytes_total = 0
    if paper_path.exists():
        papers = load_csv(paper_path)
        for i, p in enumerate(papers, start=2):
            locals_ = [x for x in (p.get("local_files") or "").split(" | ") if x]
            hashes = [x for x in (p.get("sha256") or "").split(" | ")]
            if not locals_:
                fail(f"paper_records.csv 第{i}行没有本地文件")
            for j, rel in enumerate(locals_):
                fp = ROOT / rel
                if not fp.exists():
                    fail(f"论文 PDF 缺失：{rel}")
                    continue
                size = fp.stat().st_size
                paper_bytes_total += size
                if j < len(hashes) and hashes[j]:
                    digest = hashlib.sha256(fp.read_bytes()).hexdigest()
                    if digest != hashes[j]:
                        fail(f"{fp.name} sha256 不一致")
                head = fp.open("rb").read(5)
                if head != b"%PDF-":
                    fail(f"{fp.name} 不是 PDF（magic={head!r}）")
            if not (p.get("doi") or p.get("landing_url")):
                fail(f"paper_records.csv 第{i}行缺少 DOI/landing_url")
            if not p.get("title"):
                fail(f"paper_records.csv 第{i}行缺少标题")
        total_all = real_bytes + paper_bytes_total
        if total_all > HARD_CAP:
            fail(f"数据+论文总量 {total_all / 1024**3:.2f}GiB 超过 3GB")
        else:
            print(f"[OK] 论文 PDF：{len(papers)} 篇 / {paper_bytes_total / 1024**2:.1f}MB；"
                  f"数据+论文合计 {total_all / 1024**2:.1f}MB ≤ 3GB")
        paper_manifest = manifest.get("papers") or {}
        if paper_manifest:
            if int(paper_manifest.get("files") or 0) != sum(
                    len([x for x in (p.get("local_files") or "").split(" | ") if x]) for p in papers):
                fail("manifest.papers.files 与 paper_records.csv 不一致")
            if int(paper_manifest.get("bytes") or 0) != paper_bytes_total:
                fail("manifest.papers.bytes 与实际 PDF 大小不一致")
        else:
            warn("manifest 缺少 papers 统计（请重跑论文导出以合并）")
    else:
        print("[INFO] 未发现 paper_records.csv，跳过论文校验")

    print()
    for w in warns:
        print(f"[WARN] {w}")
    if skipped:
        print(f"[INFO] 跳过/失败 {len(skipped)} 项（见 download_skipped.csv）")
    if errors:
        print(f"[FAIL] {len(errors)} 项：")
        for e in errors:
            print("  -", e)
        return 1
    print("[PASS] 全网葡萄贮藏数据产物校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
