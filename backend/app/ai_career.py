from __future__ import annotations

import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET

import httpx
from fastapi import UploadFile

from .config import Settings
from .schemas import (
    AtsScoreResponse,
    InterviewAnswer,
    InterviewFeedbackResponse,
    InterviewStartResponse,
    JobResult,
    ResumeImproveAnswer,
    ResumeImproveGenerateResponse,
    ResumeImproveQuestionResponse,
)
from .search import NvidiaAPIError

ATS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "verdict": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "missing_keywords": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "resume_updates": {
            "type": "array",
            "minItems": 4,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "current_line": {"type": "string"},
                    "updated_line": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["current_line", "updated_line", "reason"],
            },
        },
    },
    "required": ["score", "verdict", "strengths", "gaps", "missing_keywords", "recommendations", "resume_updates"],
}

QUESTIONS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "questions": {"type": "array", "minItems": 10, "maxItems": 10, "items": {"type": "string"}}
    },
    "required": ["questions"],
}

FEEDBACK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "hiring_signal": {"type": "string"},
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "improvements": {"type": "array", "items": {"type": "string"}},
        "better_answer_guidance": {"type": "array", "items": {"type": "string"}},
        "question_feedback": {
            "type": "array",
            "minItems": 10,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "question": {"type": "string"},
                    "your_answer": {"type": "string"},
                    "expected_answer": {"type": "string"},
                    "feedback": {"type": "string"},
                },
                "required": ["question", "your_answer", "expected_answer", "feedback"],
            },
        },
    },
    "required": ["overall_score", "hiring_signal", "summary", "strengths", "improvements", "better_answer_guidance", "question_feedback"],
}

RESUME_IMPROVE_QUESTIONS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "questions": {"type": "array", "minItems": 4, "maxItems": 5, "items": {"type": "string"}}
    },
    "required": ["questions"],
}

RESUME_IMPROVE_GENERATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "resume_text": {"type": "string"},
        "expected_ats_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "summary": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["resume_text", "expected_ats_score", "summary", "changes"],
}


def compact_text(value: str, limit: int = 30000) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


async def extract_resume_text(file: UploadFile) -> str:
    payload = await file.read()
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    if filename.endswith(".pdf") or "pdf" in content_type:
        text = extract_pdf_text(payload)
    elif filename.endswith(".docx") or "wordprocessingml" in content_type:
        text = extract_docx_text(payload)
    else:
        text = payload.decode("utf-8", errors="ignore")
    text = compact_text(text)
    if len(text) < 80:
        raise ValueError("Could not extract enough readable text from the resume.")
    return text


