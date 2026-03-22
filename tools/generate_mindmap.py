"""
generate_mindmap.py — WebGL codebase mindmap (v2).

Produces a single self-contained HTML using the force-graph library
(WebGL canvas — handles 100k+ nodes smoothly). No D3 SVG.

Views:
  GALAXY   — Full module graph, live physics, animated edge particles
  SERVICES — 12 service supernodes, cross-service flows, glowing orbits
  CLUSTERS — Cluster convex-hull overlay on the galaxy view

Run:
    python3 tools/generate_mindmap.py
    python3 tools/generate_mindmap.py --output /tmp/mindmap.html
    python3 tools/generate_mindmap.py --warmup 80   # layout warmup iterations
"""
import json, pathlib, sys, math, argparse, colorsys, random, hashlib
from collections import defaultdict

try:
    import networkx as nx
except ImportError:
    print("networkx required: pip install networkx"); sys.exit(1)

# ── args ─────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--output",  default="")
ap.add_argument("--warmup",  type=int, default=120,
                help="Spring-layout iterations (baked into HTML as seed positions)")
args = ap.parse_args()

PIPELINE  = pathlib.Path("/home/beast/projects/mindmap/pipeline")
ARTIFACTS = PIPELINE / "demo_artifact"
OUTPUT_P  = PIPELINE / "output"
OUT_HTML  = pathlib.Path(args.output) if args.output else ARTIFACTS / "mindmap.html"


# ══════════════════════════════════════════════════════════════════════════════
# 1  Load artifacts
# ══════════════════════════════════════════════════════════════════════════════
print("Loading graph data…")
graph_data = json.loads((ARTIFACTS / "graph_with_summaries.json").read_text())
nodes_raw  = graph_data["nodes"]
edges_raw  = graph_data.get("edges", [])
cluster_summaries = graph_data.get("cluster_summaries", {})
print(f"  {len(nodes_raw):,} nodes · {len(edges_raw):,} raw edges · {len(cluster_summaries)} clusters")

fn_counts: dict[str, int] = defaultdict(int)
bs_path = OUTPUT_P / "body_store.json"
if bs_path.exists():
    for fn_id in json.loads(bs_path.read_text()):
        parts = fn_id.split(".")
        if len(parts) >= 2:
            fn_counts[".".join(parts[:-1])] += 1
    print(f"  body_store: function counts built")

cochange_top: dict[str, list] = {}
_cc_to_mg: dict[str, str] = {}   # cc_key → mg_module_name
cc_path = ARTIFACTS / "cochange_index.json"
if cc_path.exists():
    ci = json.loads(cc_path.read_text())
    for mod, pairs in ci.get("edges", {}).items():
        cochange_top[mod] = pairs[:4]
    print(f"  cochange: {len(cochange_top):,} modules")

def _cc_key_to_mg(cc_key: str) -> str:
    """Map cochange key (service::dir::Module::Sub) to Haskell module name (Module.Sub)."""
    # Also handle path-based keys (all lowercase) — return as-is
    parts = cc_key.split("::")
    for i, p in enumerate(parts):
        if p and p[0].isupper():
            return ".".join(parts[i:])
    return cc_key   # already path-based (Rust/JS services use full path as module key)


# ══════════════════════════════════════════════════════════════════════════════
# 2  Module-level graph (mirrors retrieval_engine.py)
# ══════════════════════════════════════════════════════════════════════════════
print("\nBuilding module graph…")
mod_to_svc:     dict[str, str] = {}
mod_to_cluster: dict[str, str] = {}
for n in nodes_raw:
    m, s, c = n.get("module",""), n.get("service",""), n.get("cluster_name","")
    if m:
        mod_to_svc[m]     = s
        if c: mod_to_cluster[m] = c

cluster_purpose: dict[str, str] = {
    cs.get("cluster_name",""): cs.get("cluster_purpose","") or cs.get("description","")
    for cs in cluster_summaries.values()
}

MG = nx.DiGraph()
for e in edges_raw:
    src, dst, kind = e.get("from",""), e.get("to",""), e.get("kind","")
    if kind == "import" and src in mod_to_svc and dst in mod_to_svc:
        for n in (src, dst):
            MG.add_node(n, service=mod_to_svc[n], cluster=mod_to_cluster.get(n,""))
        if MG.has_edge(src, dst):
            MG[src][dst]["weight"] += 1
        else:
            MG.add_edge(src, dst, weight=1)

cs_count = sum(1 for u,v in MG.edges()
               if MG.nodes[u].get("service") != MG.nodes[v].get("service"))
print(f"  {MG.number_of_nodes():,} modules · {MG.number_of_edges():,} edges · {cs_count:,} cross-service")


# ══════════════════════════════════════════════════════════════════════════════
# 3  Service graph
# ══════════════════════════════════════════════════════════════════════════════
print("Building service graph…")
SG = nx.DiGraph()
svc_fn_count:  dict[str, int] = defaultdict(int)
svc_mod_count: dict[str, int] = defaultdict(int)
for mod, svc in mod_to_svc.items():
    if svc:
        svc_fn_count[svc]  += fn_counts.get(mod, 0)
        svc_mod_count[svc] += 1
        SG.add_node(svc)

for u, v, d in MG.edges(data=True):
    su, sv = MG.nodes[u].get("service",""), MG.nodes[v].get("service","")
    if su and sv and su != sv:
        if SG.has_edge(su, sv): SG[su][sv]["weight"] += d.get("weight",1)
        else:                    SG.add_edge(su, sv, weight=d.get("weight",1))
print(f"  {SG.number_of_nodes()} services · {SG.number_of_edges()} cross-service edges")


# ══════════════════════════════════════════════════════════════════════════════
# 4  Palette  (vivid, distinct, dark-bg friendly)
# ══════════════════════════════════════════════════════════════════════════════
FIXED_PALETTE = [
    "#00b4d8","#f72585","#7bed9f","#ffd32a","#a29bfe",
    "#fd79a8","#55efc4","#f9ca24","#6c5ce7","#e17055",
    "#74b9ff","#00cec9","#fdcb6e","#ff7675","#b2bec3",
]

def _palette(items: list[str]) -> dict[str, str]:
    rng = random.Random(77)
    result, pool = {}, list(FIXED_PALETTE)
    for i, item in enumerate(sorted(items)):
        if i < len(pool):
            result[item] = pool[i]
        else:
            h = (i * 0.382) % 1.0
            r,g,b = colorsys.hsv_to_rgb(h, 0.75, 0.92)
            result[item] = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
    return result

all_svcs    = sorted(s for s in set(mod_to_svc.values()) if s)
svc_color   = _palette(all_svcs)
all_clusters = sorted(c for c in set(mod_to_cluster.values()) if c)
clu_color   = _palette(all_clusters)


