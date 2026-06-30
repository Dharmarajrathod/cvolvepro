import pytest

from app.ai_career import heuristic_ats_score, score_resume
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
