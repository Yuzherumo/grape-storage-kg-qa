#!/usr/bin/env python
"""抓取北京农业数字信息资源中心（www.agridata.ac.cn，端口 80）旧版专题数据库
「农产品贮藏保鲜技术数据库」（tableID=102）的全部记录，并导出葡萄相关子集。

背景
----
用户给的旧网址 http://www.agridata.ac.cn:8888/Web/advanced_search.aspx?TITLE=保鲜技术
所在 8888 端口服务已挂（任意路径 HTTP 500）。同一单位在 80 端口的新站仍可访问，
其「农业专题数据库」里保留了这个贮藏保鲜库，表结构（真实列名）：

    果蔬类别 | 果蔬名称 | 贮藏特性 | 贮藏方法 | 主要贮藏病害及防治 | 上市质量标准

接口来自该站 /Content/Web/js/datashow.js：
    POST /DataList/GetheadTitle      {tableID}                  -> 列定义
    POST /DataList/GridnewsListJson2 {page, tableID, keywords}  -> 行数据（total 为总页数）
    GET  /DataList/DataDetails?id=<row id>&tableid=<tableID>     -> 条目详情页

用法
----
    python scripts/fetch_legacy_preserve.py            # 抓全库 + 导出葡萄子集
    python scripts/fetch_legacy_preserve.py --pages 3  # 只抓前 3 页（调试）
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://www.agridata.ac.cn"
TABLE_ID = 102
DB_NAME = "农产品贮藏保鲜技术数据库"
OUT_DIR = ROOT / "data" / "external" / "agridata" / "legacy_preserve"
RAW_DIR = ROOT / ".tmp" / "agridata" / "legacy_preserve"
TZ = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

import ssl  # noqa: E402

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S%z")


def post(path: str, data: dict, timeout: int = 40) -> str:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=body, headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE}/DataList/DataShow",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read().decode("utf-8", "replace")


def clean(fragment: str | None) -> str:
    """去 HTML 标签 / 样式 / 实体，压缩空白，保留可读正文。"""
    if not fragment:
        return ""
    text = re.sub(r"<style.*?</style>|<script.*?</script>", " ", fragment, flags=re.S | re.I)
    text = re.sub(r"</(p|div|tr|br)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ").replace("\ufeff", "")
    lines = [" ".join(ln.split()) for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def fetch_rows(page: int, page_size_hint: int = 15) -> tuple[list[dict], int]:
    raw = post("/DataList/GridnewsListJson2", {"page": page, "tableID": TABLE_ID, "keywords": ""})
    obj = json.loads(raw)
    return obj.get("rows") or [], obj.get("total") or 0


def fetch_detail(row_id: int) -> str:
    url = f"{BASE}/DataList/DataDetails?id={row_id}&tableid={TABLE_ID}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
        page = r.read().decode("utf-8", "replace")
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", body)
    text = html.unescape(text).replace("\u00a0", " ")
    return " ".join(text.split())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=0, help="只抓前 N 页（0=全部）")
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    head = json.loads(post("/DataList/GetheadTitle", {"tableID": TABLE_ID}))
    columns = [(r.get("ID"), r.get("Name")) for r in head.get("rows") or []]
    print(f"列：{columns}")

    rows, total_pages = fetch_rows(1)
    limit = args.pages or total_pages
    print(f"总页数 {total_pages}，每页约 {len(rows)} 行；抓取前 {limit} 页")
    all_rows: list[dict] = []
    for page in range(1, limit + 1):
        page_rows, _ = fetch_rows(page)
        if not page_rows:
            break
        for r in page_rows:
            rec = {
                "row_id": r.get("id"),
                "insert_date": (r.get("insert_date") or "")[:10],
                "source_url": f"{BASE}/DataList/DataDetails?id={r.get('id')}&tableid={TABLE_ID}",
            }
            for cid, cname in columns:
                rec[cname] = clean(r.get(f"column{cid}"))
            all_rows.append(rec)
        print(f"  p{page}: +{len(page_rows)}（累计 {len(all_rows)}）")
        time.sleep(0.8)

    # 去重（同一 id 只留一条）
    dedup: dict[int, dict] = {r["row_id"]: r for r in all_rows}
    records = list(dedup.values())
    (RAW_DIR / "all_records.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # 葡萄判定：先剔除「葡萄柚」（grapefruit）再匹配，避免把 柚子/甜橙 的
    # 「参见葡萄柚」「橙类和葡萄柚的主要贮藏病害」误判成葡萄。
    def grape_flag(r: dict) -> tuple[bool, list[str]]:
        name = (r.get("果蔬名称") or "").replace("葡萄柚", "")
        if "葡萄" in name or "提子" in name:
            return True, [f"名称：{r.get('果蔬名称')}"]
        hits = [c for c in ("贮藏特性", "贮藏方法", "主要贮藏病害及防治", "上市质量标准")
                if "葡萄" in (r.get(c) or "").replace("葡萄柚", "")]
        if hits:
            return True, [f"正文实质提及葡萄：{'/'.join(hits)}"]
        return False, []

    grape_records = []
    for r in records:
        ok, why = grape_flag(r)
        if ok:
            r2 = dict(r)
            r2["葡萄判定依据"] = "；".join(why)
            grape_records.append(r2)
    print(f"全库 {len(records)} 条；葡萄相关 {len(grape_records)} 条")

    # 导出 CSV
    def write_csv(path: Path, data: list[dict], fieldnames: list[str]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)

    cols = ["row_id", "insert_date", "果蔬类别", "果蔬名称", "贮藏特性", "贮藏方法",
            "主要贮藏病害及防治", "上市质量标准", "source_url"]
    write_csv(OUT_DIR / "preserve_db_all.csv", records, cols)
    write_csv(OUT_DIR / "preserve_db_grape.csv", grape_records, cols + ["葡萄判定依据"])

    # 葡萄条目详情页
    details = []
    for r in grape_records:
        try:
            text = fetch_detail(int(r["row_id"]))
            details.append({"row_id": r["row_id"], "果蔬名称": r.get("果蔬名称"),
                            "source_url": r["source_url"], "detail_text": text[:4000]})
        except Exception as exc:  # noqa: BLE001
            details.append({"row_id": r["row_id"], "果蔬名称": r.get("果蔬名称"),
                            "source_url": r["source_url"], "error": str(exc)})
        time.sleep(0.8)
    (OUT_DIR / "grape_details.json").write_text(
        json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # 葡萄条目导出成可读 markdown（按「1. 2. 3.」编号切分贮藏方法）
    if grape_records:
        g = grape_records[0]
        method = g.get("贮藏方法") or ""
        parts = re.split(r"\n(?=\d+[.、]\s*)", method.strip())
        md = [
            f"# {g.get('果蔬名称')} — 贮藏保鲜技术（旧版专题库原文整理）",
            "",
            f"- 来源库：{DB_NAME}（tableID={TABLE_ID}）",
            f"- 来源页面：{g.get('source_url')}",
            f"- 果蔬类别：{g.get('果蔬类别')}",
            f"- 入库日期：{g.get('insert_date')}",
            "- 说明：以下文字按原库字段整理，仅去除 HTML 样式，未改写内容；"
            "SO₂ 用量、温度等数值请以原始页面为准并结合现行标准核对。",
            "",
            "## 一、贮藏特性",
            "",
            g.get("贮藏特性") or "（原库为空）",
            "",
            "## 二、贮藏方法",
            "",
        ]
        for p in parts:
            p = p.strip()
            if not p:
                continue
            title_m = re.match(r"(\d+[.、])\s*(.*)", p, re.S)
            if title_m:
                md.append(f"### {title_m.group(1)} {title_m.group(2).splitlines()[0]}")
                md.append("")
                rest = "\n".join(title_m.group(2).splitlines()[1:]).strip()
                if rest:
                    md.append(rest)
                    md.append("")
            else:
                md.append(p)
                md.append("")
        md += [
            "## 三、主要贮藏病害及防治",
            "",
            g.get("主要贮藏病害及防治") or "（原库为空）",
            "",
            "## 四、上市质量标准",
            "",
            g.get("上市质量标准") or "（原库为空）",
            "",
        ]
        (OUT_DIR / "grape_storage_technique.md").write_text("\n".join(md), encoding="utf-8")
        print("写出 grape_storage_technique.md")

    manifest = {
        "dataset": DB_NAME,
        "table_id": TABLE_ID,
        "source_site": BASE,
        "source_page": f"{BASE}/DataList/DataShow?databasename={urllib.parse.quote(DB_NAME)}&ID={TABLE_ID}",
        "columns": [name for _, name in columns],
        "fetched_at": now(),
        "total_pages": total_pages,
        "records_total": len(records),
        "grape_records": len(grape_records),
        "caveat": (
            "该库为 2005 年前后建立的旧版专题库，条目为面向生产的贮藏保鲜技术描述，"
            "不含原始试验观测数据；引用请以网站原文为准。"
        ),
        "note": "旧站 8888 端口的 advanced_search.aspx 已不可用（HTTP 500），本数据取自同一机构的 80 端口站点。",
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("输出：", OUT_DIR)
    for r in grape_records[:10]:
        print("  葡萄条目:", r.get("果蔬名称"), "|", (r.get("贮藏方法") or "")[:60].replace("\n", " "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
