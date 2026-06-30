"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, BarChart3, BookOpen, Check, FileText, LayoutDashboard, LogOut, Mail, Mic, ScanSearch, Settings, ShieldCheck, Sparkles, Star, UserPlus } from "lucide-react";
import { API, AuthUser, clearAuthUser, fallbackPricing, fetchRegionalPricing, PricingPlan, readAuthUser } from "./shared";

const features = [
  ["Live Job Search", "Search job openings from public boards and company career pages in one workspace.", ScanSearch],
  ["ATS Score Check", "Upload your resume against a selected job and see how closely it matches.", ShieldCheck],
  ["Mock Interview", "Generate role-specific interview questions after your ATS score is ready.", Mic],
  ["Match Insights", "Understand why a role fits your skills, experience, and target profile.", BarChart3],
  ["Resume Readiness", "Find missing keywords and improvement areas before applying.", FileText],
  ["Application Flow", "Move from job search to ATS check to mock interview without starting over.", Mail],
] as const;

const steps = [
  ["01", "Search jobs", "Find relevant openings from live job sources and choose a role that fits."],
  ["02", "Check ATS score", "Upload your resume and compare it against the selected job."],
  ["03", "Review gaps", "See missing keywords, strengths, and areas to improve before applying."],
  ["04", "Practice interview", "Generate mock interview questions for the same job and prepare your answers."],
] as const;

