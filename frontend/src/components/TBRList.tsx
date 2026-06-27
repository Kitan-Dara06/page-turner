"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { TBREntryResponse } from "@/lib/types";
import { tbr as tbrApi } from "@/lib/api";
import BookCover from "./BookCover";
import styles from "./TBRList.module.css";

function priorityColor(score: number): string {
  // score is a float — higher is hotter
  if (score >= 0.7) return "var(--accent)";
  if (score >= 0.4) return "var(--warning)";
  return "var(--text-muted)";
}

export default function TBRList() {
  const [entries, setEntries] = useState<TBREntryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dropping, setDropping] = useState<Set<string>>(new Set());

  useEffect(() => {
    tbrApi
      .getList()
      .then((data) => {
        setEntries(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.detail ?? "Failed to load TBR.");
        setLoading(false);
      });
  }, []);

  async function handleDrop(entry: TBREntryResponse) {
    if (dropping.has(entry.tbr_uuid)) return;
    setDropping((prev) => new Set(prev).add(entry.tbr_uuid));
    try {
      await tbrApi.drop(entry.tbr_uuid);
      // Animate out then remove
      setTimeout(() => {
        setEntries((prev) => prev.filter((e) => e.tbr_uuid !== entry.tbr_uuid));
        setDropping((prev) => {
          const next = new Set(prev);
          next.delete(entry.tbr_uuid);
          return next;
        });
      }, 300);
    } catch {
      setDropping((prev) => {
        const next = new Set(prev);
        next.delete(entry.tbr_uuid);
        return next;
      });
    }
  }

  if (loading) {
    return (
      <div className={styles.list}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className={`${styles.skeletonRow} skeleton`} />
        ))}
      </div>
    );
  }

  if (error) {
    return <div className="error-banner">{error}</div>;
  }

  if (entries.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">🔖</div>
        <h3>Your TBR is empty</h3>
        <p>
          Save books from the Discover tab and they'll appear here, sorted by
          how well they fit what you were looking for.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.list}>
      {entries.map((entry, idx) => {
        const isDropping = dropping.has(entry.tbr_uuid);
        return (
          <div
            key={entry.tbr_uuid}
            className={`${styles.entry} ${isDropping ? styles.exitEntry : ""}`}
            id={`tbr-entry-${entry.tbr_uuid}`}
            style={
              {
                "--priority-color": priorityColor(entry.priority_score),
              } as React.CSSProperties
            }
          >
            {/* Priority ramp bar */}
            <div className={styles.priorityBar} />

            {/* Rank */}
            <span className={styles.rank}>#{idx + 1}</span>

            {/* Cover */}
            <div className={styles.coverWrap}>
              <BookCover work={entry.work} className={styles.cover} />
            </div>

            {/* Body */}
            <div className={styles.body}>
              <div className={styles.topRow}>
                <div>
                  <h3 className={styles.title}>{entry.work.title}</h3>
                  {entry.work.author ? (
                    <Link
                      href={`/authors/${entry.work.author.person_uuid}`}
                      className={styles.author}
                    >
                      {entry.work.author.canonical_name}
                    </Link>
                  ) : (
                    <span className={styles.author}>Unknown author</span>
                  )}
                </div>
                <div className={styles.scoreWrap}>
                  <div
                    className={styles.scoreRing}
                    style={
                      { "--score": entry.priority_score } as React.CSSProperties
                    }
                    title={`Priority score: ${(entry.priority_score * 100).toFixed(0)}`}
                  >
                    <span className={styles.scoreValue}>
                      {(entry.priority_score * 100).toFixed(0)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Context chips */}
              {(entry.add_query_text ||
                entry.add_time_of_day ||
                entry.add_day_of_week) && (
                <div className={styles.contextChips}>
                  {entry.add_query_text && (
                    <span
                      className={styles.contextChip}
                      title="Query you were searching when you saved this"
                    >
                      🔍{" "}
                      {entry.add_query_text.length > 48
                        ? entry.add_query_text.slice(0, 45) + "…"
                        : entry.add_query_text}
                    </span>
                  )}
                  {entry.add_time_of_day && (
                    <span className={styles.contextChip}>
                      🕐 {entry.add_time_of_day}
                    </span>
                  )}
                  {entry.add_day_of_week && (
                    <span className={styles.contextChip}>
                      📅 {entry.add_day_of_week}
                    </span>
                  )}
                </div>
              )}

              {/* Details + actions */}
              <div className={styles.bottomRow}>
                <div className={styles.details}>
                  {entry.work.page_count && (
                    <span>{entry.work.page_count} pp</span>
                  )}
                  {entry.work.aggregate_rating && (
                    <span>★ {entry.work.aggregate_rating.toFixed(1)}</span>
                  )}
                  <span>
                    Added{" "}
                    {new Date(entry.added_at).toLocaleDateString("en-GB", {
                      day: "numeric",
                      month: "short",
                    })}
                  </span>
                </div>
                <button
                  id={`tbr-drop-${entry.tbr_uuid}`}
                  className="btn btn-danger btn-sm"
                  onClick={() => handleDrop(entry)}
                  disabled={isDropping}
                >
                  {isDropping ? (
                    <span
                      className="spinner"
                      style={{ width: 12, height: 12 }}
                    />
                  ) : (
                    "Remove"
                  )}
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
