"""Read-only Solar Assistant MVP for Home Assistant OS."""
from __future__ import annotations

import json
import os
import re
import statistics
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from time import sleep

CORE_API = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
OPTIONS_PATH = Path("/data/options.json")
SOLAR_HINTS = {"solar", "pv", "photovoltaic", "inverter", "sunpower", "enphase"}
lock = Lock()
cache = {"generated_at": None, "summary": {}, "assets": [], "findings": [], "error": None}
breaches = {}
ollama_cache = {"signature": None, "analysis": None}


def options():
    cfg = {
        "stale_after_minutes": 30, "low_production_threshold_w": 100,
        "minimum_solar_elevation": 10, "minimum_peer_power_w": 75,
        "peer_watch_ratio": 0.85, "peer_critical_ratio": 0.50,
        "anomaly_persistence_minutes": 30, "scan_interval_minutes": 5,
        "ollama_url": "", "ollama_model": "qwen3:8b",
    }
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


def parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def watts_for(state):
    attrs = state.get("attributes", {})
    unit = attrs.get("unit_of_measurement", "")
    if attrs.get("device_class") != "power" and unit not in {"W", "kW"}:
        return None
    value = parse_float(state.get("state"))
    return None if value is None else value * (1000 if unit == "kW" else 1)


def age_minutes(state, now):
    changed = state.get("last_updated") or state.get("last_changed")
    if not changed:
        return None
    try:
        stamp = datetime.fromisoformat(changed.replace("Z", "+00:00"))
        return max(0, (now - stamp).total_seconds() / 60)
    except ValueError:
        return None


def daylight_context(states, cfg):
    sun = next((state for state in states if state.get("entity_id") == "sun.sun"), {})
    elevation = parse_float(sun.get("attributes", {}).get("elevation"))
    daylight = sun.get("state") == "above_horizon"
    if elevation is not None:
        daylight = daylight and elevation >= cfg["minimum_solar_elevation"]
    return {"daylight": daylight, "solar_elevation": elevation}


def is_inverter_power(state):
    attrs = state.get("attributes", {})
    text = " ".join((str(state.get("entity_id", "")), str(attrs.get("friendly_name", "")))).lower()
    unit = attrs.get("unit_of_measurement", "")
    power_measurement = attrs.get("device_class") == "power" or unit in {"W", "kW"}
    placeholder = bool(re.search(r"(^|[._ /-])n[._ /-]?a($|[._ /-])", text))
    return power_measurement and "inverter" in text and not placeholder and not any(
        term in text for term in ("lifetime", "total", "array", "meter", "mppt")
    )


def is_solar(state):
    entity_id = str(state.get("entity_id", ""))
    domain = entity_id.partition(".")[0]
    if domain not in {"sensor", "binary_sensor"}:
        return False
    attrs = state.get("attributes", {})
    text = " ".join(str(v).lower() for v in (
        entity_id, attrs.get("friendly_name", ""), attrs.get("device_class", "")
    ))
    tokens = set(re.findall(r"[a-z0-9]+", text))
    solar_match = bool(tokens & SOLAR_HINTS) or any(token.startswith("pvs") for token in tokens)
    if not solar_match:
        return False
    excluded = ("cost", "compensation", "price", "currency", "automation", "alert")
    return not any(term in text for term in excluded)


def recommendation_for(status, symptoms):
    text = " ".join(symptoms).lower()
    if "unavailable" in text:
        return "Check the inverter integration and PVS communication first. If peers are online, inspect this unit's connection; do not access the roof without a qualified technician."
    if "stale" in text:
        return "Refresh the integration and verify the inverter gateway is reporting. Investigate networking only if other inverters are also stale."
    if status == "critical":
        return "Compare this panel with adjacent panels, check for visible shade or debris from the ground, and arrange a qualified electrical inspection if the deficit persists."
    if status == "degraded":
        return "Monitor through another clear-sky period. Check for repeatable shade or debris and escalate if peer performance remains low."
    if symptoms:
        return "Continue monitoring until the persistence window completes; no physical action is recommended yet."
    return "No action required."


