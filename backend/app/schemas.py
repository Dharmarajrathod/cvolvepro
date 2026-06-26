from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Literal, Optional

class JobSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    location: Optional[str] = Field(default=None, max_length=100)
    remote_only: bool = False
    candidate_skills: list[str] = Field(default_factory=list, max_length=40)
    employment_type: Optional[Literal["full-time", "part-time", "contract", "internship", "freelance"]] = None
    experience_level: Optional[Literal["entry", "junior", "mid", "senior", "lead"]] = None

    @field_validator("query", "location")
    @classmethod
    def clean_text(cls, value: Optional[str]):
        return " ".join(value.split()) if value else value

class JobResult(BaseModel):
    id: str
    title: str
    company: str
    location: str
    work_mode: str = "Not specified"
    employment_type: str = "Not specified"
    salary: Optional[str] = None
    experience: Optional[str] = None
    posted_at: Optional[str] = None
    skills: list[str] = []
    summary: str
    match_score: int = Field(ge=0, le=100)
    match_reason: str
    apply_url: HttpUrl
    source: str

class JobSearchResponse(BaseModel):
    jobs: list[JobResult]
    total: int
    searched_sources: list[str]
    query_expansion: list[str]

class AtsScoreResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    verdict: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    resume_text: str
    job: JobResult

class InterviewStartRequest(BaseModel):
    job: JobResult
    resume_text: str = Field(min_length=80, max_length=30000)
    ats_score: int = Field(ge=0, le=100)
    ats_summary: Optional[str] = Field(default=None, max_length=1200)

class InterviewStartResponse(BaseModel):
    questions: list[str] = Field(min_length=10, max_length=10)

class InterviewAnswer(BaseModel):
    question: str = Field(min_length=3, max_length=1200)
    answer: str = Field(min_length=1, max_length=5000)

class InterviewFeedbackRequest(BaseModel):
    job: JobResult
    resume_text: str = Field(min_length=80, max_length=30000)
    answers: list[InterviewAnswer] = Field(min_length=10, max_length=10)

class InterviewFeedbackResponse(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    hiring_signal: str
    summary: str
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    better_answer_guidance: list[str] = Field(default_factory=list)
