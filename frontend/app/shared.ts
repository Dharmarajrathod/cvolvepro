export type Job = {
  id: string;
  title: string;
  company: string;
  location: string;
  work_mode: string;
  employment_type: string;
  salary: string | null;
  experience: string | null;
  posted_at: string | null;
  skills: string[];
  summary: string;
  match_score: number;
  match_reason: string;
  apply_url: string;
  source: string;
};

export type AtsResult = {
  score: number;
  verdict: string;
  strengths: string[];
  gaps: string[];
  missing_keywords: string[];
  recommendations: string[];
  resume_text: string;
  job: Job;
};

export type InterviewFeedback = {
  overall_score: number;
  hiring_signal: string;
  summary: string;
  strengths: string[];
  improvements: string[];
  better_answer_guidance: string[];
};

export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const AUTH_KEY = "cvolvepro:user";

export function readStoredJob() {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem("cvolvepro:selectedJob");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Job;
  } catch {
    return null;
  }
}

export type AuthUser = {
  name: string;
  email: string;
};

export function readAuthUser() {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(AUTH_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function saveAuthUser(user: AuthUser) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(user));
}
