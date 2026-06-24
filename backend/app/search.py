from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from urllib.parse import urlparse, urlunparse
import httpx
from .config import Settings
from .schemas import JobResult, JobSearchRequest, JobSearchResponse

SEARCH_SOURCES = [
    "LinkedIn Jobs", "Indeed", "Glassdoor", "Google Jobs", "Wellfound", "RemoteOK",
    "We Work Remotely", "Monster", "Dice", "Adzuna", "Naukri", "Foundit",
    "Cutshort", "Instahyre", "Internshala", "company career pages"
]

WORLD_REGIONS = [
    "United States - Northeast and Mid-Atlantic",
    "United States - South and Midwest",
    "United States - West Coast and Mountain states",
    "Canada",
    "United Kingdom and Ireland",
    "Germany, Austria, and Switzerland",
    "France, Belgium, Netherlands, and Luxembourg",
    "Nordic countries",
    "Southern and Eastern Europe",
    "India, Pakistan, Bangladesh, and Sri Lanka",
    "Singapore, Malaysia, Indonesia, Philippines, Thailand, and Vietnam",
    "Japan, South Korea, Taiwan, and Hong Kong",
    "Australia and New Zealand",
    "United Arab Emirates, Saudi Arabia, Qatar, and the wider Middle East",
    "Africa, including South Africa, Kenya, Nigeria, Egypt, and Morocco",
    "Brazil",
    "Mexico and Central America",
    "Spanish-speaking South America and the Caribbean",
    "Worldwide remote roles open across borders",
    "Global startup career pages and remote-first companies",
    "Official company career pages in North America with jobs posted this week",
    "Official company career pages in Europe with jobs posted this week",
    "Official company career pages in Asia-Pacific with jobs posted this week",
    "Official company career pages in India and the Middle East with jobs posted this week",
    "Official company career pages in Latin America and Africa with jobs posted this week",
    "Greenhouse-hosted jobs worldwide posted this week",
    "Lever-hosted jobs worldwide posted this week",
    "Ashby-hosted jobs worldwide posted this week",
    "Remote job boards worldwide with jobs posted this week",
    "Major public job boards worldwide with jobs posted this week",
]

DISCOVERY_ANGLES = [
    "Worldwide exact-title matches posted this week",
    "Worldwide adjacent job-title matches posted this week",
    "Worldwide skills-first matches where the requested role is central to the work, posted this week",
    "Worldwide entry-level and junior roles posted this week",
    "Worldwide mid-level roles posted this week",
    "Worldwide senior, staff, lead, and principal roles posted this week",
    "Worldwide internships and graduate roles posted this week",
    "Worldwide contract and freelance roles posted this week",
    "Worldwide remote-first startup roles posted this week",
    "Worldwide enterprise employer roles posted this week",
    "Worldwide public-sector, university, and nonprofit roles posted this week",
    "LinkedIn-hosted job listings worldwide posted this week",
    "Glassdoor and Google Jobs listings worldwide posted this week",
    "Wellfound startup jobs worldwide posted this week",
    "RemoteOK and We Work Remotely jobs posted this week",
    "Dice and other technology job boards posted this week",
    "Naukri, Foundit, Cutshort, Instahyre, Hirist, and Internshala jobs posted this week",
    "Adzuna, Jooble, Talent.com, Monster, and CareerBuilder jobs posted this week",
    "Direct ATS pages on Workday and SmartRecruiters posted this week",
    "Direct ATS pages on iCIMS and Taleo posted this week",
    "Direct ATS pages on BambooHR and Teamtailor posted this week",
    "Remote roles open to candidates in any country posted this week",
    "Hybrid roles in major global technology hubs posted this week",
    "On-site roles in major global technology hubs posted this week",
    "Recently reposted roles with a verified repost date this week",
    "Workable and Recruitee employer job pages worldwide posted this week",
    "Personio and Jobvite employer job pages worldwide posted this week",
    "Oracle Cloud HCM and SAP SuccessFactors employer job pages posted this week",
    "Country-specific technology job boards in Europe posted this week",
    "Country-specific technology job boards in Asia-Pacific posted this week",
    "Country-specific technology job boards in Latin America posted this week",
    "University, research institute, and laboratory careers worldwide posted this week",
    "Recruitment agency and staffing company listings worldwide posted this week",
    "Local-language employer career pages worldwide posted this week",
    "Small and medium-sized company career pages worldwide posted this week",
]