def extract_pdf_text(payload: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise ValueError("Could not read the PDF resume.") from exc


def extract_docx_text(payload: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as docx:
            xml = docx.read("word/document.xml")
        root = ET.fromstring(xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        return "\n".join(node.text or "" for node in root.findall(".//w:t", namespace))
    except Exception as exc:
        raise ValueError("Could not read the DOCX resume.") from exc


async def nvidia_json(settings: Settings, system: str, payload: dict, schema: dict, max_tokens: int = 4096) -> dict:
    if not settings.nvidia_api_key:
        raise NvidiaAPIError("NVIDIA API key is missing", 401)
    async with httpx.AsyncClient(
        base_url=settings.nvidia_base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.nvidia_api_key}", "Accept": "application/json"},
        timeout=httpx.Timeout(90.0),
    ) as client:
        response = await client.post(
            "chat/completions",
            json={
                "model": settings.nvidia_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                "temperature": 0.2,
                "max_tokens": max_tokens,
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
        return json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise NvidiaAPIError("NVIDIA NIM returned an invalid response") from exc


def job_context(job: JobResult) -> dict:
    return {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "work_mode": job.work_mode,
        "employment_type": job.employment_type,
        "experience": job.experience,
        "skills": job.skills,
        "summary": job.summary,
        "match_reason": job.match_reason,
    }


STOPWORDS = {
    "about", "above", "after", "against", "also", "and", "are", "based", "but", "can", "for", "from",
    "has", "have", "into", "join", "looking", "more", "our", "role", "that", "the", "their", "this",
    "to", "using", "with", "work", "you", "your", "will", "job", "description", "pasted", "posted",
    "days", "hours", "ago", "over", "people", "clicked", "click", "apply", "applicants", "applicant",
    "views", "viewed", "promoted", "reposted", "linkedin", "indeed", "easy", "company", "full",
    "time", "remote", "onsite", "hybrid",
}

NOISE_LINE_PATTERN = re.compile(
    r"(clicked|applicants?|posted|promoted|reposted|linkedin|indeed|apply now|days?\s+ago|hours?\s+ago|"
    r"people|followers|be among|see who|save job|show more|show less|seniority level|employment type)",
    re.I,
)

ROLE_WORD_PATTERN = re.compile(
    r"\b(engineer|developer|manager|analyst|designer|consultant|specialist|architect|lead|intern|associate|"
    r"director|administrator|scientist|tester|qa|sales|marketing|finance|hr|recruiter|devops|frontend|"
    r"backend|fullstack|data|product|project|program)\b",
    re.I,
)

KNOWN_SKILLS = [
    "React", "TypeScript", "JavaScript", "Python", "SQL", "Tableau", "Power BI", "Excel", "Node.js",
    "FastAPI", "Django", "Flask", "Java", "Spring", "REST API", "GraphQL", "PostgreSQL", "MySQL",
    "MongoDB", "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "CI/CD", "Git",
    "HTML", "CSS", "Tailwind", "Accessibility", "API integration", "Machine Learning", "Pandas",
    "NumPy", "Data Analysis", "A/B testing", "Analytics", "Dashboard", "Figma", "CRM", "Salesforce",
    "SEO", "Content Marketing", "Campaign", "Android", "iOS", "Flutter", "React Native",
]


def keyword_list(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.]{2,}", text)
    seen: dict[str, str] = {}
    for word in words:
        lowered = word.lower()
        if lowered not in STOPWORDS and lowered not in seen:
            seen[lowered] = word
    return list(seen.values())


def normalized_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z][a-z0-9+#.]{2,}", text.lower())
    values: set[str] = set()
    for token in tokens:
        values.add(token)
        if len(token) > 6:
            values.add(token[:6])
        if token.endswith("ies") and len(token) > 4:
            values.add(token[:-3] + "y")
        if token.endswith("ing") and len(token) > 5:
            values.add(token[:-3])
        if token.endswith("ed") and len(token) > 4:
            values.add(token[:-2])
        if token.endswith("s") and len(token) > 3:
            values.add(token[:-1])
    return values


def clean_job_text(text: str) -> str:
    lines = []
    for line in re.split(r"[\r\n]+", text):
        cleaned = re.sub(r"\s+", " ", line).strip(" -•\t")
        if not cleaned or NOISE_LINE_PATTERN.search(cleaned):
            continue
        lines.append(cleaned)
    return " ".join(lines) if lines else compact_text(text)


def role_label(job: JobResult) -> str:
    title = job.title.strip()
    if title and title.lower() not in {"pasted job description", "custom job role", "selected role"}:
        return title
    for line in re.split(r"[\r\n.]+", job.summary):
        cleaned = re.sub(r"\s+", " ", line).strip(" -•\t")
        if 4 <= len(cleaned) <= 90 and not NOISE_LINE_PATTERN.search(cleaned) and ROLE_WORD_PATTERN.search(cleaned):
            return cleaned
    return "this target role"


def contains_term(text: str, term: str) -> bool:
    term = term.strip().lower()
    if not term:
        return False
    if re.search(r"[+#.]", term):
        return term in text
    if bool(re.search(rf"\b{re.escape(term)}\b", text)):
        return True
    if len(normalized_tokens(term) & normalized_tokens(text)) >= 1 and len(re.findall(r"[a-z][a-z0-9+#.]{2,}", term)) == 1:
        return True
    term_tokens = normalized_tokens(term)
    if len(term_tokens) <= 1:
        return False
    text_tokens = normalized_tokens(text)
    return len(term_tokens & text_tokens) / len(term_tokens) >= 0.6


def inferred_job_skills(job: JobResult, cleaned_summary: str) -> list[str]:
    values: list[str] = []
    combined = " ".join([job.title, cleaned_summary, " ".join(job.skills)])
    combined_lower = combined.lower()
    for skill in job.skills:
        if skill and skill.strip():
            values.append(skill.strip())
    for skill in KNOWN_SKILLS:
        if contains_term(combined_lower, skill):
            values.append(skill)
    if values:
        return list(dict.fromkeys(values))[:14]
    for keyword in keyword_list(combined):
        if len(keyword) >= 4 and keyword.lower() not in STOPWORDS:
            values.append(keyword)
    return list(dict.fromkeys(values))[:10]


def deterministic_ats_score(job: JobResult, resume_text: str) -> int:
    resume_lower = resume_text.lower()
    cleaned_summary = clean_job_text(job.summary)
    inferred_role = role_label(job)
    title_keywords = keyword_list(inferred_role)
    inferred_skills = inferred_job_skills(job, cleaned_summary)
    job_keywords = keyword_list(" ".join([inferred_role, cleaned_summary, " ".join(inferred_skills)]))
    meaningful_keywords = [keyword for keyword in job_keywords if len(keyword) >= 4][:30]
    skill_keywords = [skill for skill in inferred_skills if skill and len(skill.strip()) > 1][:12]

    score = 5

    if skill_keywords:
        matched_skills = [skill for skill in skill_keywords if contains_term(resume_lower, skill)]
        skill_ratio = len(matched_skills) / max(1, len(skill_keywords))
        score += round(45 * min(1, skill_ratio))

    if meaningful_keywords:
        matched_keywords = [keyword for keyword in meaningful_keywords if contains_term(resume_lower, keyword)]
        keyword_ratio = len(matched_keywords) / max(1, len(meaningful_keywords))
        score += round(18 * min(1, keyword_ratio))

    if title_keywords and any(contains_term(resume_lower, keyword) for keyword in title_keywords):
        score += 12

    if re.search(r"\b(built|led|owned|delivered|improved|reduced|increased|designed|deployed|implemented|created|managed)\b", resume_lower):
        score += 8

    if re.search(r"\b(\d+%|\d+\+?\s*(years?|yrs?|users?|requests?|projects?|teams?)|\$\d+|\d+x)\b", resume_text, re.I):
        score += 8

    if len(resume_text.strip()) >= 250:
        score += 4

    if job.experience:
        experience_numbers = re.findall(r"\d+", job.experience)
        if not experience_numbers or any(number in resume_lower for number in experience_numbers):
            score += 5

    return max(0, min(100, score))


def heuristic_ats_score(job: JobResult, resume_text: str) -> int:
    return deterministic_ats_score(job, resume_text)


def fallback_ats_details(job: JobResult, resume_text: str, score: int) -> dict:
    resume_lower = resume_text.lower()
    cleaned_summary = clean_job_text(job.summary)
    target_role = role_label(job)
    inferred_skills = inferred_job_skills(job, cleaned_summary)
    job_keywords = keyword_list(" ".join([target_role, cleaned_summary, " ".join(inferred_skills)]))
    skill_keywords = [skill for skill in inferred_skills if skill and len(skill) > 1][:12]
    matched_skills = [skill for skill in skill_keywords if contains_term(resume_lower, skill)]
    matched_keywords = [keyword for keyword in job_keywords if contains_term(resume_lower, keyword)][:8]
    missing_keywords = [keyword for keyword in job_keywords if not contains_term(resume_lower, keyword)][:8]
    strengths: list[str] = []
    gaps: list[str] = []
    recommendations: list[str] = []

    if matched_skills:
        strengths.append(f"Your resume mentions role-relevant skills: {', '.join(matched_skills[:5])}.")
    elif matched_keywords:
        strengths.append(f"Your resume already matches these job terms: {', '.join(matched_keywords[:5])}.")
    if any(contains_term(resume_lower, keyword) for keyword in keyword_list(target_role)):
        strengths.append(f"Your resume has visible alignment with {target_role}.")
    if re.search(r"\b(\d+%|\d+\+?\s*(years?|yrs?)|\$\d+|\d+x)\b", resume_text, re.I):
        strengths.append("Your resume includes measurable details, which helps ATS and recruiter screening.")
    if not strengths:
        strengths.append("Your resume was readable, but it does not yet show strong direct overlap with the pasted job description.")

    if missing_keywords:
        gaps.append(f"Important job keywords are missing or not obvious: {', '.join(missing_keywords[:5])}.")
    if job.experience and job.experience.lower() not in resume_lower:
        gaps.append(f"The resume does not clearly mirror the requested experience level: {job.experience}.")
    if score < 70:
        gaps.append("The resume needs stronger direct overlap with the pasted job description before interview scheduling.")
    if not re.search(r"\b(built|led|owned|delivered|improved|reduced|increased|designed|deployed)\b", resume_lower):
        gaps.append("Project impact is not explicit enough; add action verbs and outcomes for key work.")

    if missing_keywords:
        recommendations.append(f"Add truthful keywords from the role where relevant: {', '.join(missing_keywords[:6])}.")
    recommendations.append(f"Rewrite 2-3 bullets to directly connect your projects to {target_role} responsibilities.")
    recommendations.append("Include metrics, scale, tools, and business impact for your strongest projects.")
    if inferred_skills:
        recommendations.append(f"Create a skills section that clearly lists matching tools such as {', '.join(inferred_skills[:6])}.")
    update_keywords = missing_keywords[:4] or inferred_skills[:4] or [target_role]
    resume_updates = resume_line_updates(resume_text, target_role, update_keywords)

    if score >= 70:
        verdict = f"Your resume is above the interview threshold for {target_role}, with enough overlap to begin interview practice."
    else:
        verdict = f"Your resume currently scores below the 70% interview threshold for {target_role}. Improve keyword overlap, project evidence, and measurable impact before scheduling."

    return {
        "verdict": verdict,
        "strengths": strengths[:4],
        "gaps": gaps[:4],
        "missing_keywords": missing_keywords[:8],
        "recommendations": recommendations[:4],
        "resume_updates": resume_updates,
    }


def resume_line_updates(resume_text: str, target_role: str, keywords: list[str]) -> list[dict]:
    lines = [
        re.sub(r"\s+", " ", line).strip(" -•\t")
        for line in re.split(r"[\r\n]+|(?<=\.)\s+", resume_text)
    ]
    useful_lines = [line for line in lines if 25 <= len(line) <= 220]
    selected = useful_lines[:4]
    keyword_text = ", ".join(keywords[:3])
    updates: list[dict] = []
    for index, line in enumerate(selected):
        has_metric = bool(re.search(r"\b(\d+%|\d+\+?\s*(years?|yrs?|users?|requests?|projects?|teams?)|\$\d+|\d+x)\b", line, re.I))
        has_action = bool(re.search(r"\b(built|led|owned|delivered|improved|reduced|increased|designed|deployed|implemented|created|managed)\b", line, re.I))
        if index == 0:
            updated = f"{target_role} candidate with hands-on experience in {keyword_text or 'the role requirements'}, backed by project evidence and measurable outcomes."
            reason = "Your opening line should immediately reflect the pasted job description instead of staying generic."
        elif not has_metric:
            updated = f"{line.rstrip('.')} using {keyword_text or 'role-relevant tools'}; add a metric such as users, time saved, accuracy, cost, revenue, or performance improvement."
            reason = "ATS and recruiters rank bullets higher when responsibilities are tied to measurable impact."
        elif not has_action:
            updated = f"Led or delivered {line[0].lower() + line[1:] if len(line) > 1 else line}"
            reason = "Starting with an ownership verb makes your contribution clearer."
        else:
            updated = f"{line.rstrip('.')} and connect it directly to {target_role} requirements such as {keyword_text or 'the key skills from the JD'}."
            reason = "This keeps the strong evidence while making the job match more explicit."
        updates.append({"current_line": line, "updated_line": updated, "reason": reason})

    while len(updates) < 4:
        updates.append({
            "current_line": "No clear resume line found for this missing requirement.",
            "updated_line": f"Add a truthful bullet showing experience with {keyword_text or target_role} and the measurable result.",
            "reason": "The pasted job description asks for this signal, but it is not easy to find in the resume.",
        })
    return updates[:4]


def matched_resume_lines(resume_text: str, terms: list[str], limit: int = 4) -> list[str]:
    lines = [
        re.sub(r"\s+", " ", line).strip(" -•\t")
        for line in re.split(r"[\r\n]+|(?<=\.)\s+", resume_text)
    ]
    useful_lines = [line for line in lines if 25 <= len(line) <= 220]
    matches = [line for line in useful_lines if any(contains_term(line.lower(), term) for term in terms)]
    combined = list(dict.fromkeys([*matches, *useful_lines]))
    return combined[:limit]


def role_family(job: JobResult, terms: list[str]) -> str:
    text = " ".join([job.title, job.summary, " ".join(terms)]).lower()
    families = [
        ("data", ("data", "analytics", "sql", "python", "machine learning", "model", "dashboard", "excel", "power bi", "tableau")),
        ("frontend", ("frontend", "front-end", "react", "javascript", "typescript", "css", "ui", "accessibility")),
        ("backend", ("backend", "api", "database", "microservice", "server", "django", "fastapi", "node", "java")),
        ("devops", ("devops", "cloud", "aws", "azure", "docker", "kubernetes", "ci/cd", "terraform")),
        ("mobile", ("android", "ios", "flutter", "react native", "mobile")),
        ("security", ("security", "soc", "iam", "threat", "vulnerability", "compliance")),
        ("sales", ("sales", "crm", "pipeline", "lead", "quota", "client", "customer")),
        ("marketing", ("marketing", "campaign", "seo", "content", "brand", "social media", "conversion")),
    ]
    for family, markers in families:
        if any(marker in text for marker in markers):
            return family
    return "general"


def technical_interview_questions(job: JobResult, resume_text: str, ats_score: int, ats_summary: str | None = None) -> list[str]:
    target_role = role_label(job)
    cleaned_summary = clean_job_text(job.summary)
    responsibility_lines = [
        re.sub(r"\s+", " ", line).strip(" -•\t")
        for line in re.split(r"[\r\n.]+", cleaned_summary)
        if 35 <= len(re.sub(r"\s+", " ", line).strip(" -•\t")) <= 180
    ]
    technical_terms = [
        term for term in [*job.skills, *keyword_list(cleaned_summary)]
        if len(term) >= 3 and term.lower() not in STOPWORDS
    ]
    deduped_terms = list(dict.fromkeys(technical_terms))[:10]
    primary = deduped_terms[0] if deduped_terms else "the main technical requirement"
    secondary = deduped_terms[1] if len(deduped_terms) > 1 else "the related tools"
    tertiary = deduped_terms[2] if len(deduped_terms) > 2 else "the expected workflow"
    resume_lines = matched_resume_lines(resume_text, deduped_terms)
    project_line = resume_lines[0] if resume_lines else "your strongest resume project"
    second_line = resume_lines[1] if len(resume_lines) > 1 else project_line
    third_line = resume_lines[2] if len(resume_lines) > 2 else second_line
    responsibility = responsibility_lines[0] if responsibility_lines else f"use {primary} for the work described in the job description"
    second_responsibility = responsibility_lines[1] if len(responsibility_lines) > 1 else responsibility
    summary_hint = ats_summary or "the ATS review"
    family = role_family(job, deduped_terms)

    family_questions = {
        "data": [
            f"The JD points to {primary}. What dataset would you need, how would you clean it, and which metric would prove the analysis is useful?",
            f"Using your resume line \"{project_line}\", explain the SQL/Python/analytics steps you would take to reproduce that outcome for this role.",
        ],
        "frontend": [
            f"The JD points to {primary}. How would you structure the UI state, components, and accessibility checks for \"{responsibility}\"?",
            f"Using your resume line \"{project_line}\", explain how you handled rendering, API data, errors, and performance.",
        ],
        "backend": [
            f"The JD points to {primary}. Design the endpoint, data model, validation, and failure handling for \"{responsibility}\".",
            f"Using your resume line \"{project_line}\", explain the backend architecture, database choices, and scaling bottlenecks.",
        ],
        "devops": [
            f"The JD points to {primary}. How would you build the deployment, monitoring, rollback, and alerting plan for \"{responsibility}\"?",
            f"Using your resume line \"{project_line}\", explain the pipeline or infrastructure decisions and how you kept it reliable.",
        ],
        "mobile": [
            f"The JD points to {primary}. How would you design the mobile screen flow, offline/error states, and release validation for \"{responsibility}\"?",
            f"Using your resume line \"{project_line}\", explain the app architecture, state management, and device testing strategy.",
        ],
        "security": [
            f"The JD points to {primary}. How would you identify, prioritize, and remediate risks in \"{responsibility}\"?",
            f"Using your resume line \"{project_line}\", explain the security controls, evidence, and escalation path you used.",
        ],
        "sales": [
            f"The JD points to {primary}. How would you qualify a lead, map stakeholders, and move an opportunity tied to \"{responsibility}\"?",
            f"Using your resume line \"{project_line}\", explain your sales process, objection handling, and conversion metric.",
        ],
        "marketing": [
            f"The JD points to {primary}. How would you plan the campaign, audience, channel mix, and success metrics for \"{responsibility}\"?",
            f"Using your resume line \"{project_line}\", explain the creative/testing decisions and what performance data changed your approach.",
        ],
        "general": [
            f"The JD says \"{responsibility}\". How would you approach that work using {primary}, and what would you deliver first?",
            f"Your resume says: \"{project_line}\". Walk through the tools, workflow, and your exact contribution.",
        ],
    }

    questions = [
        *family_questions[family],
        f"The job description emphasizes {primary}, {secondary}, and {tertiary}. Which of these is your strongest area, and what production-level example proves it?",
        f"Compare \"{second_responsibility}\" with your resume line \"{second_line}\". What parts already match, and what would you need to learn or adapt?",
        f"If you had to improve or scale the work described in \"{second_line}\", what would you change technically and how would you measure success?",
        f"For a task involving {primary} and {secondary}, what data model, workflow, API, or process would you design for this specific role?",
        f"Pick one missing or weaker ATS area from this review: {summary_hint}. How would you close that gap with a concrete project or learning plan?",
        f"How would you test, debug, or validate a feature or workflow involving {primary} before handing it to users or stakeholders?",
        f"Your resume also says: \"{third_line}\". Which metric, log, user feedback, or review signal would prove this work succeeded in the {target_role} role?",
        f"On day one as {target_role}, if assigned \"{responsibility}\", what exact technical steps would you take in the first week?",
    ]
    return questions[:10]


def resume_improvement_questions(job: JobResult, resume_text: str, missing_keywords: list[str], recommendations: list[str]) -> list[str]:
    target_role = role_label(job)
    cleaned_summary = clean_job_text(job.summary)
    terms = list(dict.fromkeys([*missing_keywords, *inferred_job_skills(job, cleaned_summary), *keyword_list(cleaned_summary)]))
    primary = terms[0] if terms else "the most important job requirement"
    secondary = terms[1] if len(terms) > 1 else "the required tools"
    tertiary = terms[2] if len(terms) > 2 else "the role responsibilities"
    resume_lines = matched_resume_lines(resume_text, terms)
    project_line = resume_lines[0] if resume_lines else "your strongest project or work experience"
    guidance = recommendations[0] if recommendations else f"connect your resume more directly to {target_role}"
    questions = [
        f"Have you used {primary} in a real project, internship, job, or coursework? Describe what you did, the tools, and the outcome.",
        f"The job also mentions {secondary}. What related experience do you have, and what measurable result can we safely add to your resume?",
        f"Which resume line or project is closest to this role: \"{project_line}\"? Share what extra details, scale, metrics, or responsibilities are missing.",
        f"Have you handled work similar to {tertiary} for users, clients, teams, or a production system? Explain your role and impact.",
        f"The ATS recommendation says to {guidance.rstrip('.')}. Which truthful skills, keywords, certifications, or achievements should be added?",
    ]
    return questions[:5]


def clean_question_text(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("question") or "").strip()
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw.replace("'", '"'))
        if isinstance(parsed, dict):
            return str(parsed.get("question") or "").strip()
    except json.JSONDecodeError:
        pass
    match = re.search(r"['\"]question['\"]\s*:\s*['\"](.+?)['\"]\s*,\s*['\"]purpose['\"]", raw)
    return (match.group(1) if match else raw).replace("\\'", "'").replace('\\"', '"').strip()


def fallback_tailored_resume(
    job: JobResult,
    resume_text: str,
    answers: list[ResumeImproveAnswer],
    missing_keywords: list[str],
    recommendations: list[str],
) -> dict:
    target_role = role_label(job)
    cleaned_summary = clean_job_text(job.summary)
    skills = list(dict.fromkeys([*job.skills, *inferred_job_skills(job, cleaned_summary), *missing_keywords]))[:12]
    useful_answers = [
        re.sub(r"\s+", " ", answer.answer).strip()
        for answer in answers
        if len(answer.answer.strip()) >= 8 and answer.answer.strip().lower() not in {"no", "n/a", "none", "not applicable"}
    ]
    original_lines = [
        re.sub(r"\s+", " ", line).strip(" -•\t")
        for line in re.split(r"[\r\n]+|(?<=\.)\s+", resume_text)
        if 12 <= len(re.sub(r"\s+", " ", line).strip(" -•\t")) <= 220
    ]
    matched_lines = matched_resume_lines(resume_text, skills)
    bullets: list[str] = []
    for answer in useful_answers[:5]:
        action = answer.rstrip(".")
        if not re.search(r"\b(built|led|owned|delivered|improved|reduced|increased|designed|deployed|implemented|created|managed|used|analyzed)\b", action, re.I):
            action = f"Applied {skills[0] if skills else 'role-relevant skills'} to {action[0].lower() + action[1:] if len(action) > 1 else action}"
        bullets.append(f"- {action}.")
    for line in matched_lines:
        if len(bullets) >= 7:
            break
        bullets.append(f"- {line.rstrip('.')}.")
    while len(bullets) < 5 and original_lines:
        line = original_lines[len(bullets) % len(original_lines)].rstrip(".")
        bullets.append(f"- {line}.")
    skills_line = ", ".join(skills[:10]) or "Role-specific tools, measurable impact, cross-functional delivery"
    recommendation_line = " ".join(recommendations[:2]) if recommendations else f"Tailored toward {target_role} responsibilities."
    tailored = "\n".join([
        f"{target_role} Resume",
        "",
        "Professional Summary",
        f"{target_role} candidate with experience aligned to {job.company or 'the target company'} requirements, including {skills_line}. {recommendation_line}",
        "",
        "Core Skills",
        skills_line,
        "",
        "Relevant Experience",
        *bullets[:7],
        "",
        "Original Resume Context",
        compact_text(resume_text, 1800),
    ])
    score = max(70, deterministic_ats_score(job, tailored))
    return {
        "resume_text": tailored,
        "expected_ats_score": score,
        "summary": f"Generated a truthful tailored resume draft for {target_role} using your original resume and answers.",
        "changes": [
            "Moved the target role and matching skills into the summary.",
            "Added answer-backed bullets for job requirements that were missing from the ATS scan.",
            "Preserved original resume context so the draft stays grounded in your existing experience.",
        ],
    }


def fallback_interview_feedback(job: JobResult, answers: list[InterviewAnswer], score: int) -> dict:
    answer_text = " ".join(answer.answer for answer in answers)
    answer_lower = answer_text.lower()
    answered_count = sum(1 for answer in answers if answer.answer.strip())
    average_words = 0
    if answered_count:
        average_words = sum(len(answer.answer.split()) for answer in answers) // answered_count
    strengths: list[str] = []
    improvements: list[str] = []
    guidance: list[str] = []

    if answered_count >= 10:
        strengths.append("You completed all 10 interview questions, which gives the interviewer enough signal to evaluate you.")
    if any(skill.lower() in answer_lower for skill in job.skills):
        matched = [skill for skill in job.skills if skill.lower() in answer_lower][:5]
        strengths.append(f"You referenced role-relevant skills in your answers: {', '.join(matched)}.")
    if re.search(r"\b(built|created|designed|deployed|led|owned|improved|reduced|increased|implemented)\b", answer_lower):
        strengths.append("You used project/action language, which helps show ownership instead of only theory.")
    if re.search(r"\b(\d+%|\d+\+?\s*(users?|requests?|years?|yrs?)|\$\d+|\d+x)\b", answer_text, re.I):
        strengths.append("You included measurable details in at least one answer.")
    if not strengths:
        strengths.append("You provided answers that can now be evaluated against the job requirements.")

    if average_words < 35:
        improvements.append("Several answers are too short; expand them with context, your exact action, and the result.")
    if not re.search(r"\b(result|impact|outcome|improved|reduced|increased|saved|scaled)\b", answer_lower):
        improvements.append("Your answers need clearer outcomes and business or technical impact.")
    missing_skills = [skill for skill in job.skills if skill.lower() not in answer_lower][:5]
    if missing_skills:
        improvements.append(f"You did not clearly mention these job skills during the interview: {', '.join(missing_skills)}.")
    if not re.search(r"\b(challenge|tradeoff|decision|because|why)\b", answer_lower):
        improvements.append("Add more reasoning about tradeoffs, decisions, and why you chose each approach.")
    if not improvements:
        improvements.append("Make strong answers even sharper by adding metrics, tradeoffs, and lessons learned.")

    guidance.append("Use the STAR structure: situation, task, action, and measurable result.")
    guidance.append(f"For {job.title}, connect each answer directly to the job responsibilities and required skills.")
    guidance.append("When discussing projects, name the tools used, the scale of the system, and your personal contribution.")
    guidance.append("End technical answers with what you would improve next or how you validated the solution.")
    question_feedback = [
        {
            "question": answer.question,
            "your_answer": answer.answer,
            "expected_answer": (
                f"A strong answer should directly address the question, connect to {job.title}, "
                "include a specific example, explain your personal actions, mention relevant tools or skills, "
                "and close with a measurable result or lesson learned."
            ),
            "feedback": "Add more role-specific evidence, structure, and measurable impact." if len(answer.answer.split()) < 50 else "Good base answer; sharpen it with clearer outcomes and tradeoffs.",
        }
        for answer in answers[:10]
    ]

    if score >= 75:
        signal = "Strong interview signal"
        summary = f"Your interview answers show promising fit for {job.title}. To improve further, make the evidence more specific and measurable."
    elif score >= 50:
        signal = "Mixed interview signal"
        summary = f"Your interview has useful material, but the answers need stronger depth, examples, and clearer connection to {job.title}."
    else:
        signal = "Needs review"
        summary = f"Your interview needs more complete, evidence-backed answers before it would be convincing for {job.title}."

    return {
        "hiring_signal": signal,
        "summary": summary,
        "strengths": strengths[:4],
        "improvements": improvements[:4],
        "better_answer_guidance": guidance[:4],
        "question_feedback": question_feedback,
    }


def normalize_resume_updates(values: object, fallback: list[dict]) -> list[dict]:
    rows: list[dict] = []
    if isinstance(values, list):
        for value in values:
            if not isinstance(value, dict):
                continue
            current_line = str(value.get("current_line") or "").strip()
            updated_line = str(value.get("updated_line") or "").strip()
            reason = str(value.get("reason") or "").strip()
            if current_line and updated_line and reason:
                rows.append({"current_line": current_line, "updated_line": updated_line, "reason": reason})
    return rows[:8] or fallback


def normalize_question_feedback(values: object, answers: list[InterviewAnswer], fallback: list[dict]) -> list[dict]:
    rows: list[dict] = []
    if isinstance(values, list):
        for index, value in enumerate(values[:10]):
            if not isinstance(value, dict):
                continue
            answer = answers[index] if index < len(answers) else None
            question = str(value.get("question") or answer.question if answer else "").strip()
            your_answer = str(value.get("your_answer") or answer.answer if answer else "").strip()
            expected_answer = str(value.get("expected_answer") or "").strip()
            feedback = str(value.get("feedback") or "").strip()
            if question and your_answer and expected_answer and feedback:
                rows.append({
                    "question": question,
                    "your_answer": your_answer,
                    "expected_answer": expected_answer,
                    "feedback": feedback,
                })
    return rows[:10] or fallback


async def score_resume(settings: Settings, job: JobResult, resume_text: str) -> AtsScoreResponse:
    system = (
        "You are an ATS and recruiter calibration engine. Score the resume against the job with strict evidence. "
        "Consider required skills, role seniority, domain fit, project/experience relevance, keywords, measurable impact, and gaps. "
        "For resume_updates, provide line-by-line resume adaptation guidance: quote or summarize the current weak line, provide a stronger replacement line, and explain why. "
        "Do not reward generic claims. Return only JSON matching the schema."
    )
    data = await nvidia_json(
        settings,
        system,
        {"job": job_context(job), "resume_text": resume_text, "scoring_scale": "0 means no fit, 100 means exceptional interview-ready fit"},
        ATS_SCHEMA,
    )
    data.setdefault("score", 0)
    score = deterministic_ats_score(job, resume_text)
    fallback = fallback_ats_details(job, resume_text, score)
    data["score"] = score
    if not data.get("verdict") or "did not provide" in str(data.get("verdict")).lower():
        data["verdict"] = fallback["verdict"]
    for field in ("strengths", "gaps", "missing_keywords", "recommendations", "resume_updates"):
        values = data.get(field)
        if not isinstance(values, list) or not [value for value in values if value]:
            data[field] = fallback[field]
    data["resume_updates"] = normalize_resume_updates(data.get("resume_updates"), fallback["resume_updates"])
    return AtsScoreResponse(job=job, resume_text=resume_text, **data)


async def generate_resume_improvement_questions(
    settings: Settings,
    job: JobResult,
    resume_text: str,
    ats_score: int,
    missing_keywords: list[str],
    recommendations: list[str],
) -> ResumeImproveQuestionResponse:
    system = (
        "You are a resume strategist. Create 4-5 short, specific questions that collect truthful evidence before rewriting a resume. "
        "Ask whether the candidate has actually done job-relevant work, what tools they used, what scale or metric applies, and which resume project can be strengthened. "
        "Do not ask generic questions. Return only JSON."
    )
    fallback = resume_improvement_questions(job, resume_text, missing_keywords, recommendations)
    data = await nvidia_json(
        settings,
        system,
        {
            "job": job_context(job),
            "resume_text": resume_text,
            "ats_score": ats_score,
            "missing_keywords": missing_keywords,
            "recommendations": recommendations,
        },
        RESUME_IMPROVE_QUESTIONS_SCHEMA,
        max_tokens=2048,
    )
    questions = [clean_question_text(question) for question in data.get("questions", [])]
    questions = [
        question for question in questions
        if question and "'purpose':" not in question.lower() and '"purpose":' not in question.lower()
    ]
    if len(questions) < 4:
        questions = fallback
    data["questions"] = questions[:5]
    return ResumeImproveQuestionResponse(**data)


async def generate_tailored_resume(
    settings: Settings,
    job: JobResult,
    resume_text: str,
    ats_score: int,
    missing_keywords: list[str],
    recommendations: list[str],
    answers: list[ResumeImproveAnswer],
) -> ResumeImproveGenerateResponse:
    system = (
        "You are an expert resume editor for ATS optimization. Rewrite the resume for the target job using only the original resume and the candidate's answers. "
        "Never invent employers, degrees, certifications, metrics, tools, or responsibilities. If evidence is thin, phrase bullets conservatively. "
        "Include ATS keywords naturally, keep the resume plain-text, and make it ready to download. Return only JSON."
    )
    fallback = fallback_tailored_resume(job, resume_text, answers, missing_keywords, recommendations)
    data = await nvidia_json(
        settings,
        system,
        {
            "job": job_context(job),
            "original_resume_text": resume_text,
            "ats_score": ats_score,
            "missing_keywords": missing_keywords,
            "recommendations": recommendations,
            "answers": [answer.model_dump() for answer in answers],
            "target": "Produce a truthful ATS-optimized resume likely to score at least 70 when evidence supports it.",
        },
        RESUME_IMPROVE_GENERATE_SCHEMA,
        max_tokens=6144,
    )
    tailored_text = compact_text(str(data.get("resume_text") or ""), 30000)
    if len(tailored_text) < 80:
        data = fallback
    else:
        data["resume_text"] = tailored_text
        data["expected_ats_score"] = max(70, deterministic_ats_score(job, tailored_text))
        if not data.get("summary"):
            data["summary"] = fallback["summary"]
        changes = data.get("changes")
        if not isinstance(changes, list) or not [change for change in changes if change]:
            data["changes"] = fallback["changes"]
    return ResumeImproveGenerateResponse(**data)


async def generate_questions(settings: Settings, job: JobResult, resume_text: str, ats_score: int, ats_summary: str | None) -> InterviewStartResponse:
    system = (
        "You are a senior interviewer. Create exactly 10 interview questions for this candidate and role. "
        "Blend technical, project, behavioral, and role-specific questions. Use the resume projects or experience when present. "
        "Questions should become more probing across the interview and be answerable in a web form. Return only JSON."
    )
    data = await nvidia_json(
        settings,
        system,
        {"job": job_context(job), "resume_text": resume_text, "ats_score": ats_score, "ats_summary": ats_summary},
        QUESTIONS_SCHEMA,
    )
    questions = [str(question) for question in data.get("questions", []) if question]
    generic_markers = ("tell me about yourself", "why should", "strengths and weaknesses", "where do you see yourself")
    if len(questions) < 10 or any(any(marker in question.lower() for marker in generic_markers) for question in questions[:3]):
        questions = technical_interview_questions(job, resume_text, ats_score, ats_summary)
    while len(questions) < 10:
        questions.append(f"Explain a technical project or experience that proves your fit for {role_label(job)}.")
    data["questions"] = questions[:10]
    return InterviewStartResponse(**data)


async def grade_interview(settings: Settings, job: JobResult, resume_text: str, answers: list[InterviewAnswer]) -> InterviewFeedbackResponse:
    system = (
        "You are an interview coach and hiring panel reviewer. Evaluate the candidate's answers for correctness, depth, clarity, "
        "relevance to the job, evidence from projects, communication, and improvement areas. Give practical guidance for better answers. "
        "For question_feedback, return one row for every submitted question with the user's answer, the expected answer, and concise feedback. "
        "Return only JSON matching the schema."
    )
    data = await nvidia_json(
        settings,
        system,
        {"job": job_context(job), "resume_text": resume_text, "answers": [answer.model_dump() for answer in answers]},
        FEEDBACK_SCHEMA,
        max_tokens=6144,
    )
    data.setdefault("overall_score", 0)
    score = max(0, min(100, int(data.get("overall_score") or 0)))
    fallback = fallback_interview_feedback(job, answers, score)
    data["overall_score"] = score
    if not data.get("hiring_signal"):
        data["hiring_signal"] = fallback["hiring_signal"]
    if not data.get("summary") or "did not provide" in str(data.get("summary")).lower():
        data["summary"] = fallback["summary"]
    for field in ("strengths", "improvements", "better_answer_guidance", "question_feedback"):
        values = data.get(field)
        if not isinstance(values, list) or not [value for value in values if value]:
            data[field] = fallback[field]
    data["question_feedback"] = normalize_question_feedback(data.get("question_feedback"), answers, fallback["question_feedback"])
    return InterviewFeedbackResponse(**data)