# ══════════════════════════════════════════════════════════════════════════════
# 5  Pre-compute layout (seed positions → browser force-graph refines live)
# ══════════════════════════════════════════════════════════════════════════════
print(f"\nWarm-up layout ({args.warmup} iterations)…")
rng = random.Random(42)
n_svcs = max(len(all_svcs), 1)
svc_center = {
    svc: (math.cos(2*math.pi*i/n_svcs)*350,
          math.sin(2*math.pi*i/n_svcs)*350)
    for i, svc in enumerate(sorted(all_svcs))
}
seed_pos = {}
for node, d in MG.nodes(data=True):
    cx, cy = svc_center.get(d.get("service",""), (0,0))
    seed_pos[node] = (cx + rng.gauss(0, 60), cy + rng.gauss(0, 60))

pos = nx.spring_layout(
    MG.to_undirected(), pos=seed_pos,
    iterations=args.warmup, seed=42, k=1.2, weight="weight",
)
# scale to ~[-1300, 1300]
xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
xr, yr = max(max(xs)-min(xs), 1), max(max(ys)-min(ys), 1)
scale = 2600 / max(xr, yr)
cx0, cy0 = (max(xs)+min(xs))/2, (max(ys)+min(ys))/2
pos = {n: ((p[0]-cx0)*scale, (p[1]-cy0)*scale) for n, p in pos.items()}

# ── Service separation: push each service cluster outward from its centroid ───
# Computes centroid per service, then scales centroid positions by PUSH_FACTOR
# so clusters spread apart while preserving internal module structure.
PUSH_FACTOR = 2.8
from collections import defaultdict as _dd
_svc_pts: dict[str, list] = _dd(list)
for _n, (_x, _y) in pos.items():
    _s = mod_to_svc.get(_n, "")
    if _s: _svc_pts[_s].append((_x, _y))
_svc_cx = {s: sum(p[0] for p in pts)/len(pts) for s, pts in _svc_pts.items()}
_svc_cy = {s: sum(p[1] for p in pts)/len(pts) for s, pts in _svc_pts.items()}
pos = {
    n: (x + _svc_cx.get(mod_to_svc.get(n,""), 0) * (PUSH_FACTOR - 1),
        y + _svc_cy.get(mod_to_svc.get(n,""), 0) * (PUSH_FACTOR - 1))
    for n, (x, y) in pos.items()
}
# ── Spherical projection — wrap the 2D layout onto a sphere surface ──────────
# The spring layout gives a flat map; normalise to [-1,1]² then apply
# equirectangular → cartesian projection so all nodes lie ON a sphere.
# This gives a natural 3D reference frame: services appear as continents.
SPHERE_R = 2400
xs2, ys2 = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
_max_r   = max(max(map(abs, xs2)), max(map(abs, ys2)), 1)

def _to_sphere(x2d: float, y2d: float, node_id: str) -> tuple:
    u = x2d / _max_r          # longitude in [-1, 1]  → θ ∈ [-π, π]
    v = y2d / _max_r          # latitude  in [-1, 1]  → φ ∈ [-π/2, π/2]
    theta = u * math.pi
    phi   = v * math.pi / 2
    # Small radial jitter keeps co-located nodes from z-fighting
    h     = int(hashlib.md5(node_id.encode()).hexdigest()[:6], 16)
    jitter = 1 + (h / 0xFFFFFF - 0.5) * 0.12   # ±6 % of radius
    r = SPHERE_R * jitter
    return (
        round(r * math.cos(phi) * math.cos(theta), 1),
        round(r * math.sin(phi),                   1),
        round(r * math.cos(phi) * math.sin(theta), 1),
    )

pos3d = {n: _to_sphere(x, y, n) for n, (x, y) in pos.items()}
print("  Layout done (spherical).")


# ══════════════════════════════════════════════════════════════════════════════
# 6  Serialise
# ══════════════════════════════════════════════════════════════════════════════
print("\nSerialising…")

# --- module nodes ---
module_nodes = []
for nid, d in MG.nodes(data=True):
    x, y, z = pos3d.get(nid, (0, 0, 0))
    svc   = d.get("service","")
    clu   = d.get("cluster","") or mod_to_cluster.get(nid,"")
    fn_c  = fn_counts.get(nid, 0)
    deg   = MG.degree(nid)
    # val = visual radius, driven purely by function count
    val   = max(1.5, min(22.0, math.sqrt(max(fn_c, 0)) * 1.8))
    module_nodes.append({
        "id": nid,
        "x": x, "y": y, "z": z,
        "svc": svc, "clu": clu,
        "purpose": cluster_purpose.get(clu,""),
        "fn": fn_c, "deg": deg,
        "col": svc_color.get(svc,"#888"),
        "val": round(val, 2),
    })

# --- module edges ---
module_links = []
for u, v, d in MG.edges(data=True):
    su, sv = MG.nodes[u].get("service",""), MG.nodes[v].get("service","")
    module_links.append({
        "source": u, "target": v,
        "w": d.get("weight",1),
        "cross": su != sv,
    })
print(f"  Module: {len(module_nodes):,} nodes · {len(module_links):,} links")

# --- co-change links (separate edge type, sampled) ---
cochange_links = []
_seen_cc = set()
for mod, pairs in cochange_top.items():
    src_mg = _cc_key_to_mg(mod)
    if src_mg not in pos: continue
    for p in pairs[:2]:
        nbr_cc = p.get("module","")
        nbr_mg = _cc_key_to_mg(nbr_cc)
        if nbr_mg not in pos: continue
        key = (min(src_mg, nbr_mg), max(src_mg, nbr_mg))
        if key in _seen_cc: continue
        _seen_cc.add(key)
        cochange_links.append({"source": src_mg, "target": nbr_mg,
                               "w": p.get("weight", 1)})
print(f"  Co-change links: {len(cochange_links):,}")

# --- service nodes (circular layout) ---
svc_layout = {
    svc: (math.cos(2*math.pi*i/n_svcs - math.pi/2) * 320,
          math.sin(2*math.pi*i/n_svcs - math.pi/2) * 320)
    for i, svc in enumerate(sorted(all_svcs))
}
service_nodes = []
for svc in sorted(all_svcs):
    x, y  = svc_layout[svc]
    fn_c  = svc_fn_count.get(svc,0)
    service_nodes.append({
        "id": svc, "x": round(x), "y": round(y),
        "fn": fn_c, "mods": svc_mod_count.get(svc,0),
        "col": svc_color.get(svc,"#888"),
        "val": max(8, min(80, 8 + math.sqrt(fn_c)*0.12 + svc_mod_count.get(svc,0)*0.03)),
    })

svc_list = sorted(all_svcs)
for n in service_nodes: n['z'] = 0.0

