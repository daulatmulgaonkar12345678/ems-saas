from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from bson import ObjectId

load_dotenv()

app = FastAPI(title="EMS SaaS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ems-saas-alpha.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = MongoClient(os.getenv("MONGO_URL"))
db = client["ems_saas"]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY", "default_secret_change_me")

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

@app.post("/api/seed")
def seed_db():
    if db.users.count_documents({"role": "super_admin"}) == 0:
        db.users.insert_one({
            "email": "admin@ems.com",
            "name": "Super Admin",
            "password": pwd_context.hash("admin123"),
            "role": "super_admin"
        })
        db.societies.insert_many([
            {"name": "Prestine Society", "location": "Mumbai", "plan": "Professional", "status": "active"},
            {"name": "Green Valley Apartments", "location": "Pune", "plan": "Basic", "status": "active"}
        ])
        db.users.insert_one({
            "email": "sec@prestine.com",
            "name": "Rahul Sharma",
            "password": pwd_context.hash("sec123"),
            "role": "society_admin",
            "society_id": str(db.societies.find_one({"name": "Prestine Society"})["_id"])
        })
    return {"message": "Database Seeded! Super Admin: admin@ems.com / admin123"}

@app.post("/api/auth/login")
def login(user: UserLogin):
    db_user = db.users.find_one({"email": user.email})
    if not db_user or not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    token = create_token({
        "id": str(db_user["_id"]), 
        "role": db_user["role"], 
        "society_id": db_user.get("society_id")
    })
    return {"token": token, "role": db_user["role"], "name": db_user["name"]}

@app.get("/api/super-admin/societies")
def get_societies():
    societies = list(db.societies.find({}, {"_id": 0}))
    for soc in societies:
        soc["id"] = str(soc.get("_id"))
    return societies

@app.post("/api/super-admin/societies")
def add_society(society: SocietyCreate):
    db.societies.insert_one(society.dict())
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
