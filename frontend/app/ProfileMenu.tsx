"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, FileText, LayoutDashboard, LogOut, Search, Settings } from "lucide-react";
import { AuthUser, clearAuthUser, readAuthUser } from "./shared";

type Props = {
  showCredits?: boolean;
};

function initialsFor(user: AuthUser | null) {
  return (user?.name || user?.email || "CP")
    .split(/\s+/)
    .map(part => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export default function ProfileMenu({ showCredits = false }: Props) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setUser(readAuthUser());
  }, []);

  if (!user) return null;

  function logout() {
    clearAuthUser();
    setOpen(false);
    sessionStorage.removeItem("cvolvepro:selectedJob");
    sessionStorage.removeItem("cvolvepro:atsResult");
    router.push("/");
  }

  return <div className="profile-wrap">
    {showCredits && <div className="credit-pill">{Number(user.credits || 0)} credits</div>}
    <button className="profile" aria-label="Open profile" onClick={() => setOpen(value => !value)}>{initialsFor(user)}</button>
    {open && <div className="profile-menu">
      <strong>{user.name}</strong>
      <span>{user.email}</span>
      <button onClick={() => router.push("/jobs")}><Search size={15}/>Jobs</button>
      <button onClick={() => router.push("/custom-ats")}><FileText size={15}/>Paste JD ATS</button>
      <button onClick={() => router.push("/plans")}><Check size={15}/>Choose plan</button>
      <button onClick={() => router.push("/dashboard")}><LayoutDashboard size={15}/>Dashboard</button>
      <button onClick={() => router.push("/settings")}><Settings size={15}/>Settings</button>
      <button onClick={logout}><LogOut size={15}/>Logout</button>
    </div>}
  </div>;
}
