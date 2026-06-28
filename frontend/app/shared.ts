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
  credits_remaining?: number;
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
export const ATS_HISTORY_KEY = "cvolvepro:atsHistory";

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
  mobile_number?: string;
  country?: string;
  account_type?: "personal" | "business";
  credits?: number;
  plan_id?: string;
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

export function clearAuthUser() {
  localStorage.removeItem(AUTH_KEY);
}

export function updateAuthUserCredits(credits: number) {
  const user = readAuthUser();
  if (!user) return null;
  const updated = { ...user, credits };
  saveAuthUser(updated);
  return updated;
}

export type AtsHistoryItem = {
  id: string;
  checked_at: string;
  score: number;
  verdict: string;
  job: Job;
};

function historyKey(email: string) {
  return `${ATS_HISTORY_KEY}:${email.toLowerCase()}`;
}

export function readAtsHistory(user: AuthUser | null) {
  if (typeof window === "undefined" || !user) return [];
  const raw = localStorage.getItem(historyKey(user.email));
  if (!raw) return [];
  try {
    return JSON.parse(raw) as AtsHistoryItem[];
  } catch {
    return [];
  }
}

export function saveAtsHistory(user: AuthUser | null, result: AtsResult) {
  if (typeof window === "undefined" || !user) return;
  const item: AtsHistoryItem = {
    id: `${result.job.id}:${Date.now()}`,
    checked_at: new Date().toISOString(),
    score: result.score,
    verdict: result.verdict,
    job: result.job,
  };
  const history = [item, ...readAtsHistory(user)].slice(0, 50);
  localStorage.setItem(historyKey(user.email), JSON.stringify(history));
}
