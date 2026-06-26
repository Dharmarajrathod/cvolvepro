"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Bookmark, BriefcaseBusiness, Check, ChevronDown, Clock3, Compass, ExternalLink, FileCheck2, LocateFixed, MapPin, Search, SlidersHorizontal, Sparkles, X } from "lucide-react";
import { readAuthUser } from "./shared";

type Job = {
  id: string; title: string; company: string; location: string; work_mode: string;
  employment_type: string; salary: string | null; experience: string | null; posted_at: string | null;
  skills: string[]; summary: string; match_score: number; match_reason: string;
  apply_url: string; source: string;
};
type Result = { jobs: Job[]; total: number; searched_sources: string[]; query_expansion: string[] };

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const PAGE_SIZE = 15;
const EMPLOYMENT_OPTIONS = [
  ["full-time", "Full-time"],
  ["part-time", "Part-time"],
  ["contract", "Contract"],
  ["internship", "Internship"],
  ["freelance", "Freelance"],
] as const;
const EXPERIENCE_OPTIONS = [
  ["entry", "Entry"],
  ["junior", "Junior"],
  ["mid", "Mid-level"],
  ["senior", "Senior"],
  ["lead", "Lead+"],
] as const;

function postedWithin(value: string | null, days: number) {
  if (days === 0) return true;
  if (!value) return false;
  const text = value.toLowerCase();
  if (text.includes("today") || text.includes("hour") || text.includes("minute")) return true;
  if (text.includes("yesterday")) return days >= 1;
  const relative = text.match(/(\d+)\s*days?/);
  if (relative) return Number(relative[1]) <= days;
  const dateMatch = value.match(/\d{4}-\d{2}-\d{2}/);
  const timestamp = Date.parse(dateMatch ? dateMatch[0] : value);
  if (Number.isNaN(timestamp)) return false;
  const age = Math.max(0, Date.now() - timestamp);
  return age <= days * 86_400_000;
}

function experienceYears(value: string | null) {
  if (!value) return null;
  const text = value.toLowerCase();
  if (/(entry|fresher|graduate|intern|no experience)/.test(text)) return 0;
  const range = text.match(/(\d+)\s*[-–]\s*(\d+)\s*(?:\+?\s*)?(?:years?|yrs?)/);
  if (range) return Number(range[1]);
  const plus = text.match(/(\d+)\s*\+?\s*(?:years?|yrs?)/);
  return plus ? Number(plus[1]) : null;
}

function matchesExperience(value: string | null, bucket: string) {
  if (bucket === "all") return true;
  const years = experienceYears(value);
  if (bucket === "unspecified") return years === null;
  if (years === null) return false;
  if (bucket === "0-1") return years <= 1;
  if (bucket === "2-4") return years >= 2 && years <= 4;
  if (bucket === "5-7") return years >= 5 && years <= 7;
  return years >= 8;
}

