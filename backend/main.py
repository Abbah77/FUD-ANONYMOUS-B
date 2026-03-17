from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import timedelta
from typing import List
import uuid

from database import supabase
from models import UserCreate, UserLogin, TokenResponse, UserResponse
from auth import verify_password, get_password_hash, create_access_token, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES

app = FastAPI(title="FUD Anonymous API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://fud-anonymous.onrender.com"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_safe_email(reg_no: str) -> str:
    """Convert REG NO to email format for unique identification"""
    return reg_no.replace("/", "_").lower() + "@fud.edu.ng"

@app.get("/")
async def root():
    return {"message": "FUD Anonymous API", "status": "running"}

@app.post("/api/auth/signup", response_model=TokenResponse)
async def signup(user_data: UserCreate):
    try:
        # Check if user already exists
        existing = supabase.table("users").select("*").eq("reg_no", user_data.reg_no).execute()
        
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration number already exists"
            )
        
        # Create user in Supabase Auth (optional) and in users table
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(user_data.password)
        
        # Insert into users table
        user_record = {
            "id": user_id,
            "full_name": user_data.full_name,
            "reg_no": user_data.reg_no,
            "email": get_safe_email(user_data.reg_no),
            "hashed_password": hashed_password,
            "created_at": "now()"
        }
        
        result = supabase.table("users").insert(user_record).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user_id}, expires_delta=access_token_expires
        )
        
        user_response = UserResponse(
            id=user_id,
            full_name=user_data.full_name,
            reg_no=user_data.reg_no,
            created_at=result.data[0]["created_at"]
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(login_data: UserLogin):
    try:
        # Find user by reg_no
        result = supabase.table("users").select("*").eq("reg_no", login_data.reg_no).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid registration number or password"
            )
        
        user = result.data[0]
        
        # Verify password
        if not verify_password(login_data.password, user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid registration number or password"
            )
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["id"]}, expires_delta=access_token_expires
        )
        
        user_response = UserResponse(
            id=user["id"],
            full_name=user["full_name"],
            reg_no=user["reg_no"],
            created_at=user["created_at"]
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        full_name=current_user["full_name"],
        reg_no=current_user["reg_no"],
        created_at=current_user["created_at"]
    )

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}
