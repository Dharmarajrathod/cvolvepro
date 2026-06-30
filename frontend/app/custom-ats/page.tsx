"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, CheckCircle2, CreditCard, FileText, FileUp, Loader2, ShieldCheck, Sparkles, TriangleAlert } from "lucide-react";
import { API, AtsResult, Job, readAuthUser, saveAtsHistory, updateAuthUserCredits } from "../shared";
import ProfileMenu from "../ProfileMenu";

function makeJob(title: string, company: string, description: string, skillsText: string): Job {
  const cleanedTitle = title.trim() || "Pasted job description";
  const cleanedCompany = company.trim() || "Custom role";
  const skills = skillsText.split(",").map(skill => skill.trim()).filter(Boolean);
  return {
    id: `custom-${cleanedCompany}-${cleanedTitle}-${Date.now()}`,
    title: cleanedTitle,
    company: cleanedCompany,
    location: "Not specified",
    work_mode: "Not specified",
    employment_type: "Not specified",
    salary: null,
    experience: null,
    posted_at: null,
    skills,
    summary: description.trim(),
    match_score: 0,
    match_reason: "User pasted this job description for ATS scoring.",
    apply_url: "https://example.com/custom-job-description",
    source: "Pasted job description",
  };
}

export default function CustomAtsPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [skills, setSkills] = useState("");
  const [description, setDescription] = useState("");
  const [resume, setResume] = useState<File | null>(null);
  const [result, setResult] = useState<AtsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [needsPlan, setNeedsPlan] = useState(false);

  useEffect(() => {
    const currentUser = readAuthUser();
    if (!currentUser) {
      sessionStorage.setItem("cvolvepro:authRedirect", "/custom-ats");
      sessionStorage.setItem("cvolvepro:authMode", "login");
      router.replace("/auth");
      return;
    }
    setNeedsPlan(!currentUser.plan_id || currentUser.plan_id === "none" || Number(currentUser.credits || 0) < 5);
  }, [router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const currentUser = readAuthUser();
    if (!currentUser) {
      router.push("/auth");
      return;
    }
    if (needsPlan) {
      router.push("/plans");
      return;
    }
    if (!resume || description.trim().length < 80) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const job = makeJob(title, company, description, skills);
      const form = new FormData();
      form.append("job", JSON.stringify(job));
      Object.entries(job).forEach(([key, value]) => {
        form.append(key, Array.isArray(value) ? JSON.stringify(value) : String(value ?? ""));
      });
      form.append("resume", resume);
      form.append("user_email", currentUser.email);
      const response = await fetch(`${API}/api/ats-score`, { method: "POST", body: form });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "ATS score could not be generated.");
      if (typeof body.credits_remaining === "number") {
        updateAuthUserCredits(body.credits_remaining);
        setNeedsPlan(body.credits_remaining < 5);
      }
      setResult(body);
      sessionStorage.setItem("cvolvepro:selectedJob", JSON.stringify(job));
      sessionStorage.setItem("cvolvepro:atsResult", JSON.stringify(body));
      saveAtsHistory(readAuthUser(), body);
    } catch (err) {
      const message = err instanceof Error ? err.message : "ATS score could not be generated.";
      setError(message);
      if (message.toLowerCase().includes("choose a plan") || message.toLowerCase().includes("credits")) setNeedsPlan(true);
    } finally {
      setLoading(false);
    }
  }

  function startInterview() {
    if (!result) return;
    sessionStorage.setItem("cvolvepro:atsResult", JSON.stringify(result));
    router.push("/interview");
  }

  return <main className="flow-page shell">
    <nav className="flow-nav"><Link className="back-link" href="/jobs"><ArrowLeft size={16}/>Back to jobs</Link><ProfileMenu showCredits/></nav>
    <section className="flow-hero manual-ats-hero">
      <div>
        <span className="kicker">CUSTOM ATS CHECK</span>
        <h1>Paste any job description and check your resume fit.</h1>
        <p>Use this when you already have a role from LinkedIn, email, a company site, or a recruiter.</p>
      </div>
      <div className="job-mini">
        <b>JD</b>
        <h2>Login, choose a plan, then check ATS</h2>
        <p>ATS checks use credits from your active plan. A score of 70% or higher unlocks the same interview room.</p>
        <button className="job-mini-button" onClick={()=>router.push("/plans")}><CreditCard size={15}/>Choose plan</button>
      </div>
    </section>

    <section className="manual-ats-layout">
      <form className="manual-ats-form" onSubmit={submit}>
        <div className="manual-grid">
          <label><span>Job title</span><input value={title} onChange={e=>setTitle(e.target.value)} placeholder="Senior frontend engineer"/></label>
          <label><span>Company</span><input value={company} onChange={e=>setCompany(e.target.value)} placeholder="Company name"/></label>
        </div>
        <label><span>Key skills</span><input value={skills} onChange={e=>setSkills(e.target.value)} placeholder="React, TypeScript, accessibility"/></label>
        <label><span>Job description</span><textarea value={description} onChange={e=>setDescription(e.target.value)} placeholder="Paste the full job description here."/></label>
        <label className="resume-drop compact">
          <input type="file" accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" onChange={e=>setResume(e.target.files?.[0] || null)}/>
          <FileUp size={30}/>
          <strong>{resume ? resume.name : "Upload your resume"}</strong>
          <span>PDF, DOCX, TXT, or MD</span>
        </label>
        {needsPlan && <div className="threshold-note"><CreditCard size={15}/>Choose or refresh a plan with at least 5 credits before generating ATS.</div>}
        {error && <p className="flow-error">{error}</p>}
        <button className="primary-action" disabled={!resume || description.trim().length < 80 || loading}>{loading ? <Loader2 className="spin" size={18}/> : <Sparkles size={18}/>}Generate ATS score</button>
      </form>

      <div className="score-panel">
        {!result && <div className="waiting-card"><ShieldCheck size={34}/><h2>Paste, upload, score</h2><p>The result will include score, gaps, missing keywords, and line by line resume adaptation suggestions.</p></div>}
        {result && <div className="ats-result">
          <div className="ats-score"><strong>{result.score}</strong><span>%</span></div>
          <h2>{result.score >= 70 ? "Interview-ready fit" : "Improve before interview"}</h2>
          <p>{result.verdict}</p>
          <div className="ats-columns">
            <section><h3>Strengths</h3>{result.strengths.map(item=><p key={item}><CheckCircle2 size={14}/>{item}</p>)}</section>
            <section><h3>Gaps</h3>{result.gaps.map(item=><p key={item}><TriangleAlert size={14}/>{item}</p>)}</section>
          </div>
          <div className="keyword-row">{result.missing_keywords.map(item=><span key={item}>{item}</span>)}</div>
          <section className="recommendations"><h3>Recommended edits</h3>{result.recommendations.map(item=><p key={item}>{item}</p>)}</section>
          {Boolean(result.resume_updates?.length) && <section className="resume-update-panel"><h3><FileText size={15}/>Line by line resume adaptation</h3><div className="responsive-table"><table><thead><tr><th>Current resume line</th><th>Update to this</th><th>Why</th></tr></thead><tbody>{result.resume_updates?.map((item, index)=><tr key={`${item.updated_line}-${index}`}><td>{item.current_line}</td><td>{item.updated_line}</td><td>{item.reason}</td></tr>)}</tbody></table></div></section>}
          {result.score >= 70 ? <button className="primary-action interview-cta" onClick={startInterview}>Give interview now <ArrowRight size={18}/></button> : <div className="threshold-note">Reach 70% or above to unlock the interview for this role.</div>}
        </div>}
      </div>
    </section>
  </main>;
}
