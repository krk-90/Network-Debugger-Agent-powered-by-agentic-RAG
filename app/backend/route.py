import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langsmith import traceable
from dotenv import load_dotenv
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from supabase import create_client
from mcp.server.transport_security import TransportSecuritySettings

from debugger_agent.agent.mcp_server.server import mcp
from debugger_agent.agent.orchestrator import orchestrate
from app.backend.oauth.oauth import router as auth_router
from app.backend.oauth.security import SupabaseUser, get_current_user

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=True)
os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_PROJECT", "debugger agent")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

limiter = Limiter(key_func=get_remote_address)
BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = BASE_DIR / "app" / "frontend" / "dist"

render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "localhost")
mcp.settings.host = os.getenv("NETWORK_MCP_HOST", "0.0.0.0")
mcp.settings.port = int(os.getenv("PORT", os.getenv("NETWORK_MCP_PORT", "10000")))
mcp.settings.streamable_http_path = "/mcp"
mcp.settings.transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[render_hostname, f"{render_hostname}:*", "localhost:*", "127.0.0.1:*"],
    allowed_origins=[os.getenv("NETWORK_MCP_ALLOWED_ORIGIN", "http://localhost:5173")],
)
mcp_http_app = mcp.streamable_http_app()

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.startup_error = None
    print("Starting unified Network Debugger service...")
    print(f"Frontend dist: {FRONTEND_DIST}")
    print("MCP endpoint: /mcp")
    async with mcp.session_manager.run():
        yield
    print("shutdown [clearing up]...")

router = FastAPI(
    title="DEBUGGER-AGENT",
    description="AI agent for debugging network issues.",
    version="1.0.0",
    lifespan=lifespan,
)
router.state.limiter = limiter
router.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]

router.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
router.include_router(auth_router)

class DiagnosticRequest(BaseModel):
    query: str

class DiagnosticResponse(BaseModel):
    results: dict[str, str]

class HealthResponse(BaseModel):
    status: str

@router.get("/health", response_model=HealthResponse)
@traceable(name="health")
async def get_health() -> HealthResponse:
    return HealthResponse(status="healthy")

@router.get("/history")
async def get_history(user: SupabaseUser = Depends(get_current_user)):
    try:
        response = (
            supabase.table("chat_history")
            .select("id, question, answer, created_at")
            .eq("user_id", str(user.id))
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        return {"history": response.data or []}
    except Exception as error:
        print(f"[CHAT HISTORY READ ERROR] {error}")
        raise HTTPException(status_code=500, detail="Unable to load history")

@router.post("/", response_model=DiagnosticResponse)
@limiter.limit("20/minute")
@traceable(name="Diagnosis")
async def run_diagnostic(
    request: Request,
    payload: DiagnosticRequest,
    user: SupabaseUser = Depends(get_current_user),
):
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    try:
        results = await orchestrate(query)
    except Exception as error:
        print(f"[DIAGNOSIS ERROR] {type(error).__name__}: {error}")
        raise HTTPException(
            status_code=502,
            detail=f"Diagnosis service failed: {type(error).__name__}: {error}",
        ) from error

    try:
        supabase.table("chat_history").insert({
            "user_id": str(user.id),
            "question": query,
            "answer": str(results),
        }).execute()
    except Exception as error:
        print(f"[CHAT HISTORY ERROR] {error}")

    return DiagnosticResponse(results=results)

router.mount("/mcp", mcp_http_app)

ASSETS_DIR = FRONTEND_DIST / "assets"
if ASSETS_DIR.exists():
    router.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="frontend-assets")

@router.get("/", include_in_schema=False)
async def frontend_root():
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=503, detail="Frontend bundle is not built")
    return FileResponse(index)

@router.get("/{path:path}", include_in_schema=False)
async def frontend_fallback(path: str):
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle is not built")
    return FileResponse(index)
