"""可交互知识图谱（自包含 HTML：内联 SVG + 原生 JS，无外部依赖、离线可用）。

交互：
- 点击节点：高亮邻居；右侧面板显示 **具体描述**（类型/属性/备注/数值区间）、
  按谓词分组的关联事实（含数值、等级/严重度、来源）以及建议提问；点邻居可继续跳转
- 滚轮缩放、拖拽平移、重置视图
- 类型筛选（品种/条件/指标/病害）、按名称搜索
"""
from __future__ import annotations

import json
from pathlib import Path

from app.graph_view import (
    COLORS,
    LABEL_CN,
    PRED_COLOR,
    Graph,
    _esc,
    layout,
    load_descriptions,
    load_sources,
)

PRED_CN = {
    "REQUIRES": "需要条件", "CONTRA_INDICATED_FOR": "禁忌", "AFFECTS": "影响",
    "SUSCEPTIBLE_TO": "易感", "PREVENTED_BY": "可预防/处置", "INDUCED_BY": "诱因",
    "ALTERNATIVE_TO": "可替代", "INDICATES": "指示", "HAS_INDICATOR_VALUE": "指标基线",
}
ATTR_CN = {
    "category": "类别", "species": "品种类型", "berry_color": "果色", "seedless": "无核",
    "maturity": "成熟期", "region": "主产区", "pathogen_latin": "病原拉丁名",
    "symptom": "症状", "method": "方式", "stage": "阶段", "direction": "方向",
    "value_min": "数值下限", "value_max": "数值上限", "unit": "单位", "aliases": "别名",
}
LABEL_ORDER = ["Variety", "Disease", "QualityIndicator", "Condition"]
PRED_ORDER = ["REQUIRES", "PREVENTED_BY", "INDUCED_BY", "SUSCEPTIBLE_TO", "CONTRA_INDICATED_FOR",
              "ALTERNATIVE_TO", "AFFECTS", "HAS_INDICATOR_VALUE", "INDICATES"]

_CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#1f2328;
     background:#fff;display:flex;flex-direction:column;height:100vh;overflow:hidden}
#top{padding:10px 14px 6px;border-bottom:1px solid #e6e8eb;display:flex;align-items:center;
     gap:10px;flex-wrap:wrap;background:#fff;z-index:3}
#top h3{margin:0;font-size:16px}
#top .sub{font-size:11px;color:#6b7280}
#tools{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#tools input{border:1px solid #e6e8eb;border-radius:8px;padding:4px 8px;font-size:12px;width:140px}
#tools button{border:1px solid #e6e8eb;background:#f9fafb;border-radius:8px;padding:4px 10px;
              font-size:12px;cursor:pointer;color:#1f2328}
#tools button:hover{border-color:#4d6bfe;color:#4d6bfe}
.filter{display:inline-flex;align-items:center;gap:4px;font-size:12px;color:#6b7280;cursor:pointer}
#main{flex:1;display:flex;min-height:0}
#graph{flex:1;position:relative;overflow:hidden;background:#fff}
#graph svg{width:100%;height:100%;display:block;cursor:grab;user-select:none}
#graph svg.dragging{cursor:grabbing}
#panel{width:370px;border-left:1px solid #e6e8eb;overflow:auto;padding:14px 14px 24px;font-size:12.5px;
       line-height:1.65;background:#fbfcfe}
#panel h4{margin:0 0 4px;font-size:15px}
#panel .hint{color:#9ca3af;font-size:12px;margin-top:40px;text-align:center}
#panel .tag{display:inline-block;padding:0 7px;border-radius:999px;font-size:11px;margin-right:4px}
#panel .sec{font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.06em;
            margin:12px 0 4px}
#panel .desc{background:#eef2ff;border-radius:8px;padding:8px 10px;color:#374151;margin:6px 0}
#panel .desc b{display:block;margin-bottom:2px}
#panel .desc-src{color:#6b7280;font-size:11px;margin-top:2px}
#panel .desc-src a{color:#4d6bfe}
#panel .note{color:#6b7280;font-size:11.5px;margin:4px 0 0}
#panel table{border-collapse:collapse;width:100%;font-size:12px}
#panel td{padding:2px 0;vertical-align:top}
#panel td.k{color:#6b7280;width:78px;white-space:nowrap}
#panel ul{list-style:none;margin:4px 0;padding:0}
#panel li{border:1px solid #e6e8eb;border-radius:8px;padding:5px 8px;margin:4px 0;background:#fff;
          cursor:pointer;font-size:12px}
