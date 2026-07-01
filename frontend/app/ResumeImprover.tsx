"use client";

import { useState } from "react";
import { Download, FileText, Loader2, Sparkles } from "lucide-react";
import { API, AtsResult, ResumeImproveAnswer, ResumeImproveResult } from "./shared";

type Props = {
  result: AtsResult;
  onResumeReady: (result: AtsResult) => void;
};

type ExportFormat = "pdf" | "doc" | "md" | "txt";

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

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function publicResumeText(text: string) {
  return text.split(/\nOriginal Resume Context\b/i)[0].trim();
}

function normalizeResumeLines(text: string) {
  return publicResumeText(text)
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
}

function isSectionHeading(line: string, index: number) {
  if (index === 0) return true;
  return /^(professional summary|summary|core skills|skills|technical skills|relevant experience|experience|work experience|projects|education|certifications|achievements)$/i.test(line);
}

function resumeBaseName(title: string) {
  return `${title || "tailored"}-resume`.replace(/[^a-z0-9.-]+/gi, "-").replace(/^-|-$/g, "").toLowerCase();
}

function formatResumeMarkdown(text: string) {
  return normalizeResumeLines(text).map((line, index) => {
    if (index === 0) return `# ${line.replace(/\s+Resume$/i, "")}`;
    if (isSectionHeading(line, index)) return `\n## ${line}`;
    if (line.startsWith("-")) return line;
    return line;
  }).join("\n");
}

function formatResumePlainText(text: string) {
  return normalizeResumeLines(text).map((line, index) => {
    if (isSectionHeading(line, index)) {
      const heading = index === 0 ? line.replace(/\s+Resume$/i, "") : line.toUpperCase();
      return `${index === 0 ? "" : "\n"}${heading}\n${"=".repeat(Math.min(heading.length, 42))}`;
    }
    return line;
  }).join("\n");
}

function formatResumeHtml(text: string) {
  const lines = normalizeResumeLines(text);
  const body = lines.map((line, index) => {
    if (index === 0) return `<h1>${escapeHtml(line.replace(/\s+Resume$/i, ""))}</h1>`;
    if (isSectionHeading(line, index)) return `<h2>${escapeHtml(line)}</h2>`;
    if (line.startsWith("-")) return `<p class="bullet">${escapeHtml(line.replace(/^-\s*/, ""))}</p>`;
    return `<p>${escapeHtml(line)}</p>`;
  }).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    body{font-family:Arial,sans-serif;color:#111827;line-height:1.45;margin:48px;max-width:760px}
    h1{font-size:24px;margin:0 0 18px;text-align:center;letter-spacing:.4px}
    h2{font-size:13px;margin:22px 0 8px;border-bottom:1px solid #CBD5E1;padding-bottom:4px;text-transform:uppercase;letter-spacing:.8px}
    p{font-size:11.5px;margin:5px 0}.bullet{padding-left:16px;text-indent:-10px}
    .bullet:before{content:"• ";font-weight:bold}
  </style></head><body>${body}</body></html>`;
}

function pdfEscape(value: string) {
  return value.replace(/[^\x09\x0A\x0D\x20-\x7E]/g, "").replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

function wrapPdfLine(line: string, maxChars = 92) {
  const words = line.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  words.forEach(word => {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  });
  if (current) lines.push(current);
  return lines;
}

function makeResumePdf(text: string) {
  const lines = formatResumePlainText(text).split(/\n/).flatMap(line => line ? wrapPdfLine(line) : [""]);
  const pageLines = 47;
  const pages: string[][] = [];
  for (let index = 0; index < lines.length; index += pageLines) pages.push(lines.slice(index, index + pageLines));
  const fontObject = pages.length * 2 + 3;
  const objects: string[] = ["<< /Type /Catalog /Pages 2 0 R >>", ""];
  const kids: string[] = [];
  pages.forEach(page => {
    const pageObject = objects.length + 1;
    const contentObject = pageObject + 1;
    kids.push(`${pageObject} 0 R`);
    const stream = `BT /F1 10.5 Tf 54 738 Td 0 -15 TD\n${page.map(line => `(${pdfEscape(line)}) Tj T*`).join("\n")}\nET`;
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 ${fontObject} 0 R >> >> /Contents ${contentObject} 0 R >>`);
    objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  });
  objects[1] = `<< /Type /Pages /Kids [${kids.join(" ")}] /Count ${pages.length} >>`;
  objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, "0")} 00000 n `).join("\n")}\n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return new Blob([pdf], { type: "application/pdf" });
}

function downloadResume(format: ExportFormat, title: string, resumeText: string) {
  const baseName = resumeBaseName(title);
  if (format === "pdf") {
    downloadBlob(`${baseName}.pdf`, makeResumePdf(resumeText));
  } else if (format === "doc") {
    downloadBlob(`${baseName}.doc`, new Blob([formatResumeHtml(resumeText)], { type: "application/msword;charset=utf-8" }));
  } else if (format === "md") {
    downloadBlob(`${baseName}.md`, new Blob([formatResumeMarkdown(resumeText)], { type: "text/markdown;charset=utf-8" }));
  } else {
    downloadBlob(`${baseName}.txt`, new Blob([formatResumePlainText(resumeText)], { type: "text/plain;charset=utf-8" }));
  }
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
      <div className="resume-export-actions" aria-label="Download resume formats">
        <button onClick={() => downloadResume("pdf", result.job.title, generated.resume_text)}><Download size={15}/>PDF</button>
        <button onClick={() => downloadResume("doc", result.job.title, generated.resume_text)}><FileText size={15}/>DOC</button>
        <button onClick={() => downloadResume("md", result.job.title, generated.resume_text)}><FileText size={15}/>MD</button>
        <button onClick={() => downloadResume("txt", result.job.title, generated.resume_text)}><FileText size={15}/>TXT</button>
      </div>
    </div>}
    {error && <p className="flow-error">{error}</p>}
  </section>;
}
