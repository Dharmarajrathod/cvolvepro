"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Compass, LockKeyhole, LogIn, Mail, UserRound, UserRoundPlus } from "lucide-react";
import { saveAuthUser } from "../shared";

type Mode = "login" | "register";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!email.trim() || !password.trim()) {
      setError("Enter your email and password to continue.");
      return;
    }
    if (mode === "register" && !name.trim()) {
      setError("Enter your name to create an account.");
      return;
    }
    saveAuthUser({ name: name.trim() || email.split("@")[0] || "Candidate", email: email.trim() });
    const redirect = sessionStorage.getItem("cvolvepro:authRedirect") || "/ats";
    sessionStorage.removeItem("cvolvepro:authRedirect");
    router.replace(redirect);
  }

  return <main className="auth-page">
    <section className="auth-shell">
      <div className="auth-copy">
        <Link className="back-link" href="/"><ArrowLeft size={16}/>Back to jobs</Link>
        <a className="brand auth-brand" href="/"><span className="brand-mark"><Compass size={18}/></span>Cvolve<span>Pro</span></a>
        <span className="kicker">ATS ACCESS</span>
        <h1>{mode === "login" ? "Sign in to check your ATS score." : "Create your account to continue."}</h1>
        <p>Your selected role is saved. After login or registration, you will continue directly to the resume scoring page.</p>
      </div>
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={()=>setMode("login")}><LogIn size={16}/>Login</button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={()=>setMode("register")}><UserRoundPlus size={16}/>Register</button>
        </div>
        {mode === "register" && <label className="auth-field"><UserRound size={18}/><span><small>Name</small><input value={name} onChange={e=>setName(e.target.value)} placeholder="Your name"/></span></label>}
        <label className="auth-field"><Mail size={18}/><span><small>Email</small><input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com"/></span></label>
        <label className="auth-field"><LockKeyhole size={18}/><span><small>Password</small><input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Enter password"/></span></label>
        {error && <p className="flow-error">{error}</p>}
        <button className="primary-action auth-submit">{mode === "login" ? <LogIn size={18}/> : <UserRoundPlus size={18}/>} {mode === "login" ? "Login and continue" : "Register and continue"}</button>
      </form>
    </section>
  </main>;
}
