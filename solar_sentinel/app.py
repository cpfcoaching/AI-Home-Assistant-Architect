"""Read-only Solar Sentinel MVP for Home Assistant OS."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

CORE_API = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
OPTIONS_PATH = Path("/data/options.json")
SOLAR_HINTS = ("solar", "pv", "photovoltaic", "inverter", "pvs", "sunpower", "enphase")
lock = Lock()
cache = {"generated_at": None, "summary": {}, "assets": [], "findings": [], "error": None}


def options():
    cfg = {"stale_after_minutes": 30, "low_production_threshold_w": 100}
    try:
        cfg.update(json.loads(OPTIONS_PATH.read_text()))
    except (OSError, ValueError):
        pass
    return cfg


def api_get(path):
    req = urllib.request.Request(
        CORE_API + path,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def is_solar(state):
    attrs = state.get("attributes", {})
    text = " ".join(str(v).lower() for v in (
        state.get("entity_id", ""), attrs.get("friendly_name", ""), attrs.get("device_class", "")
    ))
    return any(hint in text for hint in SOLAR_HINTS)


def assess(state, cfg):
    score, symptoms = 100, []
    value = str(state.get("state", "")).lower()
    attrs = state.get("attributes", {})
    if value in {"unknown", "unavailable", "none", ""}:
        return 20, ["Telemetry unavailable"]
    changed = state.get("last_updated") or state.get("last_changed")
    if changed:
        try:
            stamp = datetime.fromisoformat(changed.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - stamp).total_seconds() / 60
            if age > cfg["stale_after_minutes"]:
                score -= 35
                symptoms.append("Telemetry stale for %d minutes" % int(age))
        except ValueError:
            pass
    unit = attrs.get("unit_of_measurement", "")
    if attrs.get("device_class") == "power" or unit in {"W", "kW"}:
        try:
            watts = float(value) * (1000 if unit == "kW" else 1)
            if watts < cfg["low_production_threshold_w"]:
                score -= 10
                symptoms.append("Production below configured threshold")
        except ValueError:
            score -= 15
            symptoms.append("Non-numeric production value")
    return max(0, score), symptoms


def scan():
    cfg, assets, findings = options(), [], []
    for state in api_get("/states"):
        if not is_solar(state):
            continue
        score, symptoms = assess(state, cfg)
        status = "critical" if score < 40 else "degraded" if score < 70 else "watch" if score < 90 else "healthy"
        asset = {
            "entity_id": state["entity_id"],
            "name": state.get("attributes", {}).get("friendly_name", state["entity_id"]),
            "state": state.get("state"),
            "unit": state.get("attributes", {}).get("unit_of_measurement"),
            "health_score": score,
            "status": status,
            "symptoms": symptoms,
        }
        assets.append(asset)
        if symptoms:
            findings.append({"entity_id": state["entity_id"], "severity": status, "symptoms": symptoms})
    average = round(sum(a["health_score"] for a in assets) / len(assets)) if assets else 0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "health_score": average,
            "assets": len(assets),
            "healthy": sum(a["status"] == "healthy" for a in assets),
            "attention": sum(a["status"] != "healthy" for a in assets),
        },
        "assets": sorted(assets, key=lambda a: a["health_score"]),
        "findings": findings,
        "error": None,
    }


def refresh():
    global cache
    try:
        result = scan()
    except Exception as exc:
        result = dict(cache)
        result.update(error=str(exc), generated_at=datetime.now(timezone.utc).isoformat())
    with lock:
        cache = result
    return result


PAGE = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'>
<title>Solar Sentinel</title><style>:root{color-scheme:dark;font-family:system-ui;background:#101214;color:#e8eaed}body{margin:0;padding:24px}header{display:flex;justify-content:space-between;align-items:center}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.card{background:#1c1f22;border:1px solid #34383d;border-radius:12px;padding:18px;margin:14px 0}.metric{font-size:2rem;font-weight:700}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #34383d}.healthy{color:#4caf50}.watch{color:#ffc107}.degraded,.critical{color:#ff7043}button{background:#03a9f4;border:0;border-radius:8px;color:#fff;padding:10px 14px}small{color:#9aa0a6}</style></head>
<body><header><div><h1>Solar Sentinel</h1><small>Read-only solar health and inventory</small></div><button onclick='load(true)'>Scan now</button></header><div id=error></div><div class=grid id=summary></div><div class=card><h2>Solar assets</h2><table><thead><tr><th>Asset</th><th>State</th><th>Health</th><th>Finding</th></tr></thead><tbody id=assets></tbody></table></div>
<script>const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function load(force=false){let r=await fetch(force?'api/scan':'api/status',{method:force?'POST':'GET'}),d=await r.json();error.innerHTML=d.error?'<div class="card critical">'+esc(d.error)+'</div>':'';let s=d.summary||{};summary.innerHTML=[['System health',s.health_score||0],['Discovered assets',s.assets||0],['Healthy',s.healthy||0],['Need attention',s.attention||0]].map(x=>'<div class=card><small>'+esc(x[0])+'</small><div class=metric>'+esc(x[1])+'</div></div>').join('');assets.innerHTML=(d.assets||[]).map(a=>'<tr><td>'+esc(a.name)+'<br><small>'+esc(a.entity_id)+'</small></td><td>'+esc(a.state)+' '+esc(a.unit||'')+'</td><td class='+esc(a.status)+'>'+esc(a.health_score)+' · '+esc(a.status)+'</td><td>'+esc(a.symptoms.join(', ')||'No active finding')+'</td></tr>').join('')}load();setInterval(load,300000)</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, payload, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = self.path.rstrip("/")
        if path.endswith("/health"):
            self.reply(200, b'{"status":"ok"}', "application/json")
        elif path.endswith("/api/status"):
            with lock:
                payload = json.dumps(cache).encode()
            self.reply(200, payload, "application/json")
        else:
            self.reply(200, PAGE.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        if self.path.rstrip("/").endswith("/api/scan"):
            self.reply(200, json.dumps(refresh()).encode(), "application/json")
        else:
            self.reply(404, b'{"error":"not found"}', "application/json")

    def log_message(self, fmt, *args):
        print("%s %s" % (self.client_address[0], fmt % args), flush=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("SUPERVISOR_TOKEN is required")
    refresh()
    print("Solar Sentinel listening on port 8099", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8099), Handler).serve_forever()
