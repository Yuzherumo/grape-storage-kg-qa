#!/usr/bin/env python
"""把全网筛查到的记录整理成可浏览清单（screened_records.csv）。

数据来源：Lead 自己的多源采集 + 两位队友的候选/初筛文件（Zenodo、Dryad、
Harvard Dataverse、Mendeley、DataCite、ScienceDB、CSData、agridata 等）。
用与下载管线同一套严格判据重新分级，输出 A/B/C/D 全量清单，便于核查覆盖范围。
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".tmp" / "web_grape"
OUT = ROOT / "data" / "external" / "web_grape_storage" / "screened_records.csv"
sys.path.insert(0, str(ROOT / "scripts"))
from collect_web_grape_storage import classify  # noqa: E402

POOLS = [
    ("pool_all.json", "en-repos 全量初筛"),
    ("review_AC.json", "en-repos A/C 复核"),
    ("candidates_english.json", "en-repos 候选"),
    ("candidates_chinese.json", "zh-sources 候选"),
    ("raw/lead_candidates.json", "Lead 多源采集"),
]


def iter_records(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return
    if isinstance(data, dict):
        for key in ("candidates", "records", "hits"):
            if isinstance(data.get(key), list):
                yield from data[key]
                return
        for v in data.values():
            if isinstance(v, list):
                yield from v
        return
    if isinstance(data, list):
        yield from data


def main() -> int:
    seen: dict[str, dict] = {}
    for name, label in POOLS:
        p = WORK / name
        n = 0
        for rec in iter_records(p):
            if not isinstance(rec, dict):
                continue
            title = (rec.get("title") or rec.get("name_zh") or rec.get("title_zh")
                     or rec.get("name") or "").strip()
            if not title:
                continue
            doi = (rec.get("doi") or "").strip()
            key = (doi or title).lower()
            if key in seen:
                continue
            desc = rec.get("description") or rec.get("desc") or rec.get("introduction") or ""
            cls = classify(title, desc)
            files = rec.get("files") or []
            known = sum((f.get("size_bytes") or f.get("size") or 0) for f in files)
            seen[key] = {
                "tier": cls["tier"],
                "source": rec.get("source") or label,
                "pool": label,
                "title": " ".join(title.split())[:300],
                "year": str(rec.get("published") or rec.get("issue_time") or rec.get("year") or "")[:10],
                "doi": doi,
                "landing_url": rec.get("landing_url") or rec.get("url") or "",
                "resource_type": rec.get("resource_type") or "",
                "file_count": len(files),
                "known_bytes": int(known) if known else 0,
                "why": cls["why"],
                "grape_terms": " | ".join(cls["grape_terms"][:6]),
                "storage_terms": " | ".join(cls["storage_terms"][:6]),
            }
            n += 1
        print(f"{name}: +{n} 条")

    rows = sorted(seen.values(), key=lambda r: ({"A": 0, "B": 1, "C": 2, "D": 3}[r["tier"]],
                                                r["source"], r["title"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["tier"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1
    print(f"[screened] {len(rows)} 条 -> {OUT}；分级 {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
