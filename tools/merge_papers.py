"""合并所有已下载论文 + 当前候选，重建论文清单并按标题规则复核。

用途：broad 检索与 title 精确检索两轮候选会互相覆盖，本脚本以
.tmp/web_grape/papers_downloads.json（所有成功下载）为准，
缺失的元数据从 Zenodo 记录 API 或下载记录本身补齐。
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "external" / "web_grape_storage"
REJECTED = ROOT / ".tmp" / "web_grape" / "papers_rejected"
WORK = ROOT / ".tmp" / "web_grape"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

STORAGE_TITLE = [
    "storage", "postharvest", "post-harvest", "preservation", "preserve", "shelf life",
    "shelf-life", "cold", "decay", "coating", "quality", "transport", "rachis",
    "browning", "packaging", "conservazione", "poscosecha", "conservación", "lagerung",
    "entreposage", "conservation", "fresh-keeping", "so2", "sulfur dioxide",
    "controlled atmosphere", "modified atmosphere", "freshness", "spoilage",
    "贮藏", "储藏", "保鲜", "冷藏", "气调", "货架期", "采后", "腐烂", "运输",
]
STORAGE_ABSTRACT = [
    "storage", "postharvest", "post-harvest", "preservation", "shelf life", "cold storage",
    "decay", "coating", "controlled atmosphere", "sulfur dioxide", "so2", "quality loss",
    "weight loss", "rachis", "browning", "berry drop", "firmness", "botrytis",
]
BAD_TITLE = [
    "volume", "issue", "editorial", "preface", "proceedings", "conference report",
    "etruscan", "etruschi", "furniture", "homoeopathic", "pollution", "activated carbon",
    "cosmetic", "gluten-free", "halva", "acai", "açaí", "hedges", "micropropagation",
    "seedling", "interbreeding", "phylloxera", "heritage", "ocular", "miniature",
    "water management", "field notes", "dairy-based", "yogurt", "mayonnaise",
    "marmalade",
]


def keep(title: str, why: str) -> bool:
    t = title.lower()
    if "grapefruit" in t or any(b in t for b in BAD_TITLE):
        return False
    if not re.search(r"\bgrape|vitis|葡萄", t):
        return False
    if any(s in t for s in STORAGE_TITLE):
        return True
    w = (why or "").lower()
    return len({s for s in STORAGE_ABSTRACT if s in w}) >= 2


def fetch_zenodo(rec_id: str) -> dict:
    url = f"https://zenodo.org/api/records/{rec_id}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return {}


def main() -> int:
    dl = json.loads((WORK / "papers_downloads.json").read_text(encoding="utf-8"))
    cands = json.loads((WORK / "paper_candidates.json").read_text(encoding="utf-8"))
    cand_map = {}
    for c in cands:
        cand_map[(c["source"], c.get("doi") or c["id"])] = c

    records = []
    missing_meta = 0
    for key, entry in dl.items():
        if not entry.get("ok") or not entry.get("local"):
            continue
        src, doi, name = key.split("|", 2)
        c = cand_map.get((src, doi))
        if not c:
            title = entry.get("title") or name
            authors = container = lic = ""  # noqa: E501
            landing = ""
            year = ""
            why = ""
            if src == "zenodo":
                rid = doi.split(".")[-1] if doi.startswith("10.5281/zenodo.") else ""
                if rid.isdigit():
                    meta = fetch_zenodo(rid)
                    md = meta.get("metadata") or {}
                    if md:
                        title = md.get("title") or title
                        creators = md.get("creators") or []
                        authors = "; ".join(
                            x.get("name") or "" for x in creators)[:400]
                        container = str(md.get("journal") or md.get("imprint") or "")[:200]
                        year = (md.get("publication_date") or "")[:4]
                        lic = (md.get("license") or {}).get("id") or ""
                        landing = meta.get("doi_url") or f"https://zenodo.org/records/{rid}"
                        missing_meta += 1
        else:
            title = c["title"]
            authors = c.get("authors") or ""
            container = c.get("container") or ""
            lic = c.get("license") or ""
            landing = c.get("landing_url") or ""
            year = c.get("year") or ""
            why = c.get("why") or ""
        records.append({
            "source": src, "doi": doi, "title": title, "authors": authors,
            "container": container, "year": year, "license": lic,
            "landing_url": landing, "local": entry["local"], "bytes": entry["bytes"],
            "sha256": entry.get("sha256") or "", "url": entry.get("url") or "",
            "why": why, "fetched_at": entry.get("fetched_at") or "",
        })

    # 去重（同 DOI 只留第一个）
    seen = set()
    uniq = []
    for r in records:
        k = (r["doi"] or r["title"]).lower()
        if k in seen:
            # 重复 PDF 移到 rejected
            p = ROOT / r["local"]
            if p.exists():
                REJECTED.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(REJECTED / p.name))
            continue
        seen.add(k)
        uniq.append(r)

    kept, dropped = [], []
    for r in uniq:
        (kept if keep(r["title"], r["why"]) else dropped).append(r)
    REJECTED.mkdir(parents=True, exist_ok=True)
    for r in dropped:
        p = ROOT / r["local"]
        if p.exists():
            shutil.move(str(p), str(REJECTED / p.name))

    cols = ["source", "doi", "title", "authors", "container", "year", "license",
            "landing_url", "pdf_urls", "files", "bytes", "local_files", "sha256",
            "why", "fetched_at"]
    with (DIR / "paper_records.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in kept:
            r = dict(r)
            r["pdf_urls"] = r["url"]
            r["files"] = 1
            r["local_files"] = r["local"]
            w.writerow(r)
    total = sum(int(r["bytes"]) for r in kept)
    summary = {"papers": len(kept), "files": len(kept), "bytes": total,
               "dropped": len(dropped), "metadata_refetched": missing_meta,
               "generated_at": "2026-11-27"}
    (WORK / "paper_export_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[merge] 下载成功 {len(records)} 个 PDF，去重后 {len(uniq)}，保留 {len(kept)} 篇 / "
          f"{total / 1024**2:.1f}MB，剔除 {len(dropped)}；补抓元数据 {missing_meta}")
    for r in kept:
        print(f"  KEEP {r['source']:7s} {int(r['bytes']) / 1024**2:5.2f}MB | {r['title'][:78]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