JOB_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "jobs": {"type":"array", "items":{"type":"object", "additionalProperties":False, "properties":{
            "title":{"type":"string"}, "company":{"type":"string"}, "location":{"type":"string"},
            "work_mode":{"type":"string"}, "employment_type":{"type":"string"},
            "salary":{"type":["string","null"]}, "experience":{"type":["string","null"]},
            "posted_at":{"type":["string","null"]}, "skills":{"type":"array","items":{"type":"string"}},
            "summary":{"type":"string"}, "match_score":{"type":"integer"}, "match_reason":{"type":"string"},
            "apply_url":{"type":"string"}, "source":{"type":"string"}
        }, "required":["title","company","location","work_mode","employment_type","salary","experience","posted_at","skills","summary","match_score","match_reason","apply_url","source"]}},
        "searched_sources":{"type":"array","items":{"type":"string"}},
        "query_expansion":{"type":"array","items":{"type":"string"}}
    }, "required":["jobs","searched_sources","query_expansion"]
}

def canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Apply URL is not a public HTTP URL")
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", "", ""))

def posting_date(value: str | None) -> date | None:
    if not value: return None
    text = value.strip().lower()
    today = date.today()
    if "today" in text or "hour" in text or "minute" in text: return today
    if "yesterday" in text: return today - timedelta(days=1)
    relative = re.search(r"(\d+)\s*days?", text)
    if relative: return today - timedelta(days=int(relative.group(1)))
    try: return date.fromisoformat(value.strip()[:10])
    except ValueError: return None

def clean_text(value: object, limit: int = 260) -> str:
    text = html.unescape(str(value or ""))
    if "â" in text or "\x80" in text:
        try:
            text = text.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip()

