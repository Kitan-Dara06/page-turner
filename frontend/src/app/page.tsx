"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { recommendations as recApi, profile as profileApi } from "@/lib/api";
import type {
  CheckpointItem,
  RecommendationResponse,
  TBRDropCandidate,
} from "@/lib/types";
import RecommendationCard from "@/components/RecommendationCard";
import CheckpointModal from "@/components/CheckpointModal";
import styles from "./page.module.css";

const ONBOARDING_KEY = "pageturner_onboarded";

const PLACEHOLDERS = [
  "Give me a grumpy x sunshine dynamic, but make the angst physically painful...",
  "Something similar to Ronnie Mathews, but with a faster plot...",
  "A quiet standalone sci-fi with beautiful, lyrical prose...",
  "A fantasy romance where the villain falls first and falls hard...",
  "Give me a book with high tolerance for moral darkness...",
  "A cozy mystery with ghosts and a slow burn secondary romance...",
  "Devastate me. A tragic love story with high stakes and gorgeous prose...",
];

type PageState = "idle" | "checkpoint" | "loading" | "results";

export default function HomePage() {
  const router = useRouter();
  const [state, setState] = useState<PageState>("idle");
  const [results, setResults] = useState<RecommendationResponse | null>(null);
  const [pending, setPending] = useState<CheckpointItem[]>([]);
  const [dropCandidates, setDropCandidates] = useState<TBRDropCandidate[]>([]);
  const [query, setQuery] = useState("");
  const [placeholder, setPlaceholder] = useState("");
  const [activeCardIndex, setActiveCardIndex] = useState(0);
  const [calibration, setCalibration] = useState<any>(null);
  const pendingQueryRef = useRef("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load calibration data on mount
  useEffect(() => {
    profileApi
      .get()
      .then((data) => {
        if (data.calibration) {
          setCalibration(data.calibration);
        }
      })
      .catch(() => {});
  }, []);

  // Redirect to onboarding if not done
  useEffect(() => {
    if (!localStorage.getItem(ONBOARDING_KEY)) router.replace("/onboarding");
  }, [router]);

  // Set random placeholder on mount
  useEffect(() => {
    const idx = Math.floor(Math.random() * PLACEHOLDERS.length);
    setPlaceholder(PLACEHOLDERS[idx]);
  }, [state]);

  // Auto-focus the vibe prompt textarea in idle state
  useEffect(() => {
    if (state === "idle" && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [state]);

  async function handleSubmit() {
    if (!query.trim()) return;
    pendingQueryRef.current = query;
    try {
      const ck = await recApi.getCheckpoint();
      if (ck.pending_items.length > 0 || ck.drop_candidates.length > 0) {
        setPending(ck.pending_items);
        setDropCandidates(ck.drop_candidates);
        setState("checkpoint");
        return;
      }
    } catch {
      /* non-fatal fallback */
    }
    await fireQuery(query);
  }

  async function fireQuery(q: string) {
    setState("loading");
    try {
      // Submit async task
      const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const token = (await import("@/lib/api")).getAuthToken();
      const submitRes = await fetch(`${BASE}/api/v1/recommend/async`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query: q }),
      });
      if (!submitRes.ok) throw new Error("Failed to submit");
      const { task_id } = await submitRes.json();

      // Poll every 2s until complete
      const poll = async (): Promise<any> => {
        const statusRes = await fetch(
          `${BASE}/api/v1/recommend/status/${task_id}`,
          {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          },
        );
        if (!statusRes.ok) throw new Error("Status check failed");
        return statusRes.json();
      };

      let data = await poll();
      while (data.status === "processing" || data.status === "pending") {
        await new Promise((r) => setTimeout(r, 2000));
        data = await poll();
      }

      if (data.status === "complete") {
        setResults(data);
        setActiveCardIndex(0);
        setState("results");
      } else {
        throw new Error(data.detail || "Unknown error");
      }
    } catch {
      setState("idle");
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleReset = () => {
    setQuery("");
    setResults(null);
    setActiveCardIndex(0);
    setState("idle");
  };

  const handleNextCard = () => {
    setActiveCardIndex((prev) => prev + 1);
  };

  return (
    <div className={styles.container}>
      {/* Frosted glass CheckpointModal slider */}
      {state === "checkpoint" &&
        (pending.length > 0 || dropCandidates.length > 0) && (
          <CheckpointModal
            items={pending}
            dropCandidates={dropCandidates}
            onComplete={() => {
              setPending([]);
              setDropCandidates([]);
              fireQuery(pendingQueryRef.current);
            }}
          />
        )}

      {/* 1. Home / Idle State */}
      {state === "idle" && (
        <div className={styles.promptWrapper}>
          <label className={styles.promptLabel} htmlFor="vibe-prompt">
            Describe a Vibe
          </label>
          <div className={styles.textareaWrap}>
            <textarea
              id="vibe-prompt"
              ref={textareaRef}
              className={styles.vibeTextarea}
              placeholder={placeholder}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
          <p className={styles.helperText}>
            press enter to seek · shift+enter for new line
          </p>

          {calibration && !calibration.complete && (
            <div className={styles.calibrationCard}>
              <div className={styles.calibrationHeader}>
                <span className={styles.calibrationTitle}>
                  ⚙️ calibrating taste profile
                </span>
                <span className={styles.calibrationStats}>
                  {calibration.total_interactions}/20 interactions
                </span>
              </div>
              <div className={styles.progressBarBg}>
                <div
                  className={styles.progressBarFill}
                  style={{
                    width: `${Math.min(100, (calibration.total_interactions / 20) * 100)}%`,
                  }}
                />
              </div>
              <span className={styles.calibrationHint}>
                The engine is learning your taste.{" "}
                {calibration.interactions_remaining} meaningful interactions
                remaining.
              </span>
            </div>
          )}
        </div>
      )}

      {/* 2. Loading State */}
      {state === "loading" && (
        <div className={styles.loadingContainer}>
          <div className={styles.loadingPulse} />
          <p className={styles.loadingText}>Summoning stories...</p>
        </div>
      )}

      {/* 3. Results State (Single Card Feed) */}
      {state === "results" && results && (
        <div className={styles.feedContainer}>
          <div className={styles.feedHeader}>
            <span className={styles.feedActiveVibe}>
              seeking: "{results.query_rewritten || query}"
            </span>
            <button className={styles.resetBtn} onClick={handleReset}>
              change vibe
            </button>
          </div>

          {activeCardIndex < results.results.length ? (
            <RecommendationCard
              item={results.results[activeCardIndex]}
              currentQuery={results.query_rewritten}
              currentMoodTags={results.mood_tags_extracted}
              onDecision={handleNextCard}
            />
          ) : (
            <div className={styles.endOfFeed}>
              <div className={styles.endIcon}>✦</div>
              <h3 className={styles.endTitle}>End of Feed</h3>
              <p className={styles.endSubtitle}>
                You've reviewed all immediate recommendations for this craving.
              </p>
              <button className={styles.newVibeBtn} onClick={handleReset}>
                Seek a New Vibe
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
