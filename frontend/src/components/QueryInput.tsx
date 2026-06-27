"use client";

import { useState, useRef, useEffect } from "react";
import styles from "./QueryInput.module.css";

interface Props {
  onSubmit: (query: string) => void;
  loading: boolean;
  disabled?: boolean;
}

const PLACEHOLDERS = [
  "Something that'll make me cry on the tube…",
  "A fantasy with morally grey characters and slow burn romance…",
  "Dense literary fiction like Donna Tartt but darker…",
  "Cozy mystery, amateur sleuth, no cliffhangers…",
  "Sci-fi that's more philosophical than action…",
  "A short one — under 300 pages — that punches hard…",
];

export default function QueryInput({ onSubmit, loading, disabled }: Props) {
  const [value, setValue] = useState("");
  const [placeholder, setPlaceholder] = useState(PLACEHOLDERS[0]);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Rotate placeholder every 5 seconds
  useEffect(() => {
    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % PLACEHOLDERS.length;
      setPlaceholder(PLACEHOLDERS[i]);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || loading || disabled) return;
    onSubmit(trimmed);
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  }

  // Auto-resize textarea
  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} id="query-form">
      <div className={`${styles.inputWrap} ${loading ? styles.loading : ""} ${disabled ? styles.disabled : ""}`}>
        <textarea
          ref={inputRef}
          id="query-input"
          className={styles.textarea}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKey}
          placeholder={placeholder}
          rows={1}
          disabled={loading || disabled}
          aria-label="Describe what you're in the mood to read"
        />
        <button
          id="query-submit"
          type="submit"
          className={`btn btn-primary ${styles.submitBtn}`}
          disabled={!value.trim() || loading || disabled}
          aria-label="Get recommendations"
        >
          {loading ? (
            <span className="spinner" style={{ width: 16, height: 16 }} />
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M5 12h14M13 5l7 7-7 7" />
            </svg>
          )}
        </button>
      </div>
      <p className={styles.hint}>
        {loading
          ? "Searching your taste profile…"
          : "Enter · Shift+Enter for newline"}
      </p>
    </form>
  );
}
