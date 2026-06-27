"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RecommendedItem } from "@/lib/types";
import { feedback, tbr } from "@/lib/api";
import BookCover from "./BookCover";
import styles from "./RecommendationCard.module.css";

interface Props {
  item: RecommendedItem;
  currentQuery?: string;
  currentMoodTags?: string[];
  onDecision: () => void;
}

export default function RecommendationCard({
  item,
  currentQuery,
  currentMoodTags,
  onDecision,
}: Props) {
  const { work, match_source, explanation } = item;
  const [animateOut, setAnimateOut] = useState(false);

  // Reset animation state when a new card arrives (React reuses component)
  useEffect(() => {
    setAnimateOut(false);
  }, [work.work_uuid]);

  const handleAction = async (
    action: "save" | "read" | "pass" | "interested",
  ) => {
    if (animateOut) return;
    setAnimateOut(true);

    // Trigger next card transition after exit animation finishes
    setTimeout(onDecision, 300);

    // Call API in the background (zero blocking)
    try {
      if (action === "save") {
        await tbr.add({
          work_uuid: work.work_uuid,
          current_query_text: currentQuery,
          current_mood_tags: currentMoodTags,
        });
      } else if (action === "interested") {
        await feedback.submit({
          work_uuid: work.work_uuid,
          event_type: "interested",
        });
      } else if (action === "read") {
        let eventType: any = "logged_read";
        try {
          const history = await feedback.getHistory();
          const hasRead = history.finished.some((b) => b.work_uuid === work.work_uuid);
          if (hasRead) {
            const confirmReread = window.confirm(`You've already read "${work.title}". Is this a reread?`);
            if (confirmReread) {
              eventType = "reread";
            }
          }
        } catch {
          // ignore error and proceed with logged_read
        }
        await feedback.submit({
          work_uuid: work.work_uuid,
          event_type: eventType,
        });
      } else if (action === "pass") {
        await feedback.submit({
          work_uuid: work.work_uuid,
          event_type: "not_interested",
        });
      }
    } catch {
      /* background failures are silent */
    }
  };

  return (
    <article
      className={`${styles.card} ${animateOut ? styles.animateOut : ""}`}
      id={`rec-${work.work_uuid}`}
    >
      <div className={styles.cardContainer}>
        {/* Left Side: Large high-res cover with deep shadow */}
        <div className={styles.leftSection}>
          <div className={styles.coverWrap}>
            <BookCover work={work} className={styles.cover} />
            {match_source === "exploration" && (
              <span className={styles.explorationBadge}>◎ beyond map</span>
            )}
          </div>
        </div>

        {/* Right Side: Title, Author, Metadata, why this */}
        <div className={styles.rightSection}>
          <div className={styles.metaHeader}>
            <h2 className={styles.title}>{work.title}</h2>
            {work.author ? (
              <Link
                href={`/authors/${work.author.person_uuid}`}
                className={styles.author}
              >
                by {work.author.canonical_name}
              </Link>
            ) : (
              <span className={styles.author}>Unknown author</span>
            )}

            <div className={styles.bookStats}>
              {work.page_count && <span>{work.page_count} pages</span>}
              {work.page_count && work.aggregate_rating && <span>·</span>}
              {work.aggregate_rating && (
                <span>★ {work.aggregate_rating.toFixed(1)}</span>
              )}
              {work.publication_year && <span>·</span>}
              {work.publication_year && <span>{work.publication_year}</span>}
            </div>
          </div>

          <div className={styles.whySection}>
            <h4 className={styles.whyTitle}>Why this?</h4>
            <p className={styles.whyBody}>
              {explanation ||
                "Surfaced because it matches your recent cravings and taste footprint."}
            </p>
          </div>

          {/* Floating actions in the bottom right of the card context */}
          <div className={styles.actions}>
            <button
              className={styles.actionBtnPass}
              onClick={() => handleAction("pass")}
              aria-label="Pass book"
              title="Pass (Not interested)"
            >
              ✕ Pass
            </button>
            <button
              className={styles.actionBtnInterested}
              onClick={() => handleAction("interested")}
              aria-label="Interested in vibe"
              title="Interested (track vibe, not TBR)"
            >
              ◈ Interested
            </button>
            <button
              className={styles.actionBtnSave}
              onClick={() => handleAction("save")}
              aria-label="Save Vibe to TBR"
              title="Save Vibe (TBR)"
            >
              🔖 Save Vibe
            </button>
            <button
              className={styles.actionBtnRead}
              onClick={() => handleAction("read")}
              aria-label="Mark as Read"
              title="Read It"
            >
              ✓ Read It
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
