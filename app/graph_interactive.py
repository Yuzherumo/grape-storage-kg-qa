# -*- coding: utf-8 -*-
"""可交互知识图谱（自包含 HTML：内联 SVG + 原生 JS，无外部依赖、离线可用）。

交互：
- 点击节点：高亮邻居、右侧面板显示类型/连接度/关联三元组（可点邻居继续跳转）
- 滚轮缩放、拖拽平移、重置视图
- 类型筛选（品种/条件/指标/病害）、按名称搜索
- 节点悬停显示名称与度

用法：interactive_html(graph) -> str，交给 st.components.v1.html 渲染。
"""
from __future__ import annotations

import html
import json
from typing import Dict, List

from app.graph_view import (
    COLORS, LABEL_CN, PRED_COLOR, Graph, _esc, layout,
)

PRED_CN = {
    "REQUIRES": "需要条件", "CONTRA_INDICATED_FOR": "禁忌", "AFFECTS": "影响",
    "SUSCEPTIBLE_TO": "易感", "PREVENTED_BY": "可预防/处置", "INDUCED_BY": "诱因",
    "ALTERNATIVE_TO": "可替代", "INDICATES": "指示", "HAS_INDICATOR_VALUE": "指标基线",
}
LABEL_ORDER = ["Variety", "Disease", "QualityIndicator", "Condition"]

_CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#1f2328;
     background:#fff;display:flex;flex-direction:column;height:100vh;overflow:hidden}
#top{padding:10px 14px 6px;border-bottom:1px solid #e6e8eb;display:flex;align-items:center;
     gap:10px;flex-wrap:wrap;background:#fff;z-index:3}
#top h3{margin:0;font-size:16px}
#top .sub{font-size:11px;color:#6b7280}
#tools{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#tools input{border:1px solid #e6e8eb;border-radius:8px;padding:4px 8px;font-size:12px;width:150px}
#tools button{border:1px solid #e6e8eb;background:#f9fafb;border-radius:8px;padding:4px 10px;
              font-size:12px;cursor:pointer;color:#1f2328}
#tools button:hover{border-color:#4d6bfe;color:#4d6bfe}
.filter{display:inline-flex;align-items:center;gap:4px;font-size:12px;color:#6b7280;cursor:pointer}
#main{flex:1;display:flex;min-height:0}
#graph{flex:1;position:relative;overflow:hidden;background:#fff}
#graph svg{width:100%;height:100%;display:block;cursor:grab;user-select:none}
#graph svg.dragging{cursor:grabbing}
#panel{width:330px;border-left:1px solid #e6e8eb;overflow:auto;padding:12px;font-size:12.5px;
       line-height:1.6;background:#fbfcfe}
#panel h4{margin:0 0 6px;font-size:14px}
#panel .hint{color:#9ca3af;font-size:12px;margin-top:40px;text-align:center}
#panel .tag{display:inline-block;padding:0 6px;border-radius:999px;font-size:11px;margin-right:4px}
#panel ul{list-style:none;margin:6px 0;padding:0}
#panel li{border:1px solid #e6e8eb;border-radius:8px;padding:5px 8px;margin:4px 0;background:#fff;
          cursor:pointer;font-size:12px}
#panel li:hover{border-color:#4d6bfe}
#panel li .p{color:#4d6bfe;font-weight:700}
#panel li .st{float:right;font-size:10px;color:#9ca3af}
#panel .q{background:#eef2ff;border-radius:8px;padding:6px 8px;margin-top:8px;color:#374151}
#legend{position:absolute;left:12px;bottom:8px;font-size:11px;color:#6b7280;display:flex;gap:12px;
        background:rgba(255,255,255,.9);padding:4px 8px;border-radius:8px}
#legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px}
.node{cursor:pointer}
.node circle{transition:opacity .12s}
.node text{pointer-events:none}
.node.dim{opacity:.16}
.node.match circle{stroke:#f59e0b;stroke-width:4}
.edge{transition:opacity .12s}
.edge.dim{opacity:.06}
.edge.hl{opacity:.95;stroke-width:3}
#panel .kv{color:#6b7280}
"""

_JS = r"""
const SVG = document.getElementById('graph').querySelector('svg');
const VP = document.getElementById('vp');
const NODES = JSON.parse(document.getElementById('ndata').textContent);
const EDGES = JSON.parse(document.getElementById('edata').textContent);
const byId = Object.fromEntries(NODES.map(n => [n.id, n]));
const adj = {}; NODES.forEach(n => adj[n.id] = []);
EDGES.forEach((e, i) => { adj[e.s].push(i); adj[e.t].push(i); });
const CN = %CN%;
const LC = %LC%;
const COL = %COL%;
const PRED_CN = %PRED%;
let scale = 1, px = 0, py = 0, selected = null, drag = null;

function applyView(){ VP.setAttribute('transform', `translate(${px},${py}) scale(${scale})`); }
function reset(){ scale = 1; px = 0; py = 0; applyView(); }
function zoom(f){
  scale = Math.max(0.35, Math.min(5, scale * f));
  applyView();
}
document.getElementById('zin').onclick = () => zoom(1.25);
document.getElementById('zout').onclick = () => zoom(0.8);
document.getElementById('zreset').onclick = () => { reset(); clearSel(); };

SVG.addEventListener('wheel', ev => {
  if (!ev.ctrlKey){ ev.preventDefault(); zoom(ev.deltaY < 0 ? 1.12 : 0.89); }
}, {passive: false});

SVG.addEventListener('pointerdown', ev => {
  if (ev.target.closest('.node')) return;
  drag = {x: ev.clientX, y: ev.clientY, px, py};
  SVG.classList.add('dragging');
});
window.addEventListener('pointermove', ev => {
  if (!drag) return;
  px = drag.px + (ev.clientX - drag.x);
  py = drag.py + (ev.clientY - drag.y);
  applyView();
});
window.addEventListener('pointerup', () => { drag = null; SVG.classList.remove('dragging'); });

function nodeEls(){ return document.querySelectorAll('.node'); }
function edgeEls(){ return document.querySelectorAll('.edge'); }

function clearSel(){
  selected = null;
  nodeEls().forEach(el => el.classList.remove('dim'));
  edgeEls().forEach(el => el.classList.remove('dim', 'hl'));
  document.getElementById('detail').innerHTML =
    '<div class="hint">点击任意节点，查看它连向哪里</div>';
}

function select(id){
  selected = id;
  const n = byId[id]; if (!n) return;
  const nb = new Set([id]);
  adj[id].forEach(i => { nb.add(EDGES[i].s); nb.add(EDGES[i].t); });
  nodeEls().forEach(el => el.classList.toggle('dim', !nb.has(el.dataset.id)));
  const hlSet = new Set(adj[id]);
  edgeEls().forEach((el, i) => {
    const on = hlSet.has(i);
    el.classList.toggle('hl', on);
    el.classList.toggle('dim', !on);
  });
  const rows = adj[id].map(i => {
    const e = EDGES[i];
    const other = e.s === id ? e.t : e.s;
    const on = byId[other] || {name: other};
    const dir = e.s === id ? '→' : '←';
    const st = e.status === 'verified' ? '已核验' : '待核验';
    return `<li data-id="${other}"><span class="p">${PRED_CN[e.p] || e.p}</span> ${dir} ${on.name}` +
           `<span class="st">${st}</span></li>`;
  }).join('');
  const q = n.label === 'Variety' ? n.name + '放冷库该调到多少度？'
        : n.label === 'Disease' ? n.name + '怎么防？'
        : n.label === 'Condition' ? '葡萄冷藏用 ' + n.name + ' 有什么要求？'
        : n.name + ' 受什么影响？';
  document.getElementById('detail').innerHTML =
    `<h4>${n.name}</h4>` +
    `<div><span class="tag" style="background:${COL[n.label]}22;color:${COL[n.label]}">${LC[n.label]}</span>` +
    `<span class="kv">连接度 ${n.degree}</span></div>` +
    `<div class="kv" style="margin:4px 0">id: ${n.id}</div>` +
    `<ul>${rows || '<li>暂无关联三元组</li>'}</ul>` +
    `<div class="q">可以这样问：${q}</div>`;
  document.querySelectorAll('#detail li[data-id]').forEach(li => {
    li.onclick = () => select(li.dataset.id);
  });
}
nodeEls().forEach(el => { el.onclick = ev => { ev.stopPropagation(); select(el.dataset.id); }; });

document.getElementById('search').addEventListener('input', ev => {
  const kw = ev.target.value.trim();
  nodeEls().forEach(el => {
    const n = byId[el.dataset.id];
    el.classList.toggle('match', !!kw && n.name.includes(kw));
    el.classList.toggle('dim', !!kw && !n.name.includes(kw));
  });
});

function applyFilters(){
  const on = {};
  document.querySelectorAll('.filter input').forEach(cb => { on[cb.value] = cb.checked; });
  const visible = new Set();
  nodeEls().forEach(el => {
    const n = byId[el.dataset.id];
    const show = on[n.label] !== false;
    el.style.display = show ? '' : 'none';
    if (show) visible.add(n.id);
  });
  edgeEls().forEach((el, i) => {
    el.style.display = (visible.has(EDGES[i].s) && visible.has(EDGES[i].t)) ? '' : 'none';
  });
}
document.querySelectorAll('.filter input').forEach(cb => cb.onchange = applyFilters);
clearSel();
"""


def _js_escape_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def interactive_html(graph: Graph, *, width: int = 1500, height: int = 900,
                     title: str = "鲜食葡萄储藏知识图谱",
                     subtitle: str = "点击节点看关联；滚轮缩放，拖拽平移") -> str:
    layout(graph)
    W, H = width, height
    pad = 40
    pos = {n.id: (pad + n.x * (W - 2 * pad), pad + 70 + n.y * (H - 2 * pad - 90)) for n in graph.nodes}
    nodes_data: List[Dict] = []
    size: Dict[str, int] = {}
    for n in graph.nodes:
        base = 15 if n.label == "Variety" else 11
        r = int(base + (min(8, n.degree * 0.8) if n.degree else 0))
        size[n.id] = r
        nodes_data.append({"id": n.id, "name": n.name, "label": n.label,
                           "degree": n.degree, "x": round(pos[n.id][0], 1), "y": round(pos[n.id][1], 1)})
    edges_data = [{"s": e.source, "t": e.target, "p": e.predicate, "status": e.status}
                  for e in graph.edges if e.source in pos and e.target in pos]

    svg_parts = [
        f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Microsoft YaHei, PingFang SC, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="{pad}" y="34" font-size="20" font-weight="700" fill="#1f2328">{_esc(title)}</text>',
        f'<text x="{pad}" y="56" font-size="12.5" fill="#6b7280">{_esc(subtitle)}</text>',
        '<g id="vp">',
    ]
    for i, e in enumerate(edges_data):
        x1, y1 = pos[e["s"]]
        x2, y2 = pos[e["t"]]
        color = PRED_COLOR.get(e["p"], "#cbd5e1")
        w = 1.7 if e["status"] == "verified" else 1.1
        dash = ' stroke-dasharray="4 3"' if e["status"] != "verified" else ""
        svg_parts.append(
            f'<line class="edge" data-i="{i}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{w}" stroke-opacity="0.55"{dash}/>'
        )
    for n in graph.nodes:
        x, y = pos[n.id]
        r = size[n.id]
        color = COLORS.get(n.label, "#64748b")
        tip = f"{n.name}（{LABEL_CN.get(n.label, n.label)}，度 {n.degree}）"
        fs = 11 if n.label == "Variety" else 9.5
        svg_parts.append(
            f'<g class="node" data-id="{_esc(n.id)}"><title>{_esc(tip)}</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" fill-opacity="0.92" '
            f'stroke="#ffffff" stroke-width="2"/>'
            f'<text x="{x:.1f}" y="{y - r - 3:.1f}" font-size="{fs}" fill="#1f2328" '
            f'text-anchor="middle">{_esc(n.name)}</text></g>'
        )
    svg_parts.append("</g></svg>")

    filters = "".join(
        f'<label class="filter"><input type="checkbox" value="{lab}" checked>'
        f'<i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:{COLORS[lab]}"></i>'
        f'{LABEL_CN[lab]}</label>'
        for lab in LABEL_ORDER
    )
    legend = "".join(
        f'<span><i style="background:{COLORS[lab]}"></i>{LABEL_CN[lab]}</span>' for lab in LABEL_ORDER
    )
    js = (_JS.replace("%CN%", _js_escape_json(PRED_CN))
             .replace("%LC%", _js_escape_json(LABEL_CN))
             .replace("%COL%", _js_escape_json(COLORS))
             .replace("%PRED%", _js_escape_json(PRED_CN)))

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>
<div id="top">
  <div><h3>{_esc(title)}</h3><div class="sub">{_esc(subtitle)}</div></div>
  <div id="tools">
    {filters}
    <input id="search" placeholder="按名称搜索…">
    <button id="zin">放大</button><button id="zout">缩小</button><button id="zreset">重置</button>
  </div>
</div>
<div id="main">
  <div id="graph">
    {''.join(svg_parts)}
    <div id="legend">{legend}<span style="margin-left:8px">实线=已核验 · 虚线=待核验</span></div>
  </div>
  <div id="panel"><h4>节点详情</h4><div id="detail"><div class="hint">点击任意节点，查看它连向哪里</div></div></div>
</div>
<script type="application/json" id="ndata">{_js_escape_json(nodes_data)}</script>
<script type="application/json" id="edata">{_js_escape_json(edges_data)}</script>
<script>{js}</script>
</body></html>"""