#panel li:hover{border-color:#4d6bfe}
#panel li .p{color:#4d6bfe;font-weight:700}
#panel li .v{color:#b45309}
#panel li .st{float:right;font-size:10px;color:#9ca3af}
#panel .q{background:#f1f5f9;border-radius:8px;padding:6px 8px;margin-top:10px;color:#374151}
#panel .src{color:#6b7280;font-size:11px;margin-top:6px}
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
"""

_JS = r"""
const SVG = document.getElementById('graph').querySelector('svg');
const VP = document.getElementById('vp');
const NODES = JSON.parse(document.getElementById('ndata').textContent);
const EDGES = JSON.parse(document.getElementById('edata').textContent);
const SRC = JSON.parse(document.getElementById('sdata').textContent);
const byId = Object.fromEntries(NODES.map(n => [n.id, n]));
const adj = {}; NODES.forEach(n => adj[n.id] = []);
EDGES.forEach((e, i) => { adj[e.s].push(i); adj[e.t].push(i); });
const CN = %LC%;
const COL = %COL%;
const PRED_CN = %PRED%;
const ATTR_CN = %ATTR%;
const PRED_ORDER = %PORDER%;
let scale = 1, px = 0, py = 0, drag = null;

function applyView(){ VP.setAttribute('transform', `translate(${px},${py}) scale(${scale})`); }
function reset(){ scale = 1; px = 0; py = 0; applyView(); }
function zoom(f){ scale = Math.max(0.35, Math.min(5, scale * f)); applyView(); }
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
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function fmtRange(a){
  const mn = a.value_min || '', mx = a.value_max || '', u = a.unit || '', v = a.value || '';
  if (v) return `${v}${u}`;
  if (mn && mx) return `${mn}~${mx}${u}`;
  if (mn) return `≥${mn}${u}`;
  if (mx) return `≤${mx}${u}`;
  return '';
}

function clearSel(){
  nodeEls().forEach(el => el.classList.remove('dim'));
  edgeEls().forEach(el => el.classList.remove('dim', 'hl'));
  document.getElementById('detail').innerHTML =
    '<div class="hint">点击任意节点，查看它的具体描述与关联</div>';
}

