"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Compass, Mail, Phone, Settings, UserRound } from "lucide-react";
import { AuthUser, readAuthUser } from "../shared";

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const currentUser = readAuthUser();
    if (!currentUser) {
      sessionStorage.setItem("cvolvepro:authRedirect", "/settings");
      router.replace("/auth");
      return;
    }
    setUser(currentUser);
  }, [router]);

  return <main className="dashboard-page shell">
    <nav className="dashboard-nav">
      <Link className="back-link" href="/jobs"><ArrowLeft size={16}/>Back to jobs</Link>
      <a className="brand logo-brand" href="/jobs"><img src="/images/cvolvepro-logo.png" alt="Cvolve Pro"/></a>
      <Link className="settings-link" href="/dashboard"><Settings size={16}/>Dashboard</Link>
    </nav>
    <section className="settings-panel">
      <span className="kicker">SETTINGS</span>
      <h1>Profile</h1>
      <div className="settings-grid">
        <p><UserRound size={17}/><span>Name</span><strong>{user?.name || "-"}</strong></p>
        <p><Mail size={17}/><span>Email</span><strong>{user?.email || "-"}</strong></p>
        <p><Phone size={17}/><span>Mobile</span><strong>{user?.mobile_number || "-"}</strong></p>
        <p><Compass size={17}/><span>Country</span><strong>{user?.country || "-"}</strong></p>
      </div>
    </section>
  </main>;
}
