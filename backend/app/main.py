import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from .config import get_settings
from .schemas import JobSearchRequest, JobSearchResponse
from .search import NvidiaAPIError, search_jobs

settings = get_settings()
requests_by_ip: dict[str, deque[float]] = defaultdict(deque)

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
