import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from dotenv import load_dotenv
from pydantic import BaseModel
from supabase import create_client
from app.backend.oauth.security import SupabaseUser, get_current_user

load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / ".env", override=True)

router = APIRouter(prefix="/auth", tags=["auth"])
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: SupabaseUser

class SignupResponse(BaseModel):
    message: str
    user: SupabaseUser
    access_token: str | None = None

def save_login(user: SupabaseUser) -> None:
    supabase.table("user_accounts").upsert(
        {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "last_login_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="id",
    ).execute()

@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(body: LoginRequest):
    try:
        result = supabase.auth.sign_up({
            "email": str(body.email),
            "password": body.password,
        })
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to create account")

    if not result.user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to create account")

    user = SupabaseUser(
        id=str(result.user.id),
        email=result.user.email,
        role=(result.user.user_metadata or {}).get("role"),
    )
    try:
        save_login(user)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Account profile could not be saved")

    if result.session:
        return SignupResponse(
            message="Account created and logged in",
            user=user,
            access_token=result.session.access_token,
        )

    return SignupResponse(
        message="Account created. Check your email to confirm your account.",
        user=user,
    )

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    try:
        result = supabase.auth.sign_in_with_password({
            "email": str(body.email),
            "password": body.password,
        })
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not result.session or not result.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login failed")

    user = SupabaseUser(
        id=str(result.user.id),
        email=result.user.email,
        role=(result.user.user_metadata or {}).get("role"),
    )
    try:
        save_login(user)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Account profile could not be saved")
    return LoginResponse(access_token=result.session.access_token, user=user)

@router.get("/me", response_model=SupabaseUser)
async def me(user: SupabaseUser = Depends(get_current_user)):
    return user