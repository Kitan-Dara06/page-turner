"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { onboarding as onboardingApi } from "@/lib/api";
import { WorkResponse, FlashcardDecision } from "@/lib/types";
import BookCover from "./BookCover";
import styles from "./FlashcardStack.module.css";

const ONBOARDING_KEY = "pageturner_onboarded";

type Decision = {
  label: string;
  icon: string;
  value: FlashcardDecision;
  className: string;
};

const DECISIONS: Decision[] = [
  { label: "Not for me",   icon: "✕", value: "not_interested", className: styles.decisionNo },
  { label: "Want to read", icon: "🔖", value: "interested",     className: styles.decisionTbr },
  { label: "Read it",      icon: "✓", value: "read_it",        className: styles.decisionYes },
];

export default function FlashcardStack() {
  const router = useRouter();
  const [cards, setCards] = useState<WorkResponse[]>([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exiting, setExiting] = useState(false);
  const [exitDir, setExitDir] = useState<"left" | "right" | "up">("right");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  // Drag Gesture States
  const [isDragging, setIsDragging] = useState(false);
  const [startX, setStartX] = useState(0);
  const [startY, setStartY] = useState(0);
  const [offsetX, setOffsetX] = useState(0);
  const [offsetY, setOffsetY] = useState(0);

  useEffect(() => {
    onboardingApi
      .getFlashcards()
      .then((data) => {
        setCards(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.detail ?? "Failed to load calibration books.");
        setLoading(false);
      });
  }, []);

  const current = cards[index];
  const progress = cards.length > 0 ? index / cards.length : 0;

  async function handleDecision(decision: FlashcardDecision) {
    if (!current || submitting || exiting) return;
    setSubmitting(true);

    const dir =
      decision === "not_interested" ? "left"
      : decision === "read_it"      ? "right"
      : "up";
    setExitDir(dir);
    setExiting(true);

    // Call background API
    onboardingApi
      .postResponse({ work_uuid: current.work_uuid, decision })
      .catch(() => {});

    // Clear drag offset
    setOffsetX(0);
    setOffsetY(0);

    setTimeout(() => {
      setExiting(false);
      setSubmitting(false);
      if (index + 1 >= cards.length) {
        setDone(true);
        localStorage.setItem(ONBOARDING_KEY, "true");
        setTimeout(() => router.push("/"), 1200);
      } else {
        setIndex((i) => i + 1);
      }
    }, 280);
  }

  // Mouse / Touch Drag Gestures
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (submitting || exiting) return;
    setIsDragging(true);
    setStartX(e.clientX);
    setStartY(e.clientY);
  };

  const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
    if (submitting || exiting) return;
    setIsDragging(true);
    setStartX(e.touches[0].clientX);
    setStartY(e.touches[0].clientY);
  };

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      setOffsetX(e.clientX - startX);
      setOffsetY(e.clientY - startY);
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (e.touches.length > 0) {
        setOffsetX(e.touches[0].clientX - startX);
        setOffsetY(e.touches[0].clientY - startY);
      }
    };

    const handleMouseUp = () => {
      handleDragEnd();
    };

    const handleTouchEnd = () => {
      handleDragEnd();
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    window.addEventListener("touchmove", handleTouchMove);
    window.addEventListener("touchend", handleTouchEnd);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
    };
  }, [isDragging, startX, startY]);

  const handleDragEnd = () => {
    setIsDragging(false);
    const threshold = 120;
    const absX = Math.abs(offsetX);
    const absY = Math.abs(offsetY);

    if (absX > threshold || absY > threshold) {
      if (absX > absY) {
        if (offsetX < 0) {
          handleDecision("not_interested");
        } else {
          handleDecision("read_it");
        }
      } else {
        if (offsetY < 0) {
          handleDecision("interested");
        } else {
          // snap back if dragged down
          setOffsetX(0);
          setOffsetY(0);
        }
      }
    } else {
      setOffsetX(0);
      setOffsetY(0);
    }
  };

  // Keyboard Navigation
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowLeft")  handleDecision("not_interested");
      if (e.key === "ArrowUp")    handleDecision("interested");
      if (e.key === "ArrowRight") handleDecision("read_it");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, submitting, exiting]);

  if (loading) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.loadingStack}>
          {[3, 2, 1].map((i) => (
            <div
              key={i}
              className={`${styles.ghostCard} skeleton`}
              style={{ transform: `scale(${0.88 + i * 0.04}) translateY(${-i * 8}px)` }}
            />
          ))}
        </div>
        <p className={styles.loadingText}>Summoning catalog...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.wrapper}>
        <div className="error-banner" style={{ maxWidth: 400 }}>{error}</div>
      </div>
    );
  }

  if (done || cards.length === 0) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.doneState}>
          <div className={styles.doneIcon}>✦</div>
          <h2>Taste profile seeded.</h2>
          <p>Heading to your recommendations…</p>
        </div>
      </div>
    );
  }

  const exitClass = exiting
    ? exitDir === "left"  ? styles.exitLeft
      : exitDir === "right" ? styles.exitRight
      :                       styles.exitUp
    : "";

  // Visual offsets while dragging
  const dragStyle = isDragging
    ? {
        transform: `translate(${offsetX}px, ${offsetY}px) rotate(${offsetX * 0.08}deg)`,
        transition: "none",
        cursor: "grabbing",
      }
    : {
        transform: "translate(0px, 0px) rotate(0deg)",
        transition: "transform 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
      };

  // Live card overlays
  const getOverlayConfig = () => {
    const absX = Math.abs(offsetX);
    const absY = Math.abs(offsetY);
    const maxOffset = Math.max(absX, absY);
    if (maxOffset < 20) return null;

    const opacity = Math.min(maxOffset / 120, 0.85);

    if (absX > absY) {
      if (offsetX < 0) {
        return { label: "Not for me", className: styles.overlayNo, opacity };
      } else {
        return { label: "Read it", className: styles.overlayYes, opacity };
      }
    } else {
      if (offsetY < 0) {
        return { label: "Want to read", className: styles.overlayTbr, opacity };
      }
    }
    return null;
  };

  const overlay = getOverlayConfig();

  return (
    <div className={styles.wrapper}>
      {/* Progress */}
      <div className={styles.progressRow}>
        <span className={styles.progressLabel}>{index + 1} of {cards.length}</span>
        <div className="progress-bar" style={{ flex: 1 }}>
          <div className="progress-bar-fill" style={{ width: `${progress * 100}%` }} />
        </div>
      </div>

      {/* Hint */}
      <p className={styles.hint}>
        Swipe Left (<kbd>←</kbd>) Not for me · Swipe Up (<kbd>↑</kbd>) Want to read · Swipe Right (<kbd>→</kbd>) Read it
      </p>

      {/* Stack */}
      <div className={styles.stackArea}>
        {/* Ghost card stack underneath */}
        {cards.slice(index + 1, index + 3).map((card, i) => (
          <div
            key={card.work_uuid}
            className={styles.ghostCard}
            style={{
              transform: `scale(${0.92 + i * 0.04}) translateY(${(2 - i) * -14}px)`,
              zIndex: i,
            }}
          />
        ))}

        {/* Swipe Card */}
        {current && (
          <div
            className={`${styles.card} ${exitClass}`}
            key={current.work_uuid}
            style={dragStyle}
            onMouseDown={handleMouseDown}
            onTouchStart={handleTouchStart}
          >
            <div className={styles.coverWrap}>
              <BookCover work={current} className={styles.cover} />
              {current.series && (
                <div className={`badge badge-gold ${styles.seriesBadge}`}>
                  {current.series.title} #{current.series.order_float}
                </div>
              )}

              {/* Swipe Label Overlay */}
              {overlay && (
                <div
                  className={`${styles.cardOverlay} ${overlay.className}`}
                  style={{ opacity: overlay.opacity }}
                >
                  <span className={styles.overlayText}>{overlay.label}</span>
                </div>
              )}
            </div>

            <div className={styles.meta} style={{ userSelect: "none" }}>
              <h2 className={styles.title}>{current.title}</h2>
              <p className={styles.author}>{current.author.canonical_name}</p>
              <div className={styles.details}>
                {current.publication_year && <span>{current.publication_year}</span>}
                {current.page_count && <span>·</span>}
                {current.page_count && <span>{current.page_count} pages</span>}
                {current.aggregate_rating && <span>·</span>}
                {current.aggregate_rating && (
                  <span>★ {current.aggregate_rating.toFixed(1)}</span>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Buttons */}
      <div className={styles.actions}>
        {DECISIONS.map((d) => (
          <button
            key={d.value}
            onClick={() => handleDecision(d.value)}
            className={`${styles.actionBtn} ${d.className}`}
            disabled={submitting}
            title={d.label}
            id={`decision-${d.value}`}
          >
            <span className={styles.actionIcon}>{d.icon}</span>
            <span className={styles.actionLabel}>{d.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