max_sw = max((d.get("weight",1) for _,_,d in SG.edges(data=True)), default=1)
service_links = [
    {"source": u, "target": v,
     "w": d.get("weight",1), "nw": d.get("weight",1)/max_sw}
    for u, v, d in SG.edges(data=True)
]

# --- cluster hulls (centroid + radius) ---
cluster_hulls = {}
for clu in all_clusters:
    pts = [(pos3d[n][0], pos3d[n][1])
           for n, d in MG.nodes(data=True)
           if (d.get("cluster","") or mod_to_cluster.get(n,"")) == clu and n in pos3d]
    if len(pts) < 2: continue
    cx_ = sum(p[0] for p in pts)/len(pts)
    cy_ = sum(p[1] for p in pts)/len(pts)
    r   = max(math.dist((cx_,cy_), p) for p in pts)
    cluster_hulls[clu] = {
        "cx": round(cx_,1), "cy": round(cy_,1),
        "r":  round(min(r + 30, 600), 1),
        "n":  len(pts),
        "purpose": cluster_purpose.get(clu,""),
        "col": clu_color.get(clu,"#888"),
    }

payload = {
    "module_nodes":   module_nodes,
    "module_links":   module_links,
    "cochange_links": cochange_links,
    "service_nodes":  service_nodes,
    "service_links":  service_links,
    "cluster_hulls":  cluster_hulls,
    "svc_color":      svc_color,
    "stats": {
        "symbols":        sum(fn_counts.values()),
        "modules":        MG.number_of_nodes(),
        "import_edges":   MG.number_of_edges(),
        "cross_svc":      cs_count,
        "services":       len(all_svcs),
        "clusters":       len(cluster_summaries),
        "cochange_pairs": sum(len(v) for v in cochange_top.values()),
    },
}
graph_json = json.dumps(payload, separators=(",",":"))
print(f"  Payload: {len(graph_json)//1024} KB")

# Write data file separately (HTML fetches it — no baking)
data_file = ARTIFACTS / "graph-data.json"
data_file.write_text(graph_json, encoding="utf-8")
print(f"  Data file → {data_file}  ({data_file.stat().st_size//1024} KB)")


