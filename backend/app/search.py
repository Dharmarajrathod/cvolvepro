from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from urllib.parse import parse_qs, parse_qsl, urlencode, unquote, urlparse, urlunparse
import httpx
from .config import Settings
from .schemas import JobResult, JobSearchRequest, JobSearchResponse

SEARCH_SOURCES = [
    "LinkedIn", "Indeed", "Glassdoor", "ZipRecruiter", "Monster", "CareerBuilder",
    "Remote OK", "We Work Remotely", "Remotive", "FlexJobs", "Wellfound", "Jobspresso", "Working Nomads",
    "Jobright.ai", "Teal", "Jobscan", "Huntr", "Final Round AI", "LazyApply", "Sonara", "LoopCV", "Careerflow", "Kickresume",
    "Y Combinator Jobs",
    "Upwork", "Fiverr", "Toptal", "Freelancer.com",
    "HackerRank Jobs", "Dice", "Hired", "Otta"
]

BLOCKED_SOURCES = [
    "Jobicy", "Himalayas", "Arbeitnow", "The Muse", "Adzuna", "Naukri", "Foundit",
    "Cutshort", "Instahyre", "Internshala", "Jooble", "Talent.com"
]

ALLOWED_PLATFORM_TARGETS = [
    ("LinkedIn", ["linkedin.com/jobs"]),
    ("Indeed", ["indeed.com"]),
    ("Glassdoor", ["glassdoor.com/Job"]),
    ("ZipRecruiter", ["ziprecruiter.com"]),
    ("Monster", ["monster.com/jobs"]),
    ("CareerBuilder", ["careerbuilder.com/jobs"]),
    ("Remote OK", ["remoteok.com"]),
    ("We Work Remotely", ["weworkremotely.com/remote-jobs"]),
    ("Remotive", ["remotive.com/remote-jobs"]),
    ("FlexJobs", ["flexjobs.com"]),
    ("Wellfound", ["wellfound.com/jobs"]),
    ("Jobspresso", ["jobspresso.co/remote-work"]),
    ("Working Nomads", ["workingnomads.com"]),
    ("Jobright.ai", ["jobright.ai"]),
    ("Teal", ["tealhq.com/job-search"]),
    ("Jobscan", ["jobscan.co/jobs"]),
    ("Huntr", ["huntr.co/jobs"]),
    ("Final Round AI", ["finalroundai.com/jobs"]),
    ("LazyApply", ["lazyapply.com/jobs"]),
    ("Sonara", ["sonara.ai"]),
    ("LoopCV", ["loopcv.pro/jobs"]),
    ("Careerflow", ["careerflow.ai/jobs"]),
    ("Kickresume", ["kickresume.com/jobs"]),
    ("Y Combinator Jobs", ["ycombinator.com", "workatastartup.com"]),
    ("Upwork", ["upwork.com/freelance-jobs"]),
    ("Fiverr", ["fiverr.com/categories"]),
    ("Toptal", ["toptal.com/freelance-jobs"]),
    ("Freelancer.com", ["freelancer.com/jobs"]),
    ("HackerRank Jobs", ["hackerrank.com/jobs"]),
    ("Dice", ["dice.com"]),
    ("Hired", ["hired.com/jobs"]),
    ("Otta", ["otta.com/jobs"]),
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
    "LinkedIn, Indeed, Glassdoor, ZipRecruiter, Monster, and CareerBuilder jobs posted this week",
    "Remote OK, We Work Remotely, Remotive, FlexJobs, Jobspresso, and Working Nomads jobs posted this week",
    "Wellfound and Y Combinator Jobs startup roles posted this week",
    "Jobright.ai, Teal, Jobscan, Huntr, Final Round AI, LazyApply, Sonara, LoopCV, Careerflow, and Kickresume job matches posted this week",
    "Upwork, Fiverr, Toptal, and Freelancer.com contract or freelance projects posted this week",
    "HackerRank Jobs, Dice, Hired, and Otta technology roles posted this week",
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
    keep_query_keys = {"q", "query", "keywords", "search", "term", "sc.keyword"}
    query = urlencode([(key, value) for key, value in parse_qsl(parsed.query) if key in keep_query_keys])
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", query, ""))

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

def allowed_source_for_url(url: str) -> str | None:
    lower = url.lower()
    for blocked in BLOCKED_SOURCES:
        if blocked.lower().replace(" ", "") in lower:
            return None
    for source, domains in ALLOWED_PLATFORM_TARGETS:
        if any(domain.lower() in lower for domain in domains):
            return source
    return None

def is_actual_job_url(source: str, url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    if any(token in path for token in ("/search", "/jobs/search", "/job-search", "/jobs.htm")):
        return False
    patterns = {
        "LinkedIn": ["/jobs/view/"],
        "Indeed": ["/viewjob", "/rc/clk"],
        "Glassdoor": ["/job-listing/", "/partner/joblisting"],
        "ZipRecruiter": ["/c/", "/jobs/"],
        "Monster": ["/job-openings/", "/jobs/"],
        "CareerBuilder": ["/job/"],
        "Remote OK": ["/remote-jobs/"],
        "We Work Remotely": ["/remote-jobs/"],
        "Remotive": ["/remote-jobs/"],
        "FlexJobs": ["/publicjobs/"],
        "Wellfound": ["/jobs/"],
        "Jobspresso": ["/remote-work/"],
        "Working Nomads": ["/job/"],
        "Jobright.ai": ["/jobs/"],
        "Teal": ["/job/"],
        "Jobscan": ["/jobs/"],
        "Huntr": ["/jobs/"],
        "Final Round AI": ["/jobs/"],
        "LazyApply": ["/jobs/"],
        "Sonara": ["/jobs/"],
        "LoopCV": ["/jobs/"],
        "Careerflow": ["/jobs/"],
        "Kickresume": ["/jobs/"],
        "Y Combinator Jobs": ["/jobs", "/companies/"],
        "Upwork": ["/freelance-jobs/"],
        "Fiverr": ["/gigs/"],
        "Toptal": ["/freelance-jobs/"],
        "Freelancer.com": ["/projects/"],
        "HackerRank Jobs": ["/jobs/"],
        "Dice": ["/job-detail/"],
        "Hired": ["/jobs/"],
        "Otta": ["/jobs/"],
    }
    if source == "Indeed" and "jk=" in query:
        return True
    return any(pattern in path for pattern in patterns.get(source, []))

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

def strip_tags(value: object, limit: int = 260) -> str:
    return clean_text(value, limit)

def linkedin_job_id(url: str) -> str | None:
    match = re.search(r"/jobs/view/[^/?]*?(\d+)", url)
    return match.group(1) if match else None

def extract_dice_jobs_from_html(text: str) -> list[dict]:
    marker = r'\"jobList\":{\"data\":'
    marker_index = text.find(marker)
    if marker_index < 0:
        return []
    start = text.find("[", marker_index)
    if start < 0:
        return []
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                escaped_array = text[start:index + 1]
                try:
                    return json.loads(escaped_array.replace(r'\"', '"').replace(r"\/", "/"))
                except json.JSONDecodeError:
                    return []
    return []

def parse_linkedin_cards(html_text: str) -> list[dict]:
    cards: list[dict] = []
    blocks = re.findall(r"<li>\s*(.*?)\s*</li>", html_text, flags=re.S)
    for block in blocks:
        def text_for(pattern: str) -> str | None:
            match = re.search(pattern, block, flags=re.S)
            if not match:
                return None
            return clean_text(match.group(1), 220)

        href_match = re.search(r'href="([^"]+)"', block)
        job_url = html.unescape(href_match.group(1)) if href_match else ""
        job_id_match = re.search(r'data-entity-urn="urn:li:jobPosting:(\d+)"', block)
        job_id = job_id_match.group(1) if job_id_match else linkedin_job_id(job_url)
        title = text_for(r'class="base-search-card__title[^"]*"[^>]*>(.*?)</h3>')
        company = text_for(r'class="base-search-card__subtitle[^"]*"[^>]*>.*?(?:<a[^>]*>)?(.*?)(?:</a>)?\s*</h4>')
        location = text_for(r'class="job-search-card__location[^"]*"[^>]*>(.*?)</span>')
        date_match = re.search(r'<time[^>]+datetime="([^"]+)"', block)
        posted_at = date_match.group(1) if date_match else None
        if job_url and title and company and job_id:
            cards.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": location or "Not specified",
                "posted_at": posted_at,
                "apply_url": job_url,
            })
    return cards

