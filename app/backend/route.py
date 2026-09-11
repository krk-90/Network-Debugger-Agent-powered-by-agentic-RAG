import os
from pathlib import Path
from typing import Optional,List
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException,Request
from slowapi import Limiter,_rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from contextlib import asynccontextmanager
from langsmith import traceable
from dotenv import load_dotenv
from pydantic import BaseModel,Field
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2]/".env",override=True)
os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_PROJECT", "debugger agent")

if not os.environ.get("LANGCHAIN_API_KEY") and not os.environ.get("LANGSMITH_API_KEY"):
    print("[WARN] LANGCHAIN_API_KEY / LANGSMITH_API_KEY not set — @traceable calls will not report to LangSmith.")

from debugger_agent.agent.orchestrator import orchestrate,get_graph,is_ready

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
        app.state.startup_error = str(e)
        print(f"[ERROR] agent failed to initialize: {e}")

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


@router.post("/", response_model=DiagnosticResponse)
@limiter.limit("20/minute")
@traceable(name="Diagnosis")
async def run_diagnostic(request: DiagnosticRequest) -> DiagnosticResponse:
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")
    if not is_ready():
        raise HTTPException(status_code=503, detail="agent is not ready")
    results = await orchestrate(query)
    return DiagnosticResponse(results=results)