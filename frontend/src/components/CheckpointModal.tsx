"use client";

import { useEffect, useState } from "react";
import {
  CheckpointItem,
  CheckpointStatus,
  TBRDropCandidate,
} from "@/lib/types";
import { feedback, tbr } from "@/lib/api";
import BookCover from "./BookCover";
import styles from "./CheckpointModal.module.css";

const STATUSES: {
  value: CheckpointStatus;
  label: string;
  icon: string;
}[] = [
  { value: "abandoned", label: "Burned it", icon: "💀" },
  { value: "still_reading", label: "In the trenches", icon: "📖" },
  { value: "finished", label: "Devoured it", icon: "🖤" },
  { value: "havent_started", label: "Haven't started", icon: "🕒" },
];

interface Props {
  items: CheckpointItem[];
  dropCandidates: TBRDropCandidate[];
  onComplete: () => void;
}

function getRelativeTimeString(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffTime = Math.abs(now.getTime() - date.getTime());
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays <= 0) return "today";
    if (diffDays === 1) return "yesterday";
    if (diffDays < 7) {
      const days = [
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
      ];
      return `last ${days[date.getDay()]}`;
    }
    return "recently";
  } catch {
    return "recently";
  }
}

export default function CheckpointModal({
  items,
  dropCandidates,
  onComplete,
}: Props) {
  const [isSlidUp, setIsSlidUp] = useState(true);

  // Trigger slide-down animation on mount
  useEffect(() => {
    const t = setTimeout(() => setIsSlidUp(false), 50);
    return () => clearTimeout(t);
  }, []);

  const hasReadingItem = items.length > 0;
  const hasDropItem = !hasReadingItem && dropCandidates.length > 0;

  if (!hasReadingItem && !hasDropItem) {
    return null;
  }

  // Pick the first item to focus the user
  const readingItem = items[0];
  const dropItem = dropCandidates[0];

  function dismissAndComplete() {
    setIsSlidUp(true);
    setTimeout(onComplete, 350); // wait for slide-up transition
  }

  async function handleStatus(status: CheckpointStatus) {
    // Zero friction: instantly dismiss
    dismissAndComplete();

    // Fire API call in the background
    try {
      await feedback.submit({
        work_uuid: readingItem.work.work_uuid,
        event_type: "checkpoint_update",
        checkpoint_status: status,
      });
    } catch {
      /* background failure is silent */
    }
  }

  async function handleKeep() {
    dismissAndComplete();
    try {
      await tbr.resetPriority(dropItem.tbr_uuid);
    } catch {
      /* background failure is silent */
    }
  }

  async function handleDrop() {
    dismissAndComplete();
    try {
      await tbr.drop(dropItem.tbr_uuid);
    } catch {
      /* background failure is silent */
    }
  }

  return (
    <>
      <div className={styles.backdrop} onClick={dismissAndComplete} />
      <div
        className={`${styles.modal} ${isSlidUp ? styles.slidUp : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label="Reading checkpoint"
      >
        <div className={styles.container}>
          {hasReadingItem ? (
            <>
              {/* Cover on Left */}
              <div className={styles.coverWrap}>
                <BookCover work={readingItem.work} className={styles.cover} />
              </div>

              {/* Content on Right */}
              <div className={styles.body}>
                <h3 className={styles.title}>Hold up.</h3>
                <p className={styles.copy}>
                  You pulled <strong>"{readingItem.work.title}"</strong> by{" "}
                  {readingItem.work.author?.canonical_name ?? "Unknown"}{" "}
                  {getRelativeTimeString(readingItem.delivered_at)}. Where are
                  we at?
                </p>

                <div className={styles.actions}>
                  {STATUSES.map((s) => (
                    <button
                      key={s.value}
                      className={styles.actionBtn}
                      onClick={() => handleStatus(s.value)}
                    >
                      <span className={styles.icon}>{s.icon}</span>
                      <span className={styles.label}>{s.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Drop Candidate Cover */}
              <div className={styles.coverWrap}>
                {dropItem.cover_url ? (
                  <img
                    src={dropItem.cover_url}
                    alt={dropItem.title}
                    className={styles.cover}
                    onError={(e) => {
                      e.currentTarget.style.display = "none";
                    }}
                  />
                ) : (
                  <div className={styles.placeholderCover}>📖</div>
                )}
              </div>

              {/* Drop Candidate Content */}
              <div className={styles.body}>
                <h3 className={styles.title}>Losing interest?</h3>
                <p className={styles.copy}>
                  You saved <strong>"{dropItem.title}"</strong> by{" "}
                  {dropItem.author_name} {dropItem.days_since_added} days ago.
                  Still craving it?
                </p>

                <div className={styles.dropActions}>
                  <button className={styles.keepBtn} onClick={handleKeep}>
                    🖤 Still craving it
                  </button>
                  <button className={styles.dropBtn} onClick={handleDrop}>
                    ✕ Let it go
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
