"""Read-only Home Assistant Energy configuration troubleshooter."""
import json, os
from pathlib import Path
from aiohttp import ClientSession, WSMsgType, web

TOKEN=os.environ.get("SUPERVISOR_TOKEN","")
REST="http://supervisor/core/api"
WS="ws://supervisor/core/websocket"
OPTIONS=Path("/data/options.json")

def options():
    cfg={"import_rate_per_kwh":0,"export_rate_per_kwh":0}
    try: cfg.update(json.loads(OPTIONS.read_text()))
    except (OSError,ValueError): pass
    return cfg

async def ws_commands(commands):
    results={}
    async with ClientSession() as session:
        async with session.ws_connect(WS,timeout=15) as socket:
            await socket.receive_json()
            await socket.send_json({"type":"auth","access_token":TOKEN})
            auth=await socket.receive_json()
            if auth.get("type")!="auth_ok": raise RuntimeError("Home Assistant WebSocket authentication failed")
            for idx,(name,payload) in enumerate(commands.items(),1):
                await socket.send_json({"id":idx,**payload})
                while True:
                    msg=await socket.receive()
                    if msg.type!=WSMsgType.TEXT: raise RuntimeError("Home Assistant WebSocket closed")
                    data=json.loads(msg.data)
                    if data.get("id")==idx:
                        results[name]=data.get("result") if data.get("success") else {"error":data.get("error")}
                        break
    return results

def source_id(source, direction):
    keys = ("stat_energy_from", "entity_energy_from") if direction == "import" else ("stat_energy_to", "entity_energy_to")
    return str(next((source.get(key) for key in keys if source.get(key)), ""))


def source_family(identifier):
    value = identifier.lower()
    if "smarthub" in value:
        return "NOVEC SmartHub"
    if "pvs" in value or "power_meter" in value:
        return "PVS local meter"
    return "Other" if identifier else "Not configured"


def validation_issues(value, path=""):
    """Return only meaningful validation leaves; ignore empty nested result slots."""
    if value in (None, False, "", [], {}):
        return []
    if isinstance(value, dict):
        issues = []
        for key, child in value.items():
            child_path = ("%s.%s" % (path, key)).strip(".")
            issues.extend(validation_issues(child, child_path))
        return issues
    if isinstance(value, list):
        issues = []
        for index, child in enumerate(value):
            issues.extend(validation_issues(child, "%s[%d]" % (path, index)))
        return issues
    return [{"path": path or "validation", "message": str(value)}]


def finding(severity, title, evidence, impact, action):
    return {"severity": severity, "title": title, "evidence": evidence, "impact": impact, "action": action}


