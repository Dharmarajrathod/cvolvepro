"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, BriefcaseBusiness, CheckCircle2, ExternalLink, FileUp, Loader2, MapPin, ShieldCheck, Sparkles, TriangleAlert } from "lucide-react";
import { API, AtsResult, Job, readAuthUser, readStoredJob, saveAtsHistory, updateAuthUserCredits } from "../shared";

export default function AtsPage() {
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [resume, setResume] = useState<File | null>(null);
  const [result, setResult] = useState<AtsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!readAuthUser()) {
      sessionStorage.setItem("cvolvepro:authRedirect", "/ats");
      router.replace("/auth");
      return;
    }
    const storedJob = readStoredJob();
    setJob(storedJob);
    const rawResult = sessionStorage.getItem("cvolvepro:atsResult");
    if (rawResult) {
      try {
        const parsed = JSON.parse(rawResult) as AtsResult;
        if (!storedJob || parsed.job.id === storedJob.id) setResult(parsed);
      } catch {}
    }
  }, [router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!job || !resume) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const normalizedJob = {
        id: job.id || `${job.company}-${job.title}`,
        title: job.title || "Selected role",
        company: job.company || "Selected company",
        location: job.location || "Not specified",
        work_mode: job.work_mode || "Not specified",
        employment_type: job.employment_type || "Not specified",
        salary: job.salary || null,
        experience: job.experience || null,
        posted_at: job.posted_at || null,
        skills: Array.isArray(job.skills) ? job.skills.filter(Boolean).map(String) : [],
        summary: job.summary || "No job summary was provided.",
        match_score: Number.isFinite(Number(job.match_score)) ? Number(job.match_score) : 0,
        match_reason: job.match_reason || "Selected for ATS scoring.",
        apply_url: /^https?:\/\//.test(job.apply_url || "") ? job.apply_url : "https://example.com/selected-role",
        source: job.source || "CvolvePro"
      };
      const form = new FormData();
      form.append("job", JSON.stringify(normalizedJob));
      Object.entries(normalizedJob).forEach(([key, value]) => {
        form.append(key, Array.isArray(value) ? JSON.stringify(value) : String(value ?? ""));
      });
      form.append("resume", resume);
      const currentUser = readAuthUser();
      form.append("user_email", currentUser?.email || "");
      const response = await fetch(`${API}/api/ats-score`, { method: "POST", body: form });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "ATS score could not be generated.");
      if (typeof body.credits_remaining === "number") updateAuthUserCredits(body.credits_remaining);
      setResult(body);
      sessionStorage.setItem("cvolvepro:atsResult", JSON.stringify(body));
      saveAtsHistory(readAuthUser(), body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ATS score could not be generated.");
    } finally {
      setLoading(false);
    }
  }

  function scheduleInterview() {
    if (!result) return;
    sessionStorage.setItem("cvolvepro:atsResult", JSON.stringify(result));
    router.push("/interview");
  }

  if (!job) {
    return <main className="flow-page shell"><Link className="back-link" href="/jobs"><ArrowLeft size={16}/>Back to jobs</Link><section className="flow-empty"><TriangleAlert/><h1>Select a role first</h1><p>Search jobs, choose a role, then check your ATS score from the role card.</p></section></main>;
  }

  return <main className="flow-page shell">
    <Link className="back-link" href="/jobs"><ArrowLeft size={16}/>Back to jobs</Link>
    <section className="flow-hero">
      <div>
        <span className="kicker">ATS READINESS</span>
        <h1>Resume fit for<br/>{job.title}</h1>
        <p>{job.company} · {job.location}</p>
        <a className="job-link" href={job.apply_url} target="_blank" rel="noopener noreferrer">Open job link <ExternalLink size={15}/></a>
      </div>
      <div className="job-mini">
        <b>{job.company.slice(0, 2).toUpperCase()}</b>
        <h2>{job.title}</h2>
        <p>{job.summary}</p>
        <div><span><MapPin size={13}/>{job.work_mode}</span><span><BriefcaseBusiness size={13}/>{job.employment_type}</span></div>
        <a className="job-mini-link" href={job.apply_url} target="_blank" rel="noopener noreferrer">View full role <ExternalLink size={14}/></a>
      </div>
    </section>

    <section className="ats-layout">
      <form className="upload-panel" onSubmit={submit}>
        <label className="resume-drop">
          <input type="file" accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" onChange={e=>setResume(e.target.files?.[0] || null)}/>
          <FileUp size={34}/>
          <strong>{resume ? resume.name : "Upload your resume"}</strong>
          <span>PDF, DOCX, TXT, or MD</span>
        </label>
        <button className="primary-action" disabled={!resume || loading}>{loading ? <Loader2 className="spin" size={18}/> : <Sparkles size={18}/>}Generate ATS score</button>
        {error && <p className="flow-error">{error}</p>}
      </form>

      <div className="score-panel">
        {!result && <div className="waiting-card"><ShieldCheck size={34}/><h2>ATS score appears here</h2><p>NVIDIA compares your resume against the job description, role skills, seniority, project evidence, and missing keywords.</p></div>}
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
          {result.score >= 70 ? <button className="primary-action interview-cta" onClick={scheduleInterview}>Schedule Interview now <ArrowRight size={18}/></button> : <div className="threshold-note">Reach 70% or above to unlock the interview scheduler for this role.</div>}
        </div>}
      </div>
    </section>
  </main>;
}