async def fetch_linkedin_detail(client: httpx.AsyncClient, job_id: str) -> str:
    try:
        response = await client.get(
            f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}",
            headers={"User-Agent": "Mozilla/5.0 CvolvePro/1.0"},
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return ""
    match = re.search(r'class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', response.text, flags=re.S)
    return clean_text(match.group(1), 420) if match else ""

async def fetch_linkedin(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    jobs = []
    location = request.location or "United States"
    async def fetch_page(start: int) -> list[dict]:
        try:
            response = await client.get(
                "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                params={
                    "keywords": request.query,
                    "location": location,
                    "f_TPR": "r604800",
                    "sortBy": "DD",
                    "start": start,
                },
                headers={"User-Agent": "Mozilla/5.0 CvolvePro/1.0"},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        return parse_linkedin_cards(response.text)

    pages = await asyncio.gather(*[fetch_page(start) for start in range(0, 300, 10)], return_exceptions=True)
    cards = []
    for page in pages:
        if isinstance(page, list):
            cards.extend(page)
    fresh_cards = [card for card in cards if posting_date(card.get("posted_at"))]

    semaphore = asyncio.Semaphore(12)
    async def enrich(card: dict) -> dict | None:
        async with semaphore:
            description = await fetch_linkedin_detail(client, str(card["id"]))
        raw = {
            "title": card.get("title"),
            "company": card.get("company"),
            "location": card.get("location"),
            "work_mode": infer_work_mode(card.get("location")),
            "employment_type": "Not specified",
            "salary": None,
            "experience": infer_experience(card.get("title"), description),
            "posted_at": card.get("posted_at"),
            "skills": clean_list(keyword_terms(request)),
            "summary": description or f"{card.get('title')} role at {card.get('company')} on LinkedIn.",
            "match_reason": "Matches your query on LinkedIn.",
            "apply_url": card.get("apply_url"),
            "source": "LinkedIn",
        }
        if matches_request(raw, request):
            raw["match_score"] = score_match(raw, request)
            return raw
        return None

    outcomes = await asyncio.gather(*[enrich(card) for card in fresh_cards], return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, dict):
            jobs.append(outcome)
    return {"jobs": jobs, "searched_sources": ["LinkedIn"], "query_expansion": [request.query]}

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

async def fetch_working_nomads(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    response = await client.get(
        "https://www.workingnomads.com/api/exposed_jobs/",
        headers={"User-Agent": "Mozilla/5.0 CvolvePro/1.0"},
    )
    response.raise_for_status()
    jobs = []
    for item in response.json():
        tags = clean_list(str(item.get("tags") or "").split(","))
        raw = {
            "title": item.get("title"),
            "company": item.get("company_name") or "Working Nomads",
            "location": item.get("location") or "Remote",
            "work_mode": infer_work_mode(item.get("location"), True),
            "employment_type": infer_employment_type(item.get("category_name")),
            "salary": None,
            "experience": infer_experience(item.get("title"), item.get("description"), " ".join(tags)),
            "posted_at": str(item.get("pub_date") or "")[:10] or None,
            "skills": tags or clean_list([item.get("category_name")]),
            "summary": clean_text(item.get("description")),
            "match_reason": "Matches your query on Working Nomads.",
            "apply_url": item.get("url"),
            "source": "Working Nomads",
        }
        if matches_request(raw, request):
            raw["match_score"] = score_match(raw, request)
            jobs.append(raw)
    return {"jobs": jobs, "searched_sources": ["Working Nomads"], "query_expansion": [request.query]}

async def fetch_y_combinator_jobs(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    response = await client.get(
        "https://www.ycombinator.com/jobs",
        params={"query": request.query},
        headers={"User-Agent": "Mozilla/5.0 CvolvePro/1.0"},
    )
    response.raise_for_status()
    page_match = re.search(r'data-page="([^"]+)"', response.text)
    if not page_match:
        return {"jobs": [], "searched_sources": ["Y Combinator Jobs"], "query_expansion": [request.query]}
    try:
        page_data = json.loads(html.unescape(page_match.group(1)))
    except json.JSONDecodeError:
        return {"jobs": [], "searched_sources": ["Y Combinator Jobs"], "query_expansion": [request.query]}
    jobs = []
    postings = page_data.get("props", {}).get("jobPostings", [])
    for item in postings:
        detail_url = item.get("url") or ""
        if detail_url.startswith("/"):
            detail_url = f"https://www.ycombinator.com{detail_url}"
        skills = clean_list(item.get("skills") or [])
        summary_parts = [item.get("companyOneLiner"), item.get("roleSpecificType"), item.get("prettyRole")]
        raw = {
            "title": item.get("title"),
            "company": item.get("companyName") or "Y Combinator Jobs",
            "location": item.get("location") or "Not specified",
            "work_mode": infer_work_mode(item.get("location")),
            "employment_type": infer_employment_type(item.get("type")),
            "salary": item.get("salaryRange") or None,
            "experience": item.get("minExperience") or infer_experience(item.get("title"), item.get("roleSpecificType")),
            "posted_at": item.get("createdAt"),
            "skills": skills,
            "summary": clean_text(" ".join(str(part or "") for part in summary_parts)),
            "match_reason": "Matches your query on Y Combinator Jobs.",
            "apply_url": detail_url,
            "source": "Y Combinator Jobs",
        }
        if matches_request(raw, request):
            raw["match_score"] = score_match(raw, request)
            jobs.append(raw)
    return {"jobs": jobs, "searched_sources": ["Y Combinator Jobs"], "query_expansion": [request.query]}

async def fetch_freelancer(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    jobs = []
    async def fetch_query(query: str) -> list[dict]:
        try:
            response = await client.get(
                "https://www.freelancer.com/api/projects/0.1/projects/active/",
                params={
                    "query": query,
                    "limit": 100,
                    "compact": "true",
                    "full_description": "true",
                    "job_details": "true",
                },
                headers={"User-Agent": "Mozilla/5.0 CvolvePro/1.0"},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        found = []
        for item in response.json().get("result", {}).get("projects", []):
            skills = clean_list([skill.get("name") for skill in item.get("jobs", []) if isinstance(skill, dict)])
            currency = item.get("currency") or {}
            budget = item.get("budget") or {}
            salary = None
            if budget.get("minimum") is not None and budget.get("maximum") is not None:
                salary = f"{currency.get('sign') or currency.get('code') or ''}{budget.get('minimum')}-{budget.get('maximum')}".strip()
            if item.get("hourly_project_info"):
                hourly = item.get("hourly_project_info") or {}
                if hourly.get("minimum") is not None and hourly.get("maximum") is not None:
                    salary = f"{currency.get('sign') or currency.get('code') or ''}{hourly.get('minimum')}-{hourly.get('maximum')}/hr".strip()
            seo_url = item.get("seo_url") or f"projects/{item.get('id')}"
            raw = {
                "title": item.get("title"),
                "company": "Freelancer client",
                "location": "Remote",
                "work_mode": "Remote",
                "employment_type": "Freelance",
                "salary": salary,
                "experience": infer_experience(item.get("title"), item.get("description")),
                "posted_at": posted_from_epoch(item.get("submitdate") or item.get("time_submitted")),
                "skills": skills,
                "summary": clean_text(item.get("description") or item.get("preview_description")),
                "match_reason": "Matches your query on Freelancer.com.",
                "apply_url": f"https://www.freelancer.com/projects/{seo_url}",
                "source": "Freelancer.com",
            }
            if matches_request(raw, request):
                raw["match_score"] = score_match(raw, request)
                found.append(raw)
        return found

    outcomes = await asyncio.gather(*[fetch_query(query) for query in expanded_queries(request)[:8]], return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, list):
            jobs.extend(outcome)
    return {"jobs": jobs, "searched_sources": ["Freelancer.com"], "query_expansion": expanded_queries(request)}

async def fetch_dice(client: httpx.AsyncClient, request: JobSearchRequest) -> dict:
    jobs = []
    async def fetch_page(page: int) -> list[dict]:
        params = {"q": request.query, "page": str(page)}
        if request.location:
            params["location"] = request.location
        elif request.remote_only:
            params["location"] = "Remote"
        try:
            response = await client.get(
                "https://www.dice.com/jobs",
                params=params,
                headers={"User-Agent": "Mozilla/5.0 CvolvePro/1.0"},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        found = []
        for item in extract_dice_jobs_from_html(response.text):
            location = item.get("jobLocation") or {}
            location_name = location.get("displayName") if isinstance(location, dict) else location
            workplace_types = item.get("workplaceTypes") or []
            skills = clean_list(item.get("skills") or item.get("skillList") or workplace_types)
            raw = {
                "title": item.get("title"),
                "company": item.get("companyName"),
                "location": location_name or "Not specified",
                "work_mode": infer_work_mode(location_name, bool(item.get("isRemote"))),
                "employment_type": infer_employment_type(item.get("employmentType")),
                "salary": item.get("salary") or None,
                "experience": infer_experience(item.get("title"), item.get("summary")),
                "posted_at": str(item.get("postedDate") or "")[:10] or None,
                "skills": skills,
                "summary": clean_text(item.get("summary")),
                "match_reason": "Matches your query on Dice.",
                "apply_url": item.get("detailsPageUrl"),
                "source": "Dice",
            }
            if matches_request(raw, request):
                raw["match_score"] = score_match(raw, request)
                found.append(raw)
        return found
    outcomes = await asyncio.gather(*[fetch_page(page) for page in range(1, 11)], return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, list):
            jobs.extend(outcome)
    return {"jobs": jobs, "searched_sources": ["Dice"], "query_expansion": [request.query]}

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
            fetch_linkedin(client, request),
            fetch_dice(client, request),
            fetch_freelancer(client, request),
            fetch_working_nomads(client, request),
            fetch_y_combinator_jobs(client, request),
            fetch_remotive(client, request),
            fetch_remoteok(client, request),
            fetch_we_work_remotely(client, request),
            return_exceptions=True,
        )
    payloads = [outcome for outcome in outcomes if isinstance(outcome, dict)]
    if not payloads:
        raise ValueError("No job board search completed")
    return normalize(merge_payloads(payloads), settings.max_results, settings.max_job_age_days)

def duckduckgo_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [value])[0]
        return unquote(target)
    return value

def parse_search_results(source: str, html_text: str, limit: int = 3) -> list[dict]:
    results: list[dict] = []
    blocks = re.findall(r'<div class="result[^"]*".*?</div>\s*</div>', html_text, flags=re.S)
    if not blocks:
        blocks = re.findall(r'<a[^>]+class="result__a"[^>]+>.*?</a>', html_text, flags=re.S)
    for block in blocks:
        link_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>', block, flags=re.S)
        if not link_match:
            link_match = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.S)
        if not link_match:
            continue
        url = duckduckgo_url(html.unescape(link_match.group(1)))
        detected_source = allowed_source_for_url(url)
        if not detected_source or not is_actual_job_url(detected_source, url):
            continue
        title = clean_text(link_match.group(2), 160)
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</', block, flags=re.S)
        snippet = clean_text(snippet_match.group(1), 260) if snippet_match else title
        results.append({"source": detected_source or source, "title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results

def parse_bing_results(source: str, html_text: str, limit: int = 3) -> list[dict]:
    results: list[dict] = []
    blocks = re.findall(r'<li class="b_algo".*?</li>', html_text, flags=re.S)
    for block in blocks:
        link_match = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.S)
        if not link_match:
            continue
        url = html.unescape(link_match.group(1))
        detected_source = allowed_source_for_url(url)
        if not detected_source or not is_actual_job_url(detected_source, url):
            continue
        title = clean_text(link_match.group(2), 160)
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.S)
        snippet = clean_text(snippet_match.group(1), 260) if snippet_match else title
        results.append({"source": detected_source or source, "title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results

def platform_query(request: JobSearchRequest, domain: str) -> str:
    parts = [f"site:{domain}", request.query, "job"]
    if request.location:
        parts.append(request.location)
    if request.remote_only:
        parts.append("remote")
    if request.employment_type:
        parts.append(request.employment_type)
    if request.experience_level:
        parts.append(request.experience_level)
    return " ".join(parts)

def detail_query(request: JobSearchRequest, source: str, domain: str) -> str:
    detail_hints = {
        "LinkedIn": "/jobs/view/",
        "Indeed": "viewjob jk",
        "Glassdoor": "/job-listing/",
        "Dice": "/job-detail/",
        "Remote OK": "/remote-jobs/",
        "We Work Remotely": "/remote-jobs/",
        "Remotive": "/remote-jobs/",
        "Y Combinator Jobs": "/companies/",
        "Freelancer.com": "/projects/",
    }
    parts = [f"site:{domain}", detail_hints.get(source, "job"), request.query]
    if request.location:
        parts.append(request.location)
    if request.remote_only:
        parts.append("remote")
    if request.employment_type:
        parts.append(request.employment_type)
    if request.experience_level:
        parts.append(request.experience_level)
    return " ".join(parts)

async def discover_allowed_platform_links(request: JobSearchRequest) -> list[dict]:
    semaphore = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0), follow_redirects=True) as client:
        async def search_platform(source: str, domains: list[str]) -> list[dict]:
            found: list[dict] = []
            async with semaphore:
                for domain in domains[:2]:
                    try:
                        response = await client.get(
                            "https://duckduckgo.com/html/",
                            params={"q": detail_query(request, source, domain)},
                            headers={"User-Agent": "Mozilla/5.0 CvolvePro/1.0"},
                        )
                        response.raise_for_status()
                        found.extend(parse_search_results(source, response.text, limit=2))
                    except httpx.HTTPError:
                        pass
                    if len(found) >= 2:
                        break
                    try:
                        response = await client.get(
                            "https://www.bing.com/search",
                            params={"q": detail_query(request, source, domain)},
                            headers={"User-Agent": "Mozilla/5.0 CvolvePro/1.0"},
                        )
                        response.raise_for_status()
                        found.extend(parse_bing_results(source, response.text, limit=2))
                    except httpx.HTTPError:
                        pass
            return found
        outcomes = await asyncio.gather(
            *[search_platform(source, domains) for source, domains in ALLOWED_PLATFORM_TARGETS],
            return_exceptions=True,
        )
    seen: set[str] = set()
    links: list[dict] = []
    for outcome in outcomes:
        if not isinstance(outcome, list):
            continue
        for item in outcome:
            try:
                url = canonical_url(item["url"])
            except ValueError:
                continue
            if url in seen:
                continue
            seen.add(url)
            item["url"] = url
            links.append(item)
    return links[:80]

async def normalize_discovered_links_with_nvidia(request: JobSearchRequest, settings: Settings, links: list[dict]) -> JobSearchResponse:
    if not links:
        raise ValueError("No allowed platform links discovered")
    schema = JOB_SCHEMA
    instructions = (
        "You are CvolvePro's job result normalizer. Convert discovered allowed-platform search results into useful job cards. "
        "Use only the supplied discovered_results. Do not invent companies, links, sources, salaries, or dates. "
        "Return jobs only from preferred_sources and never from blocked_sources. "
        "If a search result is not a job listing or freelance project, skip it. "
        "Return only actual job/detail/project pages, never platform search pages. "
        "Every returned job must have a real job description summary and a visible posting date as YYYY-MM-DD. "
        "If the date is not visible in the discovered result, skip that result. Return only JSON matching the schema."
    )
    async with httpx.AsyncClient(
        base_url=settings.nvidia_base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.nvidia_api_key}", "Accept": "application/json"},
        timeout=httpx.Timeout(60.0),
    ) as client:
        response = await client.post(
            "chat/completions",
            json={
                "model": settings.nvidia_model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": json.dumps({
                        "search": request.model_dump(),
                        "preferred_sources": SEARCH_SOURCES,
                        "blocked_sources": BLOCKED_SOURCES,
                        "discovered_results": links,
                        "output_schema": schema,
                    })},
                ],
                "temperature": 0,
                "max_tokens": 8192,
                "stream": False,
                "response_format": {"type": "json_object"},
                "chat_template_kwargs": {"thinking": False},
                "nvext": {"guided_json": schema},
            },
        )
    if response.status_code >= 400:
        raise NvidiaAPIError("NVIDIA NIM request failed", response.status_code)
    try:
        content = response.json()["choices"][0]["message"]["content"]
        payload = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise NvidiaAPIError("NVIDIA NIM returned an invalid response") from exc
    filtered_jobs = []
    for raw in payload.get("jobs", []):
        source = str(raw.get("source") or "")
        url = str(raw.get("apply_url") or "")
        if source in SEARCH_SOURCES and allowed_source_for_url(url) and is_actual_job_url(source, url) and posting_date(raw.get("posted_at")):
            filtered_jobs.append(raw)
    payload["jobs"] = filtered_jobs
    payload["searched_sources"] = list(dict.fromkeys([item["source"] for item in links]))
    payload["query_expansion"] = payload.get("query_expansion") or [request.query]
    return normalize(payload, settings.max_results, settings.max_job_age_days)

