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
    "to", "using", "with", "work", "you", "your", "will",
}


def keyword_list(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.]{2,}", text)
    seen: dict[str, str] = {}
    for word in words:
        lowered = word.lower()
        if lowered not in STOPWORDS and lowered not in seen:
            seen[lowered] = word
    return list(seen.values())


def contains_term(text: str, term: str) -> bool:
    term = term.strip().lower()
    if not term:
        return False
    if re.search(r"[+#.]", term):
        return term in text
    return bool(re.search(rf"\b{re.escape(term)}\b", text))


def heuristic_ats_score(job: JobResult, resume_text: str) -> int:
    resume_lower = resume_text.lower()
    title_keywords = keyword_list(job.title)
    job_keywords = keyword_list(" ".join([job.title, job.summary, " ".join(job.skills)]))
    meaningful_keywords = [keyword for keyword in job_keywords if len(keyword) >= 4][:30]
    skill_keywords = [skill for skill in job.skills if skill and len(skill.strip()) > 1]

    score = 12 if len(resume_text.strip()) >= 250 else 6

    if skill_keywords:
        matched_skills = [skill for skill in skill_keywords if contains_term(resume_lower, skill)]
        skill_ratio = len(matched_skills) / max(1, len(skill_keywords))
        score += round(34 * min(1, skill_ratio))

    if meaningful_keywords:
        matched_keywords = [keyword for keyword in meaningful_keywords if contains_term(resume_lower, keyword)]
        keyword_ratio = len(matched_keywords) / max(1, len(meaningful_keywords))
        score += round(28 * min(1, keyword_ratio))

    if title_keywords and any(contains_term(resume_lower, keyword) for keyword in title_keywords):
        score += 10

    if re.search(r"\b(built|led|owned|delivered|improved|reduced|increased|designed|deployed|implemented|created|managed)\b", resume_lower):
        score += 8

    if re.search(r"\b(\d+%|\d+\+?\s*(years?|yrs?|users?|requests?|projects?|teams?)|\$\d+|\d+x)\b", resume_text, re.I):
        score += 8

    if job.experience:
        experience_numbers = re.findall(r"\d+", job.experience)
        if not experience_numbers or any(number in resume_lower for number in experience_numbers):
            score += 5

    return max(0, min(100, score))


def fallback_ats_details(job: JobResult, resume_text: str, score: int) -> dict:
    resume_lower = resume_text.lower()
    job_keywords = keyword_list(" ".join([job.title, job.summary, " ".join(job.skills)]))
    skill_keywords = [skill for skill in job.skills if skill and len(skill) > 1]
    matched_skills = [skill for skill in skill_keywords if skill.lower() in resume_lower]
    missing_keywords = [keyword for keyword in job_keywords if keyword.lower() not in resume_lower][:8]
    strengths: list[str] = []
    gaps: list[str] = []
    recommendations: list[str] = []

    if matched_skills:
        strengths.append(f"Your resume mentions role-relevant skills: {', '.join(matched_skills[:5])}.")
    if job.title.split()[0].lower() in resume_lower or "python" in resume_lower and "python" in job.title.lower():
        strengths.append(f"Your resume has visible alignment with the {job.title} role.")
    if re.search(r"\b(\d+%|\d+\+?\s*(years?|yrs?)|\$\d+|\d+x)\b", resume_text, re.I):
        strengths.append("Your resume includes measurable details, which helps ATS and recruiter screening.")
    if not strengths:
        strengths.append("Your resume was readable and contained enough text for an ATS comparison.")

    if missing_keywords:
        gaps.append(f"Important job keywords are missing or not obvious: {', '.join(missing_keywords[:5])}.")
    if job.experience and job.experience.lower() not in resume_lower:
        gaps.append(f"The resume does not clearly mirror the requested experience level: {job.experience}.")
    if score < 70:
        gaps.append("The resume needs stronger direct overlap with the job description before interview scheduling.")
    if not re.search(r"\b(built|led|owned|delivered|improved|reduced|increased|designed|deployed)\b", resume_lower):
        gaps.append("Project impact is not explicit enough; add action verbs and outcomes for key work.")

    if missing_keywords:
        recommendations.append(f"Add truthful keywords from the role where relevant: {', '.join(missing_keywords[:6])}.")
    recommendations.append(f"Rewrite 2-3 bullets to directly connect your projects to {job.title} responsibilities.")
    recommendations.append("Include metrics, scale, tools, and business impact for your strongest projects.")
    if job.skills:
        recommendations.append(f"Create a skills section that clearly lists matching tools such as {', '.join(job.skills[:6])}.")
    update_keywords = missing_keywords[:4] or job.skills[:4] or [job.title]
    resume_updates = [
        {
            "current_line": "Existing summary or headline does not clearly mirror the target job.",
            "updated_line": f"Add a headline that names {job.title} and the strongest matching skills.",
            "reason": "The top of the resume should immediately match the role title and core requirements.",
        },
        {
            "current_line": "Project bullets describe work without enough job-specific keywords.",
            "updated_line": f"Rewrite one project bullet to include {', '.join(update_keywords[:3])} where truthful.",
            "reason": "ATS systems and recruiters both look for direct keyword overlap with the job description.",
        },
        {
            "current_line": "Impact is not consistently quantified.",
            "updated_line": "Add metrics such as users, revenue, latency, accuracy, cost, time saved, or team size.",
            "reason": "Numbers make experience easier to rank and verify.",
        },
        {
            "current_line": "Skills are spread across the resume or hard to scan.",
            "updated_line": f"Create a focused skills section for tools and methods relevant to {job.title}.",
            "reason": "A compact skills section improves both ATS parsing and human review.",
        },
    ]

    if score >= 70:
        verdict = f"Your resume is above the interview threshold for {job.title}, but targeted edits can still improve the match."
    else:
        verdict = f"Your resume currently scores below the 70% interview threshold for {job.title}. Improve keyword overlap, project evidence, and measurable impact before scheduling."

    return {
        "verdict": verdict,
        "strengths": strengths[:4],
        "gaps": gaps[:4],
        "missing_keywords": missing_keywords[:8],
        "recommendations": recommendations[:4],
        "resume_updates": resume_updates,
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
    model_score = max(0, min(100, int(data.get("score") or 0)))
    heuristic_score = heuristic_ats_score(job, resume_text)
    score = heuristic_score if model_score <= 5 and heuristic_score > model_score else model_score
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
    while len(questions) < 10:
        questions.append(f"Tell me about a project or experience that proves your fit for {job.title}.")
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
