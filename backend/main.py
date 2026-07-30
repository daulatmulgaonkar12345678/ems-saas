import os, json
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta

app = FastAPI(title="EMS SaaS API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.json")
SECRET_KEY = os.getenv("SECRET_KEY", "ems_super_secret_2026")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return json.load(f)
    return {"users": [], "societies": [], "pi_state": {}, "pi_events": {}, "pi_commands": {}, "firmware_versions": []}

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=2)

def next_id(items):
    if not items: return "1"
    return str(max(int(x.get("id", "0")) for x in items) + 1)

def create_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(days=30)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

def version_gt(v1, v2):
    try:
        p1 = [int(x) for x in str(v1).split(".")]
        p2 = [int(x) for x in str(v2).split(".")]
        for a, b in zip(p1, p2):
            if a > b: return True
            if a < b: return False
        return len(p1) > len(p2)
    except: return False

class UserLogin(BaseModel):
    email: str
    password: str

@app.post("/api/seed")
def seed_db():
    db = load_db()
    if not any(u.get("role") == "super_admin" for u in db["users"]):
        s1 = next_id(db["societies"])
        db["societies"].append({"id": s1, "name": "Prestine Society", "location": "Mumbai", "plan": "Professional", "status": "active", "tailscale_ip": "", "pi_port": 5000, "api_key": "", "society_code": "1"})
        db["users"].extend([
            {"id": next_id(db["users"]), "email": "admin@ems.com", "name": "Super Admin", "password": pwd_context.hash("admin123"), "role": "super_admin", "society_id": None},
            {"id": next_id(db["users"]), "email": "sec@prestine.com", "name": "Rahul Sharma", "password": pwd_context.hash("sec123"), "role": "society_admin", "society_id": s1},
            {"id": next_id(db["users"]), "email": "member@prestine.com", "name": "Amit Patel", "password": pwd_context.hash("member123"), "role": "member", "society_id": s1},
        ])
        save_db(db)
    return {"message": "Seeded! admin@ems.com / sec@prestine.com / member@prestine.com"}

@app.post("/api/auth/login")
def login(user: UserLogin):
    db = load_db()
    db_user = next((u for u in db["users"] if u["email"] == user.email), None)
    if not db_user or not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_token({"id": db_user["id"], "role": db_user["role"], "society_id": db_user.get("society_id")})
    return {"token": token, "role": db_user["role"], "name": db_user["name"], "society_id": db_user.get("society_id")}

@app.get("/api/super-admin/societies")
def get_societies():
    db = load_db()
    result = []
    for s in db["societies"]:
        pi = db.get("pi_state", {}).get(s["id"])
        online = pi and (datetime.now() - datetime.fromisoformat(pi.get("last_sync", "2020-01-01T00:00:00"))).total_seconds() < 120
        result.append({"id": s["id"], "name": s["name"], "location": s["location"], "plan": s["plan"], "status": s.get("status", "active"), "tailscale_ip": s.get("tailscale_ip", ""), "pi_port": s.get("pi_port", 5000), "api_key": s.get("api_key", ""), "society_code": s.get("society_code", ""), "pi_online": online, "last_sync": pi.get("last_sync") if pi else None, "active_wing": pi.get("active_wing") if pi else None, "emergency_stop": pi.get("emergency_stop", False) if pi else False, "firmware_version": pi.get("firmware_version", "?") if pi else None})
    return result

@app.post("/api/super-admin/societies/save")
def save_society(data: dict):
    db = load_db()
    sid = data.get("id")
    society = {"name": data["name"], "location": data["location"], "plan": data["plan"], "status": "active", "tailscale_ip": data.get("tailscale_ip", ""), "pi_port": int(data.get("pi_port", 5000)), "api_key": data.get("api_key", ""), "society_code": data.get("society_code", "")}
    if sid:
        for s in db["societies"]:
            if s["id"] == sid: s.update(society); break
    else:
        society["id"] = next_id(db["societies"])
        db["societies"].append(society)
    save_db(db)
    return {"message": "Saved"}

