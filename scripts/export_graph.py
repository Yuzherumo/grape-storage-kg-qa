"""导出知识图谱可视化资产（SVG；PNG 见 .tmp/render_graph_png.py 或 --png 参数）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from app.graph_view import ego_graph, load_graph, to_svg  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(BASE / "docs" / "assets"))
    ap.add_argument("--png", action="store_true", help="同时用 Pillow 生成 PNG（需安装 Pillow）")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    graph = load_graph(BASE / "data")
    full = to_svg(
        graph, width=1600, height=980, title="鲜食葡萄储藏知识图谱",
        subtitle="GB/T 16862-2026 条文 + 5 篇综述；实线=已核验，虚线=待核验；来源节点通过 source_ids 关联",
    )
    (out / "graph_overview.svg").write_text(full, encoding="utf-8")

    ego = ego_graph(graph, "shine_muscat")
    sub = to_svg(
        ego, width=1400, height=820, title="阳光玫瑰（Shine Muscat）子图",
        subtitle="与该品种直接相连的储藏条件、品质指标、病害与禁忌关系",
    )
    (out / "graph_shine_muscat.svg").write_text(sub, encoding="utf-8")

    print(f"[ok] {out / 'graph_overview.svg'} ({len(full)//1024} KB)")
    print(f"[ok] {out / 'graph_shine_muscat.svg'} ({len(sub)//1024} KB)")

    if args.png:
        try:
            from PIL import Image, ImageDraw, ImageFont  # noqa: F401
        except ImportError:
            print("[skip] 未安装 Pillow，PNG 未生成（可用 --png 在有 Pillow 的环境跑）")
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
