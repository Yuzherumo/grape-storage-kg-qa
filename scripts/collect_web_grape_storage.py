#!/usr/bin/env python
"""全网「葡萄贮藏/采后保鲜」数据采集与 3GB 预算下载管线。

数据源（开放、免登录）：
- Zenodo（API 检索 + 文件直链）
- Dryad（API v2）
- Harvard Dataverse（API）
- 队友侦察产出的候选清单（.tmp/web_grape/candidates_*.json，含 ScienceDB/中国科学数据等）

相关性分级（与上一轮 agridata 报告口径一致）：
- A：葡萄（table grape / fresh grape / 葡萄 / 提子）且采后贮藏保鲜（storage/postharvest/cold/CA/SO2/shelf life/decay/firmness/落粒/失水/腐烂…）
- B：葡萄相关但不是采后（葡萄酒/葡萄干/果汁/栽培/育种/田间病害/基因组）——不下载
- C：其他果蔬采后贮藏——仅作参照，预算占比受限

预算：总下载量硬上限 DEFAULT_TOTAL_CAP（默认 2.85GB，低于用户要求的 3GB），
单文件上限 PER_FILE_CAP，C 级最多占 C_TIER_SHARE。按「A 级优先、相关性高优先、
同等相关性小文件优先」排序填满，超预算即停止并记录 skipped。

用法：
    python scripts/collect_web_grape_storage.py collect    # 采集元数据 -> lead_candidates.json
    python scripts/collect_web_grape_storage.py merge      # 合并队友候选 + 去重
    python scripts/collect_web_grape_storage.py download   # 按预算下载
    python scripts/collect_web_grape_storage.py export     # 导出 CSV/manifest
    python scripts/collect_web_grape_storage.py all
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".tmp" / "web_grape"
RAW = WORK / "raw"
OUT_DIR = ROOT / "data" / "external" / "web_grape_storage"
FILES_DIR = OUT_DIR / "files"
TZ = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

TOTAL_CAP = int(2.85 * 1024**3)   # 2.85 GiB，留 150MB 余量，硬性低于用户 3GB
PER_FILE_CAP = 400 * 1024**2
C_TIER_SHARE = 0.15               # C 级（其他果蔬参照）最多占预算 15%
SLEEP = 1.0
MAX_HTML_BYTES = 8 * 1024**2

# ---------------------------------------------------------------------------
# 相关性词表
# ---------------------------------------------------------------------------
GRAPE_TERMS = [
    "table grape", "table grapes", "fresh grape", "fresh grapes", "grape berry",
    "grape berries", "grape storage", "grapes", "grape", "vitis vinifera", "vitis",
    "葡萄", "提子", "鲜食葡萄",
]
STORAGE_TERMS = [
    "postharvest", "post-harvest", "cold storage", "cold chain", "controlled atmosphere",
    "modified atmosphere", "sulfur dioxide", "so2", "so 2", "shelf life", "shelf-life",
    "storage", "preservation", "decay", "botrytis", "rachis", "rachis browning",
    "berry drop", "firmness", "quality retention", "quality loss", "storability",
    "edible coating", "1-mcp", "ozone", "cold room", "refrigerated",
    "采后", "贮藏", "储藏", "保鲜", "冷藏", "气调", "二氧化硫", "货架期", "耐贮",
    "腐烂", "失水", "落粒", "冰温", "预冷", "保鲜剂", "静电场", "涂膜",
]
PROCESSING_TERMS = [
    "wine", "winemaking", "winery", "raisin", "raisins", "juice", "must",
    "fermentation", "ferment", "vinegar", "pomace", "extract", "polyphenol",
    "葡萄酒", "葡萄干", "葡萄汁", "酿酒", "发酵",
]
FIELD_TERMS = [
    "vineyard", "viticulture", "cultivar", "breeding", "genome", "transcriptome",
    "downy mildew", "powdery mildew", "rootstock", "soil", "fertiliz", "irrigation",
    "栽培", "育种", "基因组", "霜霉", "白粉", "砧木", "土壤", "施肥", "灌溉",
]
PRODUCE_TERMS = [
    "apple", "pear", "peach", "nectarine", "kiwifruit", "litchi", "lychee", "citrus",
    "strawberry", "tomato", "banana", "mango", "cherry", "plum", "blueberry",
    "avocado", "persimmon", "pomegranate", "vegetable", "fruit",
    "苹果", "梨", "桃", "猕猴桃", "荔枝", "柑橘", "草莓", "番茄", "香蕉", "芒果",
    "樱桃", "蓝莓", "柿", "石榴", "蔬菜",
]
DATA_EXT = (".csv", ".tsv", ".xlsx", ".xls", ".json", ".txt", ".zip", ".tar", ".gz",
            ".tgz", ".rar", ".7z", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".jp2",
            ".nc", ".h5", ".hdf5", ".mat", ".rds", ".sav", ".dta", ".parquet", ".gpkg",
            ".shp", ".pdf", ".docx", ".wps", ".xlsm")
SKIP_EXT = (".html", ".htm", ".php", ".aspx", ".exe")

SOURCE_REPOS = {
    "zenodo": "https://zenodo.org",
    "dryad": "https://datadryad.org",
    "dataverse": "https://dataverse.harvard.edu",
}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S%z")


def http(url: str, timeout: int = 60, accept: str = "application/json",
         method: str = "GET", data: bytes | None = None) -> tuple[int, bytes, dict]:
    # 中文文件名直链需要 percent-encode，否则 urllib 会拒绝
    if not url.isascii():
        parts = urllib.parse.urlsplit(url)
        url = parts._replace(path=urllib.parse.quote(parts.path, safe="/")).geturl()
    headers = {"User-Agent": UA, "Accept": accept}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as exc:
            body = exc.read()[:2000]
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            return exc.code, body, dict(exc.headers or {})
        except Exception as exc:  # noqa: BLE001
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            return 0, f"{type(exc).__name__}: {exc}".encode(), {}
    return 0, b"", {}


def http_json(url: str, **kw) -> tuple[int, Any]:
    st, body, _ = http(url, **kw)
    try:
        return st, json.loads(body)
    except json.JSONDecodeError:
        return st, {"_raw": body[:500].decode("utf-8", "replace")}


def get_size(url: str, timeout: int = 40) -> tuple[int | None, str]:
    """HEAD 或 Range GET 取文件大小与 content-type。"""
    st, body, headers = http(url, accept="*/*", method="HEAD", timeout=timeout)
    cl = headers.get("Content-Length") or headers.get("content-length")
    ct = headers.get("Content-Type") or headers.get("content-type") or ""
    if st in (200, 206) and cl:
        return int(cl), ct
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-0",
                                               "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            cr = r.headers.get("Content-Range") or ""
            m = re.search(r"/(\d+)$", cr)
            if m:
                return int(m.group(1)), r.headers.get("Content-Type", "")
            cl = r.headers.get("Content-Length")
            if cl and r.status == 200:
                return int(cl), r.headers.get("Content-Type", "")
    except Exception:  # noqa: BLE001
        pass
    return None, ct


def clean_text(s: str | None, limit: int = 4000) -> str:
    if not s:
        return ""
    text = re.sub(r"<[^>]+>", " ", s)
    text = html.unescape(text)
    text = " ".join(text.split())
    return text[:limit]


def track(name: str, obj: Any) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# 相关性判定
# ---------------------------------------------------------------------------
def hit_any(text: str, terms: Iterable[str]) -> list[str]:
    low = text.lower()
    return [t for t in terms if t.lower() in low]


STRICT_STORAGE_TITLE_TERMS = [
    "storage", "postharvest", "post-harvest", "cold storage", "cold chain",
    "preservation", "shelf life", "shelf-life", "controlled atmosphere",
    "modified atmosphere", "sulfur dioxide", "so2", "decay", "rachis",
    "berry drop", "firmness", "storability",
    "贮藏", "储藏", "保鲜", "冷藏", "气调", "二氧化硫", "货架期", "采后", "耐贮",
]
AVOID_TITLE_PATTERNS = [
    "figure", "supplementary", "table s", "raw data for", "data from:",
    "dodecahedron", "fish", "vinegar", "biofilm", "açaí", "acai", "passion fruit",
]


def strong_grape(title: str, description: str) -> bool:
    """标题里的葡萄证据，或描述里明确是鲜食葡萄（排除 grapefruit）。"""
    t = (title or "").lower().replace("grapefruit", " ")
    if "grape" in t or "vitis" in t or "葡萄" in (title or "") or "提子" in (title or ""):
        return True
    d = (description or "").lower().replace("grapefruit", " ")
    return any(k in d for k in ("table grape", "grape berry", "grape berries",
                                "vitis vinifera", "鲜食葡萄", "grape storage"))


def classify(title: str, description: str) -> dict[str, Any]:
    """严格判据：A 级必须标题有葡萄（或描述明确鲜食葡萄）且贮藏证据充分。

    网页检索噪声极大（同一记录可能只是图注、书本章节、鱼类保鲜等），
    因此 A 级要求：strong_grape ∧ (标题含贮藏词 ∨ 描述含 ≥2 个贮藏词)，
    且标题不命中「figure/supplementary/无关领域」模式；标题含加工词（酒/汁/干）
    而无贮藏词的降为 B。
    """
    text = f"{title} {description}"
    low_title = (title or "").lower()
    grape = hit_any(text, GRAPE_TERMS)
    storage = hit_any(text, STORAGE_TERMS)
    title_storage = hit_any(title, STRICT_STORAGE_TITLE_TERMS)
    processing = hit_any(text, PROCESSING_TERMS)
    field = hit_any(text, FIELD_TERMS)
    produce = hit_any(text, PRODUCE_TERMS)
    title_produce = hit_any(title, PRODUCE_TERMS)
    avoid = [p for p in AVOID_TITLE_PATTERNS if p in low_title]
    sg = strong_grape(title, description)
    hard_storage = any(t in (text or "").lower() for t in (
        "postharvest", "post-harvest", "cold storage", "controlled atmosphere",
        "sulfur dioxide", "shelf life", "storage life", "decay", "rachis",
        "berry drop", "firmness", "采后", "贮藏", "储藏", "保鲜", "冷藏", "气调",
        "二氧化硫", "货架期", "耐贮",
    ))
    has_storage = bool(title_storage) or (hard_storage and len(storage) >= 2)

    # A 级必须真的有贮藏词（防止 "quality traits during fruit growth" 这类误判）
    if sg and storage and has_storage and not avoid:
        if processing and not title_storage:
            tier, why = "B", f"葡萄但偏加工方向：{'/'.join(processing[:2])}"
        else:
            tier, why = "A", f"葡萄+贮藏：{'/'.join(grape[:3])} × {'/'.join(storage[:3])}"
    elif sg:
        tier, why = "B", f"葡萄但无充分贮藏证据：{'/'.join(grape[:3])}"
    elif storage and produce and (title_produce or title_storage):
        tier, why = "C", f"其他果蔬采后：{'/'.join(produce[:2])} × {'/'.join(storage[:2])}"
    else:
        tier, why = "D", "与葡萄贮藏无关（检索噪声）"
    score = 0
    if tier == "A":
        score = 100 + 10 * len(storage) + (30 if title_storage else 0)
    elif tier == "C":
        score = 20 + len(storage) + (10 if title_storage else 0)
    return {
        "tier": tier, "why": why, "score": score,
        "grape_terms": grape, "storage_terms": storage,
        "processing_terms": processing, "field_terms": field, "produce_terms": produce,
    }


# ---------------------------------------------------------------------------
# 采集：Zenodo
# ---------------------------------------------------------------------------
ZENODO_QUERIES = [
    'table grape AND storage',
    '"table grape" AND postharvest',
    'grape AND postharvest AND storage',
    'grape AND "cold storage"',
    'grape AND "controlled atmosphere"',
    'grape AND "sulfur dioxide"',
    'grape AND "shelf life"',
    'grape AND preservation AND storage',
    'grape berry AND storage',
    'grape AND rachis',
    'grape AND "berry drop"',
    'grape AND "quality" AND storage',
    'Vitis AND postharvest',
    'grapes AND "storage life"',
]


def zenodo_records(query: str, pages: int = 6, size: int = 25) -> list[dict]:
    """Zenodo 单页上限 25；用 AND 语法提高精度。"""
    out: list[dict] = []
    for page in range(1, pages + 1):
        url = "https://zenodo.org/api/records?" + urllib.parse.urlencode(
            {"q": query, "size": size, "page": page})
        st, data = http_json(url)
        if st != 200 or not isinstance(data, dict):
            print(f"  [zenodo] {query!r} p{page} HTTP {st}")
            if st in (429, 403):
                time.sleep(10)
            break
        hits = (data.get("hits") or {}).get("hits") or []
        if not hits:
            break
        out.extend(hits)
        total = (data.get("hits") or {}).get("total") or 0
        if page * size >= total:
            break
        time.sleep(0.8)
    return out


def normalize_zenodo(hit: dict) -> dict[str, Any] | None:
    md = hit.get("metadata") or {}
    title = clean_text(md.get("title"), 300)
    desc = clean_text(md.get("description"), 3000)
    cls = classify(title, desc)
    if cls["tier"] not in ("A", "C"):
        return None
    files = []
    for f in hit.get("files") or []:
        key = f.get("key") or ""
        link = (f.get("links") or {}).get("self") or (f.get("links") or {}).get("content")
        if not link:
            continue
        files.append({
            "name": key,
            "url": link,
            "size_bytes": f.get("size"),
            "type": Path(key).suffix.lower().lstrip(".") or "other",
            "verified": bool(f.get("size")),
        })
    if not files:
        return None
    lic = md.get("license") or {}
    return {
        "source": "zenodo",
        "id": f"10.5281/zenodo.{hit.get('id')}" if hit.get("doi") is None else (hit.get("doi") or f"10.5281/zenodo.{hit.get('id')}"),
        "doi": hit.get("doi") or "",
        "title": title,
        "description": desc[:500],
        "published": (md.get("publication_date") or hit.get("created") or "")[:10],
        "license": lic.get("id") or lic.get("title") or "",
        "landing_url": hit.get("doi_url") or f"https://zenodo.org/records/{hit.get('id')}",
        "files": files,
        "resource_type": (md.get("resource_type") or {}).get("type") or "",
        "relevance": {**{k: cls[k] for k in ("tier", "grape_terms", "storage_terms", "why")},
                      "score": cls["score"]},
        "notes": f"zenodo record {hit.get('id')}",
    }


def collect_zenodo() -> list[dict]:
    seen: dict[str, dict] = {}
    for q in ZENODO_QUERIES:
        hits = zenodo_records(q)
        added = 0
        for h in hits:
            rec = normalize_zenodo(h)
            if not rec:
                continue
            if rec["id"] in seen:
                continue
            seen[rec["id"]] = rec
            added += 1
        print(f"  [zenodo] {q!r}: 抓 {len(hits)} 条，新增候选 {added}")
    print(f"[zenodo] 候选合计 {len(seen)}")
    return list(seen.values())


# ---------------------------------------------------------------------------
# 采集：Dryad
# ---------------------------------------------------------------------------
DRYAD_QUERIES = ["grape storage", "table grape postharvest", "grape preservation",
                 "grape cold storage", "grape shelf life", "Vitis postharvest"]


def collect_dryad() -> list[dict]:
    seen: dict[str, dict] = {}
    for q in DRYAD_QUERIES:
        url = "https://datadryad.org/api/v2/search?" + urllib.parse.urlencode(
            {"q": q, "per_page": 50})
        st, data = http_json(url)
        if st != 200 or not isinstance(data, dict):
            print(f"  [dryad] {q!r} HTTP {st}")
            continue
        datasets = ((data.get("_embedded") or {}).get("stash:datasets") or [])
        added = 0
        for ds in datasets:
            title = clean_text(ds.get("title"), 300)
            desc = clean_text(ds.get("abstract"), 2000)
            cls = classify(title, desc)
            if cls["tier"] not in ("A", "C"):
                continue
            doi = ds.get("identifier") or ""
            self_url = (ds.get("_links") or {}).get("self", {}).get("href", "")
            key = doi or self_url
            if not key or key in seen:
                continue
            # 文件列表要再请求一次
            files = []
            try:
                ds_url = "https://datadryad.org" + self_url if self_url.startswith("/") else self_url
                st2, ds_data = http_json(ds_url + "/versions")
                versions = (ds_data.get("_embedded") or {}).get("stash:versions") or []
                if versions:
                    v = versions[-1]
                    furl = "https://datadryad.org" + (v.get("_links") or {}).get("stash:files", {}).get("href", "")
                    st3, fdata = http_json(furl + "?per_page=100")
                    for f in ((fdata.get("_embedded") or {}).get("stash:files") or []):
                        dlink = (f.get("_links") or {}).get("stash:file-download", {}).get("href", "")
                        if dlink:
                            files.append({
                                "name": f.get("path") or "",
                                "url": "https://datadryad.org" + dlink if dlink.startswith("/") else dlink,
                                "size_bytes": f.get("size"),
                                "type": (Path(f.get("path") or "").suffix.lstrip(".") or "other"),
                                "verified": bool(f.get("size")),
                            })
            except Exception as exc:  # noqa: BLE001
                print(f"    [dryad] 取文件失败 {doi}: {exc}")
            if not files:
                continue
            seen[key] = {
                "source": "dryad",
                "id": doi,
                "doi": doi,
                "title": title,
                "description": desc[:500],
                "published": (ds.get("publicationDate") or "")[:10],
                "license": ds.get("license") or "",
                "landing_url": f"https://doi.org/{doi}" if doi else self_url,
                "files": files,
                "relevance": {**{k: cls[k] for k in ("tier", "grape_terms", "storage_terms", "why")},
                              "score": cls["score"]},
                "notes": "dryad",
            }
            added += 1
        print(f"  [dryad] {q!r}: {len(datasets)} 命中，新增 {added}")
        time.sleep(SLEEP)
    print(f"[dryad] 候选合计 {len(seen)}")
    return list(seen.values())


# ---------------------------------------------------------------------------
# 采集：Harvard Dataverse
# ---------------------------------------------------------------------------
DV_QUERIES = ["table grape storage", "grape postharvest", "grape cold storage",
              "grape preservation", "grape shelf life", "grape quality storage"]


def collect_dataverse() -> list[dict]:
    seen: dict[str, dict] = {}
    for q in DV_QUERIES:
        url = "https://dataverse.harvard.edu/api/search?" + urllib.parse.urlencode(
            {"q": q, "type": "dataset", "per_page": 50})
        st, data = http_json(url)
        if st != 200 or not isinstance(data, dict):
            print(f"  [dataverse] {q!r} HTTP {st}")
            continue
        items = ((data.get("data") or {}).get("items") or [])
        added = 0
        for it in items:
            title = clean_text(it.get("name"), 300)
            desc = clean_text(" ".join(it.get("description") or []), 2000)
            cls = classify(title, desc)
            if cls["tier"] not in ("A", "C"):
                continue
            gid = it.get("global_id") or ""
            if not gid or gid in seen:
                continue
            # 取文件清单
            files = []
            try:
                st2, ds = http_json(
                    "https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId="
                    + urllib.parse.quote(gid))
                if st2 == 200:
                    for f in (((ds.get("data") or {}).get("latestVersion") or {}).get("files") or []):
                        df = f.get("dataFile") or {}
                        fid = df.get("id")
                        fname = df.get("filename") or ""
                        if not fid:
                            continue
                        files.append({
                            "name": fname,
                            "url": f"https://dataverse.harvard.edu/api/access/datafile/{fid}",
                            "size_bytes": df.get("filesize"),
                            "type": (Path(fname).suffix.lstrip(".") or "other"),
                            "verified": bool(df.get("filesize")),
                        })
            except Exception as exc:  # noqa: BLE001
                print(f"    [dataverse] 取文件失败 {gid}: {exc}")
            if not files:
                continue
            seen[gid] = {
                "source": "dataverse",
                "id": gid,
                "doi": (it.get("global_id") or "").replace("doi:", ""),
                "title": title,
                "description": desc[:500],
                "published": (it.get("published_at") or "")[:10],
                "license": it.get("license") or "",
                "landing_url": it.get("url") or f"https://doi.org/{gid.replace('doi:', '')}",
                "files": files,
                "relevance": {**{k: cls[k] for k in ("tier", "grape_terms", "storage_terms", "why")},
                              "score": cls["score"]},
                "notes": "harvard dataverse",
            }
            added += 1
        print(f"  [dataverse] {q!r}: {len(items)} 命中，新增 {added}")
        time.sleep(SLEEP)
    print(f"[dataverse] 候选合计 {len(seen)}")
    return list(seen.values())


# ---------------------------------------------------------------------------
# 采集：DataCite（跨仓储元数据目录，主要用于发现与去重）
# ---------------------------------------------------------------------------
DATACITE_QUERIES = [
    '"table grape" AND storage', '"table grape" AND postharvest',
    'grape AND preservation', 'grape AND "cold storage"',
    'grape AND postharvest', 'grape AND "storage quality"',
    '"table grape" AND quality', 'grape AND "cold chain"',
    '葡萄 贮藏', '葡萄 保鲜',
]


def enrich_mendeley(records: list[dict]) -> list[dict]:
    """DataCite 里 10.17632/* 是 Mendeley Data；用其文件 API 取真实文件清单。

    接口：GET https://data.mendeley.com/api/datasets/{id}/files
    返回 filename / content_details.size / content_details.download_url / sha256_hash。
    """
    seen = set()
    for rec in records:
        doi = (rec.get("doi") or "").lower()
        if not doi.startswith("10.17632/"):
            continue
        ds_id = doi.split("/", 1)[1].split(".")[0]
        if ds_id in seen:
            continue
        seen.add(ds_id)
        st, data = http_json(f"https://data.mendeley.com/api/datasets/{ds_id}/files")
        if st != 200 or not isinstance(data, list):
            print(f"  [mendeley] {ds_id} 文件 API HTTP {st}")
            continue
        files = []
        for item in data:
            cd = item.get("content_details") or {}
            url = cd.get("download_url")
            if not url:
                continue
            name = item.get("filename") or ""
            files.append({
                "name": name,
                "url": url,
                "size_bytes": cd.get("size"),
                "type": Path(name).suffix.lower().lstrip(".") or "other",
                "verified": bool(cd.get("size")),
                "sha256": cd.get("sha256_hash") or "",
            })
        if files:
            rec["files"] = files
            rec["source"] = "mendeley"
            rec["notes"] = (rec.get("notes") or "") + f"；mendeley files={len(files)}"
        time.sleep(SLEEP)
    return records


def collect_datacite() -> list[dict]:
    seen: dict[str, dict] = {}
    for q in DATACITE_QUERIES:
        url = "https://api.datacite.org/dois?" + urllib.parse.urlencode(
            {"query": q, "page[size]": 100, "resource-type-id": "dataset"})
        st, data = http_json(url)
        if st != 200 or not isinstance(data, dict):
            print(f"  [datacite] {q!r} HTTP {st}")
            continue
        rows = data.get("data") or []
        added = 0
        for row in rows:
            a = row.get("attributes") or {}
            titles = a.get("titles") or [{}]
            title = clean_text(titles[0].get("title"), 300)
            descs = a.get("descriptions") or [{}]
            desc = clean_text(" ".join(d.get("description") or "" for d in descs), 3000)
            cls = classify(title, desc)
            if cls["tier"] not in ("A", "C"):
                continue
            doi = a.get("doi") or ""
            if not doi or doi.lower() in seen:
                continue
            files = []
            content_url = a.get("contentUrl")
            if isinstance(content_url, str) and content_url:
                files.append({"name": content_url.rsplit("/", 1)[-1], "url": content_url,
                              "size_bytes": None, "type": "other", "verified": False})
            rights = a.get("rightsList") or [{}]
            seen[doi.lower()] = {
                "source": "datacite",
                "id": doi,
                "doi": doi,
                "title": title,
                "description": desc[:500],
                "published": (a.get("publicationYear") or ""),
                "license": (rights[0].get("rightsIdentifier") or rights[0].get("rights") or ""),
                "landing_url": a.get("url") or f"https://doi.org/{doi}",
                "files": files,
                "resource_type": "dataset",
                "relevance": {**{k: cls[k] for k in ("tier", "grape_terms", "storage_terms", "why")},
                              "score": cls["score"]},
                "notes": f"datacite publisher={a.get('publisher') or ''}",
            }
            added += 1
        print(f"  [datacite] {q!r}: {len(rows)} 条，新增 {added}")
        time.sleep(SLEEP)
    print(f"[datacite] 候选合计 {len(seen)}")
    return list(seen.values())


def stage_reclassify() -> None:
    """对已合并候选按严格判据重判（不重新联网），掉出 A/C 的剔除。"""
    p = WORK / "merged.json"
    if not p.exists():
        raise SystemExit("先运行 collect 与 merge")
    records = json.loads(p.read_text(encoding="utf-8"))
    kept = []
    dropped = 0
    for r in records:
        cls = classify(r.get("title") or "", r.get("description") or "")
        if cls["tier"] not in ("A", "C"):
            dropped += 1
            continue
        r["tier"] = cls["tier"]
        r["why"] = cls["why"]
        r["score"] = cls["score"]
        r["grape_terms"] = cls["grape_terms"]
        r["storage_terms"] = cls["storage_terms"]
        # 是否含非 PDF 数据文件
        r["data_files"] = [f for f in r.get("files") or []
                           if (f.get("name") or "").lower().rsplit(".", 1)[-1] != "pdf"]
        r["metadata_only"] = not r["data_files"]
        kept.append(r)
    kept.sort(key=lambda r: (r["tier"] != "A", r["metadata_only"], -r["score"], r["source"]))
    p.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    a = sum(1 for r in kept if r["tier"] == "A")
    c = len(kept) - a
    with_data = sum(1 for r in kept if r["data_files"])
    print(f"[reclassify] 保留 A={a} C={c}（剔除 {dropped} 条噪声）；含数据文件 {with_data} 条")


# ---------------------------------------------------------------------------
# 采集：国家农业科学数据中心（补充上一轮未下载的公开直链）
# ---------------------------------------------------------------------------
AGRI_QUERIES = [
    "果实 采后", "果蔬 保鲜", "贮藏保鲜", "葡萄 贮藏", "葡萄 保鲜",
    "鲜食葡萄 保鲜", "预冷", "气调", "二氧化硫 保鲜", "货架期", "葡萄 冷藏",
]


def collect_agridata() -> list[dict]:
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import agridata_client as ac  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"  [agridata] 客户端不可用：{exc}")
        return []
    seen: dict[str, dict] = {}
    for q in AGRI_QUERIES:
        for page in (1, 2):
            try:
                data = ac.search_datasets(q, page=page, size=100) or {}
            except Exception as exc:  # noqa: BLE001
                print(f"  [agridata] {q!r} p{page} 失败：{exc}")
                break
            recs = data.get("records") or []
            if not recs:
                break
            for r in recs:
                way = r.get("download_way")
                url = r.get("hj_entity_url") or ""
                if way not in (0, 5) or not url:
                    continue
                gid = r.get("gid")
                if not gid or gid in seen:
                    continue
                title = clean_text(r.get("name_zh"), 300)
                desc = clean_text(r.get("introduction"), 2000)
                cls = classify(title, desc)
                if cls["tier"] not in ("A", "C"):
                    continue
                fname = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])
                seen[gid] = {
                    "source": "agridata",
                    "id": gid,
                    "doi": "",
                    "title": title,
                    "description": desc[:500],
                    "published": (r.get("issue_time") or "")[:10],
                    "license": "见站点详情页数据共享说明",
                    "landing_url": f"http://www.agridata.cn/dataset/detail/{r.get('resource_type') or 'dataset_info'}/{gid}",
                    "files": [{"name": fname, "url": url, "size_bytes": None,
                               "type": Path(fname).suffix.lower().lstrip(".") or "other",
                               "verified": False}],
                    "resource_type": r.get("resource_type") or "dataset_info",
                    "relevance": {**{k: cls[k] for k in ("tier", "grape_terms", "storage_terms", "why")},
                                  "score": cls["score"]},
                    "notes": f"agridata gid={gid} download_way={way} CSTR={r.get('sci_identification') or ''}",
                }
            time.sleep(0.8)
            if len(recs) < 100:
                break
    print(f"[agridata] 公开直链候选 {len(seen)} 条")
    return list(seen.values())


# ---------------------------------------------------------------------------
# 合并 + 去重
# ---------------------------------------------------------------------------
def find_team_candidates() -> list[dict]:
    out = []
    for p in sorted(WORK.glob("candidates_*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[merge] 跳过无法解析的 {p.name}: {exc}")
            continue
        if isinstance(data, dict):
            data = data.get("candidates") or data.get("records") or []
        if not isinstance(data, list):
            continue
        print(f"[merge] {p.name}: {len(data)} 条")
        out.extend(data)
    return out


def stage_collect() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    collected = {
        "collected_at": now(),
        "zenodo": collect_zenodo(),
        "dryad": collect_dryad(),
        "dataverse": collect_dataverse(),
        "datacite": collect_datacite(),
        "agridata": collect_agridata(),
    }
    collected["datacite"] = enrich_mendeley(collected["datacite"])
    track("lead_candidates", collected)
    total = sum(len(v) for v in collected.values() if isinstance(v, list))
    print(f"[collect] 候选合计 {total} 条 -> {RAW / 'lead_candidates.json'}")


def normalize_record(rec: dict) -> dict:
    """统一队友/自采候选的字段差异（tier 顶层 vs relevance.tier、size vs size_bytes 等）。"""
    rel = rec.get("relevance") or {}
    files = []
    for f in rec.get("files") or []:
        size = f.get("size_bytes")
        if size is None:
            size = f.get("size")
        files.append({
            "name": f.get("name") or "",
            "url": f.get("url") or "",
            "size_bytes": size if isinstance(size, (int, float)) else None,
            "type": f.get("type") or (Path(f.get("name") or "").suffix.lower().lstrip(".")),
            "verified": bool(f.get("verified", True)),
        })
    return {
        "source": rec.get("source") or "other",
        "id": rec.get("id") or rec.get("doi") or "",
        "doi": rec.get("doi") or "",
        "title": clean_text(rec.get("title"), 300),
        "description": (rec.get("description") or rec.get("desc") or "")[:500],
        "published": rec.get("published") or "",
        "license": rec.get("license") or "",
        "landing_url": rec.get("landing_url") or "",
        "files": files,
        "tier": rec.get("tier") or rel.get("tier") or "",
        "why": rec.get("why") or rel.get("why") or "",
        "score": rec.get("score") or rel.get("score") or 0,
        "grape_terms": rec.get("grape_terms") or rel.get("grape_terms") or [],
        "storage_terms": rec.get("storage_terms") or rel.get("storage_terms") or [],
        "resource_type": rec.get("resource_type") or "",
        "notes": rec.get("notes") or "",
    }


def stage_merge() -> None:
    lead_raw = RAW / "lead_candidates.json"
    lead = []
    if lead_raw.exists():
        data = json.loads(lead_raw.read_text(encoding="utf-8"))
        for v in data.values():
            if isinstance(v, list):
                lead.extend(v)
    team = find_team_candidates()
    merged: dict[str, dict] = {}
    for raw in lead + team:
        rec = normalize_record(raw)
        key = (rec.get("doi") or rec.get("id") or "").strip().lower()
        if not key:
            continue
        # Mendeley 同一数据集会有带版本后缀的 DOI（xxx.1 / xxx.2），归并到同一主键
        key = re.sub(r"\.\d+$", "", key)
        if key in merged:
            known = {f.get("url") for f in merged[key].get("files") or []}
            for f in rec.get("files") or []:
                if f.get("url") not in known:
                    merged[key]["files"].append(f)
            continue
        merged[key] = rec
    records = list(merged.values())
    kept = []
    for r in records:
        if r.get("tier") not in ("A", "C"):
            continue
        files = [f for f in (r.get("files") or []) if f.get("url")]
        # 合规：站点标注「申请下载（download_way=10）」/「有条件共享」的资源
        # 只能保留元数据，不绕过申请流程去取直链。
        notes = r.get("notes") or ""
        apply_only = ("download_way=10" in notes) or ("申请下载" in notes) or ("有条件共享" in notes)
        if apply_only:
            files = []
        kept.append({
            "source": r.get("source") or "other",
            "id": r.get("id") or r.get("doi") or "",
            "doi": r.get("doi") or "",
            "title": r.get("title") or "",
            "description": (r.get("description") or "")[:500],
            "published": r.get("published") or "",
            "license": r.get("license") or "",
            "landing_url": r.get("landing_url") or "",
            "files": files,
            "tier": r["tier"],
            "why": r.get("why") or "",
            "score": r.get("score") or (100 if r["tier"] == "A" else 20),
            "grape_terms": r.get("grape_terms") or [],
            "storage_terms": r.get("storage_terms") or [],
            "resource_type": r.get("resource_type") or "",
            "access": "apply" if apply_only else "open",
            "metadata_only": not files,
            "notes": (notes + "；合规：站点要求申请，未下载") if apply_only else notes,
        })
    kept.sort(key=lambda r: (r["tier"] != "A", r["metadata_only"], -r["score"], r["source"]))
    (WORK / "merged.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    a = sum(1 for r in kept if r["tier"] == "A")
    c = len(kept) - a
    meta = sum(1 for r in kept if r["metadata_only"])
    with_files = len(kept) - meta
    print(f"[merge] 合并去重后 A={a} C={c}；有文件的 {with_files} 条，仅元数据 {meta} 条 -> {WORK / 'merged.json'}")


# ---------------------------------------------------------------------------
# 下载（预算管理）
# ---------------------------------------------------------------------------
def safe_name(text: str, fallback: str, limit: int = 80) -> str:
    keep = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", text or "").strip(" ._")
    keep = re.sub(r"\s+", "_", keep)
    return (keep or fallback)[:limit]


def dest_for(rec: dict, f: dict) -> Path:
    src = safe_name(rec.get("source") or "other", "src", 20)
    rid = safe_name(rec.get("doi") or rec.get("id") or "rec", "rec", 60)
    name = safe_name(f.get("name") or "file", "file", 100)
    ext = Path(f.get("name") or "").suffix[:10]
    if not name.lower().endswith(ext.lower()) and ext:
        name += ext
    dest = FILES_DIR / src / rid / name
    # Windows 大小写不敏感：README.txt 与 Readme.txt 会撞名，用 URL 短哈希区分
    if dest.exists():
        size = f.get("size_bytes")
        if size is None or dest.stat().st_size != size:
            tag = hashlib.sha1((f.get("url") or "").encode()).hexdigest()[:8]
            dest = dest.with_name(f"{Path(name).stem}_{tag}{Path(name).suffix}")
    return dest


def looks_like_error(body_start: bytes, ctype: str) -> bool:
    low = (ctype or "").lower()
    if "text/html" in low:
        return True
    head = body_start[:64].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def stream_download(url: str, dest: Path, expected: int | None, timeout: int = 300) -> dict:
    """流式下载，返回结果 dict。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            ctype = r.headers.get("Content-Type", "")
            cl = r.headers.get("Content-Length")
            expected = expected or (int(cl) if cl else None)
            if expected and expected > PER_FILE_CAP:
                return {"ok": False, "reason": f"超过单文件上限 {expected}"}
            h = hashlib.sha256()
            total = 0
            first = b""
            with tmp.open("wb") as fh:
                while True:
                    chunk = r.read(1024 * 256)
                    if not chunk:
                        break
                    if total == 0:
                        first = chunk[:64]
                        if looks_like_error(first, ctype):
                            tmp.unlink(missing_ok=True)
                            return {"ok": False, "reason": f"返回 HTML/错误页（{ctype}）"}
                    fh.write(chunk)
                    h.update(chunk)
                    total += len(chunk)
            tmp.replace(dest)
            return {"ok": True, "bytes": total, "sha256": h.hexdigest(), "ctype": ctype,
                    "expected": expected, "match": expected is None or total == expected}
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}


def stage_download() -> None:
    merged_path = WORK / "merged.json"
    if not merged_path.exists():
        raise SystemExit("先运行 merge 阶段")
    records = json.loads(merged_path.read_text(encoding="utf-8"))
    dl_path = WORK / "downloads.json"
    downloads: dict[str, dict] = json.loads(dl_path.read_text(encoding="utf-8")) if dl_path.exists() else {}

    used = sum(int(v.get("bytes") or 0) for v in downloads.values() if v.get("ok"))
    used_c = sum(int(v.get("bytes") or 0) for v in downloads.values()
                 if v.get("ok") and v.get("tier") == "C")
    c_cap = int(TOTAL_CAP * C_TIER_SHARE)
    print(f"[download] 已用 {used / 1024**2:.1f}MB / 上限 {TOTAL_CAP / 1024**3:.2f}GiB（C 级 {used_c / 1024**2:.1f}MB）")

    tasks: list[tuple[dict, dict]] = []
    skipped_records: list[dict] = []
    # 论文排版文件、图片插图不算「数据」，不下载（目录里保留记录）
    SKIP_DATA_EXT = {".doc", ".docx", ".pptx", ".ppt", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
    for rec in records:
        files = [f for f in rec["files"]
                 if Path(f.get("name") or "").suffix.lower() not in SKIP_EXT
                 and Path(f.get("name") or "").suffix.lower() not in SKIP_DATA_EXT
                 and not (f.get("name") or "").startswith("~$")]
        if not files:
            continue
        # 超大记录整体跳过：保持数据集完整性，避免只取到零碎分片
        oversized = [f for f in files if (f.get("size_bytes") or 0) > PER_FILE_CAP]
        if oversized:
            skipped_records.append({
                "tier": rec["tier"], "record": rec["title"], "record_id": rec.get("doi") or rec.get("id"),
                "reason": f"含超过单文件上限的文件（最大 {(oversized[0].get('size_bytes') or 0) / 1024**2:.0f}MB），整体未下载",
                "url": oversized[0].get("url"), "size": oversized[0].get("size_bytes"),
            })
            continue
        for f in files:
            ext = Path(f.get("name") or "").suffix.lower()
            if ext == ".pdf":
                # 论文正文不算「数据」，不占预算
                continue
            tasks.append((rec, f))

    def sort_key(item: tuple[dict, dict]) -> tuple:
        rec, f = item
        size = f.get("size_bytes") or 0
        return (rec["tier"] != "A", -rec["score"], size if size else 10**12, rec["source"])

    tasks.sort(key=sort_key)
    request_count = 0
    for rec, f in tasks:
        key = f"{rec['source']}|{rec.get('doi') or rec.get('id')}|{f.get('name')}"
        if key in downloads and downloads[key].get("ok"):
            continue
        if used >= TOTAL_CAP:
            downloads[key] = {"ok": False, "reason": "总预算已用尽", "tier": rec["tier"],
                              "record": rec.get("title"), "url": f.get("url"), "bytes": 0}
            continue
        # 尺寸未知先探测
        size = f.get("size_bytes")
        if not size:
            size, ctype = get_size(f["url"])
            request_count += 1
            f["size_bytes"] = size
            if size and Path(f.get("name") or "").suffix.lower() in ("", ".bin") and ctype:
                ctype_map = {"application/zip": ".zip", "text/csv": ".csv",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                             "application/pdf": ".pdf"}
                if ctype.split(";")[0] in ctype_map:
                    f["name"] = (f.get("name") or "file") + ctype_map[ctype.split(";")[0]]
        if size is None:
            downloads[key] = {"ok": False, "reason": "无法确定文件大小（可能需登录或链接失效）",
                              "tier": rec["tier"], "record": rec.get("title"),
                              "url": f.get("url"), "bytes": 0}
            continue
        if size > PER_FILE_CAP:
            downloads[key] = {"ok": False, "reason": f"超过单文件上限（{size / 1024**2:.0f}MB）",
                              "tier": rec["tier"], "record": rec.get("title"),
                              "url": f.get("url"), "bytes": 0, "size": size}
            continue
        if used + size > TOTAL_CAP:
            downloads[key] = {"ok": False, "reason": "加入后会超出总预算", "tier": rec["tier"],
                              "record": rec.get("title"), "url": f.get("url"), "bytes": 0, "size": size}
            continue
        if rec["tier"] == "C" and used_c + size > c_cap:
            downloads[key] = {"ok": False, "reason": "C 级预算份额用尽", "tier": rec["tier"],
                              "record": rec.get("title"), "url": f.get("url"), "bytes": 0,
                              "size": size}
            continue
        dest = dest_for(rec, f)
        if dest.exists() and dest.stat().st_size == size:
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            downloads[key] = {"ok": True, "bytes": size, "sha256": digest, "ctype": "",
                              "expected": size, "match": True, "tier": rec["tier"],
                              "record": rec.get("title"), "url": f.get("url"),
                              "local": str(dest.relative_to(ROOT)), "resumed": True,
                              "fetched_at": now()}
            used += size
            used_c += size if rec["tier"] == "C" else 0
            continue

        res = stream_download(f["url"], dest, size)
        request_count += 1
        entry = {
            "ok": res.get("ok"), "reason": res.get("reason"), "bytes": res.get("bytes") or 0,
            "sha256": res.get("sha256"), "ctype": res.get("ctype"),
            "tier": rec["tier"], "record": rec.get("title"),
            "record_id": rec.get("doi") or rec.get("id"),
            "license": rec.get("license"), "source": rec.get("source"),
            "url": f.get("url"), "name": f.get("name"),
            "local": str(dest.relative_to(ROOT)) if res.get("ok") else "",
            "expected": res.get("expected"), "match": res.get("match"),
            "fetched_at": now(),
        }
        downloads[key] = entry
        dl_path.write_text(json.dumps(downloads, ensure_ascii=False, indent=1), encoding="utf-8")
        if res.get("ok"):
            used += res["bytes"]
            if rec["tier"] == "C":
                used_c += res["bytes"]
            status = "OK" if res.get("match") else "OK(大小不一致)"
            print(f"  [{status}] {res['bytes'] / 1024**2:7.1f}MB {rec['tier']} {f.get('name')[:60]} 累计 {used / 1024**2:.0f}MB")
        else:
            print(f"  [SKIP] {rec['tier']} {f.get('name')[:50]}: {res.get('reason')}")
        time.sleep(0.5)

    for item in skipped_records:
        key = f"{item['record_id']}|__record__"
        downloads.setdefault(key, {"ok": False, **item, "bytes": 0, "name": "",
                                   "record_id": item["record_id"]})

    dl_path.write_text(json.dumps(downloads, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = [v for v in downloads.values() if v.get("ok")]
    print(f"[download] 成功 {len(ok)} 个文件，{sum(v['bytes'] for v in ok) / 1024**2:.1f}MB；"
          f"失败/跳过 {len(downloads) - len(ok)}；额外探测请求 {request_count}")


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------
RECORD_COLUMNS = [
    "tier", "source", "id", "doi", "title", "published", "license", "landing_url",
    "access", "grape_terms", "storage_terms", "why", "score", "file_count", "file_bytes",
    "local_files", "description", "notes", "fetched_at",
]


def stage_export() -> None:
    merged_path = WORK / "merged.json"
    if not merged_path.exists():
        raise SystemExit("先运行 merge 阶段")
    records = json.loads(merged_path.read_text(encoding="utf-8"))
    downloads = json.loads((WORK / "downloads.json").read_text(encoding="utf-8")) if (WORK / "downloads.json").exists() else {}
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    by_rec: dict[str, list[dict]] = {}
    for key, v in downloads.items():
        rid = (v.get("record_id") or "").lower()
        by_rec.setdefault(rid, []).append({**v, "key": key})

    rows, file_rows = [], []
    total_bytes = 0
    for rec in records:
        rid = (rec.get("doi") or rec.get("id") or "").lower()
        got = [d for d in by_rec.get(rid, []) if d.get("ok")]
        bytes_got = sum(int(d["bytes"]) for d in got)
        total_bytes += bytes_got
        rows.append({
            "tier": rec["tier"], "source": rec["source"], "id": rec["id"], "doi": rec["doi"],
            "title": rec["title"], "published": rec["published"], "license": rec["license"],
            "landing_url": rec["landing_url"], "access": rec.get("access") or "open",
            "grape_terms": " | ".join(rec.get("grape_terms") or []),
            "storage_terms": " | ".join(rec.get("storage_terms") or []),
            "why": rec.get("why") or "", "score": rec.get("score") or "",
            "file_count": len(rec.get("files") or []), "file_bytes": bytes_got,
            "local_files": " | ".join(d["local"] for d in got),
            "description": rec.get("description") or "", "notes": rec.get("notes") or "",
            "fetched_at": now(),
        })
        for d in got:
            file_rows.append({
                "tier": rec["tier"], "source": rec["source"], "doi": rec["doi"],
                "title": rec["title"], "name": d.get("name") or "",
                "url": d.get("url") or "", "bytes": d.get("bytes") or 0,
                "sha256": d.get("sha256") or "", "local": d.get("local") or "",
                "license": d.get("license") or rec.get("license") or "",
                "fetched_at": d.get("fetched_at") or now(),
            })

    def write_csv(path: Path, data: list[dict], cols: list[str]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)

    write_csv(OUT_DIR / "web_records.csv", rows, RECORD_COLUMNS)
    write_csv(OUT_DIR / "web_files.csv", file_rows,
              ["tier", "source", "doi", "title", "name", "url", "bytes", "sha256", "local",
               "license", "fetched_at"])
    write_csv(OUT_DIR / "web_records_tier_a.csv", [r for r in rows if r["tier"] == "A"], RECORD_COLUMNS)

    failed = [{"key": k, **{kk: vv for kk, vv in v.items() if kk in
                            ("reason", "tier", "record", "record_id", "url", "name", "size")}}
              for k, v in downloads.items() if not v.get("ok")]
    if failed:
        write_csv(OUT_DIR / "download_skipped.csv", failed,
                  ["key", "reason", "tier", "record", "record_id", "url", "name", "size"])

    ok = [v for v in downloads.values() if v.get("ok")]
    per_source: dict[str, dict] = {}
    for rec in records:
        s = per_source.setdefault(rec["source"], {"records": 0, "tier_a": 0, "files": 0, "bytes": 0})
        s["records"] += 1
        s["tier_a"] += 1 if rec["tier"] == "A" else 0
        rid = (rec.get("doi") or rec.get("id") or "").lower()
        got = [d for d in by_rec.get(rid, []) if d.get("ok")]
        s["files"] += len(got)
        s["bytes"] += sum(int(d["bytes"]) for d in got)
    screened_counts: dict[str, int] = {}
    screened_total = 0
    screened_path = OUT_DIR / "screened_records.csv"
    if screened_path.exists():
        with screened_path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                screened_total += 1
                tier = row.get("tier") or "?"
                screened_counts[tier] = screened_counts.get(tier, 0) + 1

    manifest = {
        "title": "全网鲜食葡萄采后贮藏相关开放数据采集（3GB 预算）",
        "generated_at": now(),
        "policy": {
            "total_cap_bytes": TOTAL_CAP,
            "per_file_cap_bytes": PER_FILE_CAP,
            "c_tier_share": C_TIER_SHARE,
            "login": "未登录、未付费、未申请任何权限",
            "rate_limit": "请求间隔约 1 秒",
            "sources": "Zenodo / Dryad / Harvard Dataverse / Mendeley Data / DataCite + 队友侦察候选（ScienceDB、中国科学数据、agridata）",
            "compliance": "站点标注「申请下载/有条件共享」的资源只保留元数据，不绕过申请流程取直链",
        },
        "counts": {
            "records_a": sum(1 for r in rows if r["tier"] == "A"),
            "records_c": sum(1 for r in rows if r["tier"] == "C"),
            "records_total": len(rows),
            "files_downloaded": len(ok),
            "files_skipped": len(downloads) - len(ok),
            "bytes_downloaded": total_bytes,
            "bytes_downloaded_gib": round(total_bytes / 1024**3, 3),
            "budget_used_pct": round(100 * total_bytes / TOTAL_CAP, 1),
            "screened_records": screened_total,
            "screened_tier_counts": screened_counts,
        },
        "per_source": per_source,
        "outputs": {
            "web_records.csv": len(rows),
            "web_files.csv": len(file_rows),
            "web_records_tier_a.csv": sum(1 for r in rows if r["tier"] == "A"),
            "files": len(ok),
        },
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[export] {len(rows)} 条记录 / {len(ok)} 个文件 / {total_bytes / 1024**2:.1f}MB"
          f"（预算 {TOTAL_CAP / 1024**3:.2f}GiB 用了 {manifest['counts']['budget_used_pct']}%）-> {OUT_DIR}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["collect", "merge", "reclassify", "download", "export", "all"])
    args = parser.parse_args(argv)
    stages = ["collect", "merge", "reclassify", "download", "export"] if args.stage == "all" else [args.stage]
    for s in stages:
        print(f"\n=== {s} @ {now()} ===")
        {"collect": stage_collect, "merge": stage_merge, "reclassify": stage_reclassify,
         "download": stage_download, "export": stage_export}[s]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
