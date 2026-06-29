"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, CreditCard } from "lucide-react";
import { API, AuthUser, fallbackPricing, fetchRegionalPricing, PricingPlan, readAuthUser, saveAuthUser } from "../shared";
import ProfileMenu from "../ProfileMenu";

export default function PlansPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [personalPlans, setPersonalPlans] = useState<PricingPlan[]>(fallbackPricing.personal_plans);
  const [businessPlans, setBusinessPlans] = useState<PricingPlan[]>(fallbackPricing.business_plans);
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

  useEffect(() => {
    fetchRegionalPricing()
      .then(pricing => {
        setPersonalPlans(pricing.personal_plans);
        setBusinessPlans(pricing.business_plans);
      })
      .catch(() => {});
  }, []);

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
      <ProfileMenu showCredits/>
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