@app.post("/api/super-admin/societies/delete")
def delete_society(data: dict):
    db = load_db()
    sid = data.get("id")
    db["societies"] = [s for s in db["societies"] if s["id"] != sid]
    for key in ["pi_state", "pi_events", "pi_commands"]:
        db.get(key, {}).pop(sid, None)
    db["users"] = [u for u in db["users"] if u.get("society_id") != sid]
    save_db(db)
    return {"message": "Deleted"}

@app.get("/api/super-admin/users")
def get_users():
    db = load_db()
    users = []
    for u in db["users"]:
        soc = next((s for s in db["societies"] if s["id"] == u.get("society_id")), None)
        users.append({"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"], "society_name": soc["name"] if soc else "None", "society_id": u.get("society_id")})
    return users

@app.post("/api/super-admin/users/save")
def save_user(data: dict):
    db = load_db()
    uid = data.get("id")
    if uid:
        for u in db["users"]:
            if u["id"] == uid:
                if data.get("password"): u["password"] = pwd_context.hash(data["password"])
                for k in ["email", "name", "role", "society_id"]:
                    if k in data and k != "password": u[k] = data[k]
                break
    else:
        if not data.get("password"): raise HTTPException(400, "Password required")
        user = {"id": next_id(db["users"]), "email": data["email"], "name": data["name"], "role": data["role"], "society_id": data.get("society_id") or None, "password": pwd_context.hash(data["password"])}
        db["users"].append(user)
    save_db(db)
    return {"message": "Saved"}

@app.post("/api/super-admin/users/delete")
def delete_user(data: dict):
    db = load_db()
    db["users"] = [u for u in db["users"] if u["id"] != data.get("id")]
    save_db(db)
    return {"message": "Deleted"}

@app.get("/api/super-admin/firmware/versions")
def get_firmware_versions():
    db = load_db()
    versions = db.get("firmware_versions", [])
    for v in versions: v.pop("code", None)
    return versions

