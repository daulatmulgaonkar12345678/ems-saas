import os, json, socket, time, threading, http.server, urllib.request, urllib.error
from datetime import datetime
from flask import Flask, jsonify, request, make_response

app = Flask(__name__)
DASHBOARD_PORT = 8080
PROXY_PORT = 8888
SOCIETIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'societies.json')
log_buffer = []
MAX_LOGS = 1000
stats = {'total_requests':0,'blocked':0,'allowed':0,'start_time':datetime.now().isoformat()}
active_society = None
proxy_running = False
proxy_thread = None
proxy_server = None

def load_societies():
    if os.path.exists(SOCIETIES_FILE):
        try:
            with open(SOCIETIES_FILE,'r') as f: return json.load(f)
        except: pass
    return []

def save_societies(s):
    with open(SOCIETIES_FILE,'w') as f: json.dump(s,f,indent=2)

def get_society_by_id(sid):
    for s in load_societies():
        if s['id']==sid: return s
    return None

def clean_host(h):
    h=h.strip()
    if h.startswith('https://'): h=h[8:]
    elif h.startswith('http://'): h=h[7:]
    h=h.rstrip('/')
    if ':' in h and h.split(':')[-1].isdigit(): h=h.rsplit(':',1)[0]
    return h.strip()

def add_log(method,url,action,detail="",sc=0):
    global log_buffer
    e={'id':len(log_buffer),'timestamp':datetime.now().isoformat(),'method':method,'url':url,'action':action,'detail':detail,'status_code':sc,'society':active_society['name'] if active_society else 'None'}
    log_buffer.append(e)
    if len(log_buffer)>MAX_LOGS: log_buffer=log_buffer[-MAX_LOGS:]
    for i,x in enumerate(log_buffer): x['id']=i
    stats['total_requests']+=1
    if action=='BLOCKED': stats['blocked']+=1
    else: stats['allowed']+=1

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(s,f,*a): pass
    def do_request(s):
        global active_society
        if not active_society: s.send_error(503,"No society"); return
        th=clean_host(active_society.get('target_host',''))
        tp=int(active_society.get('target_port',80))
        if not th: s.send_error(503,"No host"); return
        cl=int(s.headers.get('Content-Length',0))
        body=s.rfile.read(cl) if cl>0 else None
        tu=f"http://{th}:{tp}{s.path}"
        try:
            req=urllib.request.Request(tu,data=body,method=s.command)
            for k,v in s.headers.items():
                if k.lower() not in('host','content-length'):
                    try: req.add_header(k,v)
                    except: pass
            resp=urllib.request.urlopen(req,timeout=15)
            rb=resp.read(); s.send_response(resp.status)
            for k,v in resp.getheaders():
                if k.lower() not in('transfer-encoding','connection'): s.send_header(k,v)
            s.end_headers(); s.wfile.write(rb)
            add_log(s.command,s.path,'ALLOWED',f"{resp.status}->{th}:{tp}",resp.status)
        except urllib.error.HTTPError as e:
            rb=e.read(); s.send_response(e.code)
            for k,v in e.headers.items():
                if k.lower() not in('transfer-encoding','connection'): s.send_header(k,v)
            s.end_headers(); s.wfile.write(rb)
            add_log(s.command,s.path,'BLOCKED',f"HTTP {e.code}",e.code)
        except Exception as e:
            try: s.send_error(502,str(e))
            except: pass
            add_log(s.command,s.path,'BLOCKED',f"Error:{e}",502)
    do_GET=do_request;do_POST=do_request;do_PUT=do_request;do_DELETE=do_request;do_PATCH=do_request;do_HEAD=do_request;do_OPTIONS=do_request

def start_proxy():
    global proxy_running,proxy_server
    try:
        proxy_server=http.server.HTTPServer(('127.0.0.1',PROXY_PORT),ProxyHandler)
        proxy_running=True; proxy_server.serve_forever()
    except Exception as e: proxy_running=False

@app.route('/api/pi/send',methods=['POST'])
def api_pi_send():
    d=request.json; m=d.get('method','GET').upper(); p=d.get('path','/'); b=d.get('body','')
    if not p.startswith('/'): p='/'+p
    try:
        tu=f"http://127.0.0.1:{PROXY_PORT}{p}"
        rd=b.encode() if b else None
        req=urllib.request.Request(tu,data=rd,method=m)
        if rd and m in('POST','PUT','PATCH'): req.add_header('Content-Type','application/json')
        t0=time.time(); resp=urllib.request.urlopen(req,timeout=15)
        el=round((time.time()-t0)*1000); rb=resp.read().decode('utf-8',errors='replace')
        try: rb=json.dumps(json.loads(rb),indent=2)
        except: pass
        return jsonify({'status':'ok','http_status':resp.status,'body':rb,'time_ms':el,'size':len(rb)})
    except urllib.error.HTTPError as e:
        rb=e.read().decode('utf-8',errors='replace') if e.fp else ''
        try: rb=json.dumps(json.loads(rb),indent=2)
        except: pass
        return jsonify({'status':'ok','http_status':e.code,'body':rb,'time_ms':0,'size':len(rb)})
    except Exception as e:
        return jsonify({'status':'error','error':str(e)})

@app.route('/')
def index():
    return make_response(HTML_PAGE,200,{'Content-Type':'text/html; charset=utf-8'})

@app.route('/api/societies',methods=['GET'])
def api_get_soc():
    return jsonify({'societies':load_societies(),'active_id':active_society['id'] if active_society else None})

@app.route('/api/societies/save',methods=['POST'])
def api_save_soc():
    d=request.json;n=d.get('name','').strip();h=d.get('target_host','').strip()
    p=d.get('target_port',80);nt=d.get('notes','').strip();sid=d.get('id')
    if not n or not h: return jsonify({'status':'error','message':'Name+host required'})
    h=clean_host(h); socs=load_societies()
    if sid:
        for s in socs:
            if s['id']==sid: s.update({'name':n,'target_host':h,'target_port':int(p),'notes':nt})
    else:
        socs.append({'id':f"soc_{int(datetime.now().timestamp()*1000)}",'name':n,'target_host':h,'target_port':int(p),'notes':nt,'enabled':True})
    save_societies(socs)
    global active_society
    if active_society and active_society['id']==sid: active_society.update({'target_host':h,'target_port':int(p),'name':n,'notes':nt})
    return jsonify({'status':'ok'})

@app.route('/api/societies/activate',methods=['POST'])
def api_act_soc():
    global active_society,proxy_running,proxy_thread
    sid=request.json.get('id'); soc=get_society_by_id(sid)
    if not soc: return jsonify({'status':'error','message':'Not found'})
    soc['target_host']=clean_host(soc['target_host']); active_society=soc
    if not proxy_running:
        try: proxy_thread=threading.Thread(target=start_proxy,daemon=True); proxy_thread.start(); time.sleep(0.8)
        except Exception as e: return jsonify({'status':'error','message':str(e)})
    return jsonify({'status':'ok','name':soc['name']})

@app.route('/api/societies/delete',methods=['POST'])
def api_del_soc():
    global active_society; sid=request.json.get('id')
    socs=[s for s in load_societies() if s['id']!=sid]; save_societies(socs)
    if active_society and active_society['id']==sid: active_society=None
    return jsonify({'status':'ok'})

