#!/usr/bin/env python
"""从国家农业科学数据中心（www.agridata.cn）抓取「鲜食葡萄采后贮藏」相关数据。

抓取对象与口径
--------------
1. 数据集检索：调用站点 /api/app/dataset/search/list（前端同款接口，
   签名/回包加密见 tools/agridata_client.py），按关键词矩阵分页遍历；
2. 详情元数据：调用 /api/app/dataset/detail/{resource_type}/{gid}，
   拿到 DOI/CSTR、引用格式、使用说明、联系单位、下载方式等；
3. 公开文件：只对「在线下载」类（download_way 0/5）且给出实体直链的数据集
   下载原始文件，并做文件头/结构核验；
4. 相关性分级：
   - A：葡萄（含鲜食葡萄/提子）且涉及采后贮藏/保鲜/冷链等；
   - B：葡萄相关，但主题不是采后贮藏（栽培、育种、病虫害、加工等）；
   - C：采后贮藏相关，但不是葡萄（其他果蔬/通用）。
   「贮藏营养」「越冬贮藏」这类休眠期营养含义不算采后贮藏，单独标注，
   避免把「葡萄砧木枝条贮藏营养」误当采后储藏数据。

用法
----
    python scripts/fetch_agridata_grape.py search     # 关键词检索 -> .tmp
    python scripts/fetch_agridata_grape.py classify   # 去重 + 分级
    python scripts/fetch_agridata_grape.py details    # 抓详情元数据
    python scripts/fetch_agridata_grape.py download   # 下载公开文件（限量）
    python scripts/fetch_agridata_grape.py export     # 导出 CSV/JSON/manifest
    python scripts/fetch_agridata_grape.py all        # 全流程

纯标准库实现，不依赖 requests/pandas/openpyxl。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import agridata_client as ac  # noqa: E402

WORK = ROOT / ".tmp" / "agridata" / "harvest"
OUT_DIR = ROOT / "data" / "external" / "agridata"
FILES_DIR = OUT_DIR / "files"
DETAILS_DIR = OUT_DIR / "details"
TZ = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# 关键词矩阵：站点检索是模糊匹配（多词近似 OR），所以既要有葡萄词，
# 也要有采后词，命中后靠 classify 阶段做严格判定。
# ---------------------------------------------------------------------------
QUERIES: dict[str, list[str]] = {
    "grape": [
        "葡萄", "鲜食葡萄", "提子",
    ],
    "grape_postharvest": [
        "葡萄 贮藏", "葡萄 储藏", "葡萄 保鲜", "葡萄 采后",
        "葡萄 冷藏", "葡萄 预冷", "葡萄 气调", "葡萄 二氧化硫",
        "葡萄 货架期", "葡萄 冷链", "葡萄 耐贮", "葡萄 保鲜剂",
        "葡萄 贮藏保鲜", "葡萄 采后生理", "葡萄 腐烂", "葡萄 落粒",
        "鲜食葡萄 贮藏", "鲜食葡萄 保鲜", "葡萄 冰温", "葡萄 熏硫",
        "葡萄 保鲜纸", "葡萄 果梗", "葡萄 穗轴", "葡萄 灰霉病",
    ],
    "postharvest_general": [
        "果实 采后", "果蔬 保鲜", "贮藏保鲜", "二氧化硫 保鲜",
        "保鲜剂", "冷链物流", "货架期", "预冷",
    ],
    # 鲜食葡萄主栽品种名：数据集常以品种命名而不写「葡萄」二字，
    # 单独补一轮，避免漏掉「夏黑贮藏…」这类命名。
    "cultivar": [
        "阳光玫瑰", "夏黑", "巨峰", "红地球", "美人指", "克瑞森",
        "无核白", "火焰无核", "妮娜皇后", "蓝宝石葡萄",
    ],
}
ALL_QUERIES = [q for group in QUERIES.values() for q in group]
# 通用采后词命中量动辄几千条，只取前几页用于「站点有哪些果蔬采后数据」的对照，
# 不追求穷举；葡萄相关词才需要翻完全部页。
GROUP_MAX_PAGES = {"grape": 4, "grape_postharvest": 10, "postharvest_general": 3, "cultivar": 4}

POSTHARVEST_TERMS = [
    "采后", "贮藏", "储藏", "保鲜", "冷藏", "预冷", "气调", "冷链",
    "货架期", "货架寿命", "耐贮", "二氧化硫", "SO2", "硫处理", "熏硫",
    "保鲜剂", "保鲜袋", "保鲜膜", "腐烂率", "落粒", "失水", "呼吸强度",
    "乙烯", "冷库", "贮藏期", "贮藏保鲜", "商品率", "褐变",
]
# 「葡萄」在中文里也出现在 葡萄糖 / 葡萄球菌 / 葡萄膜炎 / 葡萄孢 / 葡萄牙 等
# 与葡萄（果实）无关的词里，必须用负向前瞻排除，否则会误判。
# 「葡萄园/葡萄霜霉病/葡萄溃疡病」这类仍然是葡萄的，不排除。
# 葡萄酒/葡萄干等加工词保留在 grape 命中里，但会由 PROCESSED_TERMS 单独标注。
GRAPE_RE = re.compile(r"葡萄(?!球菌|糖|膜炎|胎|孢|牙)")
GRAPE_TERMS = ["葡萄", "提子"]
# 鲜食葡萄主栽品种：不少数据集以品种命名而不写「葡萄」二字
CULTIVAR_TERMS = [
    "阳光玫瑰", "夏黑", "巨峰", "红地球", "美人指", "克瑞森",
    "无核白", "火焰无核", "妮娜皇后", "蓝宝石",
]
NON_POSTHARVEST_STORAGE = [
    # 休眠期/营养贮藏，不是采后储藏
    "贮藏营养", "越冬贮藏", "枝条贮藏", "贮藏养分", "养分贮藏",
]
PROCESSED_TERMS = ["葡萄酒", "葡萄干", "葡萄籽", "葡萄皮渣", "酿酒", "葡萄醋", "葡萄汁"]
# C 级（其他作物采后）只保留「果蔬/鲜食农产品」语境的记录，
# 避免把稻麦种子耐储藏、甘薯块根储藏、渔港名录这类同词不同义的数据算进来。
PRODUCE_TERMS = [
    "水果", "蔬菜", "果蔬", "果实", "浆果", "鲜食", "鲜切", "采后", "果品",
    "柑橘", "苹果", "梨", "桃", "樱桃", "猕猴桃", "草莓", "香蕉", "荔枝", "龙眼",
    "芒果", "枣", "柿", "石榴", "蓝莓", "番茄", "辣椒", "黄瓜", "食用菌", "叶菜",
    "白菜", "甘蓝", "西兰花", "蒜", "姜", "马铃薯", "洋葱", "蒜薹",
]
NON_PRODUCE_HINTS = [
    "渔港", "质量标准数据库", "种子耐储藏", "块根", "稻谷", "小麦", "玉米", "大豆",
    "薯", "粮食", "面粉", "饲料",
]

SEARCH_PAGE_SIZE = 100
SEARCH_MAX_PAGES = 8
MAX_DETAILS = 220
MAX_DOWNLOADS = 15
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024
USER_AGENT = ac.UA
HTTP_CTX = ac.CTX


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S%z")


def strip_em(text: str | None) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def polite_sleep(base: float = 0.9, jitter: float = 0.5) -> None:
    time.sleep(base + random.random() * jitter)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def hit_terms(text: str, terms: Iterable[str]) -> list[str]:
    low = text.lower()
    return sorted({t for t in terms if t.lower() in low})


# ---------------------------------------------------------------------------
# 阶段 1：检索
# ---------------------------------------------------------------------------
def _record_kind(raw: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """判断检索命中是数据集还是项目/文献，并给出可读标题。

    站点同一接口会混入国家自然科学基金项目库等记录，它们没有 name_zh，
    标题在 title/title_zh，且 data 字段里带 source_name/record_type。
    """
    inner: dict[str, Any] = {}
    blob = raw.get("data")
    if isinstance(blob, str) and blob.strip().startswith("{"):
        try:
            inner = json.loads(blob)
        except json.JSONDecodeError:
            inner = {}
    if (raw.get("name_zh") or "").strip():
        return "dataset", strip_em(raw.get("name_zh")), inner
    title = strip_em(raw.get("title_zh") or raw.get("title") or "")
    source = inner.get("source_name") or raw.get("source_name") or ""
    rtype = inner.get("record_type") or ""
    if rtype == "research" or "基金" in source:
        return "project", title, inner
    if "论文" in source or "文献" in source:
        return "literature", title, inner
    return "other", title, inner


def stage_search(groups: list[str] | None = None) -> dict[str, Any]:
    """按关键词组检索。已存在的 search_hits.json 会被合并，支持分组建模增量补抓。"""
    existing = read_json(WORK / "search_hits.json", {}) or {}
    hits: dict[str, dict[str, Any]] = {h["gid"]: h for h in existing.get("hits") or []}
    per_query: dict[str, dict[str, Any]] = dict(existing.get("queries") or {})
    requests = 0
    selected = [g for g in QUERIES if not groups or g in groups]
    for group in selected:
        queries = QUERIES[group]
        max_pages = GROUP_MAX_PAGES.get(group, SEARCH_MAX_PAGES)
        for q in queries:
            if q in per_query:
                print(f"  [skip] {q!r} 已抓过")
                continue
            total = 0
            for page in range(1, max_pages + 1):
                try:
                    res = ac.search_datasets(q, page=page, size=SEARCH_PAGE_SIZE)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [WARN] {q} p{page} 失败: {exc}")
                    break
                requests += 1
                data = res if isinstance(res, dict) else {}
                total = data.get("totalRecord") or 0
                records = data.get("records") or []
                if not records:
                    break
                for r in records:
                    gid = r.get("gid")
                    if not gid:
                        continue
                    kind, title, inner = _record_kind(r)
                    item = hits.setdefault(
                        gid,
                        {
                            "gid": gid,
                            "record_kind": kind,
                            "resource_type": r.get("resource_type") or "dataset_info",
                            "name_zh": strip_em(r.get("name_zh")) or title,
                            "title_only": title if not (r.get("name_zh") or "").strip() else "",
                            "source_name": inner.get("source_name") or r.get("source_name") or "",
                            "inner_record_type": inner.get("record_type") or "",
                            "keywords": strip_em(r.get("keywords")),
                            "introduction": strip_em(r.get("introduction")),
                            "issue_time": r.get("issue_time") or inner.get("start_date"),
                            "data_size": r.get("data_size"),
                            "data_format": r.get("data_format"),
                            "download_way": r.get("download_way"),
                            "data_share": r.get("data_share"),
                            "year": r.get("year"),
                            "sci_identification": r.get("sci_identification"),
                            "property_right_unit": strip_em(r.get("property_right_unit")),
                            "author": strip_em(r.get("author")),
                            "hj_entity_url": r.get("hj_entity_url"),
                            "resource_link": r.get("resource_link"),
                            "matched_queries": [],
                            "query_group": group,
                        },
                    )
                    if q not in item["matched_queries"]:
                        item["matched_queries"].append(q)
                print(f"  [{group}] {q!r} p{page}: +{len(records)} 条（该词共 {total} 条）")
                if len(records) < SEARCH_PAGE_SIZE or page * SEARCH_PAGE_SIZE >= total:
                    break
                polite_sleep()
            per_query[q] = {"group": group, "total": total}
            polite_sleep()
    payload = {
        "fetched_at": now(),
        "queries": per_query,
        "total_requests": (existing.get("total_requests") or 0) + requests,
        "unique_hits": len(hits),
        "hits": list(hits.values()),
    }
    write_json(WORK / "search_hits.json", payload)
    kinds: dict[str, int] = {}
    for h in hits.values():
        kinds[h["record_kind"]] = kinds.get(h["record_kind"], 0) + 1
    print(f"[search] 去重命中 {len(hits)} 条（{kinds}），本轮请求 {requests} 次 -> {WORK / 'search_hits.json'}")
    return payload


# ---------------------------------------------------------------------------
# 阶段 2：分级
# ---------------------------------------------------------------------------
def _grape_terms(text: str) -> list[str]:
    """识别真葡萄（排除 葡萄糖 / 葡萄球菌 / 葡萄膜炎 之类的假命中；
    品种名如「阳光玫瑰」「夏黑」也算葡萄证据）。"""
    found = []
    if GRAPE_RE.search(text):
        found.append("葡萄")
    if "提子" in text:
        found.append("提子")
    found.extend(t for t in CULTIVAR_TERMS if t in text)
    return found


def classify_hit(hit: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        [hit.get("name_zh") or "", hit.get("keywords") or "", hit.get("introduction") or ""]
    )
    name_kw = " ".join([hit.get("name_zh") or "", hit.get("keywords") or ""])
    grape = _grape_terms(text)
    grape_core = _grape_terms(name_kw)  # 名称或关键词里明确是葡萄（更硬的证据）
    post = hit_terms(text, POSTHARVEST_TERMS)
    dormant = hit_terms(text, NON_POSTHARVEST_STORAGE)
    processed = hit_terms(text, PROCESSED_TERMS)
    produce = hit_terms(text, PRODUCE_TERMS)
    non_produce = hit_terms(text, NON_PRODUCE_HINTS)
    # 只有「贮藏营养/越冬」等词命中、且没有其他采后词时，不算采后
    post_effective = list(post)
    if dormant and set(post) <= set(dormant) | {"贮藏", "储藏"}:
        post_effective = []
        dormant_only = True
    else:
        dormant_only = False
    # 葡萄酒/葡萄干等加工词，且名称里没有「鲜食」、也没有采后词 -> 不算鲜食葡萄
    processed_only = bool(processed) and not post_effective and "鲜食" not in name_kw
    # 仅正文顺带出现葡萄、名称与关键词都不是葡萄 -> 不算葡萄主题数据
    grape_weak = bool(grape) and not grape_core

    if grape_core and post_effective:
        tier = "A"
        reason = "名称/关键词为葡萄且含采后贮藏词：" + "+".join(grape_core) + " / " + "+".join(post_effective)
    elif grape_core:
        tier = "B"
        if dormant_only:
            reason = "葡萄相关，但「贮藏」指休眠期营养贮藏，非采后：" + "+".join(dormant)
        elif processed_only:
            reason = "葡萄加工品相关（" + "+".join(processed) + "），非鲜食葡萄采后贮藏"
        else:
            reason = "葡萄相关，但未见采后贮藏词：" + "+".join(grape_core)
    elif post_effective and produce and not non_produce:
        tier = "C"
        reason = "果蔬采后贮藏相关，但主体不是葡萄：" + "+".join(produce) + " / " + "+".join(post_effective)
    else:
        tier = "D"
        if grape_weak:
            reason = "仅正文顺带提及葡萄，名称/关键词不是葡萄主题"
        elif post_effective:
            reason = "命中储藏类词但非果蔬采后语境（" + "+".join(non_produce or post_effective) + "）"
        else:
            reason = "既非葡萄也非采后贮藏（检索模糊命中）"

    hit["tier"] = tier
    hit["tier_reason"] = reason
    hit["evidence_terms"] = {
        "grape": grape, "grape_core": grape_core, "postharvest": post_effective,
        "produce": produce, "dormant_storage": dormant, "processed": processed,
    }
    return hit


def stage_classify() -> dict[str, Any]:
    src = read_json(WORK / "search_hits.json")
    if not src:
        raise SystemExit("先运行 search 阶段")
    hits = [classify_hit(h) for h in src["hits"]]
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    hits.sort(key=lambda h: (order[h["tier"]], h.get("issue_time") or ""), reverse=False)
    counts: dict[str, int] = {}
    for h in hits:
        counts[h["tier"]] = counts.get(h["tier"], 0) + 1
    payload = {"classified_at": now(), "counts": counts, "hits": hits}
    write_json(WORK / "candidates.json", payload)
    print(f"[classify] 分级统计: {counts}")
    return payload


# ---------------------------------------------------------------------------
# 阶段 3：详情
# ---------------------------------------------------------------------------
def stage_details() -> dict[str, Any]:
    src = read_json(WORK / "candidates.json")
    if not src:
        raise SystemExit("先运行 classify 阶段")
    # 详情抓取优先级：A 全抓；B 全抓（葡萄相关要能说清楚站点都有什么）；
    # C 按命中词多少取前 40 条；D 不抓。
    tier_a = [h for h in src["hits"] if h["tier"] == "A"]
    tier_b = [h for h in src["hits"] if h["tier"] == "B"]
    tier_c = sorted(
        [h for h in src["hits"] if h["tier"] == "C"],
        key=lambda h: (len(h["evidence_terms"]["postharvest"]), h.get("name_zh") or ""),
        reverse=True,
    )[:40]
    targets = tier_a + tier_b + tier_c
    targets = targets[:MAX_DETAILS]
    print(f"[details] 目标 {len(targets)} 条（A={len(tier_a)} B={len(tier_b)} C={len(tier_c)}）")

    store = read_json(WORK / "details.json", {}) or {}
    fetched = 0
    for i, hit in enumerate(targets, 1):
        gid = hit["gid"]
        if gid in store and "error" not in store[gid]:
            continue
        rtype = hit.get("resource_type") or "dataset_info"
        try:
            detail = ac.api(f"/api/app/dataset/detail/{rtype}/{gid}", {})
            store[gid] = {"fetched_at": now(), "resource_type": rtype, "detail": detail}
            fetched += 1
            print(f"  [{i}/{len(targets)}] {hit['tier']} {gid} {hit.get('name_zh','')[:36]}")
        except Exception as exc:  # noqa: BLE001
            store[gid] = {"fetched_at": now(), "resource_type": rtype, "error": str(exc)}
            print(f"  [{i}/{len(targets)}] ERR {gid}: {exc}")
        if i % 25 == 0:
            write_json(WORK / "details.json", store)
        polite_sleep()
    write_json(WORK / "details.json", store)
    ok = sum(1 for v in store.values() if "error" not in v)
    print(f"[details] 完成 {fetched} 条，累计成功 {ok}/{len(store)}")
    return store


# ---------------------------------------------------------------------------
# 阶段 3.5：用详情字段二次分级
# ---------------------------------------------------------------------------
def stage_refine() -> dict[str, Any]:
    """检索列表的 introduction 可能被截断，用详情里的关键词/描述/摘要重新判定。

    只对已抓到详情的记录生效；项目/文献记录没有详情，保持原判。
    """
    cands = read_json(WORK / "candidates.json")
    details = read_json(WORK / "details.json", {}) or {}
    if not cands:
        raise SystemExit("先运行 classify 阶段")
    changed = []
    for hit in cands["hits"]:
        det = (details.get(hit["gid"]) or {}).get("detail") or {}
        if not det:
            continue
        merged = dict(hit)
        merged["name_zh"] = det.get("datasetNameZh") or hit.get("name_zh")
        merged["keywords"] = det.get("keywords") or hit.get("keywords")
        merged["introduction"] = " ".join(filter(None, [
            det.get("introduction") or hit.get("introduction"),
            det.get("dataSummary") or "",
            det.get("specialName") or "",
            det.get("timeRange") or "",
        ]))
        rerun = classify_hit(merged)
        if rerun["tier"] != hit["tier"]:
            changed.append((hit["gid"], hit["tier"], rerun["tier"], rerun.get("name_zh") or hit.get("name_zh")))
            hit["tier"] = rerun["tier"]
            hit["tier_reason"] = rerun["tier_reason"] + "（依据详情字段复核）"
            hit["evidence_terms"] = rerun["evidence_terms"]
    counts: dict[str, int] = {}
    for h in cands["hits"]:
        counts[h["tier"]] = counts.get(h["tier"], 0) + 1
    cands["refined_at"] = now()
    cands["counts"] = counts
    write_json(WORK / "candidates.json", cands)
    print(f"[refine] 复核后分级 {counts}；发生变化的 {len(changed)} 条")
    for gid, old, new, name in changed:
        print(f"  {old}->{new} {gid} {name[:40]}")
    return cands


# ---------------------------------------------------------------------------
# 阶段 4：下载公开文件
# ---------------------------------------------------------------------------
def _quote_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return parts._replace(path=urllib.parse.quote(parts.path, safe="/")).geturl()


def _safe_filename(name: str, fallback: str) -> str:
    keep = re.sub(r"[\\/:*?\"<>|\r\n\t]", "_", name or "").strip(" ._")
    return keep[:120] or fallback


def _sniff(path: Path) -> dict[str, Any]:
    """轻量结构核验：文件头 + xlsx 工作表名 / zip 条目 / 文本首行。"""
    info: dict[str, Any] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    head = path.read_bytes()[:8]
    info["magic"] = head.hex()
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                info["zip_entries"] = len(names)
                info["zip_preview"] = names[:10]
                sheets = [n for n in names if n.startswith("xl/worksheets/sheet")]
                if sheets:
                    info["container"] = "xlsx"
                    info["worksheet_count"] = len(sheets)
                    if "xl/workbook.xml" in names:
                        wb = zf.read("xl/workbook.xml").decode("utf-8", "replace")
                        info["sheet_names"] = re.findall(r'name="([^"]+)"', wb)[:20]
                else:
                    info["container"] = "zip"
        else:
            raw = path.read_bytes()[:4000]
            for enc in ("utf-8-sig", "gb18030", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = raw.decode("utf-8", "replace")
            info["container"] = "text"
            info["first_lines"] = [ln for ln in text.splitlines()[:5] if ln.strip()][:5]
    except Exception as exc:  # noqa: BLE001
        info["sniff_error"] = f"{type(exc).__name__}: {exc}"
    return info


def stage_download() -> dict[str, Any]:
    cands = read_json(WORK / "candidates.json")
    details = read_json(WORK / "details.json", {}) or {}
    if not cands:
        raise SystemExit("先运行 classify 阶段")
    manifest = read_json(WORK / "downloads.json", {}) or {}
    FILES_DIR.mkdir(parents=True, exist_ok=True)

    todo = [h for h in cands["hits"] if h["tier"] in ("A", "B", "C")]
    picked: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for hit in todo:
        rec = details.get(hit["gid"], {})
        det = rec.get("detail") or {}
        way = det.get("downloadWay", hit.get("download_way"))
        url = det.get("hjEntityUrl") or hit.get("hj_entity_url") or ""
        if way in (0, 5) and url:
            picked.append((hit, det))
        if len(picked) >= MAX_DOWNLOADS:
            break

    print(f"[download] 在线下载类候选 {len(picked)} 个")
    for hit, det in picked:
        gid = hit["gid"]
        if gid in manifest and "error" not in manifest[gid]:
            continue
        url = det.get("hjEntityUrl") or hit.get("hj_entity_url")
        ext = Path(urllib.parse.urlsplit(url).path).suffix or ".bin"
        fname = _safe_filename(
            f"{hit['tier']}_{gid[:8]}_{det.get('datasetNameZh') or hit.get('name_zh')}", gid
        ) + ext
        dest = FILES_DIR / fname
        try:
            quoted = _quote_url(url)
            req = urllib.request.Request(quoted, headers={"User-Agent": USER_AGENT, "Referer": ac.BASE + "/"})
            with urllib.request.urlopen(req, timeout=120, context=HTTP_CTX) as r:
                length = int(r.headers.get("Content-Length") or 0)
                if length > MAX_DOWNLOAD_BYTES:
                    raise RuntimeError(f"文件过大 {length} 字节，跳过")
                data = r.read()
                ctype = r.headers.get("Content-Type", "")
            dest.write_bytes(data)
            sniff = _sniff(dest)
            manifest[gid] = {
                "fetched_at": now(),
                "file": str(dest.relative_to(ROOT)),
                "source_url": url,
                "http_content_type": ctype,
                "http_content_length": length,
                "tier": hit["tier"],
                "name_zh": det.get("datasetNameZh") or hit.get("name_zh"),
                "sci_identification": det.get("sciIdentification") or hit.get("sci_identification"),
                **sniff,
            }
            print(f"  OK {gid} {dest.name} {sniff.get('bytes')}B {sniff.get('container')}")
        except Exception as exc:  # noqa: BLE001
            manifest[gid] = {
                "fetched_at": now(), "source_url": url, "tier": hit["tier"],
                "name_zh": det.get("datasetNameZh") or hit.get("name_zh"),
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"  ERR {gid} {exc}")
        write_json(WORK / "downloads.json", manifest)
        polite_sleep(1.2, 0.8)
    write_json(WORK / "downloads.json", manifest)
    ok = sum(1 for v in manifest.values() if "error" not in v)
    print(f"[download] 成功 {ok}/{len(manifest)}")
    return manifest


# ---------------------------------------------------------------------------
# 阶段 5：导出
# ---------------------------------------------------------------------------
DOWNLOAD_WAY_LABEL = {0: "在线下载", 5: "在线下载", 3: "外链下载", 4: "外链下载", 10: "申请下载"}
DATA_SHARE_LABEL = {1: "完全公开", 2: "有条件共享", 3: "不共享"}

CSV_COLUMNS = [
    "tier", "tier_reason", "record_kind", "source_name", "gid", "name_zh", "name_en", "keywords", "introduction",
    "sci_identification", "data_set_doi", "article_doi", "citation_format", "refer_standard",
    "issue_time", "open_start_date", "year", "data_size", "data_format", "data_type",
    "area", "time_range", "languages", "download_way", "download_way_label",
    "data_share", "data_share_label", "special_name", "certificate_code", "full_certificate_code",
    "property_right_unit", "organization", "producer", "author", "contact", "unit", "email",
    "project_name", "project_code", "version", "view_count", "download_count", "cite_count",
    "data_summary", "usage_notes", "refer_standard_note",
    "hj_entity_url", "resource_link", "file_local", "detail_url",
    "matched_queries", "matched_query_count", "evidence_grape", "evidence_postharvest",
    "evidence_dormant", "evidence_processed",
]
KIND_LABEL = {"dataset": "数据集", "project": "科研项目", "literature": "文献", "other": "其他"}


def _row(hit: dict[str, Any], det: dict[str, Any], dl: dict[str, Any]) -> dict[str, Any]:
    ev = hit.get("evidence_terms") or {}
    rtype = hit.get("resource_type") or "dataset_info"
    return {
        "tier": hit["tier"],
        "tier_reason": hit["tier_reason"],
        "record_kind": hit.get("record_kind") or "dataset",
        "source_name": hit.get("source_name") or "",
        "gid": hit["gid"],
        "name_zh": det.get("datasetNameZh") or hit.get("name_zh"),
        "name_en": det.get("datasetNameEn") or "",
        "keywords": det.get("keywords") or hit.get("keywords"),
        "introduction": det.get("introduction") or hit.get("introduction"),
        "sci_identification": det.get("sciIdentification") or hit.get("sci_identification") or "",
        "data_set_doi": det.get("dataSetDoi") or "",
        "article_doi": det.get("articleDoi") or "",
        "citation_format": det.get("citationFormat") or "",
        "refer_standard": det.get("referStandard") or "",
        "issue_time": det.get("issueTime") or hit.get("issue_time"),
        "open_start_date": det.get("openStartDate") or "",
        "year": hit.get("year") or "",
        "data_size": det.get("dataSize") or hit.get("data_size") or "",
        "data_format": det.get("dataFormat") or hit.get("data_format") or "",
        "data_type": det.get("dataType") if det else "",
        "area": det.get("area") or "",
        "time_range": det.get("timeRange") or "",
        "languages": det.get("languages") or "",
        "download_way": det.get("downloadWay") if det else hit.get("download_way"),
        "download_way_label": DOWNLOAD_WAY_LABEL.get(det.get("downloadWay") if det else hit.get("download_way"), ""),
        "data_share": det.get("dataShare") if det else hit.get("data_share"),
        "data_share_label": DATA_SHARE_LABEL.get(det.get("dataShare") if det else hit.get("data_share"), ""),
        "special_name": det.get("specialName") or "",
        "certificate_code": det.get("certificateCode") or "",
        "full_certificate_code": det.get("fullCertificateCode") or "",
        "property_right_unit": det.get("propertyRightUnit") or hit.get("property_right_unit") or "",
        "organization": det.get("organization") or "",
        "producer": det.get("producer") or "",
        "author": det.get("author") or hit.get("author") or "",
        "contact": det.get("contact") or "",
        "unit": det.get("unit") or "",
        "email": det.get("email") or "",
        "project_name": det.get("projectName") or "",
        "project_code": det.get("projectCode") or "",
        "version": det.get("version") or "",
        "view_count": det.get("viewCount") if det else "",
        "download_count": det.get("downloadCount") if det else "",
        "cite_count": det.get("citeCount") if det else "",
        "data_summary": det.get("dataSummary") or "",
        "usage_notes": det.get("usageNotes") or "",
        "refer_standard_note": det.get("thankWay") or "",
        "hj_entity_url": det.get("hjEntityUrl") or hit.get("hj_entity_url") or "",
        "resource_link": det.get("resourceLink") or hit.get("resource_link") or "",
        "file_local": dl.get("file") or "",
        "detail_url": f"{ac.BASE}/dataset/detail/{rtype}/{hit['gid']}",
        "matched_queries": " | ".join(hit.get("matched_queries") or []),
        "matched_query_count": len(hit.get("matched_queries") or []),
        "evidence_grape": " | ".join(ev.get("grape") or []),
        "evidence_postharvest": " | ".join(ev.get("postharvest") or []),
        "evidence_dormant": " | ".join(ev.get("dormant_storage") or []),
        "evidence_processed": " | ".join(ev.get("processed") or []),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_index_md(relevant: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    """生成便于人读的索引：A 级单列，B 级按主题粗分组，C 级作参照。"""

    def topic(row: dict[str, Any]) -> str:
        text = (row.get("name_zh") or "") + (row.get("keywords") or "")
        rules = [
            ("种质/品种资源", ["种质", "品种", "农家品种", "资源圃", "SSR", "指纹", "花色苷", "香气", "糖酸", "有机酸", "抗热"]),
            ("栽培/土肥水", ["栽培", "施肥", "肥料", "土壤", "养分", "灌溉", "水分", "水肥", "复合种植", "套种", "减施"]),
            ("病虫害/病毒", ["病害", "霜霉", "溃疡", "病毒", "灰霉", "果蝇", "脱毒", "裂果"]),
            ("果实品质/表型", ["品质", "果实性状", "可溶性固形物", "图像", "识别", "目标检测", "语义分割"]),
            ("采后/贮运", ["采后", "贮藏", "储藏", "保鲜", "冷藏", "预冷", "气调", "货架期", "冷链", "落粒", "耐贮"]),
        ]
        for name, keys in rules:
            if any(k in text for k in keys):
                return name
        return "其他"

    lines = [
        "# 站内葡萄相关数据索引（自动生成）",
        "",
        f"- 生成时间：{manifest.get('generated_at')}",
        f"- 来源：{manifest.get('source_site')}（国家农业科学数据中心）",
        f"- 分级计数：{json.dumps(manifest.get('tier_counts'), ensure_ascii=False)}",
        "- 说明：A=葡萄且采后；B=葡萄但非采后；C=其他果蔬采后。判定依据见 CSV 的 `tier_reason` 与 `evidence_*` 列。",
        "",
        "## A 级：葡萄 × 采后（直接相关）",
        "",
    ]
    tier_a = [r for r in relevant if r["tier"] == "A"]
    if not tier_a:
        lines.append("_无_")
    else:
        lines += ["| 名称 | 类型 | 关键词 | 标识/DOI | 链接 |", "|---|---|---|---|---|"]
        for r in tier_a:
            lines.append(
                f"| {r['name_zh']} | {KIND_LABEL.get(r['record_kind'], r['record_kind'])} | "
                f"{r.get('keywords', '')} | {r.get('sci_identification') or r.get('data_set_doi') or '—'} | "
                f"[详情]({r['detail_url']}) |"
            )
    lines += ["", "## B 级：葡萄相关（非采后方向）", ""]
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in relevant:
        if r["tier"] == "B":
            groups.setdefault(topic(r), []).append(r)
    for name in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        lines += [f"### {name}（{len(groups[name])} 条）", "",
                  "| 名称 | 类型 | 关键词 | 标识/DOI | 获取方式 | 链接 |",
                  "|---|---|---|---|---|---|"]
        for r in groups[name]:
            lines.append(
                f"| {r['name_zh']} | {KIND_LABEL.get(r['record_kind'], r['record_kind'])} | "
                f"{(r.get('keywords') or '')[:60]} | {r.get('sci_identification') or r.get('data_set_doi') or '—'} | "
                f"{r.get('download_way_label') or '—'} | [详情]({r['detail_url']}) |"
            )
        lines.append("")
    lines += ["## C 级：其他果蔬采后（可作方法参照）", "",
              "| 名称 | 关键词 | 标识/DOI | 链接 |", "|---|---|---|---|"]
    for r in relevant:
        if r["tier"] == "C":
            lines.append(
                f"| {r['name_zh']} | {(r.get('keywords') or '')[:60]} | "
                f"{r.get('sci_identification') or r.get('data_set_doi') or '—'} | [详情]({r['detail_url']}) |"
            )
    lines += ["", "---", "",
              "另见：`legacy_preserve/grape_storage_technique.md`（旧站「农产品贮藏保鲜技术数据库」葡萄条目原文整理）。"]
    (OUT_DIR / "grape_datasets_index.md").write_text("\n".join(lines), encoding="utf-8")


def stage_export() -> dict[str, Any]:
    cands = read_json(WORK / "candidates.json")
    details = read_json(WORK / "details.json", {}) or {}
    downloads = read_json(WORK / "downloads.json", {}) or {}
    search = read_json(WORK / "search_hits.json", {}) or {}
    if not cands:
        raise SystemExit("先运行 classify 阶段")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for hit in cands["hits"]:
        det = (details.get(hit["gid"]) or {}).get("detail") or {}
        dl = downloads.get(hit["gid"]) or {}
        rows.append(_row(hit, det, dl))

    # 全部检索命中（含 D 级）与 A/B/C 分级表
    _write_csv(OUT_DIR / "datasets_all_hits.csv", rows)
    relevant = [r for r in rows if r["tier"] in ("A", "B", "C")]
    _write_csv(OUT_DIR / "datasets_grape_postharvest.csv", relevant)
    _write_csv(OUT_DIR / "datasets_relevant_only.csv", [r for r in relevant if r["record_kind"] == "dataset"])
    _write_csv(OUT_DIR / "projects_literature_relevant.csv", [r for r in relevant if r["record_kind"] != "dataset"])
    _write_csv(OUT_DIR / "datasets_tier_a.csv", [r for r in rows if r["tier"] == "A"])

    # 检索命中明细（关键词 -> gid 的对应关系）
    hit_rows = []
    for hit in cands["hits"]:
        for q in hit.get("matched_queries") or []:
            hit_rows.append({
                "keyword": q,
                "gid": hit["gid"],
                "name_zh": hit.get("name_zh"),
                "tier": hit["tier"],
                "issue_time": hit.get("issue_time"),
                "download_way": hit.get("download_way"),
            })
    hit_rows.sort(key=lambda r: (r["keyword"], r["name_zh"] or ""))
    with (OUT_DIR / "search_hit_pairs.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(hit_rows[0].keys()) if hit_rows else ["keyword"])
        writer.writeheader()
        writer.writerows(hit_rows)

    # 详情原始 JSON（逐条留档，便于复核）
    for gid, rec in details.items():
        write_json(DETAILS_DIR / f"{gid}.json", rec)

    # 下载清单
    dl_rows = []
    for gid, rec in downloads.items():
        dl_rows.append({
            "gid": gid,
            "name_zh": rec.get("name_zh"),
            "tier": rec.get("tier"),
            "file": rec.get("file") or "",
            "source_url": rec.get("source_url") or "",
            "bytes": rec.get("bytes") or "",
            "container": rec.get("container") or "",
            "sha256": rec.get("sha256") or "",
            "zip_entries": rec.get("zip_entries") or "",
            "sheet_names": " | ".join(rec.get("sheet_names") or []),
            "fetched_at": rec.get("fetched_at") or "",
            "error": rec.get("error") or "",
        })
    if dl_rows:
        with (OUT_DIR / "downloads.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(dl_rows[0].keys()))
            writer.writeheader()
            writer.writerows(dl_rows)

    tier_counts: dict[str, int] = {}
    for r in rows:
        tier_counts[r["tier"]] = tier_counts.get(r["tier"], 0) + 1
    kind_counts: dict[str, int] = {}
    for r in rows:
        kind_counts[r["record_kind"]] = kind_counts.get(r["record_kind"], 0) + 1
    tier_by_kind: dict[str, dict[str, int]] = {}
    for r in rows:
        tier_by_kind.setdefault(r["tier"], {}).setdefault(r["record_kind"], 0)
        tier_by_kind[r["tier"]][r["record_kind"]] += 1
    tier_a_datasets = sum(1 for r in rows if r["tier"] == "A" and r["record_kind"] == "dataset")
    manifest = {
        "title": "国家农业科学数据中心（www.agridata.cn）鲜食葡萄采后贮藏相关数据抓取",
        "generated_at": now(),
        "source_site": ac.BASE,
        "api_endpoints": [
            "/api/app/dataset/search/list",
            "/api/app/dataset/detail/{resource_type}/{gid}",
        ],
        "robots": "Disallow: /console/（其余路径允许；本抓取未访问 /console/）",
        "policy": {
            "rate_limit": "约每 1 秒 1 次请求，带 0-0.5 秒随机抖动",
            "login": "未登录、未注册、未提交下载申请",
            "download_scope": "仅 download_way∈{0,5} 且站点直接给出实体 URL 的公开文件，单文件 ≤40MB，最多 15 个",
        },
        "queries": search.get("queries") or {},
        "search_requests": search.get("total_requests"),
        "unique_hits": len(rows),
        "tier_counts": tier_counts,
        "record_kind_counts": kind_counts,
        "tier_by_kind": tier_by_kind,
        "tier_a_dataset_count": tier_a_datasets,
        "details_fetched": sum(1 for v in details.values() if "error" not in v),
        "details_failed": sum(1 for v in details.values() if "error" in v),
        "files_downloaded": sum(1 for v in downloads.values() if "error" not in v),
        "files_failed": sum(1 for v in downloads.values() if "error" in v),
        "outputs": {
            "datasets_all_hits.csv": len(rows),
            "datasets_grape_postharvest.csv": len(relevant),
            "datasets_relevant_only.csv": sum(1 for r in relevant if r["record_kind"] == "dataset"),
            "projects_literature_relevant.csv": sum(1 for r in relevant if r["record_kind"] != "dataset"),
            "datasets_tier_a.csv": sum(1 for r in rows if r["tier"] == "A"),
            "search_hit_pairs.csv": len(hit_rows),
            "details": len(details),
            "files": sum(1 for _ in FILES_DIR.glob("*")) if FILES_DIR.exists() else 0,
        },
    }
    write_json(OUT_DIR / "manifest.json", manifest)
    _write_index_md(relevant, manifest)
    print(f"[export] 分级 {tier_counts}；输出目录 {OUT_DIR}")
    return manifest


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["search", "classify", "details", "refine", "download", "export", "all"],
        help="执行的阶段",
    )
    parser.add_argument("--groups", default="", help="只跑指定关键词组，逗号分隔（search 阶段）")
    args = parser.parse_args(argv)
    groups = [g.strip() for g in args.groups.split(",") if g.strip()] or None
    stages = (["search", "classify", "details", "refine", "download", "export"]
              if args.stage == "all" else [args.stage])
    for stage in stages:
        print(f"\n=== {stage} @ {now()} ===")
        if stage == "search":
            stage_search(groups=groups)
        else:
            {"classify": stage_classify, "details": stage_details, "refine": stage_refine,
             "download": stage_download, "export": stage_export}[stage]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