function select(id){
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

  const a = n.attrs || {};
  const d = n.desc || {};
  const note = a.note || '';
  const range = fmtRange(a);
  const rows = Object.keys(ATTR_CN).filter(k => k !== 'aliases' && k !== 'value_min' &&
      k !== 'value_max' && k !== 'unit' && a[k]).map(k =>
      `<tr><td class="k">${ATTR_CN[k]}</td><td>${esc(a[k])}</td></tr>`).join('');
  const attrTable = rows || range ? `<table>${rows}${range ? `<tr><td class="k">数值</td><td>${esc(range)}</td></tr>` : ''}</table>` : '';

  let facts = '';
  const srcIds = new Set();
  (EDGES.filter(e => e.s === id || e.t === id)).forEach(e => {
    if (e.src) e.src.split(';').filter(Boolean).forEach(x => srcIds.add(x));
  });
  const groups = {};
  adj[id].forEach(i => {
    const e = EDGES[i];
    (groups[e.p] = groups[e.p] || []).push(e);
  });
  PRED_ORDER.forEach(p => {
    if (!groups[p]) return;
    const items = groups[p].map(e => {
      const other = e.s === id ? e.t : e.s;
      const o = byId[other] || {name: other};
      const dir = e.s === id ? '→' : '←';
      let val = '';
      if (e.value) val = `${e.value}${e.unit || ''}`;
      else if (e.value_min || e.value_max) {
        const mn = e.value_min || '', mx = e.value_max || '';
        val = (mn && mx) ? `${mn}~${mx}${e.unit || ''}` : (mn ? `≥${mn}${e.unit || ''}` : `≤${mx}${e.unit || ''}`);
      }
      const extra = [e.level ? `等级 ${e.level}` : '', e.severity ? `严重度 ${e.severity}` : '',
                     e.effect ? e.effect : '', e.reason ? e.reason : ''].filter(Boolean).join('；');
      const st = e.status === 'verified' ? '已核验' : '待核验';
      return `<li data-id="${esc(other)}"><span class="p">${esc(PRED_CN[e.p] || e.p)}</span> ${dir} ${esc(o.name)}` +
             (val ? ` <span class="v">${esc(val)}</span>` : '') +
             (extra ? `<div style="color:#6b7280;margin-top:2px">${esc(extra)}</div>` : '') +
             `<span class="st">${st}</span></li>`;
    }).join('');
    facts += `<div class="sec">${esc(PRED_CN[p] || p)} · ${groups[p].length}</div><ul>${items}</ul>`;
  });

  const srcTitles = Array.from(srcIds).map(x => SRC[x]).filter(Boolean);
  const srcHtml = srcTitles.length
    ? `<div class="src">来源：${esc(srcTitles.slice(0, 4).join('；'))}${srcTitles.length > 4 ? ` 等 ${srcTitles.length} 条` : ''}</div>`
    : '';
  const q = n.label === 'Variety' ? n.name + '放冷库该调到多少度？'
        : n.label === 'Disease' ? n.name + '怎么防？'
        : n.label === 'Condition' ? '葡萄冷藏用 ' + n.name + ' 有什么要求？'
        : n.name + ' 受什么影响？';
  const col = /^#[0-9a-fA-F]{3,8}$/.test(String(COL[n.label] || '')) ? COL[n.label] : '#64748b';
  document.getElementById('detail').innerHTML =
    `<h4>${esc(n.name)}</h4>` +
    `<div><span class="tag" style="background:${col}22;color:${col}">${esc(CN[n.label] || n.label)}</span>` +
    `<span style="color:#6b7280;font-size:11px">连接度 ${esc(n.degree)}</span></div>` +
    `<div class="sec">具体描述</div>` +
    (d.summary || d.detail
      ? `<div class="desc">${d.summary ? `<b>${esc(d.summary)}</b>` : ''}${d.detail ? esc(d.detail) : ''}` +
        (d.source_name ? `<div class="desc-src">来源：${d.source_url
            ? `<a href="${esc(d.source_url)}" target="_blank" rel="noopener">${esc(d.source_name)}</a>`
            : esc(d.source_name)}</div>` : '') + `</div>`
      : `<div class="desc">${note ? esc(note) : '该节点暂无科普描述，下面是从图谱关系归纳的信息。'}</div>`) +
    (note && (d.summary || d.detail) ? `<div class="note">图谱备注：${esc(note)}</div>` : '') +
    (attrTable ? `<div class="sec">属性</div>${attrTable}` : '') +
    (facts ? `<div class="sec">关联事实</div>${facts}` : '') +
    srcHtml +
    `<div class="q">可以这样问：${esc(q)}</div>`;
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


def _js_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


# 详情面板里 source_url 会渲染成 <a href>：只允许 http(s)，
# javascript:/data:/file: 等 scheme 一律不渲染为链接（descriptions.csv 属数据输入面）。
_ALLOWED_URL_PREFIXES = ("http://", "https://")


def _safe_source_url(url: object) -> str:
    text = str(url or "").strip()
    return text if text.lower().startswith(_ALLOWED_URL_PREFIXES) else ""


def interactive_html(graph: Graph, *, width: int = 1500, height: int = 900,
                     title: str = "鲜食葡萄储藏知识图谱",
                     subtitle: str = "点击节点看具体描述与关联；滚轮缩放，拖拽平移",
                     data_dir: Path | str | None = None) -> str:
    layout(graph)
    W, H = width, height
    pad = 40
    if data_dir is None:
        data_dir = Path(__file__).resolve().parents[1] / "data"
    sources = load_sources(data_dir)
    descs = load_descriptions(data_dir)
    pos = {n.id: (pad + n.x * (W - 2 * pad), pad + 70 + n.y * (H - 2 * pad - 90)) for n in graph.nodes}
    nodes_data: list[dict] = []
    size: dict[str, int] = {}
    for n in graph.nodes:
        base = 15 if n.label == "Variety" else 11
        r = int(base + (min(8, n.degree * 0.8) if n.degree else 0))
        size[n.id] = r
        desc = dict(descs.get(n.id) or {})
        if desc.get("source_url"):
            desc["source_url"] = _safe_source_url(desc["source_url"])
        nodes_data.append({"id": n.id, "name": n.name, "label": n.label, "degree": n.degree,
                           "x": round(pos[n.id][0], 1), "y": round(pos[n.id][1], 1),
                           "attrs": n.attrs, "desc": desc})
    edges_data = [{
        "s": e.source, "t": e.target, "p": e.predicate, "status": e.status,
        "value": e.value, "unit": e.unit, "value_min": e.value_min, "value_max": e.value_max,
        "level": e.level, "severity": e.severity, "reason": e.reason, "effect": e.effect,
        "src": e.source_ids,
    } for e in graph.edges if e.source in pos and e.target in pos]

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
    js = (_JS.replace("%LC%", _js_json(LABEL_CN))
             .replace("%COL%", _js_json(COLORS))
             .replace("%PRED%", _js_json(PRED_CN))
             .replace("%ATTR%", _js_json(ATTR_CN))
             .replace("%PORDER%", _js_json(PRED_ORDER)))

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
  <div id="panel"><h4>节点详情</h4><div id="detail"><div class="hint">点击任意节点，查看它的具体描述与关联</div></div></div>
</div>
<script type="application/json" id="ndata">{_js_json(nodes_data)}</script>
<script type="application/json" id="edata">{_js_json(edges_data)}</script>
<script type="application/json" id="sdata">{_js_json(sources)}</script>
<script>{js}</script>
</body></html>"""
