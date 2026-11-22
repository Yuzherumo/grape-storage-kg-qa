# -*- coding: utf-8 -*-
"""知识图谱可视化（纯标准库，生成自包含 SVG；UI 与导出脚本共用）。

数据来源：data/entities.csv + data/triples.csv（Source 节点作为溯源属性，不画进主图）。
布局：按实体类型分簇 + 简单力导向（Fruchterman-Reingold 变体，固定随机种子，结果可复现）。
"""
from __future__ import annotations

import csv
import hashlib
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

LABEL_CN = {
    "Variety": "品种", "Condition": "储藏条件", "QualityIndicator": "品质指标",
    "Disease": "病害", "Source": "来源",
}
COLORS = {
    "Variety": "#4d6bfe", "Condition": "#16a34a", "QualityIndicator": "#ea580c",
    "Disease": "#dc2626", "Source": "#64748b",
}
PRED_COLOR = {
    "REQUIRES": "#94a3b8", "PREVENTED_BY": "#16a34a", "INDUCED_BY": "#dc2626",
    "SUSCEPTIBLE_TO": "#ea580c", "CONTRA_INDICATED_FOR": "#dc2626",
    "ALTERNATIVE_TO": "#4d6bfe", "AFFECTS": "#8b5cf6", "HAS_INDICATOR_VALUE": "#64748b",
    "INDICATES": "#0ea5e9",
}
LABEL_ORDER = ["Variety", "Disease", "QualityIndicator", "Condition"]


@dataclass
class GNode:
    id: str
    name: str
    label: str
    x: float = 0.0
    y: float = 0.0
    degree: int = 0


@dataclass
class GEdge:
    source: str
    target: str
    predicate: str
    status: str = "anchor"


@dataclass
class Graph:
    nodes: List[GNode] = field(default_factory=list)
    edges: List[GEdge] = field(default_factory=list)

    def by_id(self) -> Dict[str, GNode]:
        return {n.id: n for n in self.nodes}


