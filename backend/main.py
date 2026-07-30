import os, json, math, time
from fastapi import FastAPI, HTTPException
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
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {"users": [], "societies": [], "pi_state": {}, "pi_events": {}, "pi_commands": {}}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def next_id(items):
    if not items:
        return "1"
    return str(max(int(x.get("id", "0")) for x in items) + 1)

def create_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(days=30)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

class UserLogin(BaseModel):
    email: str
    password: str

class SocietyCreate(BaseModel):
    name: str
    location: str
    plan: str
    tailscale_ip: str = ""
    pi_port: int = 5000
    api_key: str = ""

class PiCommand(BaseModel):
    society_id: str
    command: str
    wing: str = ""

@app.post("/api/seed")
def seed_db():
    db = load_db()
    if not any(u.get("role") == "super_admin" for u in db["users"]):
        s1 = next_id(db["societies"])
        s2 = next_id(db["societies"])
        db["societies"].extend([
            {"id": s1, "name": "Prestine Society", "location": "Mumbai", "plan": "Professional", "status": "active", "tailscale_ip": "", "pi_port": 5000, "api_key": "", "society_code": "GP001"},
            {"id": s2, "name": "Green Valley Apartments", "location": "Pune", "plan": "Basic", "status": "active", "tailscale_ip": "", "pi_port": 5000, "api_key": "", "society_code": ""}
        ])
        db["users"].extend([
            {"id": next_id(db["users"]), "email": "admin@ems.com", "name": "Super Admin", "password": pwd_context.hash("admin123"), "role": "super_admin", "society_id": None},
            {"id": next_id(db["users"]), "email": "sec@prestine.com", "name": "Rahul Sharma", "password": pwd_context.hash("sec123"), "role": "society_admin", "society_id": s1}
        ])
        save_db(db)
    return {"message": "Database Seeded! admin@ems.com / admin123"}

@app.post("/api/auth/login")
def login(user: UserLogin):
    db = load_db()
    db_user = next((u for u in db["users"] if u["email"] == user.email), None)
    if not db_user or not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_token({"id": db_user["id"], "role": db_user["role"], "society_id": db_user.get("society_id")})
    return {"token": token, "role": db_user["role"], "name": db_user["name"]}

@app.get("/api/super-admin/societies")
def get_societies():
    db = load_db()
    result = []
    for s in db["societies"]:
        pi = db.get("pi_state", {}).get(s["id"])
        result.append({**s, "pi_online": pi is not None and (datetime.now() - datetime.fromisoformat(pi.get("last_sync", "2020-01-01T00:00:00"))).total_seconds() < 120, "last_sync": pi.get("last_sync") if pi else None, "active_wing": pi.get("active_wing") if pi else None, "emergency_stop": pi.get("emergency_stop", False) if pi else False})
    return result

@app.post("/api/super-admin/societies")
def add_society(society: SocietyCreate):
    db = load_db()
    new_soc = {"id": next_id(db["societies"]), "name": society.name, "location": society.location, "plan": society.plan, "status": "active", "tailscale_ip": society.tailscale_ip, "pi_port": society.pi_port, "api_key": society.api_key, "society_code": ""}
    db["societies"].append(new_soc)
    save_db(db)
    return {"message": "Society added"}

@app.post("/api/super-admin/societies/update")
def update_society(data: dict):
    db = load_db()
    sid = data.get("id")
    for s in db["societies"]:
        if s["id"] == sid:
            for k in ["name", "location", "plan", "tailscale_ip", "api_key", "society_code"]:
                if k in data:
                    s[k] = data[k]
            if "pi_port" in data:
                s["pi_port"] = int(data["pi_port"])
            break
    save_db(db)
    return {"message": "Updated"}

@app.post("/api/super-admin/societies/delete")
def delete_society(data: dict):
    db = load_db()
    sid = data.get("id")
    db["societies"] = [s for s in db["societies"] if s["id"] != sid]
    db.get("pi_state", {}).pop(sid, None)
    db.get("pi_events", {}).pop(sid, None)
    db.get("pi_commands", {}).pop(sid, None)
    save_db(db)
    return {"message": "Deleted"}