# ══════════════════════════════════════════════════════════════════════════════
# 7  HTML  (v4 — Three.js production 3D renderer)
# ══════════════════════════════════════════════════════════════════════════════
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Codebase Mindmap</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<script type="importmap">
{"imports":{"three":"https://unpkg.com/three@0.169.0/build/three.module.js","three/addons/":"https://unpkg.com/three@0.169.0/examples/jsm/"}}
</script>
<style>
:root{
  --bg:#050c14; --surface:#0d1b2a; --surface2:#112240;
  --border:#1e3a5f; --accent:#00b4d8; --accent2:#f72585;
  --text:#ccd6f6; --muted:#8892b0; --particle:#ffd32a;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:var(--bg);font-family:'Inter',system-ui,sans-serif;color:var(--text)}
#chrome{position:fixed;inset:0;display:grid;grid-template-rows:56px 1fr;grid-template-columns:1fr 300px;pointer-events:none;z-index:10}
#chrome>*{pointer-events:auto}
#topbar{grid-column:1/-1;display:flex;align-items:center;gap:10px;padding:0 18px;background:rgba(5,12,20,.82);backdrop-filter:blur(18px);border-bottom:1px solid var(--border)}
#brand{font-size:15px;font-weight:700;color:var(--accent);letter-spacing:.5px;white-space:nowrap}
#brand span{color:var(--accent2)}
.vbtn{padding:5px 16px;border-radius:20px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;font-size:12px;transition:all .2s;white-space:nowrap}
.vbtn:hover{border-color:var(--accent);color:var(--accent)}
.vbtn.active{background:var(--accent);border-color:var(--accent);color:#000;font-weight:600}
#search-wrap{position:relative;margin-left:8px}
#search{padding:5px 12px 5px 32px;border-radius:20px;border:1px solid var(--border);background:rgba(13,27,42,.8);color:var(--text);font-size:12px;width:200px;transition:border-color .2s}
#search:focus{outline:none;border-color:var(--accent)}
#search-icon{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:13px;pointer-events:none}
#search-clear{position:absolute;right:8px;top:50%;transform:translateY(-50%);color:var(--muted);cursor:pointer;font-size:14px;display:none}
#chip-row{display:flex;gap:6px;flex-wrap:nowrap;overflow-x:auto;padding:2px 0}
#chip-row::-webkit-scrollbar{display:none}
.chip{padding:3px 10px;border-radius:12px;font-size:10px;cursor:pointer;border:1px solid;opacity:.8;transition:opacity .15s,transform .15s;white-space:nowrap;flex-shrink:0}
.chip:hover{opacity:1;transform:scale(1.05)}
.chip.off{opacity:.22}
#topbar-right{margin-left:auto;display:flex;align-items:center;gap:14px}
#stat-ticker{font-size:11px;color:var(--muted);white-space:nowrap}
/* fps card */
#fps-card{display:flex;gap:20px;background:rgba(13,27,42,.7);border:1px solid var(--border);border-radius:10px;padding:8px 18px;pointer-events:none}
.fps-col{display:flex;flex-direction:column;align-items:center;gap:2px}
.fps-label{font-size:9px;letter-spacing:1px;color:var(--muted);text-transform:uppercase}
.fps-num{font-size:18px;font-weight:700;color:#fff;line-height:1}
/* bottom controls */
#ctrl-bar{
  position:fixed;bottom:0;left:0;right:300px;
  height:72px;display:flex;align-items:center;justify-content:center;gap:32px;
  background:rgba(5,12,20,.88);backdrop-filter:blur(16px);
  border-top:1px solid var(--border);z-index:10;padding:0 24px;
}
.ctrl-group{display:flex;align-items:center;gap:10px}
.ctrl-label{font-size:11px;color:var(--muted);white-space:nowrap;width:100px;text-align:right}
.ctrl-slider{-webkit-appearance:none;appearance:none;width:160px;height:3px;border-radius:2px;background:var(--border);outline:none;cursor:pointer}
.ctrl-slider::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;border-radius:50%;background:var(--accent);cursor:pointer;box-shadow:0 0 6px var(--accent)}
.ctrl-val{font-size:12px;font-weight:600;color:#fff;min-width:32px;text-align:center;background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:2px 6px}
#panel{grid-row:2;grid-column:2;background:rgba(5,12,20,.88);backdrop-filter:blur(18px);border-left:1px solid var(--border);padding:18px 16px;overflow-y:auto;display:flex;flex-direction:column;gap:16px}
.panel-section h4{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:10px}
#stat-cards{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.scard{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px;text-align:center}
.scard-val{font-size:20px;font-weight:700;color:var(--accent);line-height:1}
.scard-lbl{font-size:9px;color:var(--muted);margin-top:3px;text-transform:uppercase;letter-spacing:.5px}
#legend-list{display:flex;flex-direction:column;gap:5px}
.leg-row{display:flex;align-items:center;gap:8px;font-size:11px;cursor:pointer;padding:3px 6px;border-radius:5px;transition:background .15s}
.leg-row:hover{background:var(--surface2)}
.leg-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.leg-name{flex:1;color:var(--text)}
.leg-count{color:var(--muted);font-size:10px}
#detail-box{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;display:none}
#detail-box h3{font-size:13px;color:var(--accent);word-break:break-all;margin-bottom:10px;line-height:1.4}
.drow{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:6px;font-size:11px}
.dkey{color:var(--muted);flex-shrink:0}
.dval{color:var(--text);text-align:right;word-break:break-all;max-width:170px}
.dpurpose{font-size:10px;color:var(--muted);font-style:italic;margin-top:8px;line-height:1.5;border-top:1px solid var(--border);padding-top:8px}
#graph-canvas{position:fixed;top:56px;right:300px;bottom:72px;left:0}
.node-label{background:rgba(5,12,20,.72);border:1px solid;border-radius:3px;padding:2px 7px;font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;white-space:nowrap;backdrop-filter:blur(4px);pointer-events:none}
#graph-canvas canvas{display:block;width:100%!important;height:100%!important}
#loading{position:fixed;top:56px;right:300px;bottom:72px;left:0;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;z-index:5}
.spinner{width:48px;height:48px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#loading-msg{color:var(--muted);font-size:13px}
#progress-wrap{width:220px;height:3px;background:var(--border);border-radius:2px;overflow:hidden}
#progress-bar{height:100%;background:var(--accent);width:0%;transition:width .15s}
#hud{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);display:flex;gap:8px;pointer-events:auto;background:rgba(5,12,20,.75);backdrop-filter:blur(12px);border:1px solid var(--border);border-radius:24px;padding:6px 12px}
.hbtn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:18px;line-height:1;padding:2px 6px;border-radius:8px;transition:color .15s,background .15s}
.hbtn:hover{color:var(--accent);background:var(--surface2)}
#tt{position:fixed;pointer-events:none;background:rgba(13,27,42,.95);backdrop-filter:blur(12px);border:1px solid var(--border);border-radius:10px;padding:10px 14px;font-size:11px;z-index:20;max-width:260px;line-height:1.7;display:none}
#tt-name{font-weight:700;color:var(--accent);margin-bottom:2px;word-break:break-all}
#tt-rows{color:var(--muted)}
#tt-rows b{color:var(--text)}
#fade{position:fixed;top:56px;right:300px;bottom:72px;left:0;background:var(--bg);opacity:0;pointer-events:none;z-index:4;transition:opacity .3s}
#fade.show{opacity:1}
#panel::-webkit-scrollbar{width:4px}
#panel::-webkit-scrollbar-track{background:transparent}
#panel::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
</style>
</head>
<body>
<div id="loading">
  <div class="spinner"></div>
  <div id="loading-msg">Fetching graph data…</div>
  <div id="progress-wrap"><div id="progress-bar"></div></div>
</div>
<div id="fade"></div>
<div id="graph-canvas"></div>
<div id="chrome">
  <div id="topbar">
    <div id="brand">⬡ Code<span>Map</span></div>
    <button class="vbtn active" id="btn-galaxy"   onclick="switchView('galaxy')">Galaxy</button>
    <button class="vbtn"        id="btn-services"  onclick="switchView('services')">Services</button>
    <button class="vbtn"        id="btn-clusters"  onclick="switchView('clusters')">Clusters</button>
    <div id="search-wrap">
      <span id="search-icon">⎕</span>
      <input id="search" type="text" placeholder="Search module…" oninput="onSearch(event)"/>
      <span id="search-clear" onclick="clearSearch()">✕</span>
    </div>
    <div id="chip-row"></div>
    <div id="topbar-right">
      <div id="stat-ticker">—</div>
      <div id="fps-card">
        <div class="fps-col"><span class="fps-label">Nodes</span><span class="fps-num" id="fps-nodes">—</span></div>
        <div class="fps-col"><span class="fps-label">Links</span><span class="fps-num" id="fps-links">—</span></div>
        <div class="fps-col"><span class="fps-label">FPS</span><span class="fps-num" id="fps-val">—</span></div>
      </div>
    </div>
  </div>
  <div id="panel">
    <div class="panel-section">
      <h4>Graph Stats</h4>
      <div id="stat-cards">
        <div class="scard"><div class="scard-val" id="sc-symbols">—</div><div class="scard-lbl">Symbols</div></div>
        <div class="scard"><div class="scard-val" id="sc-modules">—</div><div class="scard-lbl">Modules</div></div>
        <div class="scard"><div class="scard-val" id="sc-edges">—</div><div class="scard-lbl">Import Edges</div></div>
        <div class="scard"><div class="scard-val" id="sc-cross">—</div><div class="scard-lbl">Cross-Service</div></div>
      </div>
    </div>
    <div class="panel-section"><h4>Services</h4><div id="legend-list"></div></div>
    <div id="detail-box">
      <h3 id="det-name">—</h3>
      <div class="drow"><span class="dkey">Service</span><span class="dval" id="det-svc">—</span></div>
      <div class="drow"><span class="dkey">Cluster</span><span class="dval" id="det-clu">—</span></div>
      <div class="drow"><span class="dkey">Functions</span><span class="dval" id="det-fn">—</span></div>
      <div class="drow"><span class="dkey">Import degree</span><span class="dval" id="det-deg">—</span></div>
      <div class="dpurpose" id="det-purpose"></div>
    </div>
  </div>
</div>
<div id="hud">
  <button class="hbtn" onclick="zoomBy(1.4)" title="Zoom in">+</button>
  <button class="hbtn" onclick="zoomBy(0.7)" title="Zoom out">−</button>
  <button class="hbtn" onclick="fitView()"   title="Fit">⊙</button>
  <button class="hbtn" onclick="toggleParticles()" id="ptbtn" title="Toggle flow">⚡</button>
</div>
<div id="tt"><div id="tt-name"></div><div id="tt-rows"></div></div>

<div id="ctrl-bar">
  <div class="ctrl-group">
    <span class="ctrl-label">Auto-Rotate</span>
    <input class="ctrl-slider" type="range" min="0" max="5" step="0.1" value="0" oninput="setRotation(this.value)"/>
    <span class="ctrl-val" id="rot-val">0.0</span>
  </div>
  <div class="ctrl-group">
    <span class="ctrl-label">Node Size</span>
    <input class="ctrl-slider" type="range" min="0.3" max="3" step="0.1" value="1" oninput="setNodeSize(this.value)"/>
    <span class="ctrl-val" id="size-val">1.0</span>
  </div>
  <div class="ctrl-group">
    <span class="ctrl-label">Edge Opacity</span>
    <input class="ctrl-slider" type="range" min="0" max="1" step="0.01" value="0.18" oninput="setEdgeOpacity(this.value)"/>
    <span class="ctrl-val" id="edge-val">0.18</span>
  </div>
</div>

<script type="module">
import * as THREE from 'three';
import { OrbitControls }    from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment }  from 'three/addons/environments/RoomEnvironment.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// ── globals ─────────────────────────────────────────────────────────────────────────────────
let G, nodeById = {};
let renderer, labelRenderer, scene, camera, controls, raycaster;
let nodesMesh = null, linkLines = null, ccLines = null, ptsMesh = null;
let visNodes = [];
let view = 'galaxy', activeSvcs = new Set(), searchStr = '';
let hoveredIdx = -1, particlesOn = true;
const mouse = new THREE.Vector2(-9999, -9999);
const _col   = new THREE.Color();
const origColors = new Map();
let svcLabelObjs = [];   // CSS2DObject list for cleanup
// live controls
let nodeSizeMult = 1.0;
let edgeOpacity   = 0.18;
// fps
let _fpsCount = 0, _fpsLast = performance.now(), _fps = 60;

// ── boot ──────────────────────────────────────────────────────────────────────────────────
async function boot() {
  initRenderer();
  G = await fetchWithProgress('./graph-data.json', pct => {
    document.getElementById('progress-bar').style.width = (pct * 100).toFixed(0) + '%';
    document.getElementById('loading-msg').textContent  = 'Loading… ' + (pct*100).toFixed(0) + '%';
  });
  G.module_nodes.forEach(n => nodeById[n.id] = n);
  G.service_nodes.forEach(n => nodeById[n.id] = n);
  activeSvcs = new Set(G.service_nodes.map(n => n.id));
  buildStats(); buildChips(); buildLegend();
  document.getElementById('loading-msg').textContent = 'Building 3D scene…';
  buildScene();
  buildSvcLabels();
  document.getElementById('loading').style.display = 'none';
  animate();
  fitView();
}

// ── streaming fetch ───────────────────────────────────────────────────────────────────────────────
async function fetchWithProgress(url, cb) {
  const res   = await fetch(url);
  const total = parseInt(res.headers.get('Content-Length') || '0');
  const rdr   = res.body.getReader();
  const bufs  = [];
  let got = 0;
  for (;;) {
    const { done, value } = await rdr.read();
    if (done) break;
    bufs.push(value); got += value.length;
    if (total) cb(got / total);
  }
  cb(1);
  return JSON.parse(await new Blob(bufs).text());
}

// ── THREE init ────────────────────────────────────────────────────────────────────────────────
function initRenderer() {
  const el = document.getElementById('graph-canvas');
  const w = el.clientWidth, h = el.clientHeight;
  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.sortObjects = false;
  el.appendChild(renderer.domElement);
  // Environment map — makes physical materials reflect a room, letting service colors show through
  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();
  const envMap = pmrem.fromScene(new RoomEnvironment()).texture;
  pmrem.dispose();
  scene  = new THREE.Scene();
  scene.background = new THREE.Color(0x050c14);
  scene.environment = envMap;
  // Supplemental lights — boost diffuse so colors are vivid
  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.8);
  sun.position.set(600, 800, 600); scene.add(sun);
  const fill = new THREE.DirectionalLight(0x8899ff, 0.5);
  fill.position.set(-600, -300, -400); scene.add(fill);
  camera = new THREE.PerspectiveCamera(60, w/h, 1, 200000);
  camera.position.set(0, 0, 2500);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.07;
  // CSS2D label renderer — composited on top of WebGL canvas, no layout cost
  labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(w, h);
  labelRenderer.domElement.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;overflow:hidden';
  el.appendChild(labelRenderer.domElement);
  window.addEventListener('resize', () => {
    const w2 = el.clientWidth, h2 = el.clientHeight;
    labelRenderer.setSize(w2, h2);
  });
  controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
  controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };
  raycaster = new THREE.Raycaster();
  el.addEventListener('mousemove', onMouseMove);
  el.addEventListener('click',     onClick);
  window.addEventListener('resize', () => {
    const w2 = el.clientWidth, h2 = el.clientHeight;
    camera.aspect = w2/h2; camera.updateProjectionMatrix();
    renderer.setSize(w2, h2);
    // labelRenderer resize handled above
  });
}

