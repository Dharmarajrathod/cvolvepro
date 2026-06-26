import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import urlparse
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from pydantic import ValidationError
from .ai_career import extract_resume_text, generate_questions, grade_interview, score_resume
from .config import get_settings
from .schemas import InterviewFeedbackRequest, InterviewStartRequest, JobResult, JobSearchRequest, JobSearchResponse
from .search import NvidiaAPIError, search_jobs

settings = get_settings()
requests_by_ip: dict[str, deque[float]] = defaultdict(deque)

def parse_selected_job(payload: Optional[str], fallback: Optional[dict] = None) -> JobResult:
    fallback = fallback or {}
    try:
        data = json.loads(payload or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data = {**fallback, **{key: value for key, value in data.items() if value not in (None, "")}}
    apply_url = str(data.get("apply_url") or "").strip()
    parsed_url = urlparse(apply_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        apply_url = "https://example.com/selected-role"
    try:
        match_score = int(data.get("match_score") or 0)
    except (TypeError, ValueError):
        match_score = 0
    skills = data.get("skills")
    if not isinstance(skills, list):
        skills = []
    normalized = {
        "id": str(data.get("id") or f'{data.get("company", "company")}-{data.get("title", "role")}'),
        "title": str(data.get("title") or "Selected role"),
        "company": str(data.get("company") or "Selected company"),
        "location": str(data.get("location") or "Not specified"),
        "work_mode": str(data.get("work_mode") or "Not specified"),
        "employment_type": str(data.get("employment_type") or "Not specified"),
        "salary": str(data.get("salary")) if data.get("salary") else None,
        "experience": str(data.get("experience")) if data.get("experience") else None,
        "posted_at": str(data.get("posted_at")) if data.get("posted_at") else None,
        "skills": [str(skill) for skill in skills if skill],
        "summary": str(data.get("summary") or data.get("description") or "No job summary was provided."),
        "match_score": max(0, min(100, match_score)),
        "match_reason": str(data.get("match_reason") or "Selected for ATS scoring."),
        "apply_url": apply_url,
        "source": str(data.get("source") or "CvolvePro"),
    }
    try:
        return JobResult.model_validate(normalized)
    except ValidationError:
        normalized["apply_url"] = "https://example.com/selected-role"
        normalized["posted_at"] = None
        normalized["skills"] = []
        return JobResult.model_validate(normalized)

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield

app = FastAPI(title="CvolvePro API", version="1.0.0", lifespan=lifespan, docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["GET","POST"], allow_headers=["Content-Type"])

@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        ip = request.client.host if request.client else "unknown"; now = time.monotonic(); bucket = requests_by_ip[ip]
        while bucket and now - bucket[0] > 60: bucket.popleft()
        if len(bucket) >= 10: return JSONResponse({"detail":"Too many searches. Please wait a minute."}, status_code=429)
        bucket.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

@app.get("/health")
async def health(): return {"status":"ok", "service":"cvolvepro-api"}

@app.post("/api/jobs/search", response_model=JobSearchResponse)
async def job_search(body: JobSearchRequest):
    try: return await search_jobs(body, settings)
    except NvidiaAPIError as exc:
        if exc.status_code in {401, 403}: raise HTTPException(503, "The NVIDIA API key is invalid.")
        if exc.status_code == 429: raise HTTPException(429, "NVIDIA NIM is busy. Please try again shortly.")
        raise HTTPException(502, "NVIDIA NIM returned an error.")
    except httpx.TimeoutException: raise HTTPException(504, "NVIDIA NIM took too long to respond. Please retry.")
    except httpx.HTTPError: raise HTTPException(502, "Could not connect to NVIDIA NIM.")
    except (ValueError, TypeError): raise HTTPException(502, "The live search response could not be validated.")

@app.post("/api/ats-score")
async def ats_score(
    resume: UploadFile = File(...),
    job: Optional[str] = Form(default=None),
    title: str = Form(default="Selected role"),
    company: str = Form(default="Selected company"),
    location: str = Form(default="Not specified"),
    work_mode: str = Form(default="Not specified"),
    employment_type: str = Form(default="Not specified"),
    salary: Optional[str] = Form(default=None),
    experience: Optional[str] = Form(default=None),
    posted_at: Optional[str] = Form(default=None),
    skills: str = Form(default="[]"),
    summary: str = Form(default="No job summary was provided."),
    match_score: str = Form(default="0"),
    match_reason: str = Form(default="Selected for ATS scoring."),
    apply_url: str = Form(default="https://example.com/selected-role"),
    source: str = Form(default="CvolvePro"),
):
    try:
        try:
            parsed_skills = json.loads(skills)
        except json.JSONDecodeError:
            parsed_skills = []
        try:
            parsed_job = parse_selected_job(job, {
                "title": title,
                "company": company,
                "location": location,
                "work_mode": work_mode,
                "employment_type": employment_type,
                "salary": salary,
                "experience": experience,
                "posted_at": posted_at,
                "skills": parsed_skills,
                "summary": summary,
                "match_score": match_score,
                "match_reason": match_reason,
                "apply_url": apply_url,
                "source": source,
            })
        except (ValidationError, TypeError) as exc:
            raise HTTPException(400, f"The selected job could not be normalized: {exc}")
        resume_text = await extract_resume_text(resume)
        return await score_resume(settings, parsed_job, resume_text)
    except HTTPException:
        raise
    except ValidationError:
        raise HTTPException(502, "The ATS score response could not be validated.")
    except NvidiaAPIError as exc:
        if exc.status_code in {401, 403}: raise HTTPException(503, "The NVIDIA API key is missing or invalid.")
        if exc.status_code == 429: raise HTTPException(429, "NVIDIA NIM is busy. Please try again shortly.")
        raise HTTPException(502, "NVIDIA NIM returned an error.")
    except httpx.TimeoutException:
        raise HTTPException(504, "NVIDIA NIM took too long to respond. Please retry.")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except httpx.HTTPError:
        raise HTTPException(502, "Could not connect to NVIDIA NIM.")

@app.post("/api/interview/start")
async def interview_start(body: InterviewStartRequest):
    try:
        return await generate_questions(settings, body.job, body.resume_text, body.ats_score, body.ats_summary)
    except NvidiaAPIError as exc:
        if exc.status_code in {401, 403}: raise HTTPException(503, "The NVIDIA API key is missing or invalid.")
        if exc.status_code == 429: raise HTTPException(429, "NVIDIA NIM is busy. Please try again shortly.")
        raise HTTPException(502, "NVIDIA NIM returned an error.")
    except httpx.TimeoutException:
        raise HTTPException(504, "NVIDIA NIM took too long to respond. Please retry.")
    except httpx.HTTPError:
        raise HTTPException(502, "Could not connect to NVIDIA NIM.")

@app.post("/api/interview/feedback")
async def interview_feedback(body: InterviewFeedbackRequest):
    try:
        return await grade_interview(settings, body.job, body.resume_text, body.answers)
    except NvidiaAPIError as exc:
        if exc.status_code in {401, 403}: raise HTTPException(503, "The NVIDIA API key is missing or invalid.")
        if exc.status_code == 429: raise HTTPException(429, "NVIDIA NIM is busy. Please try again shortly.")
        raise HTTPException(502, "NVIDIA NIM returned an error.")
    except httpx.TimeoutException:
        raise HTTPException(504, "NVIDIA NIM took too long to respond. Please retry.")
    except httpx.HTTPError:
        raise HTTPException(502, "Could not connect to NVIDIA NIM.")