def analyze(prefs, stats, validation):
    findings = []
    smarthub = [s for s in stats if "smarthub" in s.get("statistic_id", "").lower()]
    sources = (prefs or {}).get("energy_sources", []) if isinstance(prefs, dict) else []
    grids = [s for s in sources if s.get("type") == "grid"]
    solar = [s for s in sources if s.get("type") == "solar"]
    grid = grids[0] if grids else {}
    imported, exported = source_id(grid, "import"), source_id(grid, "export")

    if not grids:
        findings.append(finding("critical", "No grid source configured", "Energy preferences contain no grid source.",
            "Home Assistant cannot calculate utility import, export, or complete home consumption.",
            "Configure an Electricity grid source in Energy settings."))
    else:
        if not imported:
            findings.append(finding("critical", "Grid import is missing", "No import statistic or entity is selected.",
                "Imported energy and calculated home consumption will be incomplete.",
                "Select a cumulative kWh import sensor."))
        if not exported:
            findings.append(finding("watch", "Grid export is missing", "No export statistic or entity is selected.",
                "Solar sent to the grid will be counted as home consumption.",
                "Select a cumulative kWh export sensor, or leave it empty only if the site cannot export."))
        if imported and exported and source_family(imported) != source_family(exported):
            findings.append(finding("degraded", "Import and export use different meter families",
                "%s for import; %s for export." % (source_family(imported), source_family(exported)),
                "Different update schedules can create implausible home-consumption totals.",
                "Use synchronized import and export counters from the same meter when possible."))

        cost = str(grid.get("entity_energy_from_cost") or "")
        if cost and ("monthly" in cost.lower() or "usage" in cost.lower()):
            findings.append(finding("critical", "Energy usage selected as cost", cost,
                "Home Assistant may interpret kWh as currency and display incorrect costs.",
                "Use a currency-valued total-cost entity, a verified price entity, or disable cost tracking."))
        compensation = str(grid.get("entity_energy_to_compensation") or "")
        if compensation and ("to_home" in compensation.lower() or "import" in compensation.lower()):
            findings.append(finding("critical", "Import cost selected as export compensation", compensation,
                "Export credits will be calculated from the wrong direction.",
                "Use a verified export-compensation entity/rate or disable compensation tracking."))

    if smarthub and any(s.get("statistics_unit_of_measurement") != "kWh" for s in smarthub):
        findings.append(finding("degraded", "Unexpected SmartHub unit",
            "At least one SmartHub energy statistic is not reported in kWh.",
            "It may not be accepted as a cumulative Energy source.",
            "Use a SmartHub statistic whose unit is kWh."))

    issues = validation_issues(validation)
    for issue in issues[:10]:
        findings.append(finding("degraded", "Home Assistant validation issue", issue["path"] + ": " + issue["message"],
            "Home Assistant reported a problem with this Energy source.",
            "Open Energy configuration and verify the referenced source and its units."))

    if not findings:
        findings.append(finding("healthy", "Configuration checks passed",
            "Grid mappings are present, meter families are consistent, and Home Assistant returned no validation issues.",
            "No obvious configuration fault was detected.",
            "No change is recommended. Compare dashboard totals with the physical utility/inverter meters periodically."))

    overview = {
        "status": "critical" if any(f["severity"] == "critical" for f in findings) else
                  "degraded" if any(f["severity"] == "degraded" for f in findings) else
                  "watch" if any(f["severity"] == "watch" for f in findings) else "healthy",
        "grid_sources": len(grids), "solar_sources": len(solar),
        "smarthub_statistics": len(smarthub), "validation_issues": len(issues),
        "import": {"id": imported, "family": source_family(imported)},
        "export": {"id": exported, "family": source_family(exported)},
    }
    return findings, overview, issues

async def audit():
    data=await ws_commands({"prefs":{"type":"energy/get_prefs"},"validation":{"type":"energy/validate"},"stats":{"type":"recorder/list_statistic_ids","statistic_type":"sum"}})
    prefs=data.get("prefs") or {}; stats=data.get("stats") or []
    findings, overview, issues = analyze(prefs, stats, data.get("validation") or {})
    return {
        "read_only": True, "findings": findings, "overview": overview,
        "validation": {"status": "passed" if not issues else "issues_found", "issues": issues},
        "smarthub_statistics": [s for s in stats if "smarthub" in s.get("statistic_id", "").lower()],
        "energy_preferences": prefs, "rates": options(),
    }

PAGE="""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Energy Troubleshooter</title><style>:root{color-scheme:dark;font-family:system-ui;background:#101214;color:#eee}body{padding:24px}.card{background:#1c1f22;border:1px solid #383b40;border-radius:12px;padding:18px;margin:14px 0}.critical{border-left:5px solid #f44336}.degraded{border-left:5px solid #ff9800}.watch{border-left:5px solid #ffc107}.healthy{border-left:5px solid #4caf50}small{color:#aaa}code{word-break:break-all}</style></head><body><h1>Energy Data Troubleshooter</h1><small>SmartHub · Energy preferences · tariffs · read-only</small><div id=out class=card>Running audit…</div><script>const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));fetch('api/audit').then(r=>r.json()).then(d=>{out.className='';out.innerHTML=d.findings.map(f=>'<div class="card '+esc(f.severity)+'"><h3>'+esc(f.title)+'</h3><p>'+esc(f.detail)+'</p></div>').join('')+'<div class=card><h2>SmartHub statistics</h2>'+d.smarthub_statistics.map(s=>'<p><code>'+esc(s.statistic_id)+'</code> · '+esc(s.statistics_unit_of_measurement)+'</p>').join('')+'</div>'}).catch(e=>out.textContent=e)</script></body></html>"""

