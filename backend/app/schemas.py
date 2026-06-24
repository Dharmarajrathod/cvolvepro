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