def clean_list(values: list[object]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        if isinstance(value, list):
            cleaned.extend(clean_list(value))
        elif value:
            cleaned.append(clean_text(value, 80))
    return [value for value in dict.fromkeys(cleaned) if value]

def keyword_terms(request: JobSearchRequest) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9+#.]+", request.query.lower())
    terms = [word for word in words if len(word) > 2]
    terms.extend(skill.strip().lower() for skill in request.candidate_skills if skill.strip())
    return list(dict.fromkeys(terms))

def expanded_queries(request: JobSearchRequest) -> list[str]:
    base = request.query.strip()
    terms = keyword_terms(request)
    expansions = [base]
    if "python" in terms:
        expansions.extend([
            "python",
            "developer",
            "engineer",
            "software engineer",
            "python developer",
            "python engineer",
            "backend developer",
            "backend engineer",
            "backend developer python",
            "software engineer python",
            "django developer",
            "flask developer",
            "full stack developer",
            "data engineer python",
            "full stack developer python",
        ])
    if any(term in terms for term in {"javascript", "typescript", "react", "node"}):
        expansions.extend(["frontend developer", "react developer", "node developer", "full stack developer"])
    if any(term in terms for term in {"data", "sql", "analytics"}):
        expansions.extend(["data engineer", "data analyst", "analytics engineer"])
    if not any(expansion.lower() != base.lower() for expansion in expansions):
        expansions.extend([term for term in terms[:4] if term != base.lower()])
    return list(dict.fromkeys(expansion for expansion in expansions if expansion))

def role_title_terms(terms: list[str]) -> set[str]:
    synonyms = {
        "developer": {"developer", "engineer", "programmer"},
        "engineer": {"engineer", "developer", "programmer"},
        "designer": {"designer"},
        "manager": {"manager", "lead", "head"},
        "analyst": {"analyst"},
        "scientist": {"scientist"},
        "architect": {"architect"},
        "consultant": {"consultant"},
        "administrator": {"administrator", "admin"},
    }
    result: set[str] = set()
    for term in terms:
        result.update(synonyms.get(term, set()))
    return result

def skill_terms(terms: list[str]) -> set[str]:
    known = {
        "python", "javascript", "typescript", "java", "react", "node", "django", "flask",
        "sql", "aws", "azure", "gcp", "kubernetes", "docker", "go", "golang", "rust",
        "php", "ruby", "swift", "kotlin", "android", "ios", "machine", "ai", "ml",
    }
    return {term for term in terms if term in known}

def infer_work_mode(location: object, remote_hint: bool = False) -> str:
    text = str(location or "").lower()
    if remote_hint or "remote" in text or "worldwide" in text or "anywhere" in text:
        return "Remote"
    if "hybrid" in text:
        return "Hybrid"
    return "On-site"

def infer_employment_type(value: object) -> str:
    text = str(value or "").lower()
    if "part" in text:
        return "Part-time"
    if "contract" in text:
        return "Contract"
    if "freelance" in text:
        return "Freelance"
    if "intern" in text:
        return "Internship"
    if "full" in text or "permanent" in text:
        return "Full-time"
    return "Not specified"

def infer_experience(*values: object) -> str | None:
    text = " ".join(str(value or "") for value in values).lower()
    if "intern" in text or "entry" in text or "graduate" in text or "junior" in text:
        return "0-1 years"
    if "mid" in text:
        return "2-4 years"
    if "senior" in text:
        return "5+ years"
    if "lead" in text or "principal" in text or "staff" in text:
        return "8+ years"
    years = re.search(r"(\d+)\s*\+?\s*(?:years?|yrs?)", text)
    return f"{years.group(1)}+ years" if years else None

def matches_request(raw: dict, request: JobSearchRequest) -> bool:
    title = str(raw.get("title") or "")
    text = " ".join(str(raw.get(field) or "") for field in ("title", "summary", "company", "skills", "location"))
    terms = keyword_terms(request)
    if terms:
        lower_text = text.lower()
        title_and_skills = f"{title} {raw.get('skills') or ''}".lower()
        title_terms = role_title_terms(terms)
        matched = [term for term in terms if term in lower_text]
        if len(terms) == 1 and not matched:
            return False
        if title_terms and not any(term in title.lower() for term in title_terms) and len(matched) < 2:
            return False
        if len(terms) > 1 and not title_terms and len(matched) < min(2, len(terms)) and not any(term in title_and_skills for term in terms):
            return False
    if request.remote_only and raw.get("work_mode") != "Remote":
        return False
    if request.employment_type:
        wanted = request.employment_type.replace("-", " ")
        if wanted not in str(raw.get("employment_type", "")).lower():
            return False
    if request.location and request.location.lower() not in str(raw.get("location", "")).lower() and raw.get("work_mode") != "Remote":
        return False
    if request.experience_level:
        experience_text = f"{title} {raw.get('experience') or ''}".lower()
        buckets = {
            "entry": ("entry", "graduate", "intern", "0-1"),
            "junior": ("junior", "1+", "0-1"),
            "mid": ("mid", "2+", "3+", "2-4"),
            "senior": ("senior", "5+"),
            "lead": ("lead", "principal", "staff", "8+"),
        }
        if not any(token in experience_text for token in buckets[request.experience_level]):
            return False
    return True

def score_match(raw: dict, request: JobSearchRequest) -> int:
    haystack = " ".join(str(raw.get(field) or "") for field in ("title", "summary", "skills")).lower()
    terms = keyword_terms(request)
    title = str(raw.get("title") or "").lower()
    score = 45
    score += sum(12 for term in terms if term in title)
    score += sum(5 for term in terms if term in haystack and term not in title)
    if request.remote_only and raw.get("work_mode") == "Remote":
        score += 8
    if request.employment_type and request.employment_type.replace("-", " ") in str(raw.get("employment_type", "")).lower():
        score += 8
    if request.experience_level and raw.get("experience"):
        score += 5
    if posting_date(raw.get("posted_at")):
        score += 5
    required_skills = skill_terms(terms)
    if required_skills and not any(term in haystack for term in required_skills):
        score = min(score, 62)
    return max(0, min(98, score))

def posted_from_epoch(value: object) -> str | None:
    try:
        return date.fromtimestamp(int(value)).isoformat()
    except (TypeError, ValueError, OSError):
        return None

async def fetch_remotive(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    jobs = []
    async def fetch_query(query: str) -> list[dict]:
        response = await client.get("https://remotive.com/api/remote-jobs", params={"search": query}, headers={"User-Agent": "CvolvePro/1.0"})
        response.raise_for_status()
        found = []
        for item in response.json().get("jobs", []):
            raw = {
                "title": item.get("title"),
                "company": item.get("company_name"),
                "location": item.get("candidate_required_location") or "Remote",
                "work_mode": "Remote",
                "employment_type": infer_employment_type(item.get("job_type")),
                "salary": item.get("salary") or None,
                "experience": infer_experience(item.get("title"), item.get("description")),
                "posted_at": str(item.get("publication_date") or "")[:10] or None,
                "skills": item.get("tags") or [],
                "summary": clean_text(item.get("description")),
                "match_reason": "Matches your query on Remotive.",
                "apply_url": item.get("url"),
                "source": "Remotive",
            }
            if matches_request(raw, request):
                raw["match_score"] = score_match(raw, request)
                found.append(raw)
        return found
    outcomes = await asyncio.gather(*[fetch_query(query) for query in expanded_queries(request)], return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, list):
            jobs.extend(outcome)
    return {"jobs": jobs, "searched_sources": ["Remotive"], "query_expansion": expanded_queries(request)}

async def fetch_remoteok(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    response = await client.get("https://remoteok.com/api", headers={"User-Agent": "CvolvePro/1.0"})
    response.raise_for_status()
    jobs = []
    for item in response.json():
        if not isinstance(item, dict) or not item.get("position"):
            continue
        tags = item.get("tags") or []
        raw = {
            "title": item.get("position"),
            "company": item.get("company"),
            "location": item.get("location") or "Remote",
            "work_mode": "Remote",
            "employment_type": infer_employment_type(item.get("type") or "full-time"),
            "salary": item.get("salary") or None,
            "experience": infer_experience(item.get("position"), " ".join(tags)),
            "posted_at": item.get("date") or posted_from_epoch(item.get("epoch")),
            "skills": tags,
            "summary": clean_text(item.get("description") or item.get("position")),
            "match_reason": "Matches your query on RemoteOK.",
            "apply_url": item.get("url") or item.get("apply_url"),
            "source": "RemoteOK",
        }
        if matches_request(raw, request):
            raw["match_score"] = score_match(raw, request)
            jobs.append(raw)
    return {"jobs": jobs, "searched_sources": ["RemoteOK"], "query_expansion": [request.query]}

async def fetch_jobicy(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    jobs = []
    async def fetch_query(query: str) -> list[dict]:
        response = await client.get("https://jobicy.com/api/v2/remote-jobs", params={"count": 100, "tag": query}, headers={"User-Agent": "CvolvePro/1.0"})
        response.raise_for_status()
        found = []
        for item in response.json().get("jobs", []):
            raw = {
                "title": item.get("jobTitle"),
                "company": item.get("companyName"),
                "location": item.get("jobGeo") or "Remote",
                "work_mode": "Remote",
                "employment_type": infer_employment_type(item.get("jobType")),
                "salary": None,
                "experience": infer_experience(item.get("jobLevel"), item.get("jobTitle")),
                "posted_at": str(item.get("pubDate") or "")[:10] or None,
                "skills": [item.get("jobIndustry"), item.get("jobLevel")],
                "summary": clean_text(item.get("jobExcerpt") or item.get("jobDescription")),
                "match_reason": "Matches your query on Jobicy.",
                "apply_url": item.get("url"),
                "source": "Jobicy",
            }
            raw["skills"] = clean_list(raw["skills"])
            if matches_request(raw, request):
                raw["match_score"] = score_match(raw, request)
                found.append(raw)
        return found
    outcomes = await asyncio.gather(*[fetch_query(query) for query in expanded_queries(request)], return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, list):
            jobs.extend(outcome)
    return {"jobs": jobs, "searched_sources": ["Jobicy"], "query_expansion": expanded_queries(request)}

async def fetch_arbeitnow(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    jobs = []
    async def fetch_page(page: int) -> list[dict]:
        response = await client.get("https://www.arbeitnow.com/api/job-board-api", params={"page": page}, headers={"User-Agent": "CvolvePro/1.0"})
        response.raise_for_status()
        found = []
        for item in response.json().get("data", []):
            tags = item.get("tags") or []
            raw = {
                "title": item.get("title"),
                "company": item.get("company_name"),
                "location": item.get("location") or "Not specified",
                "work_mode": infer_work_mode(item.get("location"), bool(item.get("remote"))),
                "employment_type": infer_employment_type(item.get("job_types")),
                "salary": None,
                "experience": infer_experience(item.get("title"), item.get("description"), " ".join(tags)),
                "posted_at": posted_from_epoch(item.get("created_at")),
                "skills": tags,
                "summary": clean_text(item.get("description")),
                "match_reason": "Matches your query on Arbeitnow.",
                "apply_url": item.get("url"),
                "source": "Arbeitnow",
            }
            if matches_request(raw, request):
                raw["match_score"] = score_match(raw, request)
                found.append(raw)
        return found
    outcomes = await asyncio.gather(*[fetch_page(page) for page in range(1, 6)], return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, list):
            jobs.extend(outcome)
    return {"jobs": jobs, "searched_sources": ["Arbeitnow"], "query_expansion": [request.query]}

async def fetch_himalayas(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    jobs = []
    async def fetch_page(query: str, offset: int) -> list[dict]:
        response = await client.get("https://himalayas.app/jobs/api", params={"limit": 50, "offset": offset, "query": query}, headers={"User-Agent": "CvolvePro/1.0"})
        response.raise_for_status()
        found = []
        for item in response.json().get("jobs", []):
            salary = None
            if item.get("minSalary") and item.get("maxSalary"):
                salary = f"{item.get('currency') or ''} {item['minSalary']}-{item['maxSalary']} {item.get('salaryPeriod') or ''}".strip()
            seniority = item.get("seniority") or []
            categories = item.get("categories") or []
            locations = item.get("locationRestrictions") or []
            raw = {
                "title": item.get("title"),
                "company": item.get("companyName"),
                "location": ", ".join(locations) if locations else "Remote",
                "work_mode": "Remote",
                "employment_type": infer_employment_type(item.get("employmentType")),
                "salary": salary,
                "experience": infer_experience(" ".join(seniority), item.get("title"), item.get("description")),
                "posted_at": posted_from_epoch(item.get("pubDate")),
                "skills": categories[:8],
                "summary": clean_text(item.get("excerpt") or item.get("description")),
                "match_reason": "Matches your query on Himalayas.",
                "apply_url": item.get("applicationLink") or item.get("guid"),
                "source": "Himalayas",
            }
            if matches_request(raw, request):
                raw["match_score"] = score_match(raw, request)
                found.append(raw)
        return found
    outcomes = await asyncio.gather(
        *[fetch_page(query, offset) for query in expanded_queries(request) for offset in (0, 50, 100)],
        return_exceptions=True,
    )
    for outcome in outcomes:
        if isinstance(outcome, list):
            jobs.extend(outcome)
    return {"jobs": jobs, "searched_sources": ["Himalayas"], "query_expansion": expanded_queries(request)}

async def fetch_we_work_remotely(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    response = await client.get("https://weworkremotely.com/remote-jobs.rss", headers={"User-Agent": "CvolvePro/1.0"})
    response.raise_for_status()
    root = ET.fromstring(response.text)
    jobs = []
    for item in root.findall("./channel/item"):
        def field(name: str) -> str | None:
            node = item.find(name)
            return node.text if node is not None else None

        title = field("title") or ""
        company, _, role = title.partition(": ")
        skills = [part.strip() for part in (field("skills") or "").split(",") if part.strip()]
        raw = {
            "title": role or title,
            "company": company if role else "We Work Remotely",
            "location": field("region") or field("country") or "Remote",
            "work_mode": "Remote",
            "employment_type": infer_employment_type(field("type")),
            "salary": None,
            "experience": infer_experience(title, field("description"), " ".join(skills)),
            "posted_at": field("pubDate"),
            "skills": clean_list(skills + [field("category")]),
            "summary": clean_text(field("description")),
            "match_reason": "Matches your query on We Work Remotely.",
            "apply_url": field("link"),
            "source": "We Work Remotely",
        }
        if matches_request(raw, request):
            raw["match_score"] = score_match(raw, request)
            jobs.append(raw)
    return {"jobs": jobs, "searched_sources": ["We Work Remotely"], "query_expansion": expanded_queries(request)}

async def fetch_the_muse(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    jobs = []
    async def fetch_page(page: int) -> list[dict]:
        response = await client.get("https://www.themuse.com/api/public/jobs", params={"page": page}, headers={"User-Agent": "CvolvePro/1.0"})
        response.raise_for_status()
        found = []
        for item in response.json().get("results", []):
            locations = [loc.get("name") for loc in item.get("locations", []) if loc.get("name")]
            categories = [cat.get("name") for cat in item.get("categories", []) if cat.get("name")]
            levels = [level.get("name") for level in item.get("levels", []) if level.get("name")]
            company = item.get("company") or {}
            raw = {
                "title": item.get("name"),
                "company": company.get("name") or "The Muse",
                "location": ", ".join(locations) if locations else "Not specified",
                "work_mode": infer_work_mode(" ".join(locations)),
                "employment_type": infer_employment_type(item.get("type")),
                "salary": None,
                "experience": infer_experience(" ".join(levels), item.get("name"), item.get("contents")),
                "posted_at": str(item.get("publication_date") or "")[:10] or None,
                "skills": clean_list(categories + levels + (item.get("tags") or [])),
                "summary": clean_text(item.get("contents")),
                "match_reason": "Matches your query on The Muse.",
                "apply_url": (item.get("refs") or {}).get("landing_page"),
                "source": "The Muse",
            }
            if matches_request(raw, request):
                raw["match_score"] = score_match(raw, request)
                found.append(raw)
        return found
    outcomes = await asyncio.gather(*[fetch_page(page) for page in range(1, 11)], return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, list):
            jobs.extend(outcome)
    return {"jobs": jobs, "searched_sources": ["The Muse"], "query_expansion": expanded_queries(request)}

async def search_live_job_boards(request: JobSearchRequest, settings: Settings) -> JobSearchResponse:
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=True) as client:
        outcomes = await asyncio.gather(
            fetch_remotive(client, request),
            fetch_remoteok(client, request),
            fetch_jobicy(client, request),
            fetch_arbeitnow(client, request),
            fetch_himalayas(client, request),
            fetch_we_work_remotely(client, request),
            fetch_the_muse(client, request),
            return_exceptions=True,
        )
    payloads = [outcome for outcome in outcomes if isinstance(outcome, dict)]
    if not payloads:
        raise ValueError("No job board search completed")
    return normalize(merge_payloads(payloads), settings.max_results, settings.max_job_age_days)

def normalize(payload: dict, limit: int, max_age_days: int | None = None) -> JobSearchResponse:
    seen: set[str] = set(); seen_urls: set[str] = set(); jobs: list[JobResult] = []
    for raw in payload.get("jobs", []):
        try:
            url = canonical_url(raw["apply_url"])
            dedupe = f'{raw["company"].strip().lower()}|{raw["title"].strip().lower()}|{raw["location"].strip().lower()}'
            if dedupe in seen or url in seen_urls: continue
            seen.add(dedupe)
            seen_urls.add(url)
            raw["apply_url"] = url
            raw["id"] = hashlib.sha256(dedupe.encode()).hexdigest()[:16]
            raw["match_score"] = max(0, min(100, int(raw.get("match_score", 0))))
            for field in ("work_mode", "employment_type"):
                if not raw.get(field) or str(raw[field]).strip().lower() in {"null", "none", "n/a", "unknown"}:
                    raw[field] = "Not specified"
            for field in ("salary", "experience", "posted_at"):
                if raw.get(field) and str(raw[field]).strip().lower() in {"null", "none", "n/a", "unknown"}:
                    raw[field] = None
            published = posting_date(raw.get("posted_at"))
            if published:
                raw["posted_at"] = published.isoformat()
            if max_age_days is not None:
                cutoff = date.today() - timedelta(days=max_age_days)
                if published is None or published < cutoff or published > date.today():
                    continue
            jobs.append(JobResult.model_validate(raw))
        except (KeyError, TypeError, ValueError):
            continue
    jobs.sort(key=lambda j: (j.match_score, posting_date(j.posted_at) or date.min), reverse=True)
    jobs = jobs[:limit]
    return JobSearchResponse(jobs=jobs, total=len(jobs), searched_sources=payload.get("searched_sources", []), query_expansion=payload.get("query_expansion", []))

def merge_payloads(payloads: list[dict]) -> dict:
    merged = {"jobs": [], "searched_sources": [], "query_expansion": []}
    for payload in payloads:
        merged["jobs"].extend(payload.get("jobs", []))
        for field in ("searched_sources", "query_expansion"):
            for value in payload.get(field, []):
                if value and value not in merged[field]:
                    merged[field].append(value)
    return merged

def search_scopes_for(request: JobSearchRequest) -> list[str]:
    if request.location:
        return [
            f"{request.location} and nearby commuting markets",
            f"remote roles explicitly open to candidates in {request.location}",
            f"international employers hiring candidates based in {request.location}",
            f"official company career pages hiring in {request.location} posted this week",
        ]
    if request.remote_only:
        return [
            "Worldwide remote roles open across borders",
            "Remote job boards worldwide with jobs posted this week",
            "Remote roles open to candidates in any country posted this week",
            "RemoteOK and We Work Remotely jobs posted this week",
            "Worldwide remote-first startup roles posted this week",
            "Global startup career pages and remote-first companies",
            "Worldwide exact-title matches posted this week",
            "Worldwide skills-first matches where the requested role is central to the work, posted this week",
        ]
    return [
        "Worldwide exact-title matches posted this week",
        "Worldwide adjacent job-title matches posted this week",
        "Worldwide skills-first matches where the requested role is central to the work, posted this week",
        "Major public job boards worldwide with jobs posted this week",
        "Official company career pages in North America with jobs posted this week",
        "Official company career pages in Europe with jobs posted this week",
        "Official company career pages in Asia-Pacific with jobs posted this week",
        "Naukri, Foundit, Cutshort, Instahyre, Hirist, and Internshala jobs posted this week",
        "Remote job boards worldwide with jobs posted this week",
        "Greenhouse-hosted jobs worldwide posted this week",
        "Lever-hosted jobs worldwide posted this week",
        "Ashby-hosted jobs worldwide posted this week",
    ]

class NvidiaAPIError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


async def _search_region(client: httpx.AsyncClient, request: JobSearchRequest, settings: Settings, region: str) -> dict:
    context = {
        "role_or_skill": request.query, "location": request.location,
        "remote_only": request.remote_only, "employment_type": request.employment_type,
        "experience_level": request.experience_level,
        "candidate_skills": request.candidate_skills, "search_scope": region,
    }
    instructions = (
            "You are CvolvePro's live job research engine. Find currently open jobs using web search. "
            "Search ONLY within the supplied search_scope so separate workers produce diverse, non-overlapping results. "
            "Expand the requested role into nearby titles but keep intent precise. Search major public boards, regional job boards, and official company career pages. "
            "Honor the requested location, remote_only, employment_type, and experience_level filters when they are supplied. "
            "Every returned job must be supported by a page you opened during this response and apply_url must be the direct public listing or official apply page. "
            "Return ONLY jobs whose visible publication date or explicit repost date is within the last 7 days. Exclude every undated or older job. "
            "Never invent a job, URL, salary, date, or requirement. Exclude expired, inaccessible, generic search, aggregator redirect, and duplicate listings. "
            "Open the listing to verify its date and return posted_at as YYYY-MM-DD. If the date cannot be verified, do not return the job. "
            "Use candidate skills only to calculate a transparent relevance score; when no skills are supplied, score against the query and filters. "
            "Summaries and match reasons must be concise factual paraphrases. Prefer roles posted recently and official employer URLs. "
            "Return as many distinct verified roles as requested, not merely a short illustrative list. Freshness is mandatory even when that means returning fewer results. "
            "Return only JSON matching the supplied schema."
    )
    response = await client.post(
        "chat/completions",
        json={
            "model": settings.nvidia_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps({
                    "search": context,
                    "preferred_sources": SEARCH_SOURCES,
                    "maximum_results": settings.results_per_region,
                    "output_schema": JOB_SCHEMA,
                })},
            ],
            "temperature": 0,
            "max_tokens": 8192,
            "stream": False,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"thinking": False},
            "nvext": {"guided_json": JOB_SCHEMA},
        },
    )
    if response.status_code >= 400:
        raise NvidiaAPIError("NVIDIA NIM request failed", response.status_code)
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
        if not content:
            raise ValueError("NVIDIA NIM returned no content")
        return json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise NvidiaAPIError("NVIDIA NIM returned an invalid response") from exc

async def search_jobs(request: JobSearchRequest, settings: Settings) -> JobSearchResponse:
    return await search_live_job_boards(request, settings)

async def search_jobs_with_nvidia(request: JobSearchRequest, settings: Settings) -> JobSearchResponse:
    scopes = search_scopes_for(request)[:settings.search_scope_limit]
    semaphore = asyncio.Semaphore(settings.search_concurrency)
    async with httpx.AsyncClient(
        base_url=settings.nvidia_base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.nvidia_api_key}", "Accept": "application/json"},
        timeout=httpx.Timeout(90.0),
    ) as client:
        async def limited_search(region: str):
            async with semaphore:
                return await _search_region(client, request, settings, region)
        outcomes = await asyncio.gather(
            *[limited_search(region) for region in scopes[:settings.search_scope_limit]],
            return_exceptions=True,
        )
    payloads = [outcome for outcome in outcomes if isinstance(outcome, dict)]
    if not payloads:
        error = next((outcome for outcome in outcomes if isinstance(outcome, Exception)), None)
        if error: raise error
        raise ValueError("No regional search completed")
    return normalize(merge_payloads(payloads), settings.max_results, settings.max_job_age_days)