PAGE_V2="""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'>
<title>Energy Troubleshooter</title><style>:root{color-scheme:dark;font-family:system-ui;background:#101214;color:#eee}body{padding:24px;max-width:1500px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}.card{background:#1c1f22;border:1px solid #383b40;border-radius:12px;padding:18px;margin:14px 0}.metric{font-size:1.8rem;font-weight:700}.critical{border-left:5px solid #f44336}.degraded{border-left:5px solid #ff9800}.watch{border-left:5px solid #ffc107}.healthy{border-left:5px solid #4caf50}.muted{color:#aaa}code{word-break:break-all}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #383b40}button{float:right;background:#03a9f4;color:#fff;border:0;border-radius:8px;padding:10px 14px}</style></head>
<body><button onclick=location.reload()>Run audit again</button><h1>Energy Data Troubleshooter</h1><div class=muted>Validates mappings, units, meter consistency, tariffs, and Home Assistant Energy results · read-only</div><div id=out class=card>Running evidence-based audit…</div>
<script>const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));fetch('api/audit').then(r=>r.json()).then(d=>{if(d.error)throw Error(d.error);let o=d.overview||{};out.className='';out.innerHTML='<div class=grid>'+[['Overall status',o.status||'unknown'],['Grid sources',o.grid_sources??0],['Solar sources',o.solar_sources??0],['Validation issues',o.validation_issues??0]].map(x=>'<div class=card><div class=muted>'+esc(x[0])+'</div><div class=metric>'+esc(x[1])+'</div></div>').join('')+'</div><div class=card><h2>What Home Assistant is using</h2><table><tr><th>Direction</th><th>Meter family</th><th>Entity/statistic</th></tr><tr><td>Grid import</td><td>'+esc(o.import?.family)+'</td><td><code>'+esc(o.import?.id||'Not configured')+'</code></td></tr><tr><td>Grid export</td><td>'+esc(o.export?.family)+'</td><td><code>'+esc(o.export?.id||'Not configured')+'</code></td></tr></table></div><h2>Findings and actions</h2>'+d.findings.map(f=>'<div class="card '+esc(f.severity)+'"><h3>'+esc(f.title)+'</h3><p><strong>Evidence:</strong> '+esc(f.evidence)+'</p><p><strong>Why it matters:</strong> '+esc(f.impact)+'</p><p><strong>Recommended action:</strong> '+esc(f.action)+'</p></div>').join('')+'<div class="card '+(d.validation.status==='passed'?'healthy':'degraded')+'"><h2>Home Assistant validation</h2><p>'+(d.validation.status==='passed'?'All validation result slots were empty. No validation error was reported.':esc(d.validation.issues.length)+' meaningful validation issue(s) were found.')+'</p></div><div class=card><h2>Available NOVEC SmartHub statistics</h2><p class=muted>These are utility-side measurements available for billing reconciliation; they are not automatically required for the live dashboard.</p>'+d.smarthub_statistics.map(s=>'<p><code>'+esc(s.statistic_id)+'</code> · '+esc(s.statistics_unit_of_measurement||'unit unavailable')+'</p>').join('')+'</div>'}).catch(e=>{out.className='card critical';out.innerHTML='<h2>Audit could not complete</h2><p>'+esc(e.message||e)+'</p>'})</script></body></html>"""

async def health(_): return web.json_response({"status":"ok"})
async def audit_api(_):
    try: return web.json_response(await audit())
    except Exception as exc: return web.json_response({"error":str(exc),"findings":[]},status=500)
async def index(_): return web.Response(text=PAGE_V2,content_type="text/html")

app=web.Application();app.router.add_get("/health",health);app.router.add_get("/api/audit",audit_api);app.router.add_get("/{tail:.*}/health",health);app.router.add_get("/{tail:.*}/api/audit",audit_api);app.router.add_get("/{tail:.*}",index)
if __name__=="__main__":
    if not TOKEN: raise SystemExit("SUPERVISOR_TOKEN is required")
    web.run_app(app,host="0.0.0.0",port=8099)