@app.route('/api/stats')
def get_stats():
    up=datetime.now()-datetime.fromisoformat(stats['start_time'])
    return jsonify({**stats,'uptime_human':str(up).split('.')[0],'log_count':len(log_buffer),'proxy_running':proxy_running,'active_society':active_society['name'] if active_society else ''})

@app.route('/api/logs')
def get_logs():
    since = int(request.args.get('since', 0))
    return jsonify({'logs':log_buffer[since:],'total':len(log_buffer),'next':len(log_buffer)})

@app.route('/api/clear-logs',methods=['POST'])
def clear_logs():
    global log_buffer; log_buffer=[]
    stats.update({'total_requests':0,'blocked':0,'allowed':0,'start_time':datetime.now().isoformat()})
    return jsonify({'status':'ok'})

@app.route('/favicon.ico')
def favicon(): return '',204

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EMS Dashboard V2.1.0</title>
<style>
:root{--bg:#0a0e17;--s:#111827;--c:#1a2236;--b:#1e2d4a;--t:#e2e8f0;--d:#64748b;--a:#22d3ee;--g:#10b981;--r:#ef4444;--y:#f59e0b;--o:#f97316;--p:#8b5cf6}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--t);min-height:100vh}
body::before{content:'';position:fixed;inset:-50%;width:200%;height:200%;background:radial-gradient(ellipse at 20% 50%,rgba(6,182,212,.06) 0%,transparent 50%),radial-gradient(ellipse at 80% 20%,rgba(139,92,246,.04) 0%,transparent 50%);z-index:0;pointer-events:none;animation:bg 20s ease-in-out infinite alternate}
@keyframes bg{to{transform:translate(-2%,-1%) rotate(3deg)}}
.ct{position:relative;z-index:1;max-width:1500px;margin:0 auto;padding:14px}
header{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;background:var(--s);border:1px solid var(--b);border-radius:12px;margin-bottom:12px;flex-wrap:wrap;gap:10px}
.logo{display:flex;align-items:center;gap:10px}
.logo-icon{width:36px;height:36px;background:linear-gradient(135deg,var(--a),var(--p));border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:17px;font-weight:900;color:#fff}
.lt h1{font-size:15px;font-weight:700}.lt span{font-size:9px;color:var(--d);letter-spacing:1px;text-transform:uppercase}
.ps{display:flex;align-items:center;gap:6px;padding:4px 10px;border-radius:16px;font-size:10px;font-weight:600}
.ps.on{background:rgba(16,185,129,.15);color:var(--g)}.ps.off{background:rgba(239,68,68,.15);color:var(--r)}
.ps .dt{width:6px;height:6px;border-radius:50%;animation:pu 2s infinite}.ps.on .dt{background:var(--g)}.ps.off .dt{background:var(--r);animation:none}
@keyframes pu{0%,100%{opacity:1}50%{opacity:.4}}
.tb{display:flex;gap:8px;align-items:center;padding:10px 16px;background:var(--s);border:1px solid var(--b);border-radius:10px;margin-bottom:12px;flex-wrap:wrap}
.tb label{font-size:10px;color:var(--d);text-transform:uppercase;letter-spacing:.5px}
.tb select,.tb input{padding:6px 10px;border-radius:6px;border:1px solid var(--b);background:var(--c);color:var(--t);font-size:11px}
.tb select:focus,.tb input:focus{outline:none;border-color:var(--a)}
.tb select{min-width:170px}.tb input[type=text]{width:220px;font-family:monospace;font-size:10px}.tb input::placeholder{color:#475569}
.sb{padding:6px 12px;border-radius:6px;border:1px solid var(--b);background:var(--c);color:var(--t);font-size:10px;cursor:pointer;transition:all .15s;white-space:nowrap}
.sb:hover{border-color:var(--a);color:var(--a)}.sb.pr{background:rgba(34,211,238,.12);border-color:var(--a);color:var(--a)}.sb.dn:hover{border-color:var(--r);color:var(--r)}
.sp{flex:1}
.mg{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
@media(max-width:1000px){.mg{grid-template-columns:1fr}}
.pn{background:var(--s);border:1px solid var(--b);border-radius:12px;overflow:hidden}
.ph{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--b);background:var(--c)}
.ph h2{font-size:12px;font-weight:600;display:flex;align-items:center;gap:6px}
.ph .ha{display:flex;gap:6px;align-items:center}
.pb{padding:14px}
.psc{max-height:calc(100vh - 170px);overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--b) transparent}
.psc::-webkit-scrollbar{width:5px}.psc::-webkit-scrollbar-thumb{background:var(--b);border-radius:3px}
.wc{display:grid;gap:8px;margin-bottom:14px}
.wk{background:var(--c);border:1px solid var(--b);border-radius:10px;padding:12px;position:relative;overflow:hidden}
.wk::before{content:'';position:absolute;top:0;left:0;bottom:0;width:4px;background:var(--d);transition:all .3s}
.wk.aw{border-color:rgba(16,185,129,.4)}.wk.aw::before{background:var(--g);box-shadow:0 0 12px rgba(16,185,129,.5)}
.wk.dw{opacity:.5}.wk.dw::before{background:var(--r)}
.wt{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;flex-wrap:wrap;gap:6px}
.wi{display:flex;align-items:center;gap:8px}
.wid{font-size:22px;font-weight:900;color:var(--a);font-family:monospace;min-width:26px}
.wnw{display:flex;flex-direction:column;gap:1px}
.wn{font-size:14px;font-weight:700}
.wni{font-size:13px;font-weight:600;padding:2px 6px;border-radius:4px;border:1px solid var(--a);background:var(--bg);color:var(--t);width:170px}
.wni:focus{outline:none;box-shadow:0 0 0 2px rgba(34,211,238,.3)}
.bg{font-size:9px;padding:1px 7px;border-radius:10px;font-weight:600;margin-left:4px}
.bg.on{background:rgba(16,185,129,.15);color:var(--g)}.bg.off{background:rgba(100,116,139,.15);color:var(--d)}
.bg.fl{background:rgba(239,68,68,.15);color:var(--r)}.bg.sy{background:rgba(34,211,238,.15);color:var(--a)}.bg.ds{background:rgba(239,68,68,.15);color:var(--r)}
.bg.phys-on{background:rgba(34,211,238,.12);color:var(--a);border:1px solid rgba(34,211,238,.3)}
.bg.phys-off{background:rgba(100,116,139,.12);color:var(--d);border:1px solid rgba(100,116,139,.3)}
.bg.phys-unk{background:rgba(245,158,11,.12);color:var(--y);border:1px solid rgba(245,158,11,.3)}
.wco{display:flex;gap:5px;align-items:center;flex-wrap:wrap}
.bo,.bf{padding:6px 18px;font-size:11px;font-weight:800;border:none;cursor:pointer;transition:all .15s;border-radius:5px}
.bo{background:var(--g);color:#fff}.bo:hover{background:#059669;box-shadow:0 0 12px rgba(16,185,129,.4)}
.bf{background:var(--r);color:#fff}.bf:hover{background:#dc2626;box-shadow:0 0 12px rgba(239,68,68,.4)}
.bo:disabled,.bf:disabled{opacity:.35;cursor:not-allowed;box-shadow:none}
.sm{padding:4px 8px;border-radius:4px;border:1px solid var(--b);background:var(--s);color:var(--d);font-size:9px;cursor:pointer;transition:all .15s}
.sm:hover{border-color:var(--a);color:var(--a)}.sm.sv:hover{border-color:var(--g);color:var(--g)}.sm.pp:hover{border-color:var(--p);color:var(--p)}.sm.rd:hover{border-color:var(--r);color:var(--r)}.sm.yl:hover{border-color:var(--y);color:var(--y)}
.ws{display:flex;gap:14px;flex-wrap:wrap}
.wsl{font-size:8px;color:var(--d);text-transform:uppercase;letter-spacing:.5px}
.wsv{font-size:12px;font-weight:700}
.wsv.g{color:var(--g)}.wsv.r{color:var(--r)}.wsv.y{color:var(--y)}.wsv.a{color:var(--a)}
.db{width:100%;height:5px;background:var(--bg);border-radius:3px;margin-top:6px;overflow:hidden}
.dbf{height:100%;border-radius:3px;transition:width .3s}
.dbf.g{background:var(--g)}.dbf.y{background:var(--y)}.dbf.r{background:var(--r)}
.sh{font-size:10px;color:var(--d);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--b);margin-top:14px}
.lp{background:#0d1117;border:2px solid #1e2d4a;border-radius:8px;padding:12px;font-family:'Courier New',monospace;font-size:16px;color:var(--g);min-height:44px;margin-bottom:8px;text-align:center;letter-spacing:3px;text-shadow:0 0 10px rgba(16,185,129,.5);white-space:pre-wrap}
.lr{display:flex;gap:6px;margin-bottom:6px}
.lin{flex:1;padding:6px 10px;border-radius:5px;border:1px solid var(--b);background:var(--c);color:var(--t);font-size:12px;font-family:'Courier New',monospace}
.lin:focus{outline:none;border-color:var(--a)}.lin::placeholder{color:#475569}
.ls{width:50px;text-align:center}
.bl{padding:6px 14px;border-radius:5px;border:none;background:var(--a);color:#000;font-size:11px;font-weight:700;cursor:pointer}.bl:hover{background:#06b6d4}
.bcl{padding:6px 10px;border-radius:5px;border:1px solid var(--b);background:var(--c);color:var(--d);font-size:11px;cursor:pointer}.bcl:hover{border-color:var(--r);color:var(--r)}
.sg{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.xb{padding:8px 4px;border-radius:6px;border:1px solid var(--b);background:var(--c);color:var(--t);font-size:9px;font-weight:600;cursor:pointer;transition:all .15s;text-align:center;display:flex;flex-direction:column;align-items:center;gap:3px}
.xb .xi{font-size:16px}
.xb:hover{border-color:var(--a);background:rgba(34,211,238,.06);transform:translateY(-1px)}
.xb.dn:hover{border-color:var(--r);background:rgba(239,68,68,.06)}.xb.wn:hover{border-color:var(--y);background:rgba(245,158,11,.06)}.xb:disabled{opacity:.3;cursor:not-allowed;transform:none}
.uc-box{background:var(--bg);border:1px solid var(--b);border-radius:8px;padding:12px;margin-bottom:14px}
.uc-mode-row{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}
.uc-mode-sel{padding:6px 12px;border-radius:6px;border:1px solid var(--b);background:var(--c);color:var(--t);font-size:12px;min-width:200px;cursor:pointer}
.uc-mode-sel:focus{outline:none;border-color:var(--a)}
.uc-mode-sel option{background:var(--c);color:var(--t)}
.uc-row{display:flex;gap:8px;align-items:center;margin-bottom:6px;flex-wrap:wrap}
.uc-label{font-size:11px;color:var(--d);min-width:160px}
.uc-input{padding:6px 10px;border-radius:5px;border:1px solid var(--b);background:var(--c);color:var(--t);font-size:13px;font-weight:700;width:110px;text-align:center}
.uc-input:focus{outline:none;border-color:var(--a)}
.uc-input.wide{width:140px}
.uc-result{padding:10px 14px;background:var(--c);border:1px solid var(--b);border-radius:8px;margin-top:10px}
.uc-avg{font-size:13px;font-weight:800;color:var(--y);text-align:center;margin:6px 0;padding:6px;background:rgba(245,158,11,.1);border-radius:6px}
.uc-result-row{display:flex;align-items:center;justify-content:space-between;padding:3px 0;font-size:11px}
.ucr-label{color:var(--d)}
.ucr-val{font-weight:700;color:var(--a);font-family:monospace}
.ucr-formula{color:var(--d);font-size:10px;font-family:monospace}
.uc-calc-btn{padding:8px 20px;border-radius:6px;border:none;background:linear-gradient(135deg,var(--y),var(--o));color:#fff;font-size:12px;font-weight:700;cursor:pointer;transition:all .15s;width:100%;margin-top:10px}
.uc-calc-btn:hover{box-shadow:0 0 15px rgba(245,158,11,.3);transform:translateY(-1px)}
.uc-calc-btn:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none}
.uc-lock-btn{padding:8px 20px;border-radius:6px;border:1px solid var(--b);background:var(--c);color:var(--t);font-size:11px;font-weight:700;cursor:pointer;transition:all .15s;margin-top:6px}
.uc-lock-btn:hover{border-color:var(--a);color:var(--a)}
.uc-lock-btn.locked{border-color:var(--y);color:var(--y);background:rgba(245,158,11,.08)}
.uc-lock-btn:disabled{opacity:.3;cursor:not-allowed}
.uc-no-wings{padding:16px;text-align:center;color:var(--d);font-size:11px}
.uc-no-wings .ri{font-size:24px;opacity:.3;margin-bottom:4px}
.lock-banner{padding:6px 12px;border-radius:6px;font-size:10px;font-weight:600;margin-bottom:8px;text-align:center}
.lock-banner.locked{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);color:var(--r)}
.lock-banner.unlocked{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);color:var(--g)}
.rs{font-weight:700;font-size:14px;margin-bottom:3px}
.rs.s2{color:var(--g)}.rs.s3{color:var(--a)}.rs.s4{color:var(--y)}.rs.s5{color:var(--r)}.rs.er{color:var(--r)}
.rm{font-size:10px;color:var(--d);margin-bottom:8px}
.rb{background:var(--bg);border:1px solid var(--b);border-radius:8px;padding:10px;max-height:480px;overflow:auto;font-family:monospace;font-size:10px;line-height:1.6;white-space:pre-wrap;word-break:break-all;scrollbar-width:thin;scrollbar-color:var(--b) transparent}
.rb::-webkit-scrollbar{width:5px}.rb::-webkit-scrollbar-thumb{background:var(--b);border-radius:3px}
.re{padding:30px 16px;text-align:center;color:var(--d);font-family:'Segoe UI',sans-serif;font-size:12px}
.re .ri{font-size:32px;margin-bottom:6px;opacity:.3}
.tgg{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-bottom:12px}
.tc{background:var(--c);border:1px solid var(--b);border-radius:8px;padding:10px;position:relative;overflow:hidden;transition:transform .2s}
.tc:hover{transform:translateY(-1px)}
.tc::after{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.tc.cy::after{background:var(--a)}.tc.gr::after{background:var(--g)}.tc.rd::after{background:var(--r)}.tc.yl::after{background:var(--y)}.tc.pu::after{background:var(--p)}.tc.or::after{background:var(--o)}.tc.bl::after{background:#3b82f6}
.tl{font-size:8px;color:var(--d);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px}
.tv{font-size:18px;font-weight:800;line-height:1}
.tv.cy{color:var(--a)}.tv.gr{color:var(--g)}.tv.rd{color:var(--r)}.tv.yl{color:var(--y)}.tv.pu{color:var(--p)}.tv.or{color:var(--o)}.tv.bl{color:#3b82f6}
.lgp{background:var(--s);border:1px solid var(--b);border-radius:12px;overflow:hidden}
.lgh{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--b);background:var(--c)}
.lgh h2{font-size:12px;font-weight:600}
.lf{display:flex;gap:5px;padding:6px 16px;border-bottom:1px solid var(--b);flex-wrap:wrap}
.fb{padding:2px 8px;border-radius:10px;border:1px solid var(--b);background:transparent;color:var(--d);font-size:9px;cursor:pointer;transition:all .15s}
.fb.ac,.fb:hover{border-color:var(--a);color:var(--a);background:rgba(34,211,238,.08)}
.lbd{max-height:180px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--b) transparent}
.lbd::-webkit-scrollbar{width:5px}.lbd::-webkit-scrollbar-thumb{background:var(--b);border-radius:3px}
.le{display:grid;grid-template-columns:95px 42px 1fr 58px 45px 1fr;align-items:center;padding:3px 16px;border-bottom:1px solid rgba(30,45,74,.4);font-size:9px;font-family:monospace;gap:4px}
.le:hover{background:rgba(34,211,238,.03)}
.lm{color:var(--d)}.lme{font-weight:700;text-transform:uppercase;padding:1px 3px;border-radius:3px;text-align:center;font-size:8px}
.lme.GET{background:rgba(16,185,129,.15);color:var(--g)}.lme.POST{background:rgba(34,211,238,.15);color:var(--a)}
.lu{color:var(--t);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.la{font-weight:700;text-align:center;padding:1px 3px;border-radius:3px;font-size:8px}
.la.ALLOWED{background:rgba(16,185,129,.12);color:var(--g)}.la.BLOCKED{background:rgba(239,68,68,.12);color:var(--r)}
.lst{color:var(--d);text-align:center}
.ldt{color:var(--d);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lle{padding:24px 16px;text-align:center;color:var(--d);font-family:'Segoe UI',sans-serif;font-size:10px}
.lle .ri{font-size:24px;margin-bottom:4px;opacity:.3}
.lle p{font-size:10px}
.mo{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:100;display:none;align-items:center;justify-content:center}
.mo.sh{display:flex}
.md{background:var(--s);border:1px solid var(--b);border-radius:14px;padding:22px;width:90%;max-width:380px}
.md h3{font-size:15px;margin-bottom:14px}
.fg{margin-bottom:12px}.fg label{display:block;font-size:10px;color:var(--d);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
.fg input{width:100%;padding:8px 10px;border-radius:6px;border:1px solid var(--b);background:var(--c);color:var(--t);font-size:12px}
.fg input:focus{outline:none;border-color:var(--a)}.fg input::placeholder{color:#475569}
.fh{font-size:9px;color:var(--a);margin-top:2px}
.fr{display:flex;gap:8px}.fr .fg{flex:1}
.ma{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}
footer{text-align:center;padding:12px;color:var(--d);font-size:9px}
.toast{position:fixed;bottom:14px;right:14px;padding:8px 16px;border-radius:8px;background:var(--c);border:1px solid var(--b);color:var(--t);font-size:11px;transform:translateY(100px);opacity:0;transition:all .3s;z-index:999}
.toast.sh{transform:translateY(0);opacity:1}.toast.ok{border-color:var(--g);color:var(--g)}.toast.er{border-color:var(--r);color:var(--r)}
@media(max-width:900px){.tgg{grid-template-columns:repeat(3,1fr)}.le{grid-template-columns:1fr;gap:2px}.sg{grid-template-columns:repeat(2,1fr)}.wt{flex-direction:column;align-items:flex-start;gap:6px}}
</style>
</head>
<body>
<div class="ct">
<header><div class="logo"><div class="logo-icon">P</div><div class="lt"><h1>EMS Proxy Dashboard</h1><span>v2.1.0</span></div></div><div class="ps off" id="pSt"><span class="dt"></span><span id="pTx">Offline</span></div></header>
<div class="tb">
<label>Society:</label><select id="sSel" onchange="onSel(this.value)"><option value="">-- Select --</option></select>
<button class="sb pr" onclick="openAdd()">+ Add</button><button class="sb" onclick="editSoc(document.getElementById('sSel').value)">Edit</button><button class="sb dn" onclick="delSoc()">Del</button>
<div class="sp"></div>
<label>API Key:</label><input type="text" id="akIn" placeholder="your_api_key_here" oninput="localStorage.setItem('ak',this.value)">
<span style="font-size:9px;color:var(--d)">Proxy: <strong style="color:var(--a)">127.0.0.1:8888</strong></span>
</div>
<div class="tgg">
<div class="tc cy"><div class="tl">Total</div><div class="tv cy" id="sT">0</div></div>
<div class="tc gr"><div class="tl">Allowed</div><div class="tv gr" id="sA">0</div></div>
<div class="tc rd"><div class="tl">Blocked</div><div class="tv rd" id="sB">0</div></div>
<div class="tc yl"><div class="tl">Uptime</div><div class="tv yl" id="sU" style="font-size:16px">00:00:00</div></div>
<div class="tc pu"><div class="tl">Logs</div><div class="tv pu" id="sL">0</div></div>
<div class="tc or"><div class="tl">Society</div><div class="tv or" id="sS" style="font-size:11px">None</div></div>
<div class="tc bl"><div class="tl">Quota</div><div class="tv bl" id="sQ" style="font-size:11px">OPEN</div></div>
</div>
<div class="mg">
<div class="pn psc">
<div class="ph"><h2>&#128225; Pi Control</h2><div class="ha"><span id="fLbl" style="font-size:9px;color:var(--d)">Detecting...</span><button class="sb" onclick="refreshPi()">&#8635; Refresh</button></div></div>
<div class="pb">
<div class="wc" id="wC"><div class="re"><div class="ri">&#127970;</div>Waiting for Pi...</div></div>
<div class="sh">&#9889; Unit-to-Days Calculator <span style="color:var(--a);font-size:9px">(Pi calculates, not browser)</span></div>
<div id="lockBanner"></div>
<div class="uc-box">
  <div class="uc-mode-row">
    <label class="uc-label">Mode:</label>
    <select id="ucMode" class="uc-mode-sel" onchange="toggleMode(this.value)">
      <option value="units">&#9889; Units Mode (Pi calculates days)</option>
      <option value="days">&#128260; Direct Days Mode</option>
    </select>
  </div>
  <div id="ucInputs"></div>
  <div id="ucResult" style="display:none"></div>
</div>
<div class="sh">&#128433; LCD Display</div>
<div class="lp" id="lcP">EMS READY</div>
<div class="lr"><input class="lin" id="l1" placeholder="Line 1 (16ch)" maxlength="16" oninput="uLcd()"><input class="lin" id="l2" placeholder="Line 2 (16ch)" maxlength="16" oninput="uLcd()"><input class="lin ls" id="lt" type="number" value="10" min="1" max="300"></div>
<div class="lr"><button class="bl" onclick="sLcd()">&#9654; Send</button><button class="bcl" onclick="cLcd()">Clear</button></div>
<div class="sh">&#9881; System</div>
<div class="sg">
<button class="xb" onclick="pG('/status')"><span class="xi">&#128994;</span>Status</button>
<button class="xb" onclick="pG('/logs')"><span class="xi">&#128196;</span>Logs</button>
<button class="xb" onclick="pG('/control/force_on')"><span class="xi">&#128161;</span>Force ON</button>
<button class="xb wn" onclick="pG('/control/reset')"><span class="xi">&#128260;</span>Reset Days</button>
<button class="xb dn" onclick="pG('/control/off_all')"><span class="xi">&#128465;</span>OFF All</button>
<button class="xb dn" id="bEs" onclick="pG('/control/estop')" disabled><span class="xi">&#9888;</span>E-Stop</button>
<button class="xb wn" id="bRs" onclick="pG('/control/restart_system')" disabled><span class="xi">&#128260;</span>Restart</button>
<button class="xb dn" id="bRb" onclick="pG('/control/reboot_device')" disabled><span class="xi">&#128260;</span>Reboot Pi</button>
<button class="xb" id="bDy" onclick="openDays()" disabled><span class="xi">&#128197;</span>Set Days</button>
</div>
<div class="sh">&#9881; Config</div>
<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
<div style="display:flex;gap:4px;align-items:center"><span style="font-size:10px;color:var(--d);font-weight:600">Reset Day:</span><input type="number" id="rdIn" class="lin" style="width:50px;text-align:center" value="22" min="1" max="28"><button class="sb" id="bRd" onclick="sRd()" disabled>Set</button></div>
<div id="rdLockInfo" style="font-size:9px;color:var(--d)"></div>
</div>
<div style="display:flex;gap:4px;align-items:center;margin-bottom:8px"><span style="font-size:10px;color:var(--d);font-weight:600">New Key:</span><input type="text" id="nkIn" class="lin" style="width:110px;font-size:9px" placeholder="min 10 chars"><button class="sb" id="bSk" onclick="sAk()" disabled>Set</button></div>
</div>
</div>
<div class="pn">
<div class="ph"><h2>&#128172; Pi Response</h2><span id="rLbl" style="font-size:9px;color:var(--d)">Waiting...</span></div>
<div class="pb">
<div class="rs" id="rSt">&mdash;</div>
<div class="rm" id="rMt">Send a command to see response</div>
<div class="rb" id="rBd"><div class="re"><div class="ri">&#128225;</div>Click any button<br>to send a command.</div></div>
</div>
</div>
</div>
<div class="lgp">
<div class="lgh"><h2>&#9654; Live Request Log</h2><div style="display:flex;gap:5px"><button class="sb" onclick="tAS()" id="bAS">Auto-Scroll: ON</button><button class="sb dn" onclick="cLogs()">Clear</button></div></div>
<div class="lf">
<button class="fb ac" data-f="ALL" onclick="sF(this)">ALL</button><button class="fb" data-f="ALLOWED" onclick="sF(this)">ALLOWED</button><button class="fb" data-f="BLOCKED" onclick="sF(this)">BLOCKED</button><button class="fb" data-f="GET" onclick="sF(this)">GET</button><button class="fb" data-f="POST" onclick="sF(this)">POST</button>
</div>
<div class="lbd" id="lBd"><div class="lle"><div class="ri">&#128268;</div><p>Waiting...</p></div></div>
</div>
<footer>EMS Dashboard V2.1.0</footer>
</div>
<div class="mo" id="mOv" onclick="if(event.target===this)clM()"><div class="md"><h3 id="mTi">Add Society</h3><div class="fg"><label>Name</label><input id="iN" placeholder="e.g. Prestine"></div><div class="fg"><label>Host / IP</label><input id="iH" placeholder="e.g. 100.122.132.57"><div class="fh">No http://</div></div><div class="fr"><div class="fg"><label>Port</label><input type="number" id="iP" value="5000"></div><div class="fg"><label>Notes</label><input id="iNt" placeholder="Optional"></div></div><div class="ma"><button class="sb" onclick="clM()">Cancel</button><button class="sb pr" onclick="sSoc()">Save</button></div></div></div>
<div class="mo" id="dMv" onclick="if(event.target===this)clD()"><div class="md"><h3>&#128197; Set Target Days</h3><div id="dIn"></div><div class="ma"><button class="sb" onclick="clD()">Cancel</button><button class="sb pr" onclick="aDays()">Apply</button></div></div></div>
<div class="toast" id="tst"></div>
<script>
var cF='ALL',aS=true,lId=0,aL=[],eId=null,piC=null,piTimer=null,storedWingIds=[],quotaLocked=false,quotaLockUntil='',resetDayLocked=false,resetDayLockUntil='';
function sT(m,t){var e=document.getElementById('tst');e.textContent=m;e.className='toast sh'+(t?' '+t:'');setTimeout(function(){e.classList.remove('sh')},3000)}
function gK(){return document.getElementById('akIn').value.trim()}
function uLcd(){var v1=document.getElementById('l1').value||'',v2=document.getElementById('l2').value||'';document.getElementById('lcP').textContent=v1.padEnd(16)+'\n'+v2.padEnd(16)}
function getWingIds(){if(storedWingIds.length>0)return storedWingIds;if(!piC)return[];return Object.keys(piC).filter(function(k){return k.indexOf('system_')!==0&&typeof piC[k]==='object'})}

async function piS(path,method){
  if(!method)method='GET';
  var k=gK(),fp=k?path+(path.indexOf('?')>=0?'&':'?')+'key='+encodeURIComponent(k):path;
  var sE=document.getElementById('rSt'),mE=document.getElementById('rMt'),bE=document.getElementById('rBd'),lE=document.getElementById('rLbl');
  lE.textContent=method+' '+path;sE.textContent='Sending...';sE.className='rs';mE.textContent='Connecting...';bE.innerHTML='<div class="re">Connecting...</div>';
  try{
    var r=await fetch('/api/pi/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:method,path:fp})});
    var d=await r.json();
    if(d.error){sE.textContent='ERROR';sE.className='rs er';mE.textContent=d.error;bE.innerHTML='<div class="re" style="color:var(--r)">&#9888; '+d.error+'</div>';return d}
    var c=d.http_status||0,cls=c<300?'s2':c<400?'s3':c<500?'s4':'s5';
    sE.textContent=c+(c===200?' OK':c===401?' Unauthorized':c===403?' Forbidden':c===404?' Not Found':'');sE.className='rs '+cls;
    mE.textContent=d.size+' bytes \u2014 '+d.time_ms+'ms';bE.textContent=d.body||'(empty)';
    if(path.indexOf('/status')>=0&&c===200){try{piC=JSON.parse(d.body);rW(piC);dFt(piC);rebuildCalc()}catch(ex){console.error(ex)}}
    return d;
  }catch(e){sE.textContent='FAILED';sE.className='rs er';mE.textContent=e.message;bE.innerHTML='<div class="re" style="color:var(--r)">&#9888; '+e.message+'</div>';return null}
}

function pG(p){piS(p,'GET')}

function dFt(d){
  var el=document.getElementById('fLbl');
  if(!d){el.textContent='No data';el.style.color='var(--r)';return}
  var wK=Object.keys(d).filter(function(k){return k.indexOf('system_')!==0&&typeof d[k]==='object'});
  if(wK.length>0){var w=d[wK[0]];el.textContent='Connected ('+wK.length+' wings)';el.style.color='var(--g)'}
  else{el.textContent='No wings';el.style.color='var(--y)'}
  var qLock=d.system_quota_lock_until||'';
  var rdLock=d.system_reset_day_lock_until||'';
  quotaLocked=qLock!==''&&new Date(qLock)>new Date();
  quotaLockUntil=qLock;
  resetDayLocked=rdLock!==''&&new Date(rdLock)>new Date();
  resetDayLockUntil=rdLock;
  document.getElementById('sQ').textContent=quotaLocked?'LOCKED':'OPEN';
  document.getElementById('sQ').style.color=quotaLocked?'var(--r)':'var(--g)';
  document.getElementById('rdIn').value=d.system_reset_day||22;
  var rdInfo=document.getElementById('rdLockInfo');
  if(resetDayLocked){rdInfo.innerHTML='<span style="color:var(--y)">&#128274; Locked until '+new Date(rdLock).toLocaleString()+'</span> <button class="sm yl" onclick="unlockResetDay()">Unlock</button>'}
  else{rdInfo.textContent=''}
  updateLockBanner();
}

function updateLockBanner(){
  var el=document.getElementById('lockBanner');
  if(quotaLocked){el.innerHTML='<div class="lock-banner locked">&#128274; Quota LOCKED until '+new Date(quotaLockUntil).toLocaleString()+' \u2014 No changes allowed on Pi</div>'}
  else{el.innerHTML='<div class="lock-banner unlocked">&#128275; Quota OPEN \u2014 Changes allowed</div>'}
}

function toggleMode(mode){
  var inp=document.getElementById('ucInputs'),res=document.getElementById('ucResult');
  inp.innerHTML='';res.style.display='none';
  var wK=getWingIds();
  if(wK.length===0){
    inp.innerHTML='<div class="uc-no-wings"><div class="ri">&#128268;</div>Connect to Pi first to see wings<br><span style="font-size:9px">Click Status button above</span></div>';
    return;
  }
  if(mode==='units'){
    var html='<div class="uc-row"><span class="uc-label">Total Monthly Units:</span><input type="number" class="uc-input wide" id="ucTotal" placeholder="e.g. 150"></div>';
    html+='<div class="uc-row"><span class="uc-label">Billing Cycle (days):</span><input type="number" class="uc-input" id="ucDays" value="30" min="1" max="365"></div>';
    wK.forEach(function(k){html+='<div class="uc-row"><span class="uc-label">Wing '+k+' monthly units:</span><input type="number" class="uc-input" id="ucW_'+k+'" value="5" min="0" step="0.5"></div>'});
    html+='<button class="uc-calc-btn" onclick="sendCalcToPi()" '+(quotaLocked?'disabled':'')+'>'+(quotaLocked?'&#128274; Quota Locked':'&#9889; Send to Pi \u2014 Pi Will Calculate Days')+'</button>';
    inp.innerHTML=html;
  }else{
    wK.forEach(function(k){var cur=piC&&piC[k]?piC[k].target_days:0;inp.innerHTML+='<div class="uc-row"><span class="uc-label">Wing '+k+' (cur: '+cur+'d):</span><input type="number" class="uc-input" id="dy_'+k+'" value="'+cur+'" min="0" max="365"></div>'});
    inp.innerHTML+='<button class="uc-calc-btn" onclick="applyDirectDays()" '+(quotaLocked?'disabled':'')+'>'+(quotaLocked?'&#128274; Quota Locked':'&#9654; Apply Days to Pi')+'</button>'+inp.innerHTML;
  }
}

function rebuildCalc(){toggleMode(document.getElementById('ucMode').value)}

async function sendCalcToPi(){
  if(quotaLocked){sT('Quota is locked on Pi','er');return}
  var total=parseFloat(document.getElementById('ucTotal').value)||0;
  var days=parseInt(document.getElementById('ucDays').value)||30;
  if(total<=0||days<=0){sT('Enter total units and cycle days','er');return}
  var wK=getWingIds(),params='total_units='+total+'&total_days='+days;
  wK.forEach(function(k){var inp=document.getElementById('ucW_'+k);var v=inp?parseFloat(inp.value)||0:0;params+='&'+k+'='+v});
  var res=await piS('/config/set_monthly_quota?'+params);
  var resEl=document.getElementById('ucResult');
  if(res&&res.http_status===200){
    try{
      var data=JSON.parse(res.body);
      var html='<div class="uc-avg">Pi calculated: '+(data.avg_daily||0).toFixed(2)+' units/day average</div>';
      if(data.results){
        for(var k in data.results){var r=data.results[k];
          html+='<div class="uc-result-row"><span class="ucr-label">Wing '+k+'</span><span class="ucr-val">'+r.days+' days</span><span class="ucr-formula">'+r.formula+'</span></div>';}
      }
      html+='<button class="uc-lock-btn" onclick="lockQuota()">&#128274; Lock Quota for 30 Days</button>';
      resEl.innerHTML=html;resEl.style.display='block';
      sT('Pi calculated days successfully','ok');
    }catch(ex){resEl.innerHTML='<div class="uc-avg" style="color:var(--r)">Parse error: '+ex.message+'</div>';resEl.style.display='block'}
  }else{sT('Failed to send to Pi','er')}
  setTimeout(refreshPi,1000);
}

async function applyDirectDays(){
  if(quotaLocked){sT('Quota is locked on Pi','er');return}
  var wK=getWingIds(),params='';
  wK.forEach(function(k){var v=document.getElementById('dy_'+k).value||0;params+='&'+k+'='+v});
  var res=await piS('/config/days'+params);
  if(res&&res.http_status===200){
    var resEl=document.getElementById('ucResult');
    resEl.innerHTML='<div class="uc-avg">Days applied to Pi</div><button class="uc-lock-btn" onclick="lockQuota()">&#128274; Lock Quota for 30 Days</button>';
    resEl.style.display='block';
    sT('Days updated on Pi','ok');
  }else{sT('Failed','er')}
  setTimeout(refreshPi,1000);
}

async function lockQuota(){var r=await piS('/config/lock_quota?days=30');if(r&&r.http_status===200){quotaLocked=true;quotaLockUntil=JSON.parse(r.body).locked_until||'';updateLockBanner();rebuildCalc();sT('Quota locked for 30 days','ok')}else{sT('Failed to lock','er')}}
async function unlockQuota(){var r=await piS('/config/unlock_quota');if(r&&r.http_status===200){quotaLocked=false;quotaLockUntil='';updateLockBanner();rebuildCalc();sT('Quota unlocked','ok')}else{sT('Failed to unlock','er')}}
async function unlockResetDay(){var r=await piS('/config/unlock_reset_day');if(r&&r.http_status===200){resetDayLocked=false;resetDayLockUntil='';document.getElementById('rdLockInfo').textContent='';sT('Reset day unlocked','ok');refreshPi()}else{sT('Failed','er')}}

function rW(d){
  var ct=document.getElementById('wC');
  if(!d||typeof d!=='object'){ct.innerHTML='<div class="re"><div class="ri">&#127970;</div>No data</div>';return}
  var aW=d.system_active_wing||'';
  var wK=Object.keys(d).filter(function(k){return k.indexOf('system_')!==0&&typeof d[k]==='object'});
  if(!wK.length){ct.innerHTML='<div class="re">No wings found</div>';return}
  storedWingIds=wK.slice();
  ct.innerHTML='';
  wK.forEach(function(k){
    var w=d[k];if(!w)return;
    var isA=aW===k,isO=(w.meter_toggle||'').toUpperCase()==='ON',isF=w.used_days>=w.target_days,isD=w.disabled===true;
    var uD=w.used_days||0,tD=w.target_days||0,pc=tD>0?Math.min(100,Math.round(uD/tD*100)):0;
    var bc=pc>80?'r':pc>50?'y':'g',dn=w.display_name||w.name||'Wing '+k,hN='display_name' in w;
    var physT=w.physical_toggle||w.meter_toggle||'UNKNOWN';
    var physCls=physT==='ON'?'phys-on':physT==='OFF'?'phys-off':'phys-unk';
    var c=document.createElement('div');c.className='wk '+(isA?'aw':'')+(isD?' dw':'');
    var h='<div class="wt"><div class="wi">';
    h+='<span class="wid">'+k+'</span><div class="wnw"><span class="wn" id="wn_'+k+'">'+dn+'</span>';
    if(hN) h+='<input class="wni" id="wi_'+k+'" value="'+dn+'" style="display:none" data-wing="'+k+'">';
    h+='</div>';
    h+=isO?'<span class="bg on">ON</span>':'<span class="bg off">OFF</span>';
    if(isF) h+='<span class="bg fl">FULL</span>';
    if(isD) h+='<span class="bg ds">DISABLED</span>';
    if(isA) h+='<span class="bg sy">&#9733; ACTIVE</span>';
    h+='<span class="bg '+physCls+'">PHYS: '+physT+'</span>';
    h+='</div><div class="wco">';
    h+='<button class="bo" data-k="'+k+'" '+(isA&&!isD?'disabled':'')+'>SWITCH TO</button>';
    h+='<button class="bf" data-k="'+k+'" data-act="off" '+((!isA||isD)?'disabled':'')+'>TURN OFF</button>';
    if(hN){
      h+='<button class="sm rd" data-k="'+k+'" data-act="toggle">'+(isD?'&#10003; En':'&#10007; Dis')+'</button>';
      h+='<button class="sm pp" data-k="'+k+'" data-act="rename">&#9998;</button>';
      h+='<button class="sm sv" id="ws_'+k+'" style="display:none" data-k="'+k+'" data-act="savename">&#10003; Save</button>';
    }
    h+='</div></div><div class="ws">';
    h+='<div class="wsl"><span class="wsv a">'+uD+'d used</span></div>';
    h+='<div class="wsl"><span class="wsv y">'+tD+'d target</span></div>';
    h+='<div class="wsl"><span class="wsv '+bc+'">'+pc+'%</span></div>';
    if('relay_clicks' in w) h+='<div class="wsl"><span class="wsv" style="color:var(--d)">Clicks: '+w.relay_clicks+'</span></div>';
    h+='</div><div class="db"><div class="dbf '+bc+'" style="width:'+pc+'%"></div></div>';
    c.innerHTML=h;ct.appendChild(c);
  });
}

document.addEventListener('click',function(e){
  var btn=e.target.closest('[data-k]');
  if(!btn)return;
  var k=btn.getAttribute('data-k'),act=btn.getAttribute('data-act');
  if(!act){wSw(k)}
  else if(act==='off'){wOf(k)}
  else if(act==='toggle'){tDis(k)}
  else if(act==='rename'){sRN(k)}
  else if(act==='savename'){sWN(k)}
});
document.addEventListener('focusout',function(e){
  if(e.target.hasAttribute('data-wing')){cWN(e.target.getAttribute('data-wing'))}
});
async function wSw(k){await pG('/control/switch/'+k);sT('Switch to Wing '+k,'ok');setTimeout(refreshPi,1000)}
async function wOf(k){await pG('/control/off/'+k);sT('Wing '+k+' OFF','ok');setTimeout(refreshPi,1000)}
async function tDis(k){await pG('/config/toggle_disable/'+k);sT('Wing '+k+' toggled','ok');setTimeout(refreshPi,1000)}
function sRN(k){document.getElementById('wn_'+k).style.display='none';document.getElementById('wi_'+k).style.display='block';document.getElementById('ws_'+k).style.display='inline-block';document.getElementById('wi_'+k).focus();document.getElementById('wi_'+k).select()}
function cWN(k){if(piC&&piC[k]){document.getElementById('wn_'+k).style.display='inline';document.getElementById('wi_'+k).style.display='none';document.getElementById('ws_'+k).style.display='none'}}
async function sWN(k){var n=document.getElementById('wi_'+k).value.trim();if(!n){sT('Enter name','er');return}await piS('/config/set_display_name/'+k+'?name='+encodeURIComponent(n));document.getElementById('wn_'+k).style.display='inline';document.getElementById('wn_'+k).textContent=n;document.getElementById('wi_'+k).style.display='none';document.getElementById('ws_'+k).style.display='none';sT('Renamed to "'+n+'"','ok')}
async function sLcd(){var l1=document.getElementById('l1').value,l2=document.getElementById('l2').value,t=document.getElementById('lt').value||10;if(!l1&&!l2){sT('Enter text','er');return}await piS('/lcd/display?l1='+encodeURIComponent(l1)+'&l2='+encodeURIComponent(l2)+'&t='+t);sT('LCD sent','ok')}
async function cLcd(){document.getElementById('l1').value='';document.getElementById('l2').value='';document.getElementById('lcP').textContent='EMS READY';await piS('/lcd/display?l1=&l2=&t=1');sT('LCD cleared','ok')}
async function sRd(){var d=document.getElementById('rdIn').value;if(resetDayLocked){sT('Reset day is locked!','er');return}await piS('/config/set_reset_day?day='+d);sT('Reset day set to '+d+' (auto-locked 30d)','ok');setTimeout(refreshPi,1500)}
async function sAk(){var k=document.getElementById('nkIn').value;if(k.length<10){sT('Min 10 chars','er');return}await piS('/config/set_key?new_key='+encodeURIComponent(k));sT('API key changed','ok')}
async function openDays(){
  if(!piC){sT('No Pi data','er');return}
  var wK=getWingIds();if(!wK.length){sT('No wings','er');return}
  var ct=document.getElementById('dIn');ct.innerHTML='';
  wK.forEach(function(k){var w=piC[k];ct.innerHTML+='<div class="fg"><label>Wing '+k+' ('+(w.display_name||w.name||'')+')</label><input type="number" id="dy2_'+k+'" value="'+(w.target_days||0)+'" min="0" max="365"></div>'});
  document.getElementById('dMv').classList.add('sh');
}
async function aDays(){var wK=getWingIds();var p='';wK.forEach(function(k){var v=document.getElementById('dy2_'+k).value||0;p+='&'+k+'='+v});await piS('/config/days'+p);clD();sT('Days updated','ok');setTimeout(refreshPi,1000)}
function clD(){document.getElementById('dMv').classList.remove('sh')}
async function refreshPi(){await piS('/status','GET')}
async function ldSoc(){try{var r=await fetch('/api/societies');var d=await r.json();rSoc(d.societies,d.active_id)}catch(e){}}
function rSoc(s,a){var sel=document.getElementById('sSel');sel.innerHTML='<option value="">-- Select --</option>';if(s)s.forEach(function(x){sel.innerHTML+='<option value="'+x.id+'"'+(x.id===a?' selected':'')+'>'+x.name+' ('+x.target_host+':'+x.target_port+')</option>'});document.getElementById('sS').textContent=a?(s.find(function(x){return x.id===a})||{}).name||'None':'None'}
async function onSel(id){if(id){try{var r=await fetch('/api/societies/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});var d=await r.json();if(d.status==='ok'){sT('Activated: '+d.name,'ok');ldSoc();refreshPi()}else sT(d.message,'er')}catch(e){}}}
function openAdd(){eId=null;document.getElementById('mTi').textContent='Add Society';document.getElementById('iN').value='';document.getElementById('iH').value='';document.getElementById('iP').value='5000';document.getElementById('iNt').value='';document.getElementById('mOv').classList.add('sh')}
async function editSoc(id){if(!id){sT('Select first','er');return}try{var r=await fetch('/api/societies');var d=await r.json();var s=d.societies.find(function(x){return x.id===id});if(!s)return;eId=id;document.getElementById('mTi').textContent='Edit Society';document.getElementById('iN').value=s.name;document.getElementById('iH').value=s.target_host;document.getElementById('iP').value=s.target_port;document.getElementById('iNt').value=s.notes||'';document.getElementById('mOv').classList.add('sh')}catch(e){}}
function clM(){document.getElementById('mOv').classList.remove('sh')}
function stripTrailing(s){while(s.length>0&&s.charAt(s.length-1)==='/'){s=s.substring(0,s.length-1)}return s}
async function sSoc(){var n=document.getElementById('iN').value.trim();var h=document.getElementById('iH').value.trim();var p=parseInt(document.getElementById('iP').value)||80;var nt=document.getElementById('iNt').value.trim();if(!n||!h){sT('Name+host required','er');return}if(h.indexOf('https://')===0){h=h.substring(8)}else if(h.indexOf('http://')===0){h=h.substring(7)}h=stripTrailing(h);try{var r=await fetch('/api/societies/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:eId,name:n,target_host:h,target_port:p,notes:nt})});var d=await r.json();if(d.status==='ok'){clM();sT(eId?'Updated':'Added','ok');ldSoc()}else sT(d.message,'er')}catch(e){sT('Failed','er')}}
async function delSoc(){var id=document.getElementById('sSel').value;if(!id){sT('Select first','er');return}if(!confirm('Delete?'))return;try{await fetch('/api/societies/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});sT('Deleted','ok');ldSoc()}catch(e){}}
async function fSt(){try{var r=await fetch('/api/stats');var d=await r.json();document.getElementById('sT').textContent=d.total_requests;document.getElementById('sA').textContent=d.allowed;document.getElementById('sB').textContent=d.blocked;document.getElementById('sU').textContent=d.uptime_human;document.getElementById('sL').textContent=d.log_count;var el=document.getElementById('pSt'),tx=document.getElementById('pTx');if(d.proxy_running){el.className='ps on';tx.textContent='Online \u2014 '+d.active_society}else{el.className='ps off';tx.textContent='Offline'}}catch(e){}}
async function fLg(){try{var r=await fetch('/api/logs?since='+lId);var d=await r.json();if(d.logs&&d.logs.length>0){aL=aL.concat(d.logs);lId=d.next;rNL(d.logs)}}catch(e){}}
function mF(l){if(cF==='ALL')return true;if(cF==='ALLOWED'||cF==='BLOCKED')return(l.action||'')===cF;return(l.method||'')===cF}
function buildLogHtml(l){var t=l.timestamp?l.timestamp.replace('T',' ').split('.')[0]:'--';var m=l.method||'GET',u=l.url||'--',a=l.action||'ALLOWED',s=l.status_code||'-',dt=l.detail||'';return '<span class="lm">'+t+'</span><span class="lme '+m+'">'+m+'</span><span class="lu">'+u+'</span><span class="la '+a+'">'+a+'</span><span class="lst">'+s+'</span><span class="ldt">'+dt+'</span>'}
function rNL(logs){var b=document.getElementById('lBd'),em=b.querySelector('.lle');if(em)em.remove();logs.forEach(function(l){if(!mF(l))return;var r=document.createElement('div');r.className='le';r.innerHTML=buildLogHtml(l);b.appendChild(r)});if(aS)b.scrollTop=b.scrollHeight}
function sF(btn){document.querySelectorAll('.fb').forEach(function(b){b.classList.remove('ac')});btn.classList.add('ac');cF=btn.dataset.f;reAL()}
function reAL(){var b=document.getElementById('lBd');b.innerHTML='';var f=aL.filter(mF);if(!f.length){b.innerHTML='<div class="lle"><div class="ri">&#128268;</div><p>No entries.</p></div>';return}f.forEach(function(l){var r=document.createElement('div');r.className='le';r.innerHTML=buildLogHtml(l);b.appendChild(r)})}
function tAS(){aS=!aS;document.getElementById('bAS').textContent='Auto-Scroll: '+(aS?'ON':'OFF')}
async function cLogs(){try{await fetch('/api/clear-logs',{method:'POST'});aL=[];lId=0;document.getElementById('lBd').innerHTML='<div class="lle"><div class="ri">&#128268;</div><p>Cleared.</p></div>';sT('Cleared','ok')}catch(e){}}
var sk=localStorage.getItem('ak');if(sk)document.getElementById('akIn').value=sk;
ldSoc();fSt();fLg();
setInterval(fSt,2000);setInterval(fLg,1500);setInterval(ldSoc,10000);
piTimer=setInterval(refreshPi,5000);
setTimeout(refreshPi,1500);
var _origRefresh=refreshPi;
refreshPi=async function(){
  var r=await _origRefresh();
  if(r&&r.http_status===200&&r.body&&!r.error){
    if(piTimer&&piTimer._slow){clearInterval(piTimer);piTimer=setInterval(refreshPi,5000);piTimer._slow=false}
  }else{
    if(piTimer&&!piTimer._slow){clearInterval(piTimer);piTimer=setInterval(refreshPi,30000);piTimer._slow=true}
  }
};
</script>
</body>
</html>"""


if __name__=='__main__':
    print("\n========================================\n  EMS LOCAL PROXY DASHBOARD V2.1.0\n  >>> http://localhost:8080 <<<\n========================================\n")
    app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=False)