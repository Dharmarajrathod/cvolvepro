import pytest

from app.ai_career import fallback_ats_details, heuristic_ats_score, role_label, score_resume, technical_interview_questions
from app.config import Settings
from app.schemas import JobResult


def sample_job() -> JobResult:
    return JobResult.model_validate({
        "id": "frontend-engineer",
        "title": "Frontend Engineer",
        "company": "Acme",
        "location": "Remote",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "salary": None,
        "experience": "3+ years",
        "posted_at": None,
        "skills": ["React", "TypeScript", "Accessibility", "API integration"],
        "summary": "Build React interfaces with TypeScript, accessibility standards, API integration, tests, and measurable product impact.",
        "match_score": 0,
        "match_reason": "Test role.",
        "apply_url": "https://example.com/frontend-engineer",
        "source": "Test",
    })


def sample_resume() -> str:
    return (
        "Frontend Engineer with 4 years of experience building React and TypeScript applications. "
        "Implemented accessible dashboards, integrated REST APIs, wrote tests, and improved page load speed by 32%. "
        "Led delivery of reusable UI components used by 12 product teams."
    )


def test_heuristic_ats_score_detects_resume_job_overlap():
    assert heuristic_ats_score(sample_job(), sample_resume()) >= 70


def test_fallback_ats_ignores_pasted_job_board_noise():
    job = JobResult.model_validate({
        "id": "custom",
        "title": "Pasted job description",
        "company": "Custom role",
        "location": "Not specified",
        "work_mode": "Not specified",
        "employment_type": "Not specified",
        "salary": None,
        "experience": None,
        "posted_at": None,
        "skills": [],
        "summary": "\n".join([
            "Frontend Engineer",
            "Over 100 people clicked apply",
            "Posted 3 days ago",
            "We need React, TypeScript, accessibility, API integration, and dashboard performance experience.",
        ]),
        "match_score": 0,
        "match_reason": "Pasted job.",
        "apply_url": "https://example.com/custom",
        "source": "Pasted job description",
    })
    details = fallback_ats_details(job, sample_resume(), 68)
    combined = " ".join(details["missing_keywords"] + details["recommendations"])
    assert role_label(job) == "Frontend Engineer"
    assert "days" not in combined.lower()
    assert "clicked" not in combined.lower()
    assert "pasted job description" not in combined.lower()
    assert details["resume_updates"][0]["current_line"] in sample_resume()


def test_pasted_job_without_manual_skills_can_score_strong_match():
    job = JobResult.model_validate({
        "id": "custom",
        "title": "Pasted job description",
        "company": "Custom role",
        "location": "Not specified",
        "work_mode": "Not specified",
        "employment_type": "Not specified",
        "salary": None,
        "experience": None,
        "posted_at": None,
        "skills": [],
        "summary": "Frontend Engineer\nWe need React, TypeScript, accessibility, API integration, and dashboard performance experience. Build UI components and integrate REST APIs.",
        "match_score": 0,
        "match_reason": "Pasted job.",
        "apply_url": "https://example.com/custom",
        "source": "Pasted job description",
    })
    assert heuristic_ats_score(job, sample_resume()) >= 85


def test_unrelated_resume_stays_low():
    unrelated = (
        "Restaurant shift supervisor with inventory planning, staff scheduling, vendor coordination, "
        "cash reconciliation, customer service, and daily store operations across multiple locations."
    )
    assert heuristic_ats_score(sample_job(), unrelated) < 45


def test_technical_interview_questions_use_job_and_resume_context():
    questions = technical_interview_questions(sample_job(), sample_resume(), 82, "Strong React and TypeScript fit.")
    joined = " ".join(questions).lower()
    assert len(questions) == 10
    assert "react" in joined
    assert "typescript" in joined
    assert "accessible dashboards" in joined
    assert "tell me about yourself" not in joined
    assert "technical problem you solved that is closest" not in joined
    assert "what tradeoffs would you consider" not in joined


def test_different_jobs_get_different_interview_questions():
    data_job = JobResult.model_validate({
        "id": "data-analyst",
        "title": "Data Analyst",
        "company": "Acme",
        "location": "Remote",
        "work_mode": "Remote",
        "employment_type": "Full-time",
        "salary": None,
        "experience": "2+ years",
        "posted_at": None,
        "skills": ["SQL", "Python", "Tableau", "A/B testing"],
        "summary": "Analyze product funnels, clean event datasets, build Tableau dashboards, write SQL queries, and explain experiment results to product managers.",
        "match_score": 0,
        "match_reason": "Test role.",
        "apply_url": "https://example.com/data-analyst",
        "source": "Test",
    })
    data_resume = (
        "Data analyst with 3 years using SQL and Python to clean customer datasets. "
        "Built Tableau dashboards for funnel conversion and presented A/B testing results to product teams."
    )
    frontend_questions = technical_interview_questions(sample_job(), sample_resume(), 82, "Strong React and TypeScript fit.")
    data_questions = technical_interview_questions(data_job, data_resume, 78, "Strong SQL and dashboard fit.")
    frontend_joined = " ".join(frontend_questions).lower()
    data_joined = " ".join(data_questions).lower()
    assert frontend_questions != data_questions
    assert "ui state" in frontend_joined or "rendering" in frontend_joined
    assert "dataset" in data_joined
    assert "sql" in data_joined


@pytest.mark.asyncio
async def test_score_resume_uses_stable_system_score_when_model_score_varies(monkeypatch):
    model_scores = iter([34, 85])

    async def fake_nvidia_json(*_args, **_kwargs):
        return {
            "score": next(model_scores),
            "verdict": "Model-generated verdict.",
            "strengths": [],
            "gaps": [],
            "missing_keywords": [],
            "recommendations": [],
            "resume_updates": [],
        }

    monkeypatch.setattr("app.ai_career.nvidia_json", fake_nvidia_json)
    first = await score_resume(Settings(nvidia_api_key="test"), sample_job(), sample_resume())
    second = await score_resume(Settings(nvidia_api_key="test"), sample_job(), sample_resume())
    assert first.score == second.score
    assert first.score >= 70
    assert first.resume_updates
