"""把论文 PDF 统计合并进 data/external/web_grape_storage/manifest.json。"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "external" / "web_grape_storage"
CAP = int(2.85 * 1024**3)


def main() -> int:
    manifest_path = DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    papers = list(csv.DictReader((DIR / "paper_records.csv").open(encoding="utf-8-sig")))
    paper_bytes = 0
    for p in papers:
        for rel in [x for x in (p.get("local_files") or "").split(" | ") if x]:
            fp = ROOT / rel
            if fp.exists():
                paper_bytes += fp.stat().st_size
    data_bytes = int((manifest.get("counts") or {}).get("bytes_downloaded") or 0)
    total = data_bytes + paper_bytes
    manifest["papers"] = {
        "records": len(papers),
        "files": sum(int(p.get("files") or 0) for p in papers),
        "bytes": paper_bytes,
        "note": "开放获取论文 PDF（Zenodo/DOAJ 可直链部分）；出处见 paper_records.csv",
    }
    manifest["counts"]["paper_records"] = len(papers)
    manifest["counts"]["paper_bytes"] = paper_bytes
    manifest["counts"]["total_bytes_all"] = total
    manifest["counts"]["budget_used_pct_all"] = round(100 * total / CAP, 2)
    manifest["generated_at"] = "2026-11-27"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[manifest] 数据 {data_bytes / 1024**2:.1f}MB + 论文 {paper_bytes / 1024**2:.1f}MB "
          f"= {total / 1024**2:.1f}MB（预算 {CAP / 1024**3:.2f}GiB 的 "
          f"{manifest['counts']['budget_used_pct_all']}%）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