export default function LandingPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [plans, setPlans] = useState<PricingPlan[]>(fallbackPricing.personal_plans);
  const [profileOpen, setProfileOpen] = useState(false);
  const [payingPlan, setPayingPlan] = useState("");
  const [paymentError, setPaymentError] = useState("");

  useEffect(() => {
    setUser(readAuthUser());
  }, []);

  useEffect(() => {
    fetchRegionalPricing()
      .then(pricing => setPlans(pricing.personal_plans))
      .catch(() => {});
  }, []);

  function openAuth(mode: "login" | "register") {
    sessionStorage.setItem("cvolvepro:authRedirect", "/jobs");
    sessionStorage.setItem("cvolvepro:authMode", mode);
    router.push("/auth");
  }

  function logout() {
    clearAuthUser();
    setUser(null);
    setProfileOpen(false);
  }

  async function checkout(planId: string) {
    if (planId === "free") {
      openAuth("register");
      return;
    }
    const currentUser = readAuthUser();
    if (!currentUser) {
      sessionStorage.setItem("cvolvepro:authRedirect", "/#pricing");
      sessionStorage.setItem("cvolvepro:authMode", "login");
      router.push("/auth");
      return;
    }
    setPaymentError("");
    setPayingPlan(planId);
    try {
      const response = await fetch(`${API}/api/payments/create-checkout-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: planId, email: currentUser.email }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Payment checkout could not be started.");
      window.location.href = body.url;
    } catch (err) {
      setPaymentError(err instanceof Error ? err.message : "Payment checkout could not be started.");
    } finally {
      setPayingPlan("");
    }
  }

  return <main className="landing-page">
    <nav className="landing-nav shell">
      <a className="brand logo-brand" href="/"><img src="/images/cvolvepro-logo.png" alt="Cvolve Pro"/></a>
      <div className="landing-links">
        <a href="#features">Features</a>
        <a href="#how">How it works</a>
        <a href="#about">About</a>
        <a href="#pricing">Pricing</a>
        <a href="#contact">Contact</a>
      </div>
      <div className="landing-actions">
        {!user && <>
          <button onClick={()=>openAuth("login")}>Login</button>
          <button className="primary" onClick={()=>openAuth("register")}><UserPlus size={15}/>Register</button>
        </>}
        {user && <div className="profile-wrap">
          <button className="profile" aria-label="Open profile" onClick={()=>setProfileOpen(open=>!open)}>{(user.name || user.email || "CP").split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase()}</button>
          {profileOpen && <div className="profile-menu">
            <strong>{user.name}</strong>
            <span>{user.email}</span>
          <button onClick={()=>router.push("/jobs")}><Sparkles size={15}/>Jobs</button>
          <button onClick={()=>router.push("/custom-ats")}><FileText size={15}/>Paste JD ATS</button>
            <button onClick={()=>router.push("/plans")}><Check size={15}/>Choose plan</button>
            <button onClick={()=>router.push("/dashboard")}><LayoutDashboard size={15}/>Dashboard</button>
            <button onClick={()=>router.push("/settings")}><Settings size={15}/>Settings</button>
            <button onClick={logout}><LogOut size={15}/>Logout</button>
          </div>}
        </div>}
      </div>
    </nav>

    <section className="landing-hero shell">
      <div className="landing-copy">
        <div className="eyebrow"><span><Sparkles size={13}/></span>AI job search, ATS check, and mock interview</div>
        <h1>Your job hunt, sharpened from search to interview.</h1>
        <p>CvolvePro helps you search relevant jobs, compare your resume with each role, and generate mock interview questions so you can apply with more clarity.</p>
        <div className="hero-actions">
          <button className="hero-primary" onClick={()=>user ? router.push("/jobs") : openAuth("register")}>{user ? "Go to jobs" : "Try free"} <ArrowRight size={18}/></button>
          <button className="hero-secondary" onClick={()=>user ? router.push("/custom-ats") : openAuth("login")}>{user ? "Paste job description" : "Login"}</button>
        </div>
        <div className="hero-metrics">
          <span><Star size={15}/>4.8/5 avg. user rating</span>
          <span><BarChart3 size={15}/>+60% more interviews*</span>
          <span><ShieldCheck size={15}/>Privacy-first</span>
        </div>
      </div>
      <div className="hero-media">
        <img src="/images/cvolvepro-hero.png" alt="Resume scoring workspace preview"/>
      </div>
    </section>

    <section className="landing-band shell">
      <strong>Pro Tip</strong>
      <p>Start with job search, choose the role you want, check your resume fit, then use mock interview questions to prepare before applying.</p>
    </section>

    <section className="landing-section shell" id="features">
      <div className="section-head"><span className="kicker">FEATURES</span><h2>Everything from job search to interview prep</h2><p>Search roles, check resume fit, and prepare for interviews in one guided workflow.</p></div>
      <div className="feature-grid">
        {features.map(([title, body, Icon]) => <article key={title}><Icon size={22}/><h3>{title}</h3><p>{body}</p></article>)}
      </div>
    </section>

    <section className="landing-section shell" id="how">
      <div className="section-head"><span className="kicker">HOW IT WORKS</span><h2>A simple flow from search to mock interview</h2><p>Choose a job, check your ATS score, review improvements, and practice with role-focused interview questions.</p></div>
      <div className="landing-steps">
        {steps.map(([num, title, body]) => <article key={num}><b>{num}</b><h3>{title}</h3><p>{body}</p></article>)}
      </div>
    </section>

    <section className="about-founder shell" id="about">
      <div>
        <span className="kicker">ABOUT</span>
        <h2>Built from a candidate's real job-search pain.</h2>
        <p>CVOLVEPRO was founded by Aparajita Sudarshan to help candidates search jobs, understand resume fit, and prepare for interviews faster.</p>
      </div>
      <article>
        <BookOpen size={24}/>
        <h3>Aparajita Sudarshan</h3>
        <p>Founder and Senior Learning & Development Specialist with experience across India, Malaysia, Bahrain, Qatar, the UAE, and the UK.</p>
        <p>CvolvePro combines job discovery, ATS scoring, and STAR-method mock interview preparation in one practical workflow.</p>
      </article>
    </section>

    <section className="landing-section shell" id="pricing">
      <div className="section-head"><span className="kicker">PRICING</span><h2>Simple, transparent pricing</h2><p>Pick a plan that fits your job search and start from the workspace after login.</p></div>
      <div className="pricing-grid">
        {plans.map(plan => <article key={plan.id} className={plan.id === "premium" ? "featured" : ""}>
          <span className="plan-tag">{plan.tag}</span>
          <h3>{plan.name}</h3>
          <div className="price"><strong>{plan.price}</strong><span>/ {plan.period}</span></div>
          {plan.items.map(item => <p key={item}><Check size={15}/>{item}</p>)}
          <button onClick={()=>checkout(plan.id)} disabled={payingPlan === plan.id}>{payingPlan === plan.id ? "Opening checkout..." : plan.id === "free" ? "Start free" : "Pay with Stripe"}</button>
        </article>)}
      </div>
      {paymentError && <p className="flow-error payment-error">{paymentError}</p>}
    </section>

    <section className="landing-cta shell" id="contact">
      <div><span className="kicker">CONTACT</span><h2>Ready to find jobs and prepare better?</h2><p>Launch the app, search roles, check ATS score, and practice mock interviews from your dashboard.</p></div>
      <div><button className="hero-primary" onClick={()=>user ? router.push("/jobs") : openAuth("register")}>Launch app <ArrowRight size={18}/></button><a href="mailto:support@cvolvepro.com">support@cvolvepro.com</a></div>
    </section>

    <footer className="shell"><a className="brand logo-brand" href="/"><img src="/images/cvolvepro-logo.png" alt="Cvolve Pro"/></a><p>Move toward work that matters.</p><span>© 2026 CVOLVE PRO</span></footer>
  </main>;
}
