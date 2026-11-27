#!/usr/bin/env python
"""全网葡萄采后贮藏「论文 PDF」采集（≤3GB 总预算，与数据文件共用预算）。

为什么只选这两个源（2026-11-27 实测）：
- Zenodo：API 稳定，PDF 直链可下（%PDF 校验通过），记录含标题/作者/期刊/DOI/许可；
- DOAJ：元数据 API 可用，部分 OA 期刊给出可直接下载的 PDF 直链；
- 出版商（MDPI/Wiley/E3S）、PMC、Europe PMC 的 PDF 在本机网络被 403/Cloudflare 拦截，
  Europe PMC 仅元数据可用（本脚本不下载其 PDF，避免伪造成功）。

输出：
- data/external/web_grape_storage/papers/<source>/<id>.pdf
- data/external/web_grape_storage/paper_records.csv（出处、DOI、许可、sha256、抓取时间）
- .tmp/web_grape/papers_downloads.json（断点续跑）

用法：
    python scripts/collect_grape_papers.py collect
    python scripts/collect_grape_papers.py download
    python scripts/collect_grape_papers.py export
    python scripts/collect_grape_papers.py all
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".tmp" / "web_grape"
OUT_DIR = ROOT / "data" / "external" / "web_grape_storage"
PAPER_DIR = OUT_DIR / "papers"
TZ = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

TOTAL_CAP = int(2.85 * 1024**3)   # 与数据文件共用的项目总上限
PER_FILE_CAP = 200 * 1024**2
SLEEP = 1.0

GRAPE_TERMS = ["grape", "grapes", "table grape", "vitis", "葡萄"]
STORAGE_TERMS = [
    "postharvest", "post-harvest", "storage", "cold storage", "cold chain", "preservation",
    "shelf life", "shelf-life", "controlled atmosphere", "modified atmosphere", "sulfur dioxide",
    "so2", "decay", "botrytis", "rachis", "berry drop", "firmness", "storability", "coating",
    "edible coating", "1-mcp", "quality loss", "weight loss", "browning",
]
EXCLUDE_TITLE = ["grapefruit", "wine", "winemaking", "raisin", "juice", "vinegar", "figure",
                 "supplementary", "erratum", "correction", "contents"]


def now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S%z")


def http(url: str, accept: str = "application/json", timeout: int = 90,
         method: str = "GET") -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept}, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            return exc.code, exc.read()[:400], dict(exc.headers or {})
        except Exception as exc:  # noqa: BLE001
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            return 0, str(exc)[:200].encode(), {}
    return 0, b"", {}


def http_json(url: str, timeout: int = 90) -> tuple[int, Any]:
    st, body, _ = http(url, timeout=timeout)
    try:
        return st, json.loads(body)
    except json.JSONDecodeError:
        return st, {"_raw": body[:300].decode("utf-8", "replace")}


def clean(text: Any, limit: int = 500) -> str:
    if text is None:
        return ""
    if isinstance(text, dict):
        text = text.get("title") or text.get("name") or json.dumps(text, ensure_ascii=False)
    elif not isinstance(text, str):
        text = str(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.replace("\u00a0", " ").split())
    return text[:limit]


def classify(title: str, abstract: str) -> dict[str, Any] | None:
    low_title = (title or "").lower()
    if any(x in low_title for x in EXCLUDE_TITLE):
        return None
    text = f"{title} {abstract}".lower()
    grape = [t for t in GRAPE_TERMS if t in text]
    storage = [t for t in STORAGE_TERMS if t in text]
    if not grape or len(storage) < 1:
        return None
    title_grape = any(t in low_title for t in GRAPE_TERMS)
    title_storage = any(t in low_title for t in STORAGE_TERMS)
    score = 10 * len(storage) + (30 if title_grape else 0) + (30 if title_storage else 0)
    return {"grape": grape, "storage": storage, "score": score,
            "why": f"葡萄×贮藏：{'/'.join(grape[:3])} × {'/'.join(storage[:3])}"}


# ---------------------------------------------------------------------------
# Zenodo 论文
# ---------------------------------------------------------------------------
ZENODO_QUERIES = [
    'title:(grape OR grapes) AND title:(storage OR postharvest OR preservation OR shelf OR cold OR decay OR coating OR quality OR transport)',
    'title:(grape OR grapes) AND title:("cold storage" OR "shelf life" OR "controlled atmosphere" OR "sulfur dioxide" OR "modified atmosphere")',
    'title:("table grape" OR "table grapes") AND title:(storage OR postharvest OR preservation OR shelf OR cold OR decay OR coating OR quality)',
    'title:(grape OR grapes) AND description:(postharvest AND storage)',
    'title:(Vitis) AND title:(postharvest OR storage OR preservation OR cold OR shelf)',
    'title:(grape OR grapes) AND title:(storage OR postharvest) AND title:(quality OR decay OR preservation OR packaging)',
]


def collect_zenodo() -> list[dict]:
    out: dict[str, dict] = {}
    for q in ZENODO_QUERIES:
        for page in range(1, 21):
            url = "https://zenodo.org/api/records?" + urllib.parse.urlencode(
                {"q": q, "size": 25, "page": page})
            st, d = http_json(url)
            if st != 200 or not isinstance(d, dict):
                print(f"  [zenodo] {q!r} p{page} HTTP {st}")
                if st in (403, 429):
                    time.sleep(10)
                break
            hits = (d.get("hits") or {}).get("hits") or []
            if not hits:
                break
            for h in hits:
                md = h.get("metadata") or {}
                title = clean(md.get("title"), 300)
                abstract = clean(md.get("description"), 1500)
                cls = classify(title, abstract)
                if not cls:
                    continue
                pdfs = [f for f in (h.get("files") or [])
                        if (f.get("key") or "").lower().endswith(".pdf")
                        and (f.get("links") or {}).get("self")]
                if not pdfs:
                    continue
                key = (h.get("doi") or h.get("id")).lower()
                if key in out:
                    continue
                creators = md.get("creators") or []
                authors = "; ".join(
                    c.get("name") or " ".join(filter(None, [c.get("givenName"), c.get("familyName")]))
                    for c in creators)[:400]
                lic = md.get("license") or {}
                out[key] = {
                    "source": "zenodo",
                    "id": str(h.get("id")),
                    "doi": (h.get("doi") or ""),
                    "title": title,
                    "authors": authors,
                    "container": clean(md.get("journal") or md.get("imprint") or "", 200),
                    "year": (md.get("publication_date") or h.get("created") or "")[:4],
                    "license": lic.get("id") or lic.get("title") or "",
                    "landing_url": h.get("doi_url") or f"https://zenodo.org/records/{h.get('id')}",
                    "pdf_urls": [(f.get("links") or {}).get("self") for f in pdfs],
                    "file_names": [f.get("key") for f in pdfs],
                    "sizes": [f.get("size") for f in pdfs],
                    "score": cls["score"],
                    "why": cls["why"],
                }
            total = (d.get("hits") or {}).get("total") or 0
            if page * 25 >= total or page >= 20:
                break
            time.sleep(0.7)
        print(f"  [zenodo] {q!r}: 累计 {len(out)} 篇")
        time.sleep(SLEEP)
    print(f"[zenodo] 候选论文 {len(out)} 篇")
    return list(out.values())


# ---------------------------------------------------------------------------
# DOAJ 直链 PDF
# ---------------------------------------------------------------------------
DOAJ_QUERIES = [
    '"table grape" AND storage', '"table grape" AND postharvest',
    'grape AND preservation AND storage', 'grape AND "cold storage"',
    '"Vitis vinifera" AND postharvest', 'grape AND "shelf life"',
]


def collect_doaj() -> list[dict]:
    out: dict[str, dict] = {}
    for q in DOAJ_QUERIES:
        url = ("https://doaj.org/api/search/articles/" + urllib.parse.quote(q)
               + "?" + urllib.parse.urlencode({"pageSize": 100}))
        st, d = http_json(url)
        if st != 200 or not isinstance(d, dict):
            print(f"  [doaj] {q!r} HTTP {st}")
            continue
        results = d.get("results") or []
        added = 0
        for r in results:
            bib = r.get("bibjson") or {}
            title = clean(bib.get("title"), 300)
            abstract = clean(bib.get("abstract"), 1200)
            cls = classify(title, abstract)
            if not cls:
                continue
            doi = ""
            for ident in bib.get("identifier") or []:
                if ident.get("type") == "doi":
                    doi = ident.get("id") or ""
            links = [ln.get("url") for ln in (bib.get("link") or []) if ln.get("url")]
            pdf_links = [u for u in links if u.lower().split("?")[0].endswith(".pdf")]
            if not pdf_links:
                continue
            key = (doi or title).lower()
            if key in out:
                continue
            authors = "; ".join(a.get("name") or "" for a in (bib.get("author") or []))[:400]
            out[key] = {
                "source": "doaj",
                "id": doi or hashlib.sha1(title.encode()).hexdigest()[:12],
                "doi": doi,
                "title": title,
                "authors": authors,
                "container": (bib.get("journal") or {}).get("title") or "",
                "year": str(bib.get("year") or ""),
                "license": (bib.get("journal") or {}).get("license") or "",
                "landing_url": links[0] if links else "",
                "pdf_urls": pdf_links,
                "file_names": [u.rsplit("/", 1)[-1] for u in pdf_links],
                "sizes": [None] * len(pdf_links),
                "score": cls["score"],
                "why": cls["why"],
            }
            added += 1
        print(f"  [doaj] {q!r}: {len(results)} 条，新增 {added}")
        time.sleep(SLEEP)
    print(f"[doaj] 候选论文 {len(out)} 篇")
    return list(out.values())


# ---------------------------------------------------------------------------
# 采集 & 下载
# ---------------------------------------------------------------------------
def stage_collect() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    zen = collect_zenodo()
    doaj = collect_doaj()
    merged: dict[str, dict] = {}
    for rec in zen + doaj:
        key = (rec.get("doi") or rec.get("title") or "").lower()
        if not key or key in merged:
            continue
        merged[key] = rec
    records = sorted(merged.values(), key=lambda r: (-r["score"], r["source"]))
    (WORK / "paper_candidates.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[collect] 论文候选 {len(records)} 篇 -> {WORK / 'paper_candidates.json'}")


def safe(text: str, limit: int = 70) -> str:
    keep = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", text or "").strip(" ._")
    return (keep or "paper")[:limit]


def is_pdf(head: bytes) -> bool:
    return head[:5] == b"%PDF-"


def stream_pdf(url: str, dest: Path, expected: int | None) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
            if expected and expected > PER_FILE_CAP:
                return {"ok": False, "reason": f"超过单文件上限 {expected}"}
            h = hashlib.sha256()
            total = 0
            first = b""
            with tmp.open("wb") as fh:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    if not first:
                        first = chunk[:8]
                        if not is_pdf(first):
                            tmp.unlink(missing_ok=True)
                            return {"ok": False, "reason": "返回内容不是 PDF"}
                    fh.write(chunk)
                    h.update(chunk)
                    total += len(chunk)
                    if total > PER_FILE_CAP:
                        tmp.unlink(missing_ok=True)
                        return {"ok": False, "reason": "文件超过单文件上限"}
            tmp.replace(dest)
            return {"ok": True, "bytes": total, "sha256": h.hexdigest()}
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}


def existing_bytes(manifest_path: Path) -> int:
    if not manifest_path.exists():
        return 0
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        return int((m.get("counts") or {}).get("bytes_downloaded") or 0)
    except (json.JSONDecodeError, ValueError):
        return 0


def stage_download() -> None:
    cand_path = WORK / "paper_candidates.json"
    if not cand_path.exists():
        raise SystemExit("先运行 collect")
    records = json.loads(cand_path.read_text(encoding="utf-8"))
    dl_path = WORK / "papers_downloads.json"
    downloads: dict[str, dict] = json.loads(dl_path.read_text(encoding="utf-8")) if dl_path.exists() else {}
    manifest_path = OUT_DIR / "manifest.json"
    used = existing_bytes(manifest_path) + sum(
        int(v.get("bytes") or 0) for v in downloads.values() if v.get("ok"))
    print(f"[download] 论文已用 {sum(int(v.get('bytes') or 0) for v in downloads.values() if v.get('ok')) / 1024**2:.1f}MB；项目总预算 {TOTAL_CAP / 1024**3:.2f}GiB")

    for rec in records:
        if used >= TOTAL_CAP:
            print("  总预算用尽，停止")
            break
        for url, name, size in zip(rec["pdf_urls"], rec["file_names"], rec["sizes"], strict=False):
            key = f"{rec['source']}|{rec.get('doi') or rec['id']}|{name}"
            if key in downloads and downloads[key].get("ok"):
                continue
            dest = PAPER_DIR / rec["source"] / f"{safe(rec.get('doi') or rec['id'], 60)}__{safe(name, 80)}"
            if dest.exists() and dest.stat().st_size > 1024:
                downloads[key] = {
                    "ok": True, "bytes": dest.stat().st_size,
                    "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
                    "tier": "A", "source": rec["source"], "doi": rec.get("doi"),
                    "local": str(dest.relative_to(ROOT)), "resumed": True, "fetched_at": now(),
                }
                used += downloads[key]["bytes"]
                continue
            if size and used + size > TOTAL_CAP:
                continue
            res = stream_pdf(url, dest, size)
            downloads[key] = {
                "ok": res.get("ok"), "reason": res.get("reason"),
                "bytes": res.get("bytes") or 0, "sha256": res.get("sha256"),
                "tier": "A", "source": rec["source"], "doi": rec.get("doi"),
                "title": rec["title"], "url": url, "name": name,
                "local": str(dest.relative_to(ROOT)) if res.get("ok") else "",
                "fetched_at": now(),
            }
            dl_path.write_text(json.dumps(downloads, ensure_ascii=False, indent=1), encoding="utf-8")
            if res.get("ok"):
                used += res["bytes"]
                print(f"  [OK] {res['bytes'] / 1024**2:5.2f}MB {rec.get('doi')} {name[:50]} 累计 {used / 1024**2:.1f}MB")
            else:
                print(f"  [SKIP] {rec.get('doi')} {name[:40]}: {res.get('reason')}")
            time.sleep(0.4)
    dl_path.write_text(json.dumps(downloads, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = [v for v in downloads.values() if v.get("ok")]
    print(f"[download] 论文成功 {len(ok)} 篇，{sum(v['bytes'] for v in ok) / 1024**2:.1f}MB")


def stage_export() -> None:
    cand_path = WORK / "paper_candidates.json"
    if not cand_path.exists():
        raise SystemExit("先运行 collect")
    records = json.loads(cand_path.read_text(encoding="utf-8"))
    downloads = json.loads((WORK / "papers_downloads.json").read_text(encoding="utf-8")) \
        if (WORK / "papers_downloads.json").exists() else {}
    by_key: dict[str, list[dict]] = {}
    for k, v in downloads.items():
        src, doi, name = k.split("|", 2)
        by_key.setdefault((src, doi), []).append(v)

    rows = []
    total = 0
    for rec in records:
        got = [d for d in by_key.get((rec["source"], rec.get("doi") or rec["id"]), []) if d.get("ok")]
        if not got:
            continue
        total += sum(int(d["bytes"]) for d in got)
        rows.append({
            "source": rec["source"], "doi": rec.get("doi") or "", "title": rec["title"],
            "authors": rec.get("authors") or "", "container": rec.get("container") or "",
            "year": rec.get("year") or "", "license": rec.get("license") or "",
            "landing_url": rec.get("landing_url") or "",
            "pdf_urls": " | ".join(rec["pdf_urls"]),
            "files": len(got), "bytes": sum(int(d["bytes"]) for d in got),
            "local_files": " | ".join(d["local"] for d in got),
            "sha256": " | ".join(d.get("sha256") or "" for d in got),
            "why": rec.get("why") or "", "fetched_at": now(),
        })
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cols = ["source", "doi", "title", "authors", "container", "year", "license", "landing_url",
            "pdf_urls", "files", "bytes", "local_files", "sha256", "why", "fetched_at"]
    with (OUT_DIR / "paper_records.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    (WORK / "paper_export_summary.json").write_text(json.dumps({
        "papers": len(rows), "files": sum(r["files"] for r in rows), "bytes": total,
        "generated_at": now(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[export] 论文 {len(rows)} 篇 / {sum(r['files'] for r in rows)} 个 PDF / {total / 1024**2:.1f}MB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["collect", "download", "export", "all"])
    args = parser.parse_args(argv)
    stages = ["collect", "download", "export"] if args.stage == "all" else [args.stage]
    for s in stages:
        print(f"\n=== {s} @ {now()} ===")
        {"collect": stage_collect, "download": stage_download, "export": stage_export}[s]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