@app.post("/api/super-admin/firmware/save")
def save_firmware_version(data: dict):
    db = load_db()
    version = data.get("version", "").strip()
    code = data.get("code", "")
    changelog = data.get("changelog", "")
    forced = data.get("forced", False)
    if not version or not code: raise HTTPException(400, "Version and code required")
    if "firmware_versions" not in db: db["firmware_versions"] = []
    existing = next((v for v in db["firmware_versions"] if v["version"] == version), None)
    if existing:
        existing["code"] = code
        existing["changelog"] = changelog
        existing["forced"] = forced
        existing["updated_at"] = datetime.now().isoformat()
    else:
        db["firmware_versions"].insert(0, {"version": version, "code": code, "changelog": changelog, "forced": forced, "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()})
    if forced:
        for v in db["firmware_versions"]:
            if v["version"] != version: v["forced"] = False
    save_db(db)
    return {"message": "Saved"}

@app.post("/api/super-admin/firmware/delete")
def delete_firmware_version(data: dict):
    db = load_db()
    version = data.get("version")
    db["firmware_versions"] = [v for v in db.get("firmware_versions", []) if v["version"] != version]
    save_db(db)
    return {"message": "Deleted"}

@app.post("/api/super-admin/firmware/force")
def force_firmware(data: dict):
    db = load_db()
    version = data.get("version")
    if "firmware_versions" not in db: db["firmware_versions"] = []
    for v in db["firmware_versions"]:
        v["forced"] = (v["version"] == version)
    save_db(db)
    return {"message": "Force flag updated"}

@app.post("/api/pi/sync")
def pi_sync(payload: dict):
    sid = payload.get("societyId", "")
    db = load_db()
    society = next((s for s in db["societies"] if s["id"] == sid), None)
    if not society:
        society = next((s for s in db["societies"] if s.get("society_code") == sid), None)
    if not society:
        new_id = next_id(db["societies"])
        society = {"id": new_id, "name": payload.get("societyName", sid), "location": "Auto-detected", "plan": "Basic", "status": "active", "tailscale_ip": "", "pi_port": 5000, "api_key": payload.get("key", ""), "society_code": sid}
        db["societies"].append(society)
        sid = new_id
    else:
        sid = society["id"]
    if payload.get("key"): society["api_key"] = payload["key"]
    wings = {wid: {"name": w.get("name", wid), "used_days": w.get("usedDays", 0), "target_days": w.get("targetDays", 0), "clicks": w.get("clicks", 0)} for wid, w in payload.get("wings", {}).items()}
    pi_state = {"active_wing": payload.get("activeWing"), "wings": wings, "reset_day": payload.get("resetDay", 22), "emergency_stop": payload.get("emergencyStop", False), "firmware_version": payload.get("firmwareVersion", "?"), "uptime_seconds": payload.get("uptimeSeconds", 0), "cpu_temp": payload.get("cpuTemp", 0), "disk_free_mb": payload.get("diskFreeMB", 0), "last_sync": datetime.now().isoformat(), "boot_count": payload.get("bootCount", 0), "last_shutdown_reason": payload.get("lastShutdownReason", ""), "clock_source": payload.get("clockSource", ""), "locked": payload.get("locked", False), "pending_start": payload.get("pendingStart", False)}
    if "pi_state" not in db: db["pi_state"] = {}
    db["pi_state"][sid] = pi_state
    if "pi_events" not in db: db["pi_events"] = {}
    if sid not in db["pi_events"]: db["pi_events"][sid] = []
    for ev in payload.get("events", []): db["pi_events"][sid].append(ev)
    if len(db["pi_events"][sid]) > 500: db["pi_events"][sid] = db["pi_events"][sid][-500:]
    reply = {"success": True, "command": None}
    cmds = db.get("pi_commands", {})
    if sid in cmds and cmds[sid].get("command"):
        reply["command"] = cmds[sid]["command"]
        if cmds[sid].get("wing"): reply["wing"] = cmds[sid]["wing"]
        cmds[sid] = {"command": None, "wing": None, "queued_at": None}
    fw_versions = db.get("firmware_versions", [])
    pi_ver = payload.get("firmwareVersion", "0.0.0")
    forced_fw = next((v for v in fw_versions if v.get("forced")), None)
    latest_fw = fw_versions[0] if fw_versions else None
    target_fw = forced_fw or latest_fw
    if target_fw and version_gt(target_fw["version"], pi_ver):
        reply["firmware_update"] = {"version": target_fw["version"], "forced": target_fw.get("forced", False), "changelog": target_fw.get("changelog", "")}
    save_db(db)
    return reply

@app.get("/api/pi/firmware-download")
def download_firmware(version: str, key: str = ""):
    db = load_db()
    if key:
        society = next((s for s in db["societies"] if s.get("api_key") == key), None)
        if not society: raise HTTPException(403, "Invalid API key")
    fv = next((v for v in db.get("firmware_versions", []) if v["version"] == version), None)
    if not fv: raise HTTPException(404, "Version not found")
    return PlainTextResponse(fv["code"], media_type="text/plain")

@app.post("/api/admin/pi-command")
def queue_command(data: dict):
    db = load_db()
    sid = data.get("society_id")
    if "pi_commands" not in db: db["pi_commands"] = {}
    db["pi_commands"][sid] = {"command": data.get("command"), "wing": data.get("wing", ""), "queued_at": datetime.now().isoformat()}
    save_db(db)
    return {"success": True, "message": "Command queued"}

@app.get("/api/admin/pi-state")
def get_pi_state(society_id: str):
    db = load_db()
    state = db.get("pi_state", {}).get(society_id)
    if not state: return {"connected": False}
    return {"connected": True, **state}

@app.get("/api/admin/pi-events")
def get_pi_events(society_id: str, since: int = 0):
    db = load_db()
    events = db.get("pi_events", {}).get(society_id, [])
    return {"events": events[since:], "total": len(events), "next": len(events)}

@app.get("/api/admin/dashboard")
def admin_dashboard():
    return {"active_wing": "A", "wings": {"A": {"used_days": 5, "target_days": 10, "status": "ACTIVE"}, "B": {"used_days": 2, "target_days": 10, "status": "IDLE"}, "C": {"used_days": 10, "target_days": 10, "status": "FULL"}, "D": {"used_days": 0, "target_days": 10, "status": "OFF"}}}
