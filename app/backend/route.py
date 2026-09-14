import os
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, HTTPException,Request
from slowapi import Limiter,_rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from contextlib import asynccontextmanager
from langsmith import traceable
from dotenv import load_dotenv
from pydantic import BaseModel
from supabase import create_client
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=True)
os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_PROJECT", "debugger agent")

if not os.environ.get("LANGCHAIN_API_KEY") and not os.environ.get("LANGSMITH_API_KEY"):
    print("[WARN] LANGCHAIN_API_KEY / LANGSMITH_API_KEY not set — @traceable calls will not report to LangSmith.")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY
)

from debugger_agent.agent.orchestrator import orchestrate,get_graph,is_ready
from app.backend.oauth.oauth import router as auth_router
from app.backend.oauth.security import SupabaseUser, get_current_user

limiter = Limiter(key_func=get_remote_address)

state:dict= {
    "orchestrator":None
}

@traceable(name="warm_graph")
async def _traced_warm_graph():
    await get_graph()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("configuring agent, rag, and sub-agents...")
    app.state.startup_error = None
    try:
        await _traced_warm_graph()
        print("agent is ready...")
    except Exception as e:
        import traceback
        app.state.startup_error = str(e)
        print(f"[ERROR] agent failed to initialize: {e}")
        traceback.print_exc()
        if e.__cause__:
            print("--- caused by ---")
            traceback.print_exception(type(e.__cause__), e.__cause__, e.__cause__.__traceback__)
        for sub in getattr(e, "exceptions", []):
            print("--- sub-exception ---")
            traceback.print_exception(type(sub), sub, sub.__traceback__)

    yield

    print("shutdown [clearing up]...")

router = FastAPI(title="DEBUGGER-AGENT",description="AGENT FOR DEBUGGING NETWORK ISSUES.",version="1.0.0",lifespan=lifespan)
router.state.limiter = limiter
router.add_exception_handler(RateLimitExceeded,_rate_limit_exceeded_handler)

_cors_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins_env.split(",") if o.strip()] or [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5500",
    "null", 
]

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
    status :str

@router.get("/health", response_model=HealthResponse)
@traceable(name="health")
async def get_health() -> HealthResponse:
    return HealthResponse(status="healthy" if is_ready() else "unhealthy")


from fastapi import Request, Depends, HTTPException

@router.post("/", response_model=DiagnosticResponse)
@limiter.limit("20/minute")
@traceable(name="Diagnosis")
async def run_diagnostic(
    request: Request,
    payload: DiagnosticRequest,
    user: SupabaseUser = Depends(get_current_user)
):
    query = payload.query.strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail="query must not be empty")
    if not is_ready():
        raise HTTPException(
            status_code=503,
            detail="agent is not ready")
    results = await orchestrate(query)
    try:
        answer = str(results)
        save_result = (
            supabase.table("chat_history")
            .insert({
                "user_id": str(user.id),
                "question": query,
                "answer": answer
            })
            .execute()
        )
        print("Chat saved:", save_result)
    except Exception as e:
        print(f"[CHAT HISTORY ERROR] {e}")
    return DiagnosticResponse(results=results)