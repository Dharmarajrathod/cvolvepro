"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, CreditCard } from "lucide-react";
import { API, AuthUser, readAuthUser, saveAuthUser } from "../shared";

const personalPlans = [
  { id: "free", name: "Free", tag: "Best to try", price: "₹0", period: "forever", items: ["10 credits", "2 job searches", "2 ATS matches", "Community support"] },
  { id: "classic", name: "Classic", tag: "Best for starters", price: "₹499", period: "month", items: ["50 credits", "10 job searches", "10 ATS matches", "2 AI interviews", "Email support"] },
  { id: "premium", name: "Premium", tag: "Best value", price: "₹699", period: "month", items: ["100 credits", "20 job searches", "20 ATS matches", "5 AI interviews", "Priority support"] },
  { id: "premium_plus", name: "Premium Plus", tag: "Best for active search", price: "₹1,799", period: "3 months", items: ["350 credits", "70 job searches", "70 ATS matches", "17 AI interviews", "Priority support"] },
] as const;

const businessPlans = [
  { id: "business_starter", name: "Business Starter", tag: "Best for small teams", price: "₹2,499", period: "month", items: ["500 credits", "Up to 5 team members", "Shared credits", "Job Search, ATS, AI Interview"] },
  { id: "business_growth", name: "Business Growth", tag: "Best value for teams", price: "₹6,499", period: "quarter", items: ["2,000 credits", "Up to 15 team members", "Shared dashboard", "Priority support"] },
  { id: "business_enterprise", name: "Business Enterprise", tag: "Best for scale", price: "₹24,999", period: "year", items: ["10,000 credits", "Unlimited team members", "API and analytics", "Priority support"] },
] as const;

export default function PlansPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [busyPlan, setBusyPlan] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const currentUser = readAuthUser();
    if (!currentUser) {
      sessionStorage.setItem("cvolvepro:authRedirect", "/plans");
      sessionStorage.setItem("cvolvepro:authMode", "login");
      router.replace("/auth");
      return;
    }
    setUser(currentUser);
  }, [router]);

  async function request(path: string, body: object) {
    const response = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Plan could not be selected.");
    return data;
  }

  async function choosePlan(planId: string) {
    if (!user) return;
    setError("");
    setBusyPlan(planId);
    try {
      if (planId === "free") {
        const updated = await request("/api/payments/select-free-plan", { email: user.email });
        saveAuthUser(updated);
        router.replace("/jobs");
        return;
      }
      const body = await request("/api/payments/create-checkout-session", { plan_id: planId, email: user.email });
      window.location.href = body.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Plan could not be selected.");
    } finally {
      setBusyPlan("");
    }
  }

  const plans = user?.account_type === "business" ? businessPlans : personalPlans;

  return <main className="plans-page shell">
    <nav className="dashboard-nav">
      <Link className="back-link" href="/"><ArrowLeft size={16}/>Back home</Link>
      <a className="brand logo-brand" href="/"><img src="/images/cvolvepro-logo.png" alt="Cvolve Pro"/></a>
      <span className="settings-link">{user?.account_type === "business" ? "Business" : "Personal"}</span>
    </nav>
    <section className="dashboard-head">
      <div><span className="kicker">CHOOSE PLAN</span><h1>{user?.account_type === "business" ? "Business plans" : "Personal plans"}</h1><p>Select a plan to activate credits before entering your workspace.</p></div>
      <div className="dashboard-stat"><CreditCard size={18}/><strong>{user?.credits || 0}</strong><span>current credits</span></div>
    </section>
    <section className={`pricing-grid ${plans.length === 3 ? "business-pricing" : ""}`}>
      {plans.map(plan => <article key={plan.id} className={plan.id === "premium" || plan.id === "business_growth" ? "featured" : ""}>
        <span className="plan-tag">{plan.tag}</span>
        <h3>{plan.name}</h3>
        <div className="price"><strong>{plan.price}</strong><span>/ {plan.period}</span></div>
        {plan.items.map(item => <p key={item}><Check size={15}/>{item}</p>)}
        <button onClick={()=>choosePlan(plan.id)} disabled={busyPlan === plan.id}>{busyPlan === plan.id ? "Please wait..." : plan.id === "free" ? "Activate free credits" : "Pay with Stripe"}</button>
      </article>)}
    </section>
    {error && <p className="flow-error payment-error">{error}</p>}
  </main>;
}
