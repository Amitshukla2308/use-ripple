"""
Risk Trending Dashboard — visualize guardian_history.jsonl

Generates a self-contained HTML dashboard showing:
- Risk score over time (line chart)
- Component breakdown (stacked area)
- Verdict distribution (donut)
- Recent analyses table

Usage:
  python3 tools/risk_dashboard.py [--artifact-dir DIR] [--serve PORT]
  python3 tools/risk_dashboard.py --artifact-dir /path/to/artifacts --serve 8080
"""
import argparse, json, os, pathlib, sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

def load_history(artifact_dir: pathlib.Path) -> list[dict]:
    history_file = artifact_dir / "guardian_history.jsonl"
    if not history_file.exists():
        print(f"No history file at {history_file}", file=sys.stderr)
        return []
    entries = []
    with open(history_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def generate_html(entries: list[dict]) -> str:
    # Prepare data for charts
    timestamps = []
    risk_scores = []
    blast_scores = []
    coverage_scores = []
    reviewer_scores = []
    service_scores = []
    verdicts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    table_rows = []

    for e in entries:
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        timestamps.append(ts)

        risk = e.get("risk_score", 0)
        risk_scores.append(risk)

        components = e.get("risk_components", {})
        blast_scores.append(components.get("blast_radius", 0))
        coverage_scores.append(components.get("coverage_gap", 0))
        reviewer_scores.append(components.get("reviewer_concentration", 0))
        service_scores.append(components.get("service_spread", 0))

        verdict = e.get("verdict", "UNKNOWN")
        if verdict in verdicts:
            verdicts[verdict] += 1

        modules = e.get("modules", [])
        mod_str = ", ".join(m.split("::")[-1] for m in modules[:3])
        if len(modules) > 3:
            mod_str += f" +{len(modules)-3}"

        level = e.get("risk_level", "")
        color = {"LOW": "#22c55e", "MEDIUM": "#eab308", "HIGH": "#f97316", "CRITICAL": "#ef4444"}.get(level, "#888")

        table_rows.append(f"""<tr>
            <td>{ts}</td>
            <td>{mod_str}</td>
            <td style="color:{color};font-weight:bold">{risk}/100 ({level})</td>
            <td>{verdict}</td>
        </tr>""")

    table_rows.reverse()  # newest first

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HyperRetrieval Risk Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 8px; color: #f8fafc; }}
  .subtitle {{ color: #94a3b8; margin-bottom: 24px; font-size: 0.875rem; }}
  .grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 20px; }}
  .card {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }}
  .card h2 {{ font-size: 1rem; color: #94a3b8; margin-bottom: 12px; }}
  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }}
  .stat {{ background: #1e293b; border-radius: 12px; padding: 16px; border: 1px solid #334155; text-align: center; }}
  .stat .value {{ font-size: 2rem; font-weight: bold; }}
  .stat .label {{ color: #94a3b8; font-size: 0.75rem; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; color: #94a3b8; font-weight: 500; padding: 8px 12px; border-bottom: 1px solid #334155; font-size: 0.75rem; text-transform: uppercase; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; font-size: 0.875rem; }}
  .empty {{ text-align: center; color: #64748b; padding: 40px; }}
  canvas {{ max-height: 250px; }}
</style>
</head>
<body>
<h1>HyperRetrieval Guardian — Risk Dashboard</h1>
<p class="subtitle">Change risk trending from guardian_history.jsonl &bull; {len(entries)} analyses recorded</p>

<div class="stats">
  <div class="stat">
    <div class="value" style="color:#60a5fa">{len(entries)}</div>
    <div class="label">Total Analyses</div>
  </div>
  <div class="stat">
    <div class="value" style="color:{('#22c55e' if entries and sum(risk_scores)/len(risk_scores) < 30 else '#eab308' if entries and sum(risk_scores)/len(risk_scores) < 60 else '#ef4444')}">{round(sum(risk_scores)/max(len(risk_scores),1))}</div>
    <div class="label">Avg Risk Score</div>
  </div>
  <div class="stat">
    <div class="value" style="color:#22c55e">{verdicts['PASS']}</div>
    <div class="label">PASS</div>
  </div>
  <div class="stat">
    <div class="value" style="color:#ef4444">{verdicts['FAIL']}</div>
    <div class="label">FAIL</div>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>Risk Score Over Time</h2>
    <canvas id="riskChart"></canvas>
  </div>
  <div class="card">
    <h2>Verdict Distribution</h2>
    <canvas id="verdictChart"></canvas>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>Risk Components Over Time</h2>
    <canvas id="componentChart"></canvas>
  </div>
  <div class="card">
    <h2>Component Averages</h2>
    <canvas id="radarChart"></canvas>
  </div>
</div>

<div class="card" style="margin-top:20px">
  <h2>Recent Analyses</h2>
  {'<table><thead><tr><th>Time</th><th>Modules</th><th>Risk</th><th>Verdict</th></tr></thead><tbody>' + ''.join(table_rows) + '</tbody></table>' if table_rows else '<div class="empty">No analyses yet. Run pr_analyzer --mode guardian to generate data.</div>'}
</div>

<script>
const labels = {json.dumps(timestamps)};
const riskScores = {json.dumps(risk_scores)};
const blastScores = {json.dumps(blast_scores)};
const coverageScores = {json.dumps(coverage_scores)};
const reviewerScores = {json.dumps(reviewer_scores)};
const serviceScores = {json.dumps(service_scores)};

// Risk Score Line Chart
new Chart(document.getElementById('riskChart'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [{{
      label: 'Risk Score',
      data: riskScores,
      borderColor: '#60a5fa',
      backgroundColor: 'rgba(96,165,250,0.1)',
      fill: true,
      tension: 0.3,
      pointRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    scales: {{
      y: {{ min: 0, max: 100, grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }},
      x: {{ grid: {{ color: '#1e293b' }}, ticks: {{ color: '#94a3b8', maxRotation: 45 }} }}
    }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});

// Verdict Donut
new Chart(document.getElementById('verdictChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['PASS', 'WARN', 'FAIL'],
    datasets: [{{
      data: [{verdicts['PASS']}, {verdicts['WARN']}, {verdicts['FAIL']}],
      backgroundColor: ['#22c55e', '#eab308', '#ef4444'],
      borderWidth: 0,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#94a3b8' }} }} }}
  }}
}});

// Component Stacked Area
new Chart(document.getElementById('componentChart'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{ label: 'Blast Radius', data: blastScores, borderColor: '#f97316', backgroundColor: 'rgba(249,115,22,0.2)', fill: true, tension: 0.3 }},
      {{ label: 'Coverage Gap', data: coverageScores, borderColor: '#a855f7', backgroundColor: 'rgba(168,85,247,0.2)', fill: true, tension: 0.3 }},
      {{ label: 'Reviewer Risk', data: reviewerScores, borderColor: '#eab308', backgroundColor: 'rgba(234,179,8,0.2)', fill: true, tension: 0.3 }},
      {{ label: 'Service Spread', data: serviceScores, borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,0.2)', fill: true, tension: 0.3 }},
    ]
  }},
  options: {{
    responsive: true,
    scales: {{
      y: {{ min: 0, max: 100, grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }},
      x: {{ grid: {{ color: '#1e293b' }}, ticks: {{ color: '#94a3b8', maxRotation: 45 }} }}
    }},
    plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#94a3b8' }} }} }}
  }}
}});

// Radar Chart for component averages
const avg = (arr) => arr.length ? arr.reduce((a,b) => a+b, 0) / arr.length : 0;
new Chart(document.getElementById('radarChart'), {{
  type: 'radar',
  data: {{
    labels: ['Blast Radius', 'Coverage Gap', 'Reviewer Risk', 'Service Spread'],
    datasets: [{{
      label: 'Average',
      data: [avg(blastScores), avg(coverageScores), avg(reviewerScores), avg(serviceScores)],
      borderColor: '#60a5fa',
      backgroundColor: 'rgba(96,165,250,0.2)',
    }}]
  }},
  options: {{
    responsive: true,
    scales: {{ r: {{ min: 0, max: 100, grid: {{ color: '#334155' }}, angleLines: {{ color: '#334155' }}, pointLabels: {{ color: '#94a3b8' }}, ticks: {{ color: '#94a3b8', backdropColor: 'transparent' }} }} }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Guardian Risk Trending Dashboard")
    parser.add_argument("--artifact-dir", type=pathlib.Path,
                        default=pathlib.Path(os.environ.get("ARTIFACT_DIR", "artifacts")))
    parser.add_argument("--serve", type=int, default=0, help="Serve on this port")
    parser.add_argument("--output", type=pathlib.Path, default=None,
                        help="Output HTML file (default: artifact_dir/risk_dashboard.html)")
    args = parser.parse_args()

    entries = load_history(args.artifact_dir)
    html = generate_html(entries)

    out_path = args.output or (args.artifact_dir / "risk_dashboard.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    print(f"Dashboard written to {out_path} ({len(entries)} entries)")

    if args.serve:
        os.chdir(out_path.parent)

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, format, *a):
                pass

        server = HTTPServer(("0.0.0.0", args.serve), Handler)
        print(f"Serving at http://localhost:{args.serve}/{out_path.name}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
