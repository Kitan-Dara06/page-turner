"use client";

import { useEffect, useState, useRef, useCallback } from "react";
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

type SwipeDirection = "left" | "right" | "up" | null;

const SWIPE_THRESHOLD = 80; // px
const ANIMATION_DURATION = 300; // ms

export default function RecommendationCard({
  item,
  currentQuery,
  currentMoodTags,
  onDecision,
}: Props) {
  const { work, match_source, explanation } = item;
  const [animateOut, setAnimateOut] = useState(false);
  const [swipeDir, setSwipeDir] = useState<SwipeDirection>(null);
  const [showUndo, setShowUndo] = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const touchDelta = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const undoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset animation state when a new card arrives (React reuses component)
  useEffect(() => {
    setAnimateOut(false);
    setSwipeDir(null);
    setShowUndo(false);
    setLastAction(null);
    setExpanded(false);
    touchDelta.current = { x: 0, y: 0 };
    if (undoTimer.current) clearTimeout(undoTimer.current);
  }, [work.work_uuid]);

  const executeAction = useCallback(
    async (action: "save" | "read" | "pass" | "interested") => {
      setLastAction(action);

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
            const hasRead = history.finished.some(
              (b) => b.work_uuid === work.work_uuid,
            );
            if (hasRead) {
              const confirmReread = window.confirm(
                `You've already read "${work.title}". Is this a reread?`,
              );
              if (confirmReread) eventType = "reread";
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
    },
    [work.work_uuid, work.title, currentQuery, currentMoodTags],
  );

  const handleAction = useCallback(
    (action: "save" | "read" | "pass" | "interested") => {
      if (animateOut) return;

      // Map action to swipe direction for fly-off animation
      const dirMap: Record<string, SwipeDirection> = {
        pass: "left",
        interested: "right",
        read: "up",
        save: "right", // TBR save flies right like interested
      };
      setSwipeDir(dirMap[action]);
      setAnimateOut(true);

      // Fire API in background — don't block the card transition
      executeAction(action);

      // Show undo toast with shorter delay for faster card-to-card flow
      setShowUndo(true);
      if (undoTimer.current) clearTimeout(undoTimer.current);
      undoTimer.current = setTimeout(() => {
        setShowUndo(false);
        onDecision();
      }, ANIMATION_DURATION + 1200);
    },
    [animateOut, executeAction, onDecision],
  );

  // ── Swipe gesture handlers ──
  const handleTouchStart = (e: React.TouchEvent) => {
    if (animateOut) return;
    const t = e.touches[0];
    touchStart.current = { x: t.clientX, y: t.clientY };
    touchDelta.current = { x: 0, y: 0 };
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchStart.current || animateOut) return;
    const t = e.touches[0];
    const dx = t.clientX - touchStart.current.x;
    const dy = t.clientY - touchStart.current.y;
    touchDelta.current = { x: dx, y: dy };

    // Live drag: translate the card in real time
    if (cardRef.current) {
      const rotation = dx * 0.05; // slight rotation for realism
      cardRef.current.style.transform = `translate(${dx}px, ${dy}px) rotate(${rotation}deg)`;
      cardRef.current.style.transition = "none";
    }
  };

  const handleTouchEnd = () => {
    if (!touchStart.current || animateOut) return;
    const { x: dx, y: dy } = touchDelta.current;
    touchStart.current = null;

    // Reset inline transform
    if (cardRef.current) {
      cardRef.current.style.transition = `transform ${ANIMATION_DURATION}ms cubic-bezier(0.16, 1, 0.3, 1)`;
    }

    // Determine swipe direction
    const absDx = Math.abs(dx);
    const absDy = Math.abs(dy);

    if (absDx > SWIPE_THRESHOLD || absDy > SWIPE_THRESHOLD) {
      if (absDy > absDx && dy < -SWIPE_THRESHOLD) {
        // Swipe up → Read it
        setSwipeDir("up");
        setAnimateOut(true);
        executeAction("read");
        setShowUndo(true);
        if (undoTimer.current) clearTimeout(undoTimer.current);
        undoTimer.current = setTimeout(() => {
          setShowUndo(false);
          onDecision();
        }, ANIMATION_DURATION + 1200);
      } else if (absDx > absDy && dx < -SWIPE_THRESHOLD) {
        // Swipe left → Pass
        setSwipeDir("left");
        setAnimateOut(true);
        executeAction("pass");
        setShowUndo(true);
        if (undoTimer.current) clearTimeout(undoTimer.current);
        undoTimer.current = setTimeout(() => {
          setShowUndo(false);
          onDecision();
        }, ANIMATION_DURATION + 1200);
      } else if (absDx > absDy && dx > SWIPE_THRESHOLD) {
        // Swipe right → Interested
        setSwipeDir("right");
        setAnimateOut(true);
        executeAction("interested");
        setShowUndo(true);
        if (undoTimer.current) clearTimeout(undoTimer.current);
        undoTimer.current = setTimeout(() => {
          setShowUndo(false);
          onDecision();
        }, ANIMATION_DURATION + 1200);
      } else {
        // Snap back
        if (cardRef.current) {
          cardRef.current.style.transform = "";
        }
      }
    } else {
      // Below threshold — snap back
      if (cardRef.current) {
        cardRef.current.style.transform = "";
      }
    }
  };

  const ACTION_LABELS: Record<string, string> = {
    pass: "Passed",
    interested: "Interested",
    save: "Saved to TBR",
    read: "Marked as Read",
  };

  const handleUndo = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowUndo(false);
    setAnimateOut(false);
    setSwipeDir(null);
    if (undoTimer.current) clearTimeout(undoTimer.current);
    if (cardRef.current) {
      cardRef.current.style.transform = "";
    }
  };

  return (
    <article
      ref={cardRef}
      className={`${styles.card} ${animateOut ? styles.animateOut : ""} ${swipeDir ? styles[`swipe${swipeDir.charAt(0).toUpperCase() + swipeDir.slice(1)}`] : ""}`}
      id={`rec-${work.work_uuid}`}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
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

          {/* Expandable plot details / description */}
          {item.description && (
            <div className={styles.detailSection}>
              <button
                className={styles.seeMoreBtn}
                onClick={() => setExpanded(!expanded)}
                aria-expanded={expanded}
              >
                {expanded ? "▲ Hide Details" : "▼ See More"}
              </button>
              {expanded && (
                <div className={styles.detailBody}>
                  <p className={styles.plotDescription}>{item.description}</p>
                </div>
              )}
            </div>
          )}

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

      {/* Undo toast */}
      {showUndo && lastAction && (
        <div className={styles.undoToast}>
          <span>
            {ACTION_LABELS[lastAction] || lastAction} —{" "}
            <button className={styles.undoBtn} onClick={handleUndo}>
              Undo
            </button>
          </span>
        </div>
      )}

      {/* Swipe hint — shown only on first card, no animation active */}
      {!animateOut && !showUndo && (
        <div className={styles.swipeHint}>
          <span>← pass</span>
          <span>↑ read</span>
          <span>interested →</span>
        </div>
      )}
    </article>
  );
}
