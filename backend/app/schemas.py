from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Literal, Optional

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

class JobSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    location: Optional[str] = Field(default=None, max_length=100)
    remote_only: bool = False
    candidate_skills: list[str] = Field(default_factory=list, max_length=40)
    employment_type: Optional[Literal["full-time", "part-time", "contract", "internship", "freelance"]] = None
    experience_level: Optional[Literal["entry", "junior", "mid", "senior", "lead"]] = None
    user_email: Optional[str] = Field(default=None, pattern=EMAIL_PATTERN, max_length=254)

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
    credits_remaining: Optional[int] = None

class SendVerificationCodeRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str):
        return value.strip().lower()

class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=8, max_length=120)
    mobile_number: str = Field(min_length=7, max_length=32)
    country: str = Field(min_length=2, max_length=80)
    account_type: Literal["personal", "business"] = "personal"
    verification_code: str = Field(min_length=6, max_length=6)

    @field_validator("name", "mobile_number", "country")
    @classmethod
    def clean_text(cls, value: str):
        return " ".join(value.split())

    @field_validator("email")
    @classmethod
    def clean_register_email(cls, value: str):
        return value.strip().lower()

class LoginRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def clean_login_email(cls, value: str):
        return value.strip().lower()

class AuthUserResponse(BaseModel):
    name: str
    email: str
    mobile_number: str
    country: str
    account_type: Literal["personal", "business"] = "personal"
    credits: int = 0
    plan_id: str = "none"

class CreateCheckoutSessionRequest(BaseModel):
    plan_id: Literal["classic", "premium", "premium_plus", "business_starter", "business_growth", "business_enterprise"]
    email: Optional[str] = Field(default=None, pattern=EMAIL_PATTERN, max_length=254)

    @field_validator("email")
    @classmethod
    def clean_checkout_email(cls, value: Optional[str]):
        return value.strip().lower() if value else value

class CheckoutSessionResponse(BaseModel):
    url: str

class SelectFreePlanRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)

    @field_validator("email")
    @classmethod
    def clean_free_plan_email(cls, value: str):
        return value.strip().lower()

class ConfirmCheckoutSessionRequest(BaseModel):
    session_id: str = Field(min_length=3, max_length=300)
    email: Optional[str] = Field(default=None, pattern=EMAIL_PATTERN, max_length=254)

    @field_validator("email")
    @classmethod
    def clean_confirm_email(cls, value: Optional[str]):
        return value.strip().lower() if value else value

class ResetPasswordRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=8, max_length=120)
    verification_code: str = Field(min_length=6, max_length=6)

    @field_validator("email")
    @classmethod
    def clean_reset_email(cls, value: str):
        return value.strip().lower()

class ResumeUpdate(BaseModel):
    current_line: str
    updated_line: str
    reason: str

class QuestionFeedback(BaseModel):
    question: str
    your_answer: str
    expected_answer: str
    feedback: str

class AtsScoreResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    verdict: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    resume_updates: list[ResumeUpdate] = Field(default_factory=list)
    resume_text: str
    job: JobResult

class ResumeImproveQuestionRequest(BaseModel):
    job: JobResult
    resume_text: str = Field(min_length=80, max_length=30000)
    ats_score: int = Field(ge=0, le=100)
    missing_keywords: list[str] = Field(default_factory=list, max_length=12)
    recommendations: list[str] = Field(default_factory=list, max_length=8)

class ResumeImproveQuestionResponse(BaseModel):
    questions: list[str] = Field(min_length=4, max_length=5)

class ResumeImproveAnswer(BaseModel):
    question: str = Field(min_length=3, max_length=1200)
    answer: str = Field(min_length=1, max_length=3000)

class ResumeImproveGenerateRequest(BaseModel):
    job: JobResult
    resume_text: str = Field(min_length=80, max_length=30000)
    ats_score: int = Field(ge=0, le=100)
    missing_keywords: list[str] = Field(default_factory=list, max_length=12)
    recommendations: list[str] = Field(default_factory=list, max_length=8)
    answers: list[ResumeImproveAnswer] = Field(min_length=4, max_length=5)

class ResumeImproveGenerateResponse(BaseModel):
    resume_text: str = Field(min_length=80, max_length=30000)
    expected_ats_score: int = Field(ge=0, le=100)
    summary: str
    changes: list[str] = Field(default_factory=list)

class InterviewStartRequest(BaseModel):
    job: JobResult
    resume_text: str = Field(min_length=80, max_length=30000)
    ats_score: int = Field(ge=0, le=100)
    ats_summary: Optional[str] = Field(default=None, max_length=1200)
    user_email: Optional[str] = Field(default=None, pattern=EMAIL_PATTERN, max_length=254)

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
    question_feedback: list[QuestionFeedback] = Field(default_factory=list)
