"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, LayoutDashboard, Search } from "lucide-react";
import { API, readAuthUser, saveAuthUser } from "../../shared";

function PaymentSuccessContent() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState("Confirming your credits...");

  useEffect(() => {
    const sessionId = searchParams.get("session_id");
    const user = readAuthUser();
    if (!sessionId) {
      setStatus("Payment completed. We could not find a session id to update credits.");
      return;
    }
    fetch(`${API}/api/payments/confirm-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, email: user?.email || null }),
    })
      .then(async response => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || "Credits could not be updated.");
        saveAuthUser(body);
        setStatus(`${body.credits} credits are now available.`);
      })
      .catch(err => setStatus(err instanceof Error ? err.message : "Credits could not be updated."));
  }, [searchParams]);

  return <main className="payment-page shell">
    <section className="payment-card">
      <CheckCircle2 size={42}/>
      <span className="kicker">PAYMENT COMPLETE</span>
      <h1>Your plan is ready</h1>
      <p>{status}</p>
      <div>
        <Link className="primary-action" href="/jobs"><Search size={18}/>Find jobs</Link>
        <Link className="secondary-action" href="/dashboard"><LayoutDashboard size={18}/>Dashboard</Link>
      </div>
    </section>
  </main>;
}

export default function PaymentSuccessPage() {
  return <Suspense fallback={<main className="payment-page shell"><section className="payment-card"><p>Confirming your credits...</p></section></main>}>
    <PaymentSuccessContent/>
  </Suspense>;
}
