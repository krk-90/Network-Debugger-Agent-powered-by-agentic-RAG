from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from debugger_agent.agent.orchestrator import orchestrate

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

class DiagnosticRequest(BaseModel):
    query: str

class DiagnosticResponse(BaseModel):
    results: dict[str, str]

@router.post("/", response_model=DiagnosticResponse)
async def run_diagnostic(request: DiagnosticRequest) -> DiagnosticResponse:
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    results = await orchestrate(query)
    return DiagnosticResponse(results=results)