def load_graph(data_dir: Path | str, *, include_sources: bool = False, include_isolated: bool = True) -> Graph:
    data = Path(data_dir)
    nodes: Dict[str, GNode] = {}
    with (data / "entities.csv").open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nodes[row["id"]] = GNode(id=row["id"], name=row["name"], label=row["label"])
    if include_sources:
        try:
            with (data / "sources.csv").open(encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    nodes[row["id"]] = GNode(id=row["id"], name=row.get("title", row["id"])[:14],
                                             label="Source")
        except FileNotFoundError:
            pass
    name_to_id = {n.name: n.id for n in nodes.values()}
    edges: List[GEdge] = []
    with (data / "triples.csv").open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            s = name_to_id.get(row["subject"])
            o = name_to_id.get(row["object"])
            if not s or not o:
                continue
            edges.append(GEdge(s, o, row["predicate"], row.get("status", "anchor")))
    for e in edges:
        if e.source in nodes:
            nodes[e.source].degree += 1
        if e.target in nodes:
            nodes[e.target].degree += 1
    used = {e.source for e in edges} | {e.target for e in edges}
    node_list = [n for n in nodes.values() if n.id in used or include_sources or include_isolated]
    return Graph(nodes=node_list, edges=[e for e in edges if e.source in used and e.target in used])


def ego_graph(graph: Graph, node_id: str) -> Graph:
    keep = {node_id}
    for e in graph.edges:
        if e.source == node_id:
            keep.add(e.target)
        elif e.target == node_id:
            keep.add(e.source)
    nodes = [n for n in graph.nodes if n.id in keep]
    edges = [e for e in graph.edges if e.source in keep and e.target in keep]
    return Graph(nodes=nodes, edges=edges)


def _seed_positions(nodes: List[GNode]) -> None:
    """按类型分簇放在圆周上，簇内均匀散开（确定性）。"""
    rng = random.Random(20261122)
    groups: Dict[str, List[GNode]] = {lab: [] for lab in LABEL_ORDER}
    for n in nodes:
        groups.setdefault(n.label, []).append(n)
    active = [lab for lab in LABEL_ORDER if groups.get(lab)]
    for gi, lab in enumerate(active):
        ang = 2 * math.pi * gi / max(1, len(active)) - math.pi / 2
        cx, cy = 0.5 + 0.30 * math.cos(ang), 0.5 + 0.30 * math.sin(ang)
        items = groups[lab]
        for i, n in enumerate(items):
            r = 0.10 * math.sqrt((i + 0.5) / max(1, len(items)))
            a = 2 * math.pi * i / max(1, len(items))
            n.x = cx + r * math.cos(a) + (rng.random() - 0.5) * 0.01
            n.y = cy + r * math.sin(a) + (rng.random() - 0.5) * 0.01


def layout(graph: Graph, *, iterations: int = 260, width: float = 1.0, height: float = 1.0) -> None:
    """Fruchterman-Reingold（带温度退火），坐标归一到 [0.03, 0.97]。"""
    nodes = graph.nodes
    if not nodes:
        return
    _seed_positions(nodes)
    idx = {n.id: i for i, n in enumerate(nodes)}
    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    n = len(nodes)
    if n == 1:
        nodes[0].x = nodes[0].y = 0.5
        return
    area = 1.0
    k = math.sqrt(area / n)
    t = 0.12
    edges = [(idx[e.source], idx[e.target]) for e in graph.edges if e.source in idx and e.target in idx]
    for _ in range(iterations):
        dx = [0.0] * n
        dy = [0.0] * n
        # 斥力
        for i in range(n):
            for j in range(i + 1, n):
                vx, vy = xs[i] - xs[j], ys[i] - ys[j]
                d2 = vx * vx + vy * vy + 1e-6
                d = math.sqrt(d2)
                f = k * k / d2
                ux, uy = vx / d, vy / d
                dx[i] += ux * f
                dy[i] += uy * f
                dx[j] -= ux * f
                dy[j] -= uy * f
        # 引力
        for a, b in edges:
            vx, vy = xs[a] - xs[b], ys[a] - ys[b]
            d = math.sqrt(vx * vx + vy * vy) + 1e-6
            f = d * d / k
            ux, uy = vx / d, vy / d
            dx[a] -= ux * f
            dy[a] -= uy * f
            dx[b] += ux * f
            dy[b] += uy * f
        # 类型聚拢（让同类节点靠近）
        for i, ni in enumerate(nodes):
            gx, gy = 0.0, 0.0
            cnt = 0
            for j, nj in enumerate(nodes):
                if i != j and nj.label == ni.label:
                    gx += xs[j]
                    gy += ys[j]
                    cnt += 1
            if cnt:
                dx[i] += (gx / cnt - xs[i]) * 0.9
                dy[i] += (gy / cnt - ys[i]) * 0.9
        for i in range(n):
            d = math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) + 1e-9
            step = min(d, t)
            xs[i] += dx[i] / d * step
            ys[i] += dy[i] / d * step
        t = max(0.006, t * 0.985)
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    sxn = (maxx - minx) or 1.0
    syn = (maxy - miny) or 1.0
    for i, node in enumerate(nodes):
        node.x = 0.04 + 0.92 * (xs[i] - minx) / sxn * width
        node.y = 0.05 + 0.88 * (ys[i] - miny) / syn * height


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def to_svg(graph: Graph, *, width: int = 1600, height: int = 980, title: str = "知识图谱",
           subtitle: str = "", max_labels: Optional[int] = None) -> str:
    """生成自包含 SVG（带 hover 提示、图例、边按谓词着色）。"""
    if not graph.nodes:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"></svg>'
    layout(graph)
    pad = 24
    W, H = width, height
    nodes = graph.nodes
    pos = {n.id: (pad + n.x * (W - 2 * pad), pad + 28 + n.y * (H - 2 * pad - 54)) for n in nodes}
    size = {}
    for n in nodes:
        base = 16 if n.label == "Variety" else 12
        size[n.id] = base + min(8, n.degree * 0.8) if n.degree else base

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Microsoft YaHei, PingFang SC, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="{pad}" y="34" font-size="20" font-weight="700" fill="#1f2328">{_esc(title)}</text>',
    ]
    if subtitle:
        parts.append(f'<text x="{pad}" y="58" font-size="13" fill="#6b7280">{_esc(subtitle)}</text>')

    # 边
    for e in graph.edges:
        if e.source not in pos or e.target not in pos:
            continue
        x1, y1 = pos[e.source]
        x2, y2 = pos[e.target]
        color = PRED_COLOR.get(e.predicate, "#cbd5e1")
        width_px = 1.6 if e.status == "verified" else 1.1
        dash = ' stroke-dasharray="4 3"' if e.status != "verified" else ""
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{width_px}" stroke-opacity="0.55"{dash}/>'
        )

    # 节点
    label_nodes = sorted(nodes, key=lambda n: -n.degree)
    label_keep = {n.id for n in (label_nodes if max_labels is None else label_nodes[:max_labels])}
    for n in nodes:
        x, y = pos[n.id]
        r = size[n.id]
        color = COLORS.get(n.label, "#64748b")
        tip = f"{n.name}（{LABEL_CN.get(n.label, n.label)}，度 {n.degree}）"
        parts.append(
            f'<g><title>{_esc(tip)}</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" fill-opacity="0.92" '
            f'stroke="#ffffff" stroke-width="2"/>'
            f'</g>'
        )
        if n.id in label_keep:
            fs = 12 if n.label == "Variety" else 10
            parts.append(
                f'<text x="{x:.1f}" y="{y - r - 4:.1f}" font-size="{fs}" fill="#1f2328" '
                f'text-anchor="middle">{_esc(n.name)}</text>'
            )

    # 图例
    lx, ly = pad, H - 62
    parts.append(f'<text x="{lx}" y="{ly}" font-size="12" fill="#6b7280">图例：</text>')
    offset = lx + 46
    for lab in LABEL_ORDER:
        cnt = sum(1 for n in nodes if n.label == lab)
        parts.append(f'<circle cx="{offset + 5}" cy="{ly - 4}" r="5" fill="{COLORS[lab]}"/>')
        text = f"{LABEL_CN[lab]} {cnt}"
        parts.append(f'<text x="{offset + 14}" y="{ly}" font-size="12" fill="#1f2328">{_esc(text)}</text>')
        offset += 24 + len(text) * 7
    parts.append(
        f'<text x="{W - pad}" y="{ly}" font-size="11" fill="#9ca3af" text-anchor="end">'
        f'实线=verified　虚线=anchor　悬停节点看详情</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def graph_summary(graph: Graph) -> Dict[str, int]:
    c = {lab: sum(1 for n in graph.nodes if n.label == lab) for lab in LABEL_ORDER}
    verified = sum(1 for e in graph.edges if e.status == "verified")
    return {"nodes": len(graph.nodes), "edges": len(graph.edges), **c,
            "verified": verified, "anchor": len(graph.edges) - verified}


def svg_hash(svg: str) -> str:
    return hashlib.md5(svg.encode("utf-8")).hexdigest()[:8]