def assess(state, cfg, context, peer_median, now):
    score, symptoms = 100, []
    value = str(state.get("state", "")).lower()
    if value in {"unknown", "unavailable", "none", ""}:
        return 20, ["Telemetry unavailable"], None, None, None
    watts = watts_for(state)
    age = age_minutes(state, now)
    if age is not None and age > cfg["stale_after_minutes"] and is_inverter_power(state) and context["daylight"]:
        score -= 35
        symptoms.append("Telemetry stale for %d minutes" % int(age))

    peer_ratio = None
    if watts is not None and context["daylight"] and peer_median and is_inverter_power(state):
        peer_ratio = watts / peer_median
        key = state["entity_id"]
        if peer_ratio < cfg["peer_watch_ratio"] and peer_median >= cfg["minimum_peer_power_w"]:
            started = breaches.setdefault(key, now)
            duration = (now - started).total_seconds() / 60
            if duration >= cfg["anomaly_persistence_minutes"]:
                score -= 65 if peer_ratio <= cfg["peer_critical_ratio"] else 35
                symptoms.append("Producing %d%% of peer median for %d minutes" % (round(peer_ratio * 100), int(duration)))
            else:
                score -= 10
                symptoms.append("Low peer performance under observation (%d%%)" % round(peer_ratio * 100))
        else:
            breaches.pop(key, None)
    elif watts is not None and context["daylight"] and peer_median is None and watts < cfg["low_production_threshold_w"]:
        score -= 10
        symptoms.append("Production below fallback threshold")
    else:
        breaches.pop(state.get("entity_id"), None)
    return max(0, score), symptoms, peer_ratio, watts, age


def scan():
    cfg, assets, findings = options(), [], []
    states = api_get("/states")
    now = datetime.now(timezone.utc)
    context = daylight_context(states, cfg)
    panel_states = [state for state in states if is_solar(state) and is_inverter_power(state)]
    peer_values = [watts_for(state) for state in panel_states]
    peer_values = [value for value in peer_values if value is not None and value >= 0]
    peer_median = statistics.median(peer_values) if len(peer_values) >= 3 else None
    for state in panel_states:
        score, symptoms, peer_ratio, watts, age = assess(state, cfg, context, peer_median, now)
        status = "critical" if score < 40 else "degraded" if score < 70 else "watch" if score < 90 else "healthy"
        asset = {
            "entity_id": state["entity_id"],
            "name": state.get("attributes", {}).get("friendly_name", state["entity_id"]),
            "state": state.get("state"),
            "unit": state.get("attributes", {}).get("unit_of_measurement"),
            "health_score": score,
            "status": status,
            "symptoms": symptoms,
            "power_w": round(watts, 1) if watts is not None else None,
            "peer_ratio": round(peer_ratio, 3) if peer_ratio is not None else None,
            "age_minutes": round(age, 1) if age is not None else None,
            "recommendation": recommendation_for(status, symptoms),
        }
        assets.append(asset)
        if status != "healthy":
            findings.append({
                "entity_id": state["entity_id"], "severity": status,
                "symptoms": symptoms, "recommendation": recommendation_for(status, symptoms),
            })
    average = round(sum(a["health_score"] for a in assets) / len(assets)) if assets else 0
    return {
        "generated_at": now.isoformat(),
        "summary": {
            "health_score": average,
            "assets": len(assets),
            "healthy": sum(a["status"] == "healthy" for a in assets),
            "attention": sum(a["status"] != "healthy" for a in assets),
            "daylight": context["daylight"],
            "solar_elevation": context["solar_elevation"],
            "peer_median_w": round(peer_median, 1) if peer_median is not None else None,
        },
        "assets": sorted(assets, key=lambda a: a["health_score"]),
        "findings": findings,
        "error": None,
    }


