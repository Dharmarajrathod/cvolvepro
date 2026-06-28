"use client";

import Link from "next/link";
import { ArrowLeft, CreditCard } from "lucide-react";
import ProfileMenu from "../../ProfileMenu";

export default function PaymentCancelPage() {
  return <main className="payment-page shell">
    <nav className="payment-nav"><a className="brand logo-brand" href="/"><img src="/images/cvolvepro-logo.png" alt="Cvolve Pro"/></a><ProfileMenu showCredits/></nav>
    <section className="payment-card">
      <CreditCard size={42}/>
      <span className="kicker">CHECKOUT CANCELED</span>
      <h1>No payment was taken</h1>
      <p>You can return to pricing and choose a plan whenever you are ready.</p>
      <div>
        <Link className="primary-action" href="/#pricing"><ArrowLeft size={18}/>Back to pricing</Link>
      </div>
    </section>
  </main>;
}