@app.post("/api/pi/sync")
def pi_sync(payload: dict):
    society_id = payload.get("societyId", "")
    if not society_id:
        return {"success": False, "message": "Missing societyId"}
    db = load_db()
    society = next((s for s in db["societies"] if s["id"] == society_id or s.get("society_code") == society_id), None)
    if not society:
        sid = next_id(db["societies"])
        society = {"id": sid, "name": payload.get("societyName", society_id), "location": "Auto-detected", "plan": "Basic", "status": "active", "tailscale_ip": "", "pi_port": 5000, "api_key": payload.get("key", ""), "society_code": society_id}
        db["societies"].append(society)
        society_id = sid
    if payload.get("key"):
        society["api_key"] = payload["key"]
    wings = {}
    for wid, w in payload.get("wings", {}).items():
        wings[wid] = {"name": w.get("name", wid), "used_days": w.get("usedDays", 0), "target_days": w.get("targetDays", 0), "clicks": w.get("clicks", 0)}
    pi_state = {"active_wing": payload.get("activeWing"), "wings": wings, "reset_day": payload.get("resetDay", 22), "emergency_stop": payload.get("emergencyStop", False), "firmware_version": payload.get("firmwareVersion", "unknown"), "uptime_seconds": payload.get("uptimeSeconds", 0), "cpu_temp": payload.get("cpuTemp", 0), "disk_free_mb": payload.get("diskFreeMB", 0), "last_sync": datetime.now().isoformat(), "boot_count": payload.get("bootCount", 0), "last_shutdown_reason": payload.get("lastShutdownReason", ""), "clock_source": payload.get("clockSource", "unknown"), "locked": payload.get("locked", False), "pending_start": payload.get("pendingStart", False)}
    if "pi_state" not in db:
        db["pi_state"] = {}
    db["pi_state"][society_id] = pi_state
    if "pi_events" not in db:
        db["pi_events"] = {}
    if society_id not in db["pi_events"]:
        db["pi_events"][society_id] = []
    for ev in payload.get("events", []):
        db["pi_events"][society_id].append(ev)
    if len(db["pi_events"][society_id]) > 500:
        db["pi_events"][society_id] = db["pi_events"][society_id][-500:]
    reply = {"success": True, "command": None}
    cmds = db.get("pi_commands", {})
    if society_id in cmds and cmds[society_id].get("command"):
        reply = {"success": True, "command": cmds[society_id]["command"]}
        if cmds[society_id].get("wing"):
            reply["wing"] = cmds[society_id]["wing"]
        cmds[society_id] = {"command": None, "wing": None, "queued_at": None}
    save_db(db)
    return reply

@app.post("/api/admin/pi-command")
def queue_command(cmd: PiCommand):
    db = load_db()
    if "pi_commands" not in db:
        db["pi_commands"] = {}
    db["pi_commands"][cmd.society_id] = {"command": cmd.command, "wing": cmd.wing, "queued_at": datetime.now().isoformat()}
    save_db(db)
    return {"success": True, "message": "Command queued"}

@app.get("/api/admin/pi-state")
def get_pi_state(society_id: str):
    db = load_db()
    state = db.get("pi_state", {}).get(society_id)
    if not state:
        return {"connected": False}
    return {"connected": True, **state}

@app.get("/api/admin/pi-events")
def get_pi_events(society_id: str, since: int = 0):
    db = load_db()
    events = db.get("pi_events", {}).get(society_id, [])
    return {"events": events[since:], "total": len(events), "next": len(events)}

@app.get("/api/admin/dashboard")
def admin_dashboard():
    return {"active_wing": "A", "wings": {"A": {"used_days": 5, "target_days": 10, "status": "ACTIVE"}, "B": {"used_days": 2, "target_days": 10, "status": "IDLE"}, "C": {"used_days": 10, "target_days": 10, "status": "FULL"}, "D": {"used_days": 0, "target_days": 10, "status": "OFF"}}}
