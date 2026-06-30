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
  resume_updates?: ResumeUpdate[];
  resume_text: string;
  job: Job;
  credits_remaining?: number;
};

export type ResumeUpdate = {
  current_line: string;
  updated_line: string;
  reason: string;
};

export type InterviewFeedback = {
  overall_score: number;
  hiring_signal: string;
  summary: string;
  strengths: string[];
  improvements: string[];
  better_answer_guidance: string[];
  question_feedback?: QuestionFeedback[];
};

export type QuestionFeedback = {
  question: string;
  your_answer: string;
  expected_answer: string;
  feedback: string;
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

export type PricingPlan = {
  id: string;
  name: string;
  tag: string;
  price: string;
  period: string;
  items: string[];
};

export type RegionalPricing = {
  region: "india" | "international";
  country_code: string | null;
  personal_plans: PricingPlan[];
  business_plans: PricingPlan[];
};

export const fallbackPricing: RegionalPricing = {
  region: "international",
  country_code: null,
  personal_plans: [
    { id: "free", name: "Free", tag: "Best to try", price: "$0", period: "forever", items: ["10 credits", "2 job searches", "2 ATS matches", "Community support"] },
    { id: "classic", name: "Classic", tag: "Best for starters", price: "$20", period: "month", items: ["50 credits", "10 job searches", "10 ATS matches", "2 AI interviews", "Email support"] },
    { id: "premium", name: "Premium", tag: "Best value", price: "$35", period: "month", items: ["100 credits", "20 job searches", "20 ATS matches", "5 AI interviews", "Priority support"] },
    { id: "premium_plus", name: "Premium Plus", tag: "Best for active search", price: "$90", period: "3 months", items: ["350 credits", "70 job searches", "70 ATS matches", "17 AI interviews", "Priority support"] },
  ],
  business_plans: [
    { id: "business_starter", name: "Business Starter", tag: "Best for small teams", price: "$79", period: "month", items: ["500 credits", "Up to 5 team members", "Shared credits", "Job Search, ATS, AI Interview"] },
    { id: "business_growth", name: "Business Growth", tag: "Best value for teams", price: "$199", period: "quarter", items: ["2,000 credits", "Up to 15 team members", "Shared dashboard", "Priority support"] },
    { id: "business_enterprise", name: "Business Enterprise", tag: "Best for scale", price: "$799", period: "year", items: ["10,000 credits", "Unlimited team members", "API and analytics", "Priority support"] },
  ],
};

export async function fetchRegionalPricing() {
  const response = await fetch(`${API}/api/pricing`);
  if (!response.ok) throw new Error("Pricing could not be loaded.");
  return await response.json() as RegionalPricing;
}

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
