"""
FastAPI wrapper: validation + rate limiting + routing only. All real work
happens in pipeline/ (called via api/queue.py's background worker).
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

from api.queue import get_job, queue_position, submit_job
from pipeline.errors import InvalidSmilesError
from pipeline.inputs import identify_vinyl_carbons

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app = FastAPI(title="kp prediction")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Wide open only because the frontend is served same-origin by this same
# process (see the mount below) - this is not a hole to reuse elsewhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SubmitRequest(BaseModel):
    smiles: str = Field(..., min_length=1, max_length=300)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/submit")
@limiter.limit("5/minute")
def submit(request: Request, body: SubmitRequest):
    smiles = body.smiles.strip()
    try:
        identify_vinyl_carbons(smiles)  # fail fast, before it ever enters the queue
    except InvalidSmilesError as e:
        raise HTTPException(400, str(e))

    job = submit_job(smiles)
    return {"job_id": job.id}


@app.get("/api/status/{job_id}")
@limiter.limit("120/minute")
def status(request: Request, job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "unknown job id")
    return {
        "job_id": job.id,
        "smiles": job.smiles,
        "stage": job.stage,
        "done": job.stage == "done",
        "failed": job.failed,
        "error": job.error,
        "queue_position": queue_position(job.id) if job.stage == "queued" else 0,
    }


@app.get("/api/result/{job_id}")
@limiter.limit("120/minute")
def result(request: Request, job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "unknown job id")
    if job.failed:
        raise HTTPException(409, job.error or "job failed")
    if job.stage != "done":
        raise HTTPException(409, "job not finished yet")
    return job.result


@app.get("/")
def index():
    return FileResponse(str(WEB_DIR / "index.html"))


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