// ── scene ────────────────────────────────────────────────────────────────────────────────────
function clearScene() {
  svcLabelObjs.forEach(o => { scene.remove(o); if(o.material) o.material.dispose(); }); svcLabelObjs = [];
  [nodesMesh, linkLines, ccLines, ptsMesh].forEach(o => {
    if (!o) return;
    scene.remove(o);
    o.geometry.dispose();
    (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose());
  });
  nodesMesh = linkLines = ccLines = ptsMesh = null;
  origColors.clear(); hoveredIdx = -1;
}

function buildScene() {
  clearScene();
  const clusterMode = (view === 'clusters');

  if (view === 'services') {
    visNodes = G.service_nodes.map(n => ({...n, _isSvc:true}));
    const vs  = new Set(visNodes.map(n => n.id));
    const svl = G.service_links.filter(l => vs.has(l.source) && vs.has(l.target)).map(l=>({...l,cross:true}));
    buildNodes(visNodes, false);
    if (svl.length) { linkLines = makeLines(svl, '#f72585', 0.5); scene.add(linkLines); }
  } else {
    visNodes = G.module_nodes.filter(n => activeSvcs.has(n.svc));
    const vs  = new Set(visNodes.map(n => n.id));
    const crl = G.module_links.filter(l => l.cross && vs.has(l.source) && vs.has(l.target));
    const ccl = G.cochange_links.filter(l => vs.has(l.source) && vs.has(l.target));
    buildNodes(visNodes, clusterMode);
    if (crl.length) { linkLines = makeLines(crl, '#ff6b00', 0.12); scene.add(linkLines); }
    if (ccl.length) { ccLines   = makeLines(ccl, '#00b4d8', 0.18); scene.add(ccLines);   }
    if (particlesOn) buildParticles(crl, ccl);
  }
}

function nodeHex(n, clusterMode) {
  if (clusterMode) { const h = G.cluster_hulls[n.clu]; return h ? h.col : '#445566'; }
  return n.col || '#888888';
}