export default function Home() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [location, setLocation] = useState("");
  const [remote, setRemote] = useState(false);
  const [searchEmploymentType, setSearchEmploymentType] = useState("all");
  const [searchExperience, setSearchExperience] = useState("all");
  const [skills, setSkills] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [filterOpen, setFilterOpen] = useState(false);
  const [workMode, setWorkMode] = useState("all");
  const [jobType, setJobType] = useState("all");
  const [experienceFilter, setExperienceFilter] = useState("all");
  const [companyFilter, setCompanyFilter] = useState("");
  const [titleFilter, setTitleFilter] = useState("");
  const [skillFilter, setSkillFilter] = useState("");
  const [minMatch, setMinMatch] = useState(0);
  const [salaryOnly, setSalaryOnly] = useState(false);
  const [datePosted, setDatePosted] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);

  async function search(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true); setError(""); setResult(null); setCurrentPage(1);
    try {
      const response = await fetch(`${API}/api/jobs/search`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          location: location || null,
          remote_only: remote,
          employment_type: searchEmploymentType === "all" ? null : searchEmploymentType,
          experience_level: searchExperience === "all" ? null : searchExperience,
          candidate_skills: skills.split(",").map(s => s.trim()).filter(Boolean)
        })
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Search could not be completed.");
      setResult(body);
    } catch (err) { setError(err instanceof Error ? err.message : "Search could not be completed."); }
    finally { setLoading(false); }
  }

  const workModes = useMemo(() => [...new Set(result?.jobs.map(job => job.work_mode).filter(Boolean) || [])].sort(), [result]);
  const jobTypes = useMemo(() => [...new Set(result?.jobs.map(job => job.employment_type).filter(Boolean) || [])].sort(), [result]);
  const filteredJobs = useMemo(() => {
    const companyNeedle = companyFilter.trim().toLowerCase();
    const titleNeedle = titleFilter.trim().toLowerCase();
    const skillNeedle = skillFilter.trim().toLowerCase();
    return result?.jobs.filter(job =>
      (workMode === "all" || job.work_mode === workMode) &&
      (jobType === "all" || job.employment_type === jobType) &&
      matchesExperience(job.experience, experienceFilter) &&
      (!companyNeedle || job.company.toLowerCase().includes(companyNeedle)) &&
      (!titleNeedle || job.title.toLowerCase().includes(titleNeedle)) &&
      (!skillNeedle || job.skills.some(skill => skill.toLowerCase().includes(skillNeedle))) &&
      job.match_score >= minMatch &&
      postedWithin(job.posted_at, datePosted) &&
      (!salaryOnly || Boolean(job.salary))
    ) || [];
  }, [result, workMode, jobType, experienceFilter, companyFilter, titleFilter, skillFilter, minMatch, salaryOnly, datePosted]);
  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / PAGE_SIZE));
  const pageJobs = filteredJobs.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const activeFilters = [workMode !== "all", jobType !== "all", experienceFilter !== "all", companyFilter, titleFilter, skillFilter, minMatch > 0, salaryOnly, datePosted > 0].filter(Boolean).length;
  useEffect(() => { setCurrentPage(1); }, [workMode, jobType, experienceFilter, companyFilter, titleFilter, skillFilter, minMatch, salaryOnly, datePosted]);
  function resetFilters() { setWorkMode("all"); setJobType("all"); setExperienceFilter("all"); setCompanyFilter(""); setTitleFilter(""); setSkillFilter(""); setMinMatch(0); setSalaryOnly(false); setDatePosted(0); }
  function changePage(page: number) { setCurrentPage(page); document.getElementById("results-top")?.scrollIntoView({behavior:"smooth", block:"start"}); }
  function checkAts(job: Job) {
    sessionStorage.setItem("cvolvepro:selectedJob", JSON.stringify(job));
    sessionStorage.removeItem("cvolvepro:atsResult");
    if (readAuthUser()) {
      router.push("/ats");
      return;
    }
    sessionStorage.setItem("cvolvepro:authRedirect", "/ats");
    router.push("/auth");
  }

  return <main>
    <nav className="nav shell">
      <a className="brand" href="#"><span className="brand-mark"><Compass size={19}/></span>Cvolve<span>Pro</span></a>
      <div className="nav-links"><a className="active" href="#search">Find jobs</a><a href="#how">How it works</a><a href="#saved">Saved <em>{saved.size}</em></a></div>
      <button className="profile" aria-label="Open profile">DR</button>
    </nav>

    <section className="hero shell" id="search">
      <div className="eyebrow"><span><Sparkles size={13}/></span>AI career search, grounded in live sources</div>
      <h1>Your next move,<br/><i>made clearer.</i></h1>
      <p className="lede">Search public job boards and company career pages in one place. CvolvePro finds, compares, and ranks the roles that fit you.</p>

      <form className="search-card" onSubmit={search}>
        <div className="search-row">
          <label className="field big"><Search size={20}/><span><small>WHAT DO YOU WANT TO DO?</small><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Product designer, AI engineer…" autoFocus/></span></label>
          <div className="divider"/>
          <label className="field"><MapPin size={20}/><span><small>WHERE?</small><input value={location} onChange={e=>setLocation(e.target.value)} placeholder="City or country"/></span></label>
          <button className="search-button" disabled={loading}>{loading ? <span className="spinner"/> : <ArrowUpRight size={23}/>}<span>{loading ? "Searching" : "Search jobs"}</span></button>
        </div>
        <div className="search-options">
          <label className="toggle"><input type="checkbox" checked={remote} onChange={e=>setRemote(e.target.checked)}/><span>{remote && <Check size={12}/>}</span>Remote only</label>
          <label className="quick-select"><BriefcaseBusiness size={14}/><select aria-label="Employment type" value={searchEmploymentType} onChange={e=>setSearchEmploymentType(e.target.value)}><option value="all">Any employment</option>{EMPLOYMENT_OPTIONS.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label>
          <label className="quick-select"><Clock3 size={14}/><select aria-label="Experience level" value={searchExperience} onChange={e=>setSearchExperience(e.target.value)}><option value="all">Any experience</option>{EXPERIENCE_OPTIONS.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label>
          <label className="skills"><Sparkles size={14}/>Improve matching <input value={skills} onChange={e=>setSkills(e.target.value)} placeholder="Add your skills, separated by commas"/></label>
        </div>
      </form>
      <div className="trust"><span>Searching across</span><b>LinkedIn</b><b>Dice</b><b>Freelancer</b><b>RemoteOK</b><b>Y Combinator</b><span>and more</span></div>
    </section>

    <AnimatePresence mode="wait">
      {loading && <motion.section className="results shell" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}>
        <div className="loading-state"><div className="orbit"><Sparkles size={25}/></div><h2>Searching this week’s openings</h2><p>Verifying posting dates across worldwide sources. A large search can take a few minutes…</p></div>
        {[1,2,3].map(i=><div className="skeleton" key={i}><div/><div/><div/></div>)}
      </motion.section>}
      {error && !loading && <motion.div className="notice shell" initial={{opacity:0,y:8}} animate={{opacity:1,y:0}}><X size={20}/><div><b>We couldn’t run that search</b><p>{error}</p></div></motion.div>}
      {result && !loading && <motion.section className="results shell" id="results-top" initial={{opacity:0,y:18}} animate={{opacity:1,y:0}}>
        <div className="results-head"><div><span className="kicker">CURATED FOR YOU</span><h2>{filteredJobs.length} relevant {filteredJobs.length === 1 ? "role" : "roles"}{activeFilters > 0 && <small> of {result.total}</small>}</h2></div><button className={`filter ${filterOpen ? "open" : ""}`} aria-expanded={filterOpen} aria-controls="job-filters" onClick={()=>setFilterOpen(v=>!v)}><SlidersHorizontal size={16}/>Filters {activeFilters > 0 && <b>{activeFilters}</b>}<ChevronDown size={14}/></button></div>
        <AnimatePresence>
          {filterOpen && <motion.div id="job-filters" className="filter-panel" initial={{opacity:0,height:0,y:-8}} animate={{opacity:1,height:"auto",y:0}} exit={{opacity:0,height:0,y:-8}}>
            <div className="filter-grid">
              <label><span>Work mode</span><select aria-label="Work mode" value={workMode} onChange={e=>setWorkMode(e.target.value)}><option value="all">All work modes</option>{workModes.map(value=><option value={value} key={value}>{value}</option>)}</select></label>
              <label><span>Job type</span><select aria-label="Job type" value={jobType} onChange={e=>setJobType(e.target.value)}><option value="all">All job types</option>{jobTypes.map(value=><option value={value} key={value}>{value}</option>)}</select></label>
              <label><span>Experience years</span><select aria-label="Experience years" value={experienceFilter} onChange={e=>setExperienceFilter(e.target.value)}><option value="all">Any experience</option><option value="0-1">0-1 years</option><option value="2-4">2-4 years</option><option value="5-7">5-7 years</option><option value="8+">8+ years</option><option value="unspecified">Not specified</option></select></label>
              <label><span>Minimum match</span><select aria-label="Minimum match" value={minMatch} onChange={e=>setMinMatch(Number(e.target.value))}><option value={0}>Any match</option><option value={70}>70% and above</option><option value={80}>80% and above</option><option value={90}>90% and above</option></select></label>
              <label><span>Date posted</span><select aria-label="Date posted" value={datePosted} onChange={e=>setDatePosted(Number(e.target.value))}><option value={0}>Any time</option><option value={1}>Past 24 hours</option><option value={3}>Past 3 days</option><option value={7}>Past week</option></select></label>
              <label><span>Company</span><input aria-label="Company" value={companyFilter} onChange={e=>setCompanyFilter(e.target.value)} placeholder="Filter company"/></label>
              <label><span>Title contains</span><input aria-label="Title contains" value={titleFilter} onChange={e=>setTitleFilter(e.target.value)} placeholder="Engineer, manager…"/></label>
              <label><span>Skill contains</span><input aria-label="Skill contains" value={skillFilter} onChange={e=>setSkillFilter(e.target.value)} placeholder="React, Python…"/></label>
            </div>
            <div className="filter-foot"><label className="salary-check"><input type="checkbox" checked={salaryOnly} onChange={e=>setSalaryOnly(e.target.checked)}/><span>{salaryOnly && <Check size={12}/>}</span>Salary listed only</label><span className="filter-summary">Showing <b>{filteredJobs.length}</b> of {result.total} roles</span><button className="reset-filters" onClick={resetFilters} disabled={activeFilters === 0}>Reset filters</button></div>
          </motion.div>}
        </AnimatePresence>
        <div className="job-list">
          {pageJobs.map((job,i)=><motion.article className="job" key={job.id} initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={{delay:i*.035}}>
            <div className="logo">{job.company.slice(0,2).toUpperCase()}</div>
            <div className="job-main"><div className="job-top"><div><span className="company">{job.company}</span><h3>{job.title}</h3></div><button className={`save ${saved.has(job.id)?"saved":""}`} aria-label="Save job" onClick={()=>setSaved(s=>{const n=new Set(s);n.has(job.id)?n.delete(job.id):n.add(job.id);return n})}><Bookmark size={19}/></button></div>
              <div className="meta"><span><MapPin size={14}/>{job.location}</span><span><BriefcaseBusiness size={14}/>{job.employment_type}</span>{job.posted_at&&<span><Clock3 size={14}/>{job.posted_at}</span>}{job.salary&&<span className="salary">{job.salary}</span>}</div>
              <p className="summary">{job.summary}</p><div className="tags">{job.skills.slice(0,5).map(s=><span key={s}>{s}</span>)}</div>
            </div>
            <div className="fit"><div className="score"><strong>{job.match_score}</strong><small>% MATCH</small></div><p>{job.match_reason}</p><a href={job.apply_url} target="_blank" rel="noopener noreferrer">View role <ExternalLink size={15}/></a><button className="ats-link" onClick={()=>checkAts(job)}><FileCheck2 size={15}/>Check ATS score</button>{!job.source.toLowerCase().includes("indeed") && <span className="source">via {job.source}</span>}</div>
          </motion.article>)}
          {filteredJobs.length===0&&<div className="empty"><LocateFixed/><h3>No roles match these filters</h3><p>Reset the filters or broaden your selection.</p><button className="reset-empty" onClick={resetFilters}>Reset filters</button></div>}
        </div>
        {filteredJobs.length > PAGE_SIZE && <nav className="pagination" aria-label="Job results pages"><button onClick={()=>changePage(currentPage-1)} disabled={currentPage===1}>Previous</button><div>{Array.from({length:totalPages},(_,i)=>i+1).map(page=><button key={page} className={page===currentPage?"active":""} aria-current={page===currentPage?"page":undefined} aria-label={`Page ${page}`} onClick={()=>changePage(page)}>{page}</button>)}</div><button onClick={()=>changePage(currentPage+1)} disabled={currentPage===totalPages}>Next</button><span>Page {currentPage} of {totalPages} · {filteredJobs.length} jobs</span></nav>}
      </motion.section>}
    </AnimatePresence>

    {!result && !loading && <section className="how shell" id="how"><div><span className="kicker">LESS NOISE, BETTER SIGNAL</span><h2>A search that thinks<br/>like a career advisor.</h2></div><div className="steps"><article><b>01</b><h3>We understand the role</h3><p>Your query becomes related titles, skills, and the right search language.</p></article><article><b>02</b><h3>We search live sources</h3><p>Job boards and official company sites are checked for current openings.</p></article><article><b>03</b><h3>We surface your fit</h3><p>Duplicates disappear. The clearest, most relevant opportunities rise.</p></article></div></section>}
    <footer className="shell"><a className="brand" href="#"><span className="brand-mark"><Compass size={17}/></span>Cvolve<span>Pro</span></a><p>Move toward work that matters.</p><span>© 2026 CvolvePro</span></footer>
  </main>;
}
