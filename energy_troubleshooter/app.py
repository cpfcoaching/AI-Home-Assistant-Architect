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

def analyze(prefs,stats,validation):
    findings=[]; smarthub=[s for s in stats if "smarthub" in s.get("statistic_id","").lower()]
    if not smarthub: findings.append({"severity":"critical","title":"No SmartHub statistics","detail":"The integration has not registered billing statistics."})
    elif any(s.get("statistics_unit_of_measurement")!="kWh" for s in smarthub): findings.append({"severity":"degraded","title":"Unexpected SmartHub unit","detail":"SmartHub energy statistics should use kWh."})
    sources=(prefs or {}).get("energy_sources",[]) if isinstance(prefs,dict) else []
    grids=[s for s in sources if s.get("type")=="grid"]
    if not grids: findings.append({"severity":"critical","title":"No grid source configured","detail":"Configure an Electricity grid source in Energy settings."})
    for grid in grids:
        imported=str(grid.get("stat_energy_from") or grid.get("entity_energy_from") or "")
        exported=str(grid.get("stat_energy_to") or grid.get("entity_energy_to") or "")
        if smarthub and "smarthub" not in imported.lower(): findings.append({"severity":"degraded","title":"Grid import is not using SmartHub","detail":"Use the SmartHub hourly usage statistic for utility-side imported kWh."})
        cost=str(grid.get("entity_energy_from_cost") or "")
        if cost and ("monthly" in cost.lower() or "usage" in cost.lower()): findings.append({"severity":"critical","title":"Energy usage selected as cost","detail":"The selected cost entity appears to report kWh, not currency. Use a static price or a currency cost entity."})
        comp=str(grid.get("entity_energy_to_compensation") or "")
        if comp and ("to_home" in comp.lower() or "import" in comp.lower()): findings.append({"severity":"critical","title":"Import cost selected as export compensation","detail":"Use a verified export rate or disable compensation tracking until the tariff is confirmed."})
        if not exported: findings.append({"severity":"watch","title":"No grid export statistic","detail":"Select the SmartHub return statistic if NOVEC provides it."})
    if isinstance(validation,dict):
        for key,value in validation.items():
            if value: findings.append({"severity":"degraded","title":"Energy validation finding: "+str(key),"detail":str(value)})
    if not findings: findings.append({"severity":"healthy","title":"No obvious configuration fault","detail":"SmartHub statistics and Energy mappings passed the current checks."})
    return findings

async def audit():
    data=await ws_commands({"prefs":{"type":"energy/get_prefs"},"validation":{"type":"energy/validate"},"stats":{"type":"recorder/list_statistic_ids","statistic_type":"sum"}})
    prefs=data.get("prefs") or {}; stats=data.get("stats") or []
    return {"read_only":True,"findings":analyze(prefs,stats,data.get("validation") or {}),"smarthub_statistics":[s for s in stats if "smarthub" in s.get("statistic_id","").lower()],"energy_preferences":prefs,"rates":options()}

PAGE="""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Energy Troubleshooter</title><style>:root{color-scheme:dark;font-family:system-ui;background:#101214;color:#eee}body{padding:24px}.card{background:#1c1f22;border:1px solid #383b40;border-radius:12px;padding:18px;margin:14px 0}.critical{border-left:5px solid #f44336}.degraded{border-left:5px solid #ff9800}.watch{border-left:5px solid #ffc107}.healthy{border-left:5px solid #4caf50}small{color:#aaa}code{word-break:break-all}</style></head><body><h1>Energy Data Troubleshooter</h1><small>SmartHub · Energy preferences · tariffs · read-only</small><div id=out class=card>Running audit…</div><script>const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));fetch('api/audit').then(r=>r.json()).then(d=>{out.className='';out.innerHTML=d.findings.map(f=>'<div class="card '+esc(f.severity)+'"><h3>'+esc(f.title)+'</h3><p>'+esc(f.detail)+'</p></div>').join('')+'<div class=card><h2>SmartHub statistics</h2>'+d.smarthub_statistics.map(s=>'<p><code>'+esc(s.statistic_id)+'</code> · '+esc(s.statistics_unit_of_measurement)+'</p>').join('')+'</div>'}).catch(e=>out.textContent=e)</script></body></html>"""

async def health(_): return web.json_response({"status":"ok"})
async def audit_api(_):
    try: return web.json_response(await audit())
    except Exception as exc: return web.json_response({"error":str(exc),"findings":[]},status=500)
async def index(_): return web.Response(text=PAGE,content_type="text/html")

app=web.Application();app.router.add_get("/health",health);app.router.add_get("/api/audit",audit_api);app.router.add_get("/{tail:.*}/health",health);app.router.add_get("/{tail:.*}/api/audit",audit_api);app.router.add_get("/{tail:.*}",index)
if __name__=="__main__":
    if not TOKEN: raise SystemExit("SUPERVISOR_TOKEN is required")
    web.run_app(app,host="0.0.0.0",port=8099)