function buildNodes(nodes, clusterMode) {
  const N   = nodes.length;
  const geo = new THREE.SphereGeometry(1, 32, 24);
  const mat = new THREE.MeshStandardMaterial({
    roughness: 0.52, metalness: 0.08,
    envMapIntensity: 0.7,
    vertexColors: true,
  });
  nodesMesh = new THREE.InstancedMesh(geo, mat, N);
  const dummy = new THREE.Object3D();
  nodes.forEach((n, i) => {
    n._r = n.val || 2;   // radius = fn count based (pre-computed in Python)
    dummy.position.set(n.x||0, n.y||0, n.z||0);
    dummy.scale.setScalar(n._r * nodeSizeMult);
    dummy.updateMatrix();
    nodesMesh.setMatrixAt(i, dummy.matrix);
    nodesMesh.setColorAt(i, _col.set(nodeHex(n, clusterMode)));
    n._idx = i;
  });
  nodesMesh.instanceMatrix.needsUpdate = true;
  if (nodesMesh.instanceColor) nodesMesh.instanceColor.needsUpdate = true;
  nodesMesh.userData.nodes = nodes;
  scene.add(nodesMesh);
}

function makeLines(links, hex, opacity) {
  const pos = new Float32Array(links.length * 6);
  links.forEach((l, i) => {
    const s = nodeById[typeof l.source==='string'?l.source:l.source?.id];
    const t = nodeById[typeof l.target==='string'?l.target:l.target?.id];
    if (!s||!t) return;
    pos[i*6]=s.x||0; pos[i*6+1]=s.y||0; pos[i*6+2]=s.z||0;
    pos[i*6+3]=t.x||0; pos[i*6+4]=t.y||0; pos[i*6+5]=t.z||0;
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const scaledOpacity = opacity * (edgeOpacity / 0.18);
  const mat = new THREE.LineBasicMaterial({
    color: new THREE.Color(hex), transparent: true, opacity: scaledOpacity, depthWrite: false,
  });
  mat.userData.baseHex = hex;
  mat.userData.baseOpacity = opacity;
  return new THREE.LineSegments(geo, mat);
}

// ── GPU particles (vertex shader animates via uTime — zero CPU work per frame) ──────────────────
const MAX_PT = 1200;
const _ptVert = `
attribute vec3 aStart;
attribute vec3 aEnd;
attribute float aOffset;
attribute float aSpeed;
attribute vec3 aColor;
uniform float uTime;
varying vec3 vCol;
void main(){
  float t = fract(uTime * aSpeed + aOffset);
  vec3 pos = mix(aStart, aEnd, t);
  vCol = aColor;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = clamp(18.0 * (600.0 / -mv.z), 3.0, 24.0);
  gl_Position = projectionMatrix * mv;
}`;
const _ptFrag = `
varying vec3 vCol;
void main(){
  vec2 uv = gl_PointCoord - 0.5;
  float d = length(uv);
  float a = 1.0 - smoothstep(0.25, 0.5, d);
  if(a < 0.01) discard;
  gl_FragColor = vec4(vCol, a);
}`;

function buildParticles(crl, ccl) {
  const cSamp  = crl.slice(0, Math.ceil(MAX_PT * 0.65));
  const ccSamp = ccl.slice(0, MAX_PT - cSamp.length);
  const pairs  = [...cSamp.map(l=>({l,cc:false})), ...ccSamp.map(l=>({l,cc:true}))];
  const N      = pairs.length * 2;
  const aStart  = new Float32Array(N * 3);
  const aEnd    = new Float32Array(N * 3);
  const aOffset = new Float32Array(N);
  const aSpeed  = new Float32Array(N);
  const aColor  = new Float32Array(N * 3);
  const orange  = new THREE.Color('#ffe8a0');   // pastel gold
  const blue    = new THREE.Color('#a0dff5');   // pastel cyan
  pairs.forEach(({l, cc}, pi) => {
    const sid = typeof l.source==='string'?l.source:l.source?.id;
    const tid = typeof l.target==='string'?l.target:l.target?.id;
    const s = nodeById[sid], t = nodeById[tid];
    if (!s||!t) return;
    const c = cc ? blue : orange;
    for (let k=0; k<2; k++) {
      const i = pi*2+k;
      aStart[i*3]=s.x||0; aStart[i*3+1]=s.y||0; aStart[i*3+2]=s.z||0;
      aEnd[i*3]  =t.x||0; aEnd[i*3+1]  =t.y||0; aEnd[i*3+2]  =t.z||0;
      aOffset[i] = k * 0.5 + Math.random() * 0.1;
      aSpeed[i]  = 0.12 + Math.random() * 0.12;
      aColor[i*3]=c.r; aColor[i*3+1]=c.g; aColor[i*3+2]=c.b;
    }
  });
  const geo = new THREE.BufferGeometry();
  // dummy position attr so THREE knows vertex count; actual pos computed in shader
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N*3), 3));
  geo.setAttribute('aStart',   new THREE.BufferAttribute(aStart,  3));
  geo.setAttribute('aEnd',     new THREE.BufferAttribute(aEnd,    3));
  geo.setAttribute('aOffset',  new THREE.BufferAttribute(aOffset, 1));
  geo.setAttribute('aSpeed',   new THREE.BufferAttribute(aSpeed,  1));
  geo.setAttribute('aColor',   new THREE.BufferAttribute(aColor,  3));
  const mat = new THREE.ShaderMaterial({
    vertexShader: _ptVert, fragmentShader: _ptFrag,
    uniforms: { uTime: { value: 0 } },
    transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  ptsMesh = new THREE.Points(geo, mat);
  ptsMesh.frustumCulled = false;
  scene.add(ptsMesh);
}

// ── service hub spheres — visible central node per service with permanent name label ──────────
const _hubGeo = new THREE.SphereGeometry(1, 32, 24);
function buildSvcLabels() {
  svcLabelObjs.forEach(o => { scene.remove(o); o.geometry && o.geometry.dispose(); });
  svcLabelObjs = [];
  if (view !== 'galaxy') return;

  // Compute centroid of each service from module nodes
  const acc = {};
  visNodes.forEach(n => {
    if (!n.svc) return;
    if (!acc[n.svc]) acc[n.svc] = {x:0,y:0,z:0,cnt:0,col:n.col||'#aaa',maxDeg:0};
    const a = acc[n.svc];
    a.x += n.x||0; a.y += n.y||0; a.z += n.z||0; a.cnt++;
    if ((n.deg||0) > a.maxDeg) { a.maxDeg = n.deg||0; }
  });

  Object.entries(acc).forEach(([svc, d]) => {
    const cx = d.x/d.cnt, cy = d.y/d.cnt, cz = d.z/d.cnt;
    const col = new THREE.Color(d.col);

    // Hub sphere — larger than normal nodes, service color, slight emissive glow
    const mat = new THREE.MeshStandardMaterial({
      color: col, emissive: col, emissiveIntensity: 0.35,
      roughness: 0.3, metalness: 0.2,
    });
    const hub = new THREE.Mesh(_hubGeo, mat);
    hub.scale.setScalar(22);
    hub.position.set(cx, cy, cz);
    hub.userData.isHub = true;
    scene.add(hub);
    svcLabelObjs.push(hub);

    // CSS2D name label — always visible, anchored to hub centre
    const div = document.createElement('div');
    div.className = 'node-label';
    div.textContent = svc.replace(/^euler-api-/,'').replace(/-/g,' ').toUpperCase();
    div.style.color       = d.col;
    div.style.borderColor = d.col;
    const label = new CSS2DObject(div);
    label.position.set(0, 28, 0);   // offset above hub sphere
    hub.add(label);                  // child of hub → moves with it automatically
  });
}

// ── render loop ─────────────────────────────────────────────────────────────────────────────────
function animate() {
  requestAnimationFrame(animate);
  controls.update();
  if (ptsMesh && particlesOn) ptsMesh.material.uniforms.uTime.value += 0.005;
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
  _fpsCount++;
  const now = performance.now();
  if (now - _fpsLast >= 1000) {
    _fps = _fpsCount;
    _fpsCount = 0;
    _fpsLast = now;
    const el = document.getElementById('fps-val');
    if (el) el.textContent = _fps;
  }
}

// ── hover / click ────────────────────────────────────────────────────────────────────────────────
function onMouseMove(e) {
  const el = document.getElementById('graph-canvas');
  const r  = el.getBoundingClientRect();
  mouse.x  = ((e.clientX-r.left)/r.width)*2-1;
  mouse.y  = -((e.clientY-r.top)/r.height)*2+1;
  if (!nodesMesh) return;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObject(nodesMesh);
  if (hits.length) {
    const idx  = hits[0].instanceId;
    const node = nodesMesh.userData.nodes[idx];
    if (idx !== hoveredIdx) {
      if (hoveredIdx >= 0 && origColors.has(hoveredIdx)) {
        nodesMesh.setColorAt(hoveredIdx, _col.set(origColors.get(hoveredIdx)));
        nodesMesh.instanceColor.needsUpdate = true;
      }
      hoveredIdx = idx;
      if (node) {
        origColors.set(idx, nodeHex(node, view==='clusters'));
        nodesMesh.setColorAt(idx, _col.set('#ffffff'));
        nodesMesh.instanceColor.needsUpdate = true;
        showTT(e, node); el.style.cursor = 'pointer';
      }
    } else moveTT(e);
  } else {
    if (hoveredIdx >= 0) {
      if (origColors.has(hoveredIdx)) {
        nodesMesh.setColorAt(hoveredIdx, _col.set(origColors.get(hoveredIdx)));
        nodesMesh.instanceColor.needsUpdate = true;
      }
      hoveredIdx = -1;
    }
    hideTT(); el.style.cursor = 'default';
  }
}

function onClick(e) {
  if (!nodesMesh) return;
  const el = document.getElementById('graph-canvas');
  const r  = el.getBoundingClientRect();
  mouse.x  = ((e.clientX-r.left)/r.width)*2-1;
  mouse.y  = -((e.clientY-r.top)/r.height)*2+1;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObject(nodesMesh);
  if (hits.length) { const n = nodesMesh.userData.nodes[hits[0].instanceId]; if(n){showDetail(n);zoomTo(n);} }
}

function zoomTo(node) {
  const tgt = new THREE.Vector3(node.x||0, node.y||0, node.z||0);
  const dir = camera.position.clone().sub(controls.target).normalize().multiplyScalar(120);
  animCam(camera.position.clone(), tgt.clone().add(dir), controls.target.clone(), tgt, 800);
}

function animCam(fromPos, toPos, fromTgt, toTgt, ms) {
  const t0 = performance.now();
  const fp = fromPos.clone(), tp = toPos.clone(), ft = fromTgt.clone(), tt2 = toTgt.clone();
  (function step() {
    const k = Math.min((performance.now()-t0)/ms, 1);
    const e = 1-Math.pow(1-k,3);
    camera.position.lerpVectors(fp, tp, e);
    controls.target.lerpVectors(ft, tt2, e);
    controls.update();
    if (k < 1) requestAnimationFrame(step);
  })();
}

// ── camera helpers ──────────────────────────────────────────────────────────────────────────────
function fitView() {
  if (!nodesMesh) return;
  const box  = new THREE.Box3().setFromObject(nodesMesh);
  const ctr  = box.getCenter(new THREE.Vector3());
  const sz   = box.getSize(new THREE.Vector3());
  const dist = (Math.max(sz.x, sz.y, sz.z)/2) / Math.tan(camera.fov*Math.PI/360) * 1.3;
  animCam(camera.position.clone(), ctr.clone().setZ(ctr.z+dist), controls.target.clone(), ctr, 600);
}

function zoomBy(f) {
  const d = camera.position.clone().sub(controls.target);
  d.multiplyScalar(1/f);
  animCam(camera.position.clone(), controls.target.clone().add(d), controls.target.clone(), controls.target.clone(), 300);
}

// ── view switching ──────────────────────────────────────────────────────────────────────────────
function switchViewFn(v) {
  if (v===view) return;
  view = v;
  ['galaxy','services','clusters'].forEach(id =>
    document.getElementById('btn-'+id).classList.toggle('active', id===v));
  const fade = document.getElementById('fade');
  fade.classList.add('show');
  setTimeout(() => { buildScene(); fitView(); setTimeout(()=>fade.classList.remove('show'),300); }, 200);
}

function refreshScene() { if (view==='galaxy'||view==='clusters') buildScene(); }

// ── service filter ──────────────────────────────────────────────────────────────────────────────
function toggleSvc(id) {
  activeSvcs.has(id) ? activeSvcs.delete(id) : activeSvcs.add(id);
  document.getElementById('chip-'+id)?.classList.toggle('off', !activeSvcs.has(id));
  const leg = document.getElementById('leg-'+id);
  if (leg) leg.style.opacity = activeSvcs.has(id) ? '1' : '0.3';
  refreshScene();
}

// ── search ────────────────────────────────────────────────────────────────────────────────────
function onSearchFn(e) {
  searchStr = e.target.value.trim().toLowerCase();
  document.getElementById('search-clear').style.display = searchStr ? 'block' : 'none';
  if (!searchStr || !nodesMesh) return;
  const n = G.module_nodes.find(n => n.id.toLowerCase().includes(searchStr));
  if (!n) return;
  const tgt = new THREE.Vector3(n.x||0, n.y||0, n.z||0);
  animCam(camera.position.clone(), tgt.clone().setZ(tgt.z+250), controls.target.clone(), tgt, 600);
  const vis = nodesMesh.userData.nodes.find(m => m.id===n.id);
  if (vis && vis._idx!=null) {
    origColors.set(vis._idx, nodeHex(vis, view==='clusters'));
    nodesMesh.setColorAt(vis._idx, _col.set('#ffd32a'));
    nodesMesh.instanceColor.needsUpdate = true;
  }
}
function clearSearchFn() {
  document.getElementById('search').value=''; searchStr='';
  document.getElementById('search-clear').style.display='none';
}

// ── particles toggle ──────────────────────────────────────────────────────────────────────────────
function togglePtFn() {
  particlesOn = !particlesOn;
  document.getElementById('ptbtn').style.color = particlesOn ? 'var(--accent)' : 'var(--muted)';
  if (ptsMesh) ptsMesh.visible = particlesOn;
}

// ── tooltip / detail ──────────────────────────────────────────────────────────────────────────────
const tt = document.getElementById('tt');
const fmt = n => n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'k':String(n);
function showTT(e, node) {
  document.getElementById('tt-name').textContent = node.id;
  document.getElementById('tt-rows').innerHTML =
    `<b>Service</b> ${node.svc||node.id}<br><b>Cluster</b> ${node.clu||'—'}<br>`+
    `<b>Functions</b> ${node.fn!=null?fmt(node.fn):(node.mods?node.mods+' mods':'—')}<br>`+
    (node.purpose?`<i style="color:#8892b0;font-size:10px">${node.purpose.slice(0,80)}</i>`:'');
  tt.style.display='block'; moveTT(e);
}
function moveTT(e) {
  tt.style.left=Math.min(e.clientX+16,window.innerWidth-280)+'px';
  tt.style.top=Math.max(e.clientY-8,60)+'px';
}
function hideTT() { tt.style.display='none'; }

function showDetail(node) {
  document.getElementById('detail-box').style.display='block';
  document.getElementById('det-name').textContent = node.id;
  document.getElementById('det-svc').textContent  = node.svc||node.id;
  document.getElementById('det-clu').textContent  = node.clu||'—';
  document.getElementById('det-fn').textContent   = node.fn!=null?fmt(node.fn)+' functions':(node.mods||'—');
  document.getElementById('det-deg').textContent  = node.deg!=null?node.deg:'—';
  const p = document.getElementById('det-purpose');
  p.textContent = node.purpose||''; p.style.display = node.purpose?'block':'none';
}

// ── UI builders ─────────────────────────────────────────────────────────────────────────────────
function buildStats() {
  const S = G.stats;
  document.getElementById('sc-symbols').textContent = fmt(S.symbols);
  document.getElementById('sc-modules').textContent = fmt(S.modules);
  document.getElementById('sc-edges').textContent   = fmt(S.import_edges);
  document.getElementById('sc-cross').textContent   = fmt(S.cross_svc);
  document.getElementById('stat-ticker').textContent=
    `${S.services} services · ${fmt(S.modules)} modules · ${fmt(S.import_edges)} imports`;
  document.getElementById('fps-nodes').textContent = fmt(S.modules);
  document.getElementById('fps-links').textContent = fmt(S.import_edges);
  document.getElementById('fps-val').textContent   = '—';
}
function buildChips() {
  const row = document.getElementById('chip-row');
  G.service_nodes.forEach(sn => {
    const c = document.createElement('div');
    c.className='chip'; c.id='chip-'+sn.id;
    c.style.cssText=`border-color:${sn.col};background:${sn.col}22;color:${sn.col}`;
    c.textContent = sn.id.replace('euler-api-','').replace('euler-','');
    c.title=sn.id; c.onclick=()=>toggleSvc(sn.id); row.appendChild(c);
  });
}
function buildLegend() {
  const div = document.getElementById('legend-list');
  G.service_nodes.slice().sort((a,b)=>b.fn-a.fn).forEach(sn=>{
    const row=document.createElement('div');
    row.className='leg-row'; row.id='leg-'+sn.id;
    row.innerHTML=`<div class="leg-dot" style="background:${sn.col}"></div>
      <span class="leg-name">${sn.id.replace('euler-api-','').replace('euler-','')}</span>
      <span class="leg-count">${fmt(sn.fn)} fns</span>`;
    row.onclick=()=>toggleSvc(sn.id); div.appendChild(row);
  });
}

// ── live slider handlers ───────────────────────────────────────────────────────
window.setNodeSize = v => {
  nodeSizeMult = parseFloat(v);
  document.getElementById('size-val').textContent = parseFloat(v).toFixed(1);
  if (!nodesMesh) return;
  const dummy = new THREE.Object3D();
  nodesMesh.userData.nodes.forEach((n, i) => {
    dummy.position.set(n.x||0, n.y||0, n.z||0);
    dummy.scale.setScalar((n._r||2) * nodeSizeMult);
    dummy.updateMatrix();
    nodesMesh.setMatrixAt(i, dummy.matrix);
  });
  nodesMesh.instanceMatrix.needsUpdate = true;
};
window.setEdgeOpacity = v => {
  edgeOpacity = parseFloat(v);
  document.getElementById('edge-val').textContent = parseFloat(v).toFixed(2);
  [linkLines, ccLines].forEach(l => {
    if (!l) return;
    l.material.opacity = l.material.userData.baseOpacity * (edgeOpacity / 0.18);
  });
};
window.setRotation = v => {
  const spd = parseFloat(v);
  document.getElementById('rot-val').textContent = parseFloat(v).toFixed(1);
  controls.autoRotate = spd > 0;
  controls.autoRotateSpeed = spd;
};

// ── expose to HTML onclick attrs ──────────────────────────────────────────────────────────────────────────
window.switchView      = switchViewFn;
window.onSearch        = onSearchFn;
window.clearSearch     = clearSearchFn;
window.zoomBy          = zoomBy;
window.fitView         = fitView;
window.toggleParticles = togglePtFn;

boot().catch(err => {
  document.getElementById('loading-msg').textContent = 'Error: ' + err.message;
  console.error(err);
});
</script>
</body>
</html>"""

OUT_HTML.write_text(HTML, encoding="utf-8")

sz = OUT_HTML.stat().st_size
print(f"\n{'═'*62}")
print(f"  Mindmap → {OUT_HTML}")
print(f"  Size: {sz//1024} KB   (self-contained, no server needed)")
print(f"{'═'*62}")
print(f"""
  Views
  ─────
  Galaxy    All {MG.number_of_nodes():,} modules · live WebGL force physics
            Orange particles = cross-service flows
            Blue  particles  = co-change pairs

  Services  12 service supernodes · weighted import edges
            Node size ∝ function count

  Clusters  {len(cluster_summaries)} LLM-named cluster bubbles

  Controls
  ────────
  Chips     Filter by service (top bar)
  Search    Zoom to module by name
  ⊙         Fit all nodes in view
  ⚡        Toggle animated particle flows
  Click     Pin detail panel (right)
""")