def ollama_analysis(result, cfg):
    findings = result.get("findings", [])
    if not findings or not cfg.get("ollama_url"):
        return None
    signature = json.dumps(findings, sort_keys=True)
    if ollama_cache["signature"] == signature:
        return ollama_cache["analysis"]
    prompt = (
        "You are a solar monitoring assistant. Summarize these deterministic Home Assistant "
        "findings in at most 3 short sentences. Do not invent causes; label possible causes as "
        "possibilities and recommend a safe inspection step. Findings: " + signature
    )
    request = urllib.request.Request(
        cfg["ollama_url"].rstrip("/") + "/api/generate",
        data=json.dumps({"model": cfg["ollama_model"], "prompt": prompt, "stream": False}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            analysis = json.load(response).get("response")
    except Exception as exc:
        analysis = "Ollama analysis unavailable: %s" % exc
    ollama_cache.update(signature=signature, analysis=analysis)
    return analysis


def refresh():
    global cache
    try:
        cfg = options()
        result = scan()
        result["analysis"] = ollama_analysis(result, cfg)
    except Exception as exc:
        result = dict(cache)
        result.update(error=str(exc), generated_at=datetime.now(timezone.utc).isoformat())
    with lock:
        cache = result
    return result


def scanner_loop():
    while True:
        sleep(max(1, options()["scan_interval_minutes"]) * 60)
        refresh()


PAGE = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'>
<title>Solar Assistant</title><style>:root{color-scheme:dark;font-family:system-ui;background:#101214;color:#e8eaed}body{margin:0;padding:24px}header{display:flex;justify-content:space-between;align-items:center;gap:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}.card{background:#1c1f22;border:1px solid #34383d;border-radius:12px;padding:18px;margin:14px 0}.metric{font-size:2rem;font-weight:700}.attention{border-left:5px solid #ff7043}.muted{color:#9aa0a6}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #34383d}.healthy{color:#4caf50}.watch{color:#ffc107}.degraded,.critical{color:#ff7043}button{background:#03a9f4;border:0;border-radius:8px;color:#fff;padding:10px 14px}@media(max-width:700px){body{padding:12px}table{font-size:.85rem}th:nth-child(2),td:nth-child(2){display:none}}</style></head>
<body><header><div><h1>Solar Assistant</h1><div class=muted>Daylight-aware, peer-relative solar health</div></div><button onclick='load(true)'>Scan now</button></header><div id=error></div><div class=grid id=summary></div><section id=attention></section><div class=card><h2>Solar panels</h2><table><thead><tr><th>Panel inverter</th><th>State</th><th>Health</th><th>Peer performance</th><th>Finding and recommended action</th></tr></thead><tbody id=assets></tbody></table></div>
<script>const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function load(force=false){let r=await fetch(force?'api/scan':'api/status',{method:force?'POST':'GET'}),d=await r.json();error.innerHTML=d.error?'<div class="card critical">'+esc(d.error)+'</div>':'';let s=d.summary||{},sun=s.daylight?'Solar elevation':'Monitoring paused';summary.innerHTML=[['System health',s.health_score??0],['Panels needing attention',s.attention??0],['Peer median',(s.peer_median_w??'—')+' W'],[sun,s.solar_elevation==null?'—':s.solar_elevation+'° above horizon']].map(x=>'<div class=card><div class=muted>'+esc(x[0])+'</div><div class=metric>'+esc(x[1])+'</div></div>').join('');let fs=d.findings||[];attention.innerHTML=fs.length?'<div class="card attention"><h2>Attention required</h2>'+fs.map(f=>'<p><strong>'+esc(f.entity_id)+'</strong> — '+esc(f.symptoms.join(', '))+'<br><span class=muted>Recommended: '+esc(f.recommendation)+'</span></p>').join('')+(d.analysis?'<p><strong>Local AI assessment:</strong> '+esc(d.analysis)+'</p>':'')+'</div>':'<div class=card><h2>No persistent panel anomalies</h2><div class=muted>Production comparisons run only during useful daylight.</div></div>';assets.innerHTML=(d.assets||[]).map(a=>'<tr><td>'+esc(a.name)+'<br><span class=muted>'+esc(a.entity_id)+'</span></td><td>'+esc(a.state)+' '+esc(a.unit||'')+'</td><td class='+esc(a.status)+'>'+esc(a.health_score)+' · '+esc(a.status)+'</td><td>'+esc(a.peer_ratio==null?'—':Math.round(a.peer_ratio*100)+'%')+'</td><td>'+esc(a.symptoms.join(', ')||'No active finding')+'</td></tr>').join('')}load();setInterval(load,60000)</script></body></html>"""


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
    Thread(target=scanner_loop, daemon=True).start()
    print("Solar Assistant listening on port 8099", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8099), Handler).serve_forever()
