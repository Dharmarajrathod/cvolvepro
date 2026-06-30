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


@pytest.mark.asyncio
async def test_score_resume_replaces_zero_model_score_with_evidence_score(monkeypatch):
    async def fake_nvidia_json(*_args, **_kwargs):
        return {
            "score": 0,
            "verdict": "No fit.",
            "strengths": [],
            "gaps": [],
            "missing_keywords": [],
            "recommendations": [],
            "resume_updates": [],
        }

    monkeypatch.setattr("app.ai_career.nvidia_json", fake_nvidia_json)
    result = await score_resume(Settings(nvidia_api_key="test"), sample_job(), sample_resume())
    assert result.score >= 70
    assert result.resume_updates
