"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Earth, KeyRound, LockKeyhole, LogIn, Mail, Phone, ShieldCheck, UserRound, UserRoundPlus } from "lucide-react";
import { API, saveAuthUser } from "../shared";

type Mode = "login" | "register" | "forgot";

const countries = [
  "India",
  "United States",
  "United Kingdom",
  "Canada",
  "Australia",
  "Germany",
  "France",
  "Singapore",
  "United Arab Emirates",
  "Saudi Arabia",
  "South Africa",
  "Other",
];

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mobileNumber, setMobileNumber] = useState("");
  const [country, setCountry] = useState("India");
  const [accountType, setAccountType] = useState<"personal" | "business">("personal");
  const [verificationCode, setVerificationCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const requestedMode = sessionStorage.getItem("cvolvepro:authMode");
    if (requestedMode === "login" || requestedMode === "register" || requestedMode === "forgot") {
      setMode(requestedMode);
      sessionStorage.removeItem("cvolvepro:authMode");
    }
  }, []);

  async function request(path: string, body: object) {
    const response = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "Something went wrong. Please try again.");
    }
    return data;
  }

  function continueToApp(user: { name: string; email: string; mobile_number?: string; country?: string; account_type?: "personal" | "business"; credits?: number; plan_id?: string }) {
    saveAuthUser(user);
    const redirect = mode === "register" ? "/plans" : sessionStorage.getItem("cvolvepro:authRedirect") || "/jobs";
    sessionStorage.removeItem("cvolvepro:authRedirect");
    router.replace(redirect);
  }

  function validateRegisterDetails() {
    if (!name.trim()) return "Enter your name to create an account.";
    if (!email.trim() || !password.trim()) return "Enter your email and password to continue.";
    if (!mobileNumber.trim()) return "Enter your mobile number.";
    if (!country.trim()) return "Choose your country.";
    if (!accountType) return "Choose personal or business use.";
    if (password.length < 8) return "Password must be at least 8 characters.";
    return "";
  }

  function validateForgotDetails() {
    if (!email.trim()) return "Enter your email to reset your password.";
    if (!password.trim()) return "Enter a new password.";
    if (password.length < 8) return "Password must be at least 8 characters.";
    return "";
  }

  async function sendCode() {
    setError("");
    setNotice("");
    const validationError = mode === "forgot" ? validateForgotDetails() : validateRegisterDetails();
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusy(true);
    try {
      await request("/api/auth/send-code", { email: email.trim() });
      setCodeSent(true);
      setNotice("Verification code sent to your email.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send verification code.");
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setNotice("");
    if (mode === "login" && (!email.trim() || !password.trim())) {
      setError("Enter your email and password to continue.");
      return;
    }
    if (mode === "forgot") {
      const validationError = validateForgotDetails();
      if (validationError) {
        setError(validationError);
        return;
      }
      if (!verificationCode.trim()) {
        setError("Enter the verification code from your email.");
        return;
      }
    }
    if (mode === "register") {
      const validationError = validateRegisterDetails();
      if (validationError) {
        setError(validationError);
        return;
      }
      if (!verificationCode.trim()) {
        setError("Enter the verification code from your email.");
        return;
      }
    }
    setBusy(true);
    try {
      const user = mode === "login"
        ? await request("/api/auth/login", { email: email.trim(), password })
        : mode === "forgot"
        ? await request("/api/auth/reset-password", {
          email: email.trim(),
          password,
          verification_code: verificationCode.trim(),
        })
        : await request("/api/auth/register", {
          name: name.trim(),
          email: email.trim(),
          password,
          mobile_number: mobileNumber.trim(),
          country,
          account_type: accountType,
          verification_code: verificationCode.trim(),
        });
      continueToApp(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not continue. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-page">
    <section className="auth-shell">
      <div className="auth-copy">
        <Link className="back-link" href="/"><ArrowLeft size={16}/>Back home</Link>
        <a className="brand logo-brand auth-brand" href="/"><img src="/images/cvolvepro-logo.png" alt="Cvolve Pro"/></a>
        <span className="kicker">ATS ACCESS</span>
        <h1>{mode === "login" ? "Sign in to check your ATS score." : "Create your account to continue."}</h1>
        <p>Your selected role is saved. After login or registration, you will continue directly to the resume scoring page.</p>
      </div>
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={()=>{setMode("login"); setError(""); setNotice("");}}><LogIn size={16}/>Login</button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={()=>{setMode("register"); setError(""); setNotice("");}}><UserRoundPlus size={16}/>Register</button>
        </div>
        {mode === "register" && <label className="auth-field"><UserRound size={18}/><span><small>Name</small><input value={name} onChange={e=>setName(e.target.value)} placeholder="Your name"/></span></label>}
        <label className="auth-field"><Mail size={18}/><span><small>Email</small><input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com"/></span></label>
        <label className="auth-field"><LockKeyhole size={18}/><span><small>{mode === "forgot" ? "New password" : "Password"}</small><input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder={mode === "forgot" ? "Enter new password" : "Enter password"}/></span></label>
        {mode === "login" && <button type="button" className="forgot-link" onClick={()=>{setMode("forgot"); setError(""); setNotice(""); setCodeSent(false); setVerificationCode("");}}><KeyRound size={14}/>Forgot password?</button>}
        {(mode === "register" || mode === "forgot") && <>
          {mode === "register" && <>
          <label className="auth-field"><Phone size={18}/><span><small>Mobile number</small><input type="tel" value={mobileNumber} onChange={e=>setMobileNumber(e.target.value)} placeholder="+91 98765 43210"/></span></label>
          <label className="auth-field"><Earth size={18}/><span><small>Country</small><select value={country} onChange={e=>setCountry(e.target.value)}>{countries.map(item => <option key={item} value={item}>{item}</option>)}</select></span></label>
          <div className="account-type">
            <small>Use type</small>
            <div>
              <button type="button" className={accountType === "personal" ? "active" : ""} onClick={()=>setAccountType("personal")}>Personal</button>
              <button type="button" className={accountType === "business" ? "active" : ""} onClick={()=>setAccountType("business")}>Business</button>
            </div>
          </div>
          </>}
          <div className="auth-code-row">
            <label className="auth-field auth-code-field"><ShieldCheck size={18}/><span><small>Verification code</small><input inputMode="numeric" maxLength={6} value={verificationCode} onChange={e=>setVerificationCode(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="6-digit code"/></span></label>
            <button type="button" className="secondary-action auth-code-button" onClick={sendCode} disabled={busy}>{codeSent ? "Resend" : "Send code"}</button>
          </div>
        </>}
        {notice && <p className="flow-success">{notice}</p>}
        {error && <p className="flow-error">{error}</p>}
        <button className="primary-action auth-submit" disabled={busy}>{mode === "login" ? <LogIn size={18}/> : mode === "forgot" ? <KeyRound size={18}/> : <UserRoundPlus size={18}/>} {busy ? "Please wait..." : mode === "login" ? "Login and continue" : mode === "forgot" ? "Reset password" : "Register and continue"}</button>
        {mode === "forgot" && <button type="button" className="forgot-link center" onClick={()=>{setMode("login"); setError(""); setNotice("");}}>Back to login</button>}
      </form>
    </section>
  </main>;
}
