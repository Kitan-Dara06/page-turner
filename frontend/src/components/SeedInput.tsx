"use client";

import { useState } from "react";
import { getAuthToken } from "@/lib/api";
import styles from "./SeedInput.module.css";

interface ResolvedBook {
  title: string;
  author: string;
  work_uuid: string | null;
  cover_url: string | null;
  resolved: boolean;
}

interface Props {
  onComplete: () => void;
}

const PLACEHOLDERS = [
  "Cradle by Will Wight, The Poppy War by R.F. Kuang, Jade City by Fonda Lee",
  "Pride and Prejudice, The Name of the Wind, Circe",
  "A Court of Thorns and Roses, Fourth Wing, From Blood and Ash",
];

export default function SeedInput({ onComplete }: Props) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [resolved, setResolved] = useState<ResolvedBook[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [placeholder] = useState(
    () => PLACEHOLDERS[Math.floor(Math.random() * PLACEHOLDERS.length)],
  );

  const handleSubmit = async () => {
    const titles = input
      .split(/\n|,|;/)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 3);

    if (titles.length === 0) {
      onComplete();
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/onboarding/seed`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(getAuthToken()
              ? { Authorization: `Bearer ${getAuthToken()}` }
              : {}),
          },
          body: JSON.stringify({
            books: titles.map((t) => ({ title: t })),
          }),
        },
      );

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to seed books");
      }

      const data = await res.json();
      setResolved(data.resolved_books || []);
      setSubmitted(true);

      if (!data.profile_updated) {
        setTimeout(onComplete, 2000);
      }
    } catch (e: any) {
      setError(e.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSkip = () => onComplete();

  if (submitted && resolved.length > 0) {
    return (
      <div className={styles.resolvedContainer}>
        <div className={styles.resolvedHeader}>
          <div className={styles.checkmark}>✓</div>
          <h2 className={styles.resolvedTitle}>Taste profile seeded</h2>
          <p className={styles.resolvedSub}>
            {resolved.filter((r) => r.resolved).length} of {resolved.length}{" "}
            book{resolved.length !== 1 ? "s" : ""} found. Your recommendations
            start here.
          </p>
        </div>

        <div className={styles.resolvedGrid}>
          {resolved.map((book, i) => (
            <div key={i} className={styles.resolvedCard}>
              {book.cover_url ? (
                <img
                  src={book.cover_url}
                  alt={book.title}
                  className={styles.cover}
                />
              ) : (
                <div className={styles.coverPlaceholder}>📖</div>
              )}
              <div className={styles.resolvedMeta}>
                <p className={styles.resolvedBookTitle}>{book.title}</p>
                <p className={styles.resolvedAuthor}>{book.author}</p>
                {!book.resolved && (
                  <p className={styles.notFound}>Not found — skipped</p>
                )}
              </div>
            </div>
          ))}
        </div>

        <button className={styles.continueBtn} onClick={onComplete}>
          Continue to calibration
        </button>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>Books you loved</h2>
        <p className={styles.subtitle}>
          Name up to 3 books you couldn&apos;t put down. We&apos;ll use them to
          understand your taste from day one.
        </p>
      </div>

      <textarea
        className={styles.textarea}
        placeholder={placeholder}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={3}
        autoFocus
      />

      <p className={styles.hint}>
        Separate with commas or new lines · press enter to submit
      </p>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.actions}>
        <button
          className={styles.submitBtn}
          onClick={handleSubmit}
          disabled={loading}
        >
          {loading ? (
            <span className="spinner" style={{ width: 14, height: 14 }} />
          ) : (
            "Seed my taste"
          )}
        </button>
        <button className={styles.skipBtn} onClick={handleSkip}>
          Skip for now
        </button>
      </div>
    </div>
  );
}