def normalize(payload: dict, limit: int, max_age_days: int | None = None) -> JobSearchResponse:
    seen: set[str] = set(); seen_urls: set[str] = set(); jobs: list[JobResult] = []
    for raw in payload.get("jobs", []):
        try:
            url = canonical_url(raw["apply_url"])
            dedupe = f'{raw["company"].strip().lower()}|{raw["title"].strip().lower()}|{raw["location"].strip().lower()}'
            if dedupe in seen or url in seen_urls: continue
            detected_source = allowed_source_for_url(url)
            if detected_source and not is_actual_job_url(detected_source, url):
                continue
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
    sources = {job.source for job in jobs}
    if len(sources) > 1 and limit > 3:
        grouped: dict[str, list[JobResult]] = {}
        for job in jobs:
            grouped.setdefault(job.source, []).append(job)
        source_order = sorted(
            grouped,
            key=lambda source: (
                grouped[source][0].match_score,
                posting_date(grouped[source][0].posted_at) or date.min,
            ),
            reverse=True,
        )
        balanced: list[JobResult] = []
        while len(balanced) < limit:
            added = False
            for source in source_order:
                if grouped[source]:
                    balanced.append(grouped[source].pop(0))
                    added = True
                    if len(balanced) == limit:
                        break
            if not added:
                break
        if len(balanced) < limit:
            selected_ids = {job.id for job in balanced}
            for job in jobs:
                if job.id in selected_ids:
                    continue
                balanced.append(job)
                if len(balanced) == limit:
                    break
        jobs = balanced[:limit]
    else:
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
            f"LinkedIn, Indeed, Glassdoor, ZipRecruiter, Monster, CareerBuilder roles in {request.location} posted this week",
            f"Remote OK, We Work Remotely, Remotive, FlexJobs, Jobspresso, Working Nomads roles open to candidates in {request.location}",
            f"Wellfound and Y Combinator Jobs startup roles in or open to {request.location}",
            f"HackerRank Jobs, Dice, Hired, and Otta technology roles in or open to {request.location}",
        ]
    if request.remote_only:
        return [
            "Remote OK, We Work Remotely, Remotive, FlexJobs, Jobspresso, and Working Nomads remote roles posted this week",
            "Wellfound and Y Combinator Jobs remote startup roles posted this week",
            "Upwork, Fiverr, Toptal, and Freelancer.com remote freelance projects posted this week",
            "Jobright.ai, Teal, Jobscan, Huntr, Sonara, LoopCV, Careerflow, Kickresume remote job matches posted this week",
            "Dice, Hired, HackerRank Jobs, and Otta remote technology jobs posted this week",
        ]
    return [
        "LinkedIn, Indeed, Glassdoor, ZipRecruiter, Monster, and CareerBuilder exact-title roles posted this week",
        "Remote OK, We Work Remotely, Remotive, FlexJobs, Jobspresso, and Working Nomads matching roles posted this week",
        "Wellfound and Y Combinator Jobs startup roles posted this week",
        "Jobright.ai, Teal, Jobscan, Huntr, Final Round AI, LazyApply, Sonara, LoopCV, Careerflow, and Kickresume matching roles posted this week",
        "Upwork, Fiverr, Toptal, and Freelancer.com freelance projects posted this week",
        "HackerRank Jobs, Dice, Hired, and Otta technology roles posted this week",
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
            "Expand the requested role into nearby titles but keep intent precise. Search ONLY the allowed platforms supplied in preferred_sources. "
            "Do not search or return jobs from blocked_sources. "
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
                    "blocked_sources": BLOCKED_SOURCES,
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
    live_result: JobSearchResponse | None = None
    try:
        live_result = await search_live_job_boards(request, settings)
    except (httpx.HTTPError, ValueError, TypeError):
        live_result = None
    if settings.nvidia_api_key:
        if live_result and live_result.total > 0:
            if live_result.total >= settings.max_results:
                return live_result
            try:
                discovered = await discover_allowed_platform_links(request)
                discovered_result = await normalize_discovered_links_with_nvidia(request, settings, discovered)
                if discovered_result.total > 0:
                    payload = merge_payloads([
                        response_to_payload(live_result),
                        response_to_payload(discovered_result),
                    ])
                    return normalize(payload, settings.max_results, settings.max_job_age_days)
            except NvidiaAPIError as exc:
                if exc.status_code in {401, 403, 429}:
                    return live_result
            except (httpx.HTTPError, ValueError, TypeError):
                pass
            return live_result
        try:
            discovered = await discover_allowed_platform_links(request)
            discovered_result = await normalize_discovered_links_with_nvidia(request, settings, discovered)
            if discovered_result.total > 0:
                return discovered_result
        except NvidiaAPIError as exc:
            if exc.status_code in {401, 403, 429}:
                raise
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        try:
            nvidia_result = await search_jobs_with_nvidia(request, settings)
            if nvidia_result.total > 0:
                return nvidia_result
        except NvidiaAPIError as exc:
            if exc.status_code in {401, 403, 429}:
                raise
        except (httpx.HTTPError, ValueError, TypeError):
            pass
    if live_result and live_result.total > 0:
        return live_result
    return await search_live_job_boards(request, settings)

def response_to_payload(response: JobSearchResponse) -> dict:
    return {
        "jobs": [job.model_dump() for job in response.jobs],
        "searched_sources": response.searched_sources,
        "query_expansion": response.query_expansion,
    }

async def search_jobs_with_nvidia(request: JobSearchRequest, settings: Settings) -> JobSearchResponse:
    if not settings.nvidia_api_key:
        raise NvidiaAPIError("NVIDIA API key is missing", 401)
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
