"""Read-only three-level climate advisor for Home Assistant OS."""
import json, os, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN=os.environ.get("SUPERVISOR_TOKEN","")
CORE="http://supervisor/core/api"
OPT=Path("/data/options.json")

def options():
    cfg={"summer_upper_limit_f":75,"winter_upper_minimum_f":65,"imbalance_threshold_f":3,"upper_entity_ids":"","main_entity_ids":"","lower_entity_ids":""}
    try: cfg.update(json.loads(OPT.read_text()))
    except (OSError,ValueError): pass
    return cfg

def states():
    req=urllib.request.Request(CORE+"/states",headers={"Authorization":"Bearer "+TOKEN})
    with urllib.request.urlopen(req,timeout=15) as response: return json.load(response)

def fahrenheit(state):
    try: value=float(state["state"])
    except (KeyError,ValueError,TypeError): return None
    unit=state.get("attributes",{}).get("unit_of_measurement")
    return value*9/5+32 if unit=="°C" else value

def snapshot():
    cfg=options(); rows=states(); by_id={r["entity_id"]:r for r in rows}
    levels={}
    for level in ("upper","main","lower"):
        ids=[x.strip() for x in cfg[level+"_entity_ids"].split(",") if x.strip()]
        readings=[{"entity_id":i,"name":by_id.get(i,{}).get("attributes",{}).get("friendly_name",i),"temperature_f":fahrenheit(by_id.get(i,{}))} for i in ids]
        valid=[r["temperature_f"] for r in readings if r["temperature_f"] is not None]
        levels[level]={"average_f":round(sum(valid)/len(valid),1) if valid else None,"readings":readings}
    upper,main=levels["upper"]["average_f"],levels["main"]["average_f"]
    delta=round(upper-main,1) if upper is not None and main is not None else None
    recommendations=[]
    if not levels["upper"]["readings"]: recommendations.append("Configure upper-floor temperature entities")
    if delta is not None and abs(delta)>=cfg["imbalance_threshold_f"]: recommendations.append("Run a monitored 10-15 minute circulation trial")
    if upper is not None and upper>cfg["summer_upper_limit_f"]: recommendations.append("Upper floor exceeds the 75°F cooling target")
    if upper is not None and upper<cfg["winter_upper_minimum_f"]: recommendations.append("Upper floor is below the 65°F heating target")
    equipment=[{"entity_id":r["entity_id"],"name":r.get("attributes",{}).get("friendly_name",r["entity_id"]),"state":r.get("state")} for r in rows if r["entity_id"].split(".")[0] in {"climate","fan"}]
    return {"levels":levels,"upper_main_delta_f":delta,"recommendations":recommendations,"equipment":equipment,"read_only":True}

PAGE="""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Climate Balancer</title><style>:root{color-scheme:dark;font-family:system-ui;background:#101214;color:#eee}body{padding:24px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}.card{background:#1c1f22;border:1px solid #383b40;border-radius:12px;padding:18px;margin:14px 0}.big{font-size:2rem;font-weight:700}small{color:#aaa}</style></head><body><h1>Whole-Home Climate Balancer</h1><small>Kevin V299 three-level model · read-only</small><div class=grid id=levels></div><div class=card><h2>Recommendations</h2><ul id=recs></ul></div><div class=card><h2>Discovered HVAC and fans</h2><ul id=gear></ul></div><script>const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));fetch('api/status').then(r=>r.json()).then(d=>{levels.innerHTML=['upper','main','lower'].map(k=>'<div class=card><small>'+k+' floor average</small><div class=big>'+esc(d.levels[k].average_f??'Not mapped')+(d.levels[k].average_f==null?'':'°F')+'</div></div>').join('')+'<div class=card><small>Upper-main delta</small><div class=big>'+esc(d.upper_main_delta_f??'Unknown')+(d.upper_main_delta_f==null?'':'°F')+'</div></div>';recs.innerHTML=(d.recommendations.length?d.recommendations:['No active recommendation']).map(x=>'<li>'+esc(x)+'</li>').join('');gear.innerHTML=d.equipment.map(x=>'<li>'+esc(x.name)+' — '+esc(x.state)+'</li>').join('')})</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def reply(self,code,payload,kind): self.send_response(code);self.send_header("Content-Type",kind);self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(payload)
    def do_GET(self):
        path=self.path.rstrip("/")
        if path.endswith("/health"): self.reply(200,b'{"status":"ok"}',"application/json")
        elif path.endswith("/api/status"):
            try: payload=json.dumps(snapshot()).encode();code=200
            except Exception as exc: payload=json.dumps({"error":str(exc)}).encode();code=500
            self.reply(code,payload,"application/json")
        else: self.reply(200,PAGE.encode(),"text/html; charset=utf-8")
    def log_message(self,fmt,*args): pass

if __name__=="__main__":
    if not TOKEN: raise SystemExit("SUPERVISOR_TOKEN is required")
    ThreadingHTTPServer(("0.0.0.0",8099),Handler).serve_forever()
