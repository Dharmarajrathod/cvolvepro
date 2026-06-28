"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, BriefcaseBusiness, ExternalLink, FileCheck2, LayoutDashboard, MapPin } from "lucide-react";
import { AtsHistoryItem, AuthUser, readAtsHistory, readAuthUser } from "../shared";
import ProfileMenu from "../ProfileMenu";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [history, setHistory] = useState<AtsHistoryItem[]>([]);

  useEffect(() => {
    const currentUser = readAuthUser();
    if (!currentUser) {
      sessionStorage.setItem("cvolvepro:authRedirect", "/dashboard");
      router.replace("/auth");
      return;
    }
    setUser(currentUser);
    setHistory(readAtsHistory(currentUser));
  }, [router]);

  return <main className="dashboard-page shell">
    <nav className="dashboard-nav">
      <Link className="back-link" href="/jobs"><ArrowLeft size={16}/>Back to jobs</Link>
      <a className="brand logo-brand" href="/jobs"><img src="/images/cvolvepro-logo.png" alt="Cvolve Pro"/></a>
      <ProfileMenu showCredits/>
    </nav>

    <section className="dashboard-head">
      <div><span className="kicker">DASHBOARD</span><h1>{user ? `${user.name}'s ATS scores` : "ATS scores"}</h1><p>Every resume score you generate is saved here for quick review.</p></div>
      <div className="dashboard-stat"><LayoutDashboard size={18}/><strong>{history.length}</strong><span>ATS checks</span></div>
    </section>

    {history.length === 0 && <section className="dashboard-empty"><FileCheck2 size={38}/><h2>No ATS checks yet</h2><p>Search a job, open its ATS score, and generate a resume fit score. It will appear here automatically.</p><Link className="primary-action" href="/jobs">Find jobs</Link></section>}

    {history.length > 0 && <section className="history-list">
      {history.map(item => <article className="history-card" key={item.id}>
        <div className="history-score"><strong>{item.score}</strong><span>%</span></div>
        <div>
          <span className="company">{item.job.company}</span>
          <h2>{item.job.title}</h2>
          <p>{item.verdict}</p>
          <div className="meta"><span><MapPin size={14}/>{item.job.location}</span><span><BriefcaseBusiness size={14}/>{item.job.employment_type}</span><span>{new Date(item.checked_at).toLocaleDateString()}</span></div>
        </div>
        <a href={item.job.apply_url} target="_blank" rel="noopener noreferrer">View role <ExternalLink size={15}/></a>
      </article>)}
    </section>}
  </main>;
}
