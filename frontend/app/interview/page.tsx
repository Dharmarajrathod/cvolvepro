"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Camera, CheckCircle2, ClipboardCheck, Loader2, Mic, MicOff, MessageSquareText, RotateCcw, Sparkles, Square, Table2, Trophy, Volume2 } from "lucide-react";
import { API, AtsResult, InterviewFeedback, readAuthUser, updateAuthUserCredits } from "../shared";
import ProfileMenu from "../ProfileMenu";

type Answer = { question: string; answer: string };
type SpeechRecognitionResultEvent = {
  results: ArrayLike<{ 0?: { transcript?: string } }>;
};
type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
    SpeechRecognition?: SpeechRecognitionConstructor;
  }
}

function jobSkills(ats: AtsResult) {
  const skills = ats.job.skills?.filter(Boolean) || [];
  const missing = ats.missing_keywords?.filter(Boolean) || [];
  const summaryTerms = (ats.job.summary.match(/[A-Za-z][A-Za-z0-9+#.]{2,}/g) || [])
    .filter(term => !/^(the|and|for|with|you|your|job|role|work|this|that|will|have|from)$/i.test(term));
  return [...new Set([...skills, ...missing, ...summaryTerms])].slice(0, 10);
}

function resumeEvidenceLines(ats: AtsResult, terms: string[]) {
  const lines = ats.resume_text
    .split(/\n+|(?<=\.)\s+/)
    .map(line => line.replace(/\s+/g, " ").trim())
    .filter(line => line.length >= 25 && line.length <= 220);
  const matched = lines.filter(line => terms.some(term => line.toLowerCase().includes(term.toLowerCase())));
  return [...new Set([...matched, ...lines])].slice(0, 4);
}

function fallbackQuestions(ats: AtsResult) {
  const role = ats.job.title || "this role";
  const skills = jobSkills(ats);
  const primary = skills[0] || "the main technical requirement";
  const secondary = skills[1] || "the related tools";
  const tertiary = skills[2] || "the expected workflow";
  const evidence = resumeEvidenceLines(ats, skills);
  const projectLine = evidence[0] || "your strongest resume project";
  const secondLine = evidence[1] || projectLine;
  return [
    `For the ${role} role, explain how you would use ${primary} to solve one responsibility from the job description.`,
    `Your resume says: "${projectLine}". Walk through the technical architecture, tools, and your exact contribution.`,
    `The job description emphasizes ${primary}, ${secondary}, and ${tertiary}. Which is your strongest area, and what production-level example proves it?`,
    `Describe a technical problem you solved that is closest to this job description. What was the root cause, what options did you compare, and why did you choose your approach?`,
    `If you had to improve or scale the work described in "${secondLine}", what would you change technically and how would you measure success?`,
    `What tradeoffs would you consider when implementing ${primary} with ${secondary} for this role?`,
    `Pick one weaker ATS area from this review: ${ats.gaps.slice(0, 2).join(" ")} How would you close that gap with a concrete project or learning plan?`,
    `How would you test, debug, or validate a feature or workflow involving ${primary} before handing it to users or stakeholders?`,
    `Tell me about a time you used data, logs, metrics, user feedback, or review comments to improve a technical solution relevant to ${role}.`,
    `Imagine you join as ${role} tomorrow. What technical task from the job description would you tackle first, what steps would you take, and what risks would you watch for?`,
  ];
}

function fallbackFeedback(ats: AtsResult, finalAnswers: Answer[]): InterviewFeedback {
  const answeredText = finalAnswers.map(item => item.answer).join(" ");
  const hasMetrics = /\b(\d+%|\d+\+?\s*(years?|yrs?|users?|projects?|teams?)|\$\d+|\d+x)\b/i.test(answeredText);
  const hasAction = /\b(built|led|owned|delivered|improved|reduced|increased|designed|deployed|implemented|created|managed)\b/i.test(answeredText);
  const averageWords = Math.round(finalAnswers.reduce((sum, item) => sum + item.answer.split(/\s+/).filter(Boolean).length, 0) / Math.max(1, finalAnswers.length));
  const overall = Math.max(35, Math.min(88, ats.score - 8 + (hasMetrics ? 8 : 0) + (hasAction ? 6 : 0) + (averageWords >= 45 ? 6 : 0)));
  return {
    overall_score: overall,
    hiring_signal: overall >= 75 ? "Strong interview signal" : overall >= 55 ? "Mixed interview signal" : "Needs more preparation",
    summary: `Your answers were reviewed against ${ats.job.title}. Strengthen them by using specific examples, your direct actions, and measurable results.`,
    strengths: [
      finalAnswers.length >= 10 ? "You completed the full interview set." : "You answered part of the interview set.",
      hasAction ? "Your answers include ownership/action language." : "Your answers give a starting point for role fit.",
      hasMetrics ? "You included measurable evidence in your answers." : "You can improve quickly by adding measurable evidence.",
    ],
    improvements: [
      averageWords < 45 ? "Several answers are too short; expand them with situation, action, and result." : "Make strong answers sharper by naming tradeoffs and decisions.",
      "Connect each answer directly to the job description and ATS gaps.",
      "Mention tools, scale, and business or project impact more clearly.",
    ],
    better_answer_guidance: [
      "Use STAR: situation, task, action, result.",
      "Open each answer with the direct answer, then give one concrete example.",
      "Close with a metric, result, or lesson learned.",
      `For ${ats.job.title}, reference the most important job skills and missing keywords naturally.`,
    ],
    question_feedback: finalAnswers.map(item => ({
      question: item.question,
      your_answer: item.answer,
      expected_answer: `A strong answer should directly address the question, connect to ${ats.job.title}, include a specific example, explain your action, and close with a measurable result or learning.`,
      feedback: item.answer.split(/\s+/).filter(Boolean).length < 45 ? "Add more detail, tools used, and measurable impact." : "Good foundation; make the result and job connection more explicit.",
    })),
  };
}

export default function InterviewPage() {
  const [ats, setAts] = useState<AtsResult | null>(null);
  const [questions, setQuestions] = useState<string[]>([]);
  const [current, setCurrent] = useState(0);
  const [draft, setDraft] = useState("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [mediaReady, setMediaReady] = useState(false);
  const [mediaError, setMediaError] = useState("");
  const [recording, setRecording] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(true);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<InterviewFeedback | null>(null);
  const [error, setError] = useState("");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const progress = useMemo(() => questions.length ? Math.round(((answers.length) / questions.length) * 100) : 0, [answers.length, questions.length]);

  useEffect(() => {
    const raw = sessionStorage.getItem("cvolvepro:atsResult");
    if (!raw) { setLoading(false); return; }
    try {
      const parsed = JSON.parse(raw) as AtsResult;
      setAts(parsed);
      startInterview(parsed);
    } catch {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!loading && questions[current]) speakQuestion();
  }, [loading, current, questions]);

  useEffect(() => {
    return () => {
      stopRecognition();
      window.speechSynthesis?.cancel();
      streamRef.current?.getTracks().forEach(track => track.stop());
    };
  }, []);

  async function startInterview(parsed: AtsResult) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}/api/interview/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job: parsed.job,
          resume_text: parsed.resume_text,
          ats_score: parsed.score,
          ats_summary: parsed.verdict,
          user_email: readAuthUser()?.email || null
        })
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Interview questions could not be generated.");
      if (typeof body.credits_remaining === "number") updateAuthUserCredits(body.credits_remaining);
      setQuestions(body.questions);
    } catch (err) {
      setQuestions(fallbackQuestions(parsed));
      setError("Live AI questions could not be reached, so a role-based interview was generated from your ATS result.");
    } finally {
      setLoading(false);
    }
  }

  async function submitAnswer(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim() || !questions[current]) return;
    const nextAnswers = [...answers, { question: questions[current], answer: draft.trim() }];
    setAnswers(nextAnswers);
    setDraft("");
    if (nextAnswers.length < questions.length) {
      setCurrent(value => value + 1);
      return;
    }
    await finishInterview(nextAnswers);
  }

  async function enableCameraAndMic() {
    setMediaError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = stream;
      setMediaReady(true);
      if (videoRef.current) videoRef.current.srcObject = stream;
    } catch {
      setMediaError("Camera and microphone permission is required for recorded interview answers.");
    }
  }

  function speakQuestion() {
    const question = questions[current];
    if (!question || typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(question);
    utterance.rate = 0.95;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  }

  function startRecognition() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setSpeechSupported(false);
      return;
    }
    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = event => {
      let transcript = "";
      for (let index = 0; index < event.results.length; index += 1) {
        transcript += event.results[index][0]?.transcript || "";
      }
      setDraft(transcript.trim());
    };
    recognition.onerror = () => setSpeechSupported(false);
    recognitionRef.current = recognition;
    recognition.start();
  }

  function stopRecognition() {
    try { recognitionRef.current?.stop(); } catch {}
    recognitionRef.current = null;
  }

  async function startRecording() {
    if (!streamRef.current) await enableCameraAndMic();
    const stream = streamRef.current;
    if (!stream) return;
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = event => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorderRef.current = recorder;
    recorder.start();
    setRecording(true);
    startRecognition();
  }

  function stopRecording() {
    recorderRef.current?.stop();
    stopRecognition();
    setRecording(false);
  }

  function resetForNextQuestion() {
    setDraft("");
  }

  async function submitRecordedAnswer(e: FormEvent) {
    e.preventDefault();
    if (recording) stopRecording();
    if (!draft.trim() || !questions[current]) return;
    const nextAnswers = [...answers, { question: questions[current], answer: draft.trim() }];
    setAnswers(nextAnswers);
    resetForNextQuestion();
    if (nextAnswers.length < questions.length) {
      setCurrent(value => value + 1);
      return;
    }
    await finishInterview(nextAnswers);
  }

  async function finishInterview(finalAnswers: Answer[]) {
    if (!ats) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${API}/api/interview/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job: ats.job, resume_text: ats.resume_text, answers: finalAnswers })
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Interview feedback could not be generated.");
      setFeedback(body);
    } catch (err) {
      setFeedback(fallbackFeedback(ats, finalAnswers));
      setError("Live AI feedback could not be reached, so feedback was generated from your answers and ATS result.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!ats) {
    return <main className="flow-page shell"><nav className="flow-nav"><Link className="back-link" href="/ats"><ArrowLeft size={16}/>Back to ATS</Link><ProfileMenu showCredits/></nav><section className="flow-empty"><ClipboardCheck/><h1>ATS approval required</h1><p>Generate an ATS score above 70% before opening the interview room.</p></section></main>;
  }

  return <main className="flow-page shell">
    <nav className="flow-nav"><Link className="back-link" href="/ats"><ArrowLeft size={16}/>Back to ATS score</Link><ProfileMenu showCredits/></nav>
    <section className="interview-head">
      <div><span className="kicker">AI INTERVIEW</span><h1>{ats.job.title}</h1><p>{ats.job.company} · ATS {ats.score}%</p></div>
      <div className="progress-ring"><strong>{feedback ? 100 : progress}</strong><span>%</span></div>
    </section>

    {loading && <section className="interview-card center"><Loader2 className="spin" size={28}/><h2>Generating your 10-question interview</h2><p>NVIDIA is tailoring questions to the job description, resume projects, and experience signals.</p></section>}
    {error && <p className="flow-error wide">{error}</p>}

    {!loading && !feedback && questions.length > 0 && <section className="interview-card voice-interview">
      <div className="question-top"><span>Question {current + 1} of {questions.length}</span><MessageSquareText size={20}/></div>
      <h2>{questions[current]}</h2>
      <div className="voice-actions">
        <button type="button" className="tool-button" onClick={speakQuestion}><Volume2 size={17}/><span>Replay</span></button>
        <button type="button" className={`tool-button ${mediaReady ? "ready" : ""}`} onClick={enableCameraAndMic}><Camera size={17}/><span>{mediaReady ? "Camera ready" : "Enable camera"}</span></button>
      </div>
      <form onSubmit={submitRecordedAnswer}>
        <div className="recording-grid">
          <div className="camera-panel">
            <video ref={videoRef} autoPlay muted playsInline className={mediaReady ? "" : "hidden-video"}/>
            {!mediaReady && <div className="camera-placeholder"><Camera size={32}/><span>Camera preview</span></div>}
            {recording && <span className="recording-badge">Recording</span>}
          </div>
          <div className="answer-panel">
            <div className="record-controls">
              {!recording ? <button type="button" className="record-button" onClick={startRecording}><Mic size={18}/><span>Start answer</span></button> : <button type="button" className="record-button stop" onClick={stopRecording}><Square size={18}/><span>Stop answer</span></button>}
              <button type="button" className="ghost-button" onClick={() => setDraft("")}><RotateCcw size={15}/><span>Clear transcript</span></button>
              {!speechSupported && <span><MicOff size={14}/>Speech transcript unavailable</span>}
            </div>
            <textarea value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Your spoken answer transcript appears here. Edit it if speech recognition misses anything."/>
          </div>
        </div>
        {mediaError && <p className="flow-error">{mediaError}</p>}
        <button className="primary-action" disabled={!draft.trim() || submitting}>{submitting ? <Loader2 className="spin" size={18}/> : current + 1 === questions.length ? <Sparkles size={18}/> : <ArrowRight size={18}/>} {current + 1 === questions.length ? "Finish and get feedback" : "Save answer and continue"}</button>
      </form>
      <div className="answer-strip">{answers.map((answer, index)=><span key={answer.question} className="done"><CheckCircle2 size={13}/>Q{index + 1}</span>)}</div>
    </section>}

    {feedback && <section className="feedback-panel">
      <div className="feedback-score"><Trophy size={28}/><strong>{feedback.overall_score}%</strong><span>{feedback.hiring_signal}</span></div>
      <h2>Interview feedback</h2>
      <p>{feedback.summary}</p>
      <div className="ats-columns">
        <section><h3>What worked</h3>{feedback.strengths.map(item=><p key={item}><CheckCircle2 size={14}/>{item}</p>)}</section>
        <section><h3>Improve next</h3>{feedback.improvements.map(item=><p key={item}>{item}</p>)}</section>
      </div>
      <section className="recommendations"><h3>Better answer guidance</h3>{feedback.better_answer_guidance.map(item=><p key={item}>{item}</p>)}</section>
      {Boolean(feedback.question_feedback?.length) && <section className="question-feedback-panel"><h3><Table2 size={15}/>Question by question review</h3><div className="responsive-table"><table><thead><tr><th>Question</th><th>Your answer</th><th>Expected answer</th><th>Feedback</th></tr></thead><tbody>{feedback.question_feedback?.map((item, index)=><tr key={`${item.question}-${index}`}><td>{item.question}</td><td>{item.your_answer}</td><td>{item.expected_answer}</td><td>{item.feedback}</td></tr>)}</tbody></table></div></section>}
      <Link className="secondary-action" href="/">Back to job search</Link>
    </section>}
  </main>;
}
