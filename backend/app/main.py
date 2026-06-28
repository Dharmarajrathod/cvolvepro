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
from .auth import authenticate_user, consume_verification_code, create_user, get_public_user, init_auth_database, require_user_credits, reset_user_password, send_plan_purchase_email, send_verification_code, spend_user_credits, update_user_plan
from .config import get_settings
from .payments import FREE_PLAN_CREDITS, STRIPE_PLANS, create_checkout_session, retrieve_checkout_session
from .schemas import AuthUserResponse, CheckoutSessionResponse, ConfirmCheckoutSessionRequest, CreateCheckoutSessionRequest, InterviewFeedbackRequest, InterviewStartRequest, JobResult, JobSearchRequest, JobSearchResponse, LoginRequest, RegisterRequest, ResetPasswordRequest, SelectFreePlanRequest, SendVerificationCodeRequest
from .search import NvidiaAPIError, search_jobs

settings = get_settings()
requests_by_ip: dict[str, deque[float]] = defaultdict(deque)
RATE_LIMIT_REQUESTS = 30

def rate_limit_response(request: Request) -> JSONResponse:
    response = JSONResponse({"detail":"Too many searches. Please wait a minute."}, status_code=429)
    origin = request.headers.get("origin")
    if origin in settings.origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response

def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"

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
    await init_auth_database(settings.database_url)
    yield

app = FastAPI(title="CvolvePro API", version="1.0.0", lifespan=lifespan, docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["GET","POST"], allow_headers=["Content-Type"])

@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method != "OPTIONS":
        ip = request.client.host if request.client else "unknown"; now = time.monotonic(); bucket = requests_by_ip[ip]
        while bucket and now - bucket[0] > 60: bucket.popleft()
        if len(bucket) >= RATE_LIMIT_REQUESTS: return rate_limit_response(request)
        bucket.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

@app.get("/health")
async def health(): return {"status":"ok", "service":"cvolvepro-api"}

@app.post("/api/auth/send-code")
async def auth_send_code(body: SendVerificationCodeRequest):
    await send_verification_code(settings, body.email)
    return {"detail": "Verification code sent."}

@app.post("/api/auth/register", response_model=AuthUserResponse)
async def auth_register(body: RegisterRequest, request: Request):
    await consume_verification_code(body.email, body.verification_code)
    return await create_user(body.name, body.email, body.password, body.mobile_number, body.country, body.account_type, client_ip(request))

@app.post("/api/auth/login", response_model=AuthUserResponse)
async def auth_login(body: LoginRequest, request: Request):
    return await authenticate_user(body.email, body.password, client_ip(request))

@app.post("/api/auth/reset-password", response_model=AuthUserResponse)
async def auth_reset_password(body: ResetPasswordRequest):
    await consume_verification_code(body.email, body.verification_code)
    return await reset_user_password(body.email, body.password)

@app.post("/api/payments/create-checkout-session", response_model=CheckoutSessionResponse)
async def payments_create_checkout_session(body: CreateCheckoutSessionRequest):
    if not body.email:
        raise HTTPException(401, "Login is required before payment.")
    user = await get_public_user(body.email)
    is_business_plan = body.plan_id.startswith("business_")
    if user.get("account_type") == "personal" and is_business_plan:
        raise HTTPException(403, "Personal accounts can only choose personal plans.")
    if user.get("account_type") == "business" and not is_business_plan:
        raise HTTPException(403, "Business accounts can only choose business plans.")
    return await create_checkout_session(settings, body.plan_id, body.email)

@app.post("/api/payments/select-free-plan", response_model=AuthUserResponse)
async def payments_select_free_plan(body: SelectFreePlanRequest):
    user = await get_public_user(body.email)
    if user.get("account_type") != "personal":
        raise HTTPException(403, "The free plan is only available for personal accounts.")
    return await update_user_plan(body.email, "free", FREE_PLAN_CREDITS)

@app.post("/api/payments/confirm-session", response_model=AuthUserResponse)
async def payments_confirm_session(body: ConfirmCheckoutSessionRequest):
    session = await retrieve_checkout_session(settings, body.session_id)
    if session.get("payment_status") != "paid":
        raise HTTPException(402, "Stripe payment has not completed.")
    plan_id = session.get("metadata", {}).get("plan_id")
    plan = STRIPE_PLANS.get(plan_id or "")
    if not plan:
        raise HTTPException(400, "Stripe session does not include a valid plan.")
    email = body.email or session.get("customer_details", {}).get("email") or session.get("customer_email")
    if not email:
        raise HTTPException(400, "Stripe session does not include a customer email.")
    user = await update_user_plan(email, plan_id, plan.credits)
    amount_total = session.get("amount_total") or plan.amount
    currency = (session.get("currency") or plan.currency).upper()
    amount_label = f"{currency} {amount_total / 100:,.2f}"
    await send_plan_purchase_email(settings, email, plan.name, plan.credits, amount_label)
    return user

@app.post("/api/jobs/search", response_model=JobSearchResponse)
async def job_search(body: JobSearchRequest):
    try:
        if not body.user_email:
            raise HTTPException(401, "Login is required before searching jobs.")
        await require_user_credits(body.user_email, 5, "job search")
        result = await search_jobs(body, settings)
        user = await spend_user_credits(body.user_email, 5, "job search")
        return {**result.model_dump(), "credits_remaining": user["credits"]}
    except HTTPException:
        raise
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
    user_email: Optional[str] = Form(default=None),
):
    try:
        if not user_email:
            raise HTTPException(401, "Login is required before checking ATS score.")
        await require_user_credits(user_email, 5, "ATS score")
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
        result = await score_resume(settings, parsed_job, resume_text)
        user = await spend_user_credits(user_email, 5, "ATS score")
        response = result.model_dump()
        response["credits_remaining"] = user["credits"]
        return response
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
        if not body.user_email:
            raise HTTPException(401, "Login is required before generating interview questions.")
        await require_user_credits(body.user_email, 5, "interview questions")
        result = await generate_questions(settings, body.job, body.resume_text, body.ats_score, body.ats_summary)
        user = await spend_user_credits(body.user_email, 5, "interview questions")
        return {**result, "credits_remaining": user["credits"]}
    except HTTPException:
        raise
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
