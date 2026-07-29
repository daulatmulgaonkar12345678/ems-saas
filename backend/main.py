import os, json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta

app = FastAPI(title="EMS SaaS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.json")
SECRET_KEY = os.getenv("SECRET_KEY", "ems_super_secret_2026")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {"users": [], "societies": []}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

class UserLogin(BaseModel):
    email: str
    password: str

class SocietyCreate(BaseModel):
    name: str
    location: str
    plan: str

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

def next_id(items):
    if not items:
        return "1"
    return str(max(int(x.get("id", "0")) for x in items) + 1)

@app.post("/api/seed")
def seed_db():
    db = load_db()
    if not any(u.get("role") == "super_admin" for u in db["users"]):
        soc_id_1 = next_id(db["societies"])
        soc_id_2 = next_id(db["societies"])
        db["societies"].extend([
            {"id": soc_id_1, "name": "Prestine Society", "location": "Mumbai", "plan": "Professional", "status": "active"},
            {"id": soc_id_2, "name": "Green Valley Apartments", "location": "Pune", "plan": "Basic", "status": "active"}
        ])
        db["users"].extend([
            {"id": next_id(db["users"]), "email": "admin@ems.com", "name": "Super Admin", "password": pwd_context.hash("admin123"), "role": "super_admin"},
            {"id": next_id(db["users"]), "email": "sec@prestine.com", "name": "Rahul Sharma", "password": pwd_context.hash("sec123"), "role": "society_admin", "society_id": soc_id_1}
        ])
        save_db(db)
    return {"message": "Database Seeded! admin@ems.com / admin123"}

@app.post("/api/auth/login")
def login(user: UserLogin):
    db = load_db()
    db_user = next((u for u in db["users"] if u["email"] == user.email), None)
    if not db_user or not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_token({
        "id": db_user["id"],
        "role": db_user["role"],
        "society_id": db_user.get("society_id")
    })
    return {"token": token, "role": db_user["role"], "name": db_user["name"]}

@app.get("/api/super-admin/societies")
def get_societies():
    db = load_db()
    return db["societies"]

@app.post("/api/super-admin/societies")
def add_society(society: SocietyCreate):
    db = load_db()
    new_soc = {"id": next_id(db["societies"]), "name": society.name, "location": society.location, "plan": society.plan, "status": "active"}
    db["societies"].append(new_soc)
    save_db(db)
    return {"message": "Society added successfully"}

@app.get("/api/admin/dashboard")
def get_dashboard():
    return {
        "active_wing": "A",
        "wings": {
            "A": {"used_days": 5, "target_days": 10, "status": "ACTIVE"},
            "B": {"used_days": 2, "target_days": 10, "status": "IDLE"},
            "C": {"used_days": 10, "target_days": 10, "status": "FULL"},
            "D": {"used_days": 0, "target_days": 10, "status": "OFF"}
        }
    }
