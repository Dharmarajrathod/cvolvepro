"use client";

import { useEffect, useRef, useState } from "react";

const MIN_VISIBLE_MS = 500;

export default function ClickFeedback() {
  const [active, setActive] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    function showFeedback(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const action = target.closest("button, a, [role='button']");
      if (!(action instanceof HTMLElement)) return;
      if (action.hasAttribute("disabled") || action.getAttribute("aria-disabled") === "true") return;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      setActive(true);
      timerRef.current = window.setTimeout(() => setActive(false), MIN_VISIBLE_MS);
    }

    document.addEventListener("click", showFeedback, true);
    return () => {
      document.removeEventListener("click", showFeedback, true);
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);

  return <div className={`click-feedback-layer ${active ? "active" : ""}`} aria-hidden="true">
    <div className="click-feedback">
      <div className="click-feedback-mark">
        <span/>
        <i/>
      </div>
      <b>Loading</b>
    </div>
  </div>;
}
