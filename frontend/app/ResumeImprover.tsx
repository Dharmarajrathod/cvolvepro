"use client";

import { useState } from "react";
import { Download, FileText, Loader2, Sparkles } from "lucide-react";
import { API, AtsResult, ResumeImproveAnswer, ResumeImproveResult } from "./shared";

type Props = {
  result: AtsResult;
  onResumeReady: (result: AtsResult) => void;
};

function fallbackQuestions(result: AtsResult) {
  const role = result.job.title || "this role";
  const terms = [...result.missing_keywords, ...result.job.skills].filter(Boolean);
  const primary = terms[0] || "the main job requirement";
  const secondary = terms[1] || "the required tools";
  const tertiary = terms[2] || "the role responsibilities";
  return [
    `Have you used ${primary} in a real project, internship, job, or coursework? Describe what you did, the tools, and the outcome.`,
    `The job also mentions ${secondary}. What related experience do you have, and what measurable result can we safely add?`,
    `Which existing resume project best proves fit for ${role}? Share missing scale, metrics, responsibilities, or tools.`,
    `Have you handled work similar to ${tertiary} for users, clients, teams, or a production system? Explain your role and impact.`,
    "Which truthful skills, certifications, keywords, or achievements should be added to this tailored resume?",
  ];
}

function cleanQuestion(value: unknown) {
  if (value && typeof value === "object" && "question" in value) {
    return String((value as { question?: unknown }).question || "").trim();
  }
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const parsed = JSON.parse(raw.replace(/'/g, "\""));
    if (parsed && typeof parsed === "object" && "question" in parsed) return String(parsed.question || "").trim();
  } catch {}
  const match = raw.match(/["']question["']\s*:\s*["'](.+?)["']\s*,\s*["']purpose["']/);
  return (match?.[1] || raw).replace(/\\(["'])/g, "$1").trim();
}

function normalizeQuestions(values: unknown, result: AtsResult) {
  const questions = Array.isArray(values) ? values.map(cleanQuestion).filter(Boolean) : [];
  const cleanQuestions = questions.filter(question => !question.toLowerCase().includes("'purpose':") && !question.toLowerCase().includes("\"purpose\":"));
  return (cleanQuestions.length >= 4 ? cleanQuestions : fallbackQuestions(result)).slice(0, 5);
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function ResumeImprover({ result, onResumeReady }: Props) {
  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [generated, setGenerated] = useState<ResumeImproveResult | null>(null);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  async function startImprovement() {
    setLoadingQuestions(true);
    setError("");
    setGenerated(null);
    try {
      const response = await fetch(`${API}/api/resume-improve/questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job: result.job,
          resume_text: result.resume_text,
          ats_score: result.score,
          missing_keywords: result.missing_keywords,
          recommendations: result.recommendations,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Improvement questions could not be generated.");
      const nextQuestions = normalizeQuestions(body.questions, result);
      setQuestions(nextQuestions);
      setAnswers(Object.fromEntries(nextQuestions.map((question: string) => [question, ""])));
    } catch (err) {
      const nextQuestions = fallbackQuestions(result);
      setQuestions(nextQuestions);
      setAnswers(Object.fromEntries(nextQuestions.map(question => [question, ""])));
      setError(err instanceof Error ? `${err.message} Local questions are shown instead.` : "Local questions are shown instead.");
    } finally {
      setLoadingQuestions(false);
    }
  }

  async function generateResume() {
    const finalAnswers: ResumeImproveAnswer[] = questions.map(question => ({ question, answer: (answers[question] || "").trim() })).filter(item => item.answer);
    if (finalAnswers.length < 4) {
      setError("Answer at least 4 questions before generating the tailored resume.");
      return;
    }
    setGenerating(true);
    setError("");
    try {
      const response = await fetch(`${API}/api/resume-improve/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job: result.job,
          resume_text: result.resume_text,
          ats_score: result.score,
          missing_keywords: result.missing_keywords,
          recommendations: result.recommendations,
          answers: finalAnswers.slice(0, 5),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Tailored resume could not be generated.");
      const improved = body as ResumeImproveResult;
      setGenerated(improved);
      const improvedScore = Math.max(result.score, improved.expected_ats_score || 70);
      const nextResult: AtsResult = {
        ...result,
        score: improvedScore,
        verdict: improved.summary || `Your tailored resume is expected to clear the 70% ATS threshold for ${result.job.title}.`,
        strengths: [...(improved.changes || []), ...result.strengths].slice(0, 4),
        gaps: result.gaps.filter(gap => !gap.toLowerCase().includes("70%")).slice(0, 4),
        resume_text: improved.resume_text,
      };
      sessionStorage.setItem("cvolvepro:atsResult", JSON.stringify(nextResult));
      onResumeReady(nextResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tailored resume could not be generated.");
    } finally {
      setGenerating(false);
    }
  }

  if (result.score >= 70 && !generated) return null;

  return <section className="resume-improver">
    <div className="resume-improver-head">
      <div><h3><FileText size={15}/>Improve resume for this job</h3><p>Answer a few evidence questions, then generate a tailored resume draft for download.</p></div>
      {!questions.length && <button className="secondary-action compact-action" onClick={startImprovement} disabled={loadingQuestions}>{loadingQuestions ? <Loader2 className="spin" size={16}/> : <Sparkles size={16}/>}Improve my resume</button>}
    </div>
    {questions.length > 0 && !generated && <div className="resume-question-list">
      {questions.map((question, index) => <label key={question} className="resume-question-item"><span className="question-number">{index + 1}</span><span className="question-text">{question}</span><textarea value={answers[question] || ""} onChange={e=>setAnswers(current => ({ ...current, [question]: e.target.value }))} placeholder="Add truthful experience, tools, metrics, or coursework."/></label>)}
      <button className="primary-action" onClick={generateResume} disabled={generating}>{generating ? <Loader2 className="spin" size={18}/> : <Sparkles size={18}/>}Generate improved resume</button>
    </div>}
    {generated && <div className="generated-resume-card">
      <div className="generated-score"><strong>{Math.max(70, generated.expected_ats_score || 70)}%</strong><span>Expected ATS</span></div>
      <div><p>{generated.summary}</p>{generated.changes.map(change=><p key={change}><Sparkles size={13}/>{change}</p>)}</div>
      <button className="primary-action" onClick={() => downloadText(`${result.job.title || "tailored"}-resume.txt`.replace(/[^a-z0-9.-]+/gi, "-").toLowerCase(), generated.resume_text)}><Download size={18}/>Download this resume</button>
    </div>}
    {error && <p className="flow-error">{error}</p>}
  </section>;
}